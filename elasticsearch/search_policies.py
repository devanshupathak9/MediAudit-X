"""Search policy sections three ways and compare (via LangChain ElasticsearchStore).

  keyword : matches words (English analyzer: "months" == "month")
  vector  : matches meaning ("weight" finds "body mass index")
  hybrid  : both, merged with RRF (Reciprocal Rank Fusion)

Filters (exact, applied BEFORE ranking): --cpt, --date, --type

    python search_policies.py "patient weight too high"
    python search_policies.py "patient weight too high" --mode all
    python search_policies.py "how long must therapy last" --cpt 29881 --date 2026-06-01 --type criterion
"""
import argparse

from langchain_elasticsearch import BM25Strategy, DenseVectorStrategy, ElasticsearchStore

from embedder import MODEL_NAME, get_embeddings
from es_client import es

INDEX = "payer-policies"

parser = argparse.ArgumentParser()
parser.add_argument("question")
parser.add_argument("--mode", choices=["keyword", "vector", "hybrid", "all"], default="hybrid")
parser.add_argument("--cpt", help="only policies that cover this procedure code, e.g. 29881")
parser.add_argument("--date", help="only policies in effect on this date, e.g. 2026-06-01")
parser.add_argument("--type", help="only this chunk type, e.g. criterion")
parser.add_argument("--top", type=int, default=3)
args = parser.parse_args()

# The query must be embedded with the same model the index was built with.
saved_model = es.indices.get_mapping(index=INDEX)[INDEX]["mappings"].get("_meta", {}).get("embedding_model")
if saved_model != MODEL_NAME:
    raise SystemExit(f"Index was built with {saved_model!r} but .env selects {MODEL_NAME!r}. "
                     f"Re-index, or change EMBEDDING_PROVIDER back.")

# ---- exact filters (metadata lives under "metadata.") ----
filters = []
if args.cpt:
    filters.append({"term": {"metadata.applies_to_cpt": args.cpt}})
if args.type:
    filters.append({"term": {"metadata.chunk_type": args.type}})
if args.date:
    filters.append({"range": {"metadata.effective_from": {"lte": args.date}}})
    filters.append({"bool": {"should": [
        {"range": {"metadata.effective_to": {"gte": args.date}}},
        {"bool": {"must_not": {"exists": {"field": "metadata.effective_to"}}}},
    ]}})

STRATEGIES = {
    "keyword": BM25Strategy(),
    "vector": DenseVectorStrategy(),
    "hybrid": DenseVectorStrategy(hybrid=True, rrf={"rank_constant": 20, "rank_window_size": 50}),
}

embeddings = get_embeddings()


def run(mode):
    store = ElasticsearchStore(index_name=INDEX, client=es, embedding=embeddings,
                               query_field="chunk_text", vector_query_field="chunk_vector",
                               strategy=STRATEGIES[mode])
    if mode == "hybrid":
        # LangChain returns no scores for RRF hybrid, so show the rank instead
        docs = store.similarity_search(args.question, k=args.top, filter=filters)
        results = [(doc, f"rank {i}") for i, doc in enumerate(docs, 1)]
    else:
        results = [(doc, f"score {score:.3f}")
                   for doc, score in store.similarity_search_with_score(args.question, k=args.top, filter=filters)]

    print(f"\n[{mode.upper()}]  {len(results)} result(s)")
    for doc, label in results:
        m = doc.metadata
        preview = " ".join(doc.page_content.split())[:90]
        print(f"  {label:<11}  §{m['section_no']:<4} {m['chunk_type']:<14} {preview}...")


print(f'Question: "{args.question}"   model: {MODEL_NAME}   '
      f'filters: cpt={args.cpt} date={args.date} type={args.type}')
for mode in (["keyword", "vector", "hybrid"] if args.mode == "all" else [args.mode]):
    run(mode)
