"""Search policy sections three ways and compare.

  keyword : matches words (English analyzer: "months" == "month")
  vector  : matches meaning ("weight" finds "body mass index")
  hybrid  : both, merged with RRF (Reciprocal Rank Fusion)

Filters (exact, applied BEFORE ranking): --cpt, --date, --type

    python search_policies.py "patient weight too high"
    python search_policies.py "patient weight too high" --mode all
    python search_policies.py "how long must therapy last" --cpt 29881 --date 2026-06-01 --type criterion
"""
import argparse

from embedder import embed
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

# ---- exact filters ----
filters = []
if args.cpt:
    filters.append({"term": {"applies_to_cpt": args.cpt}})
if args.type:
    filters.append({"term": {"chunk_type": args.type}})
if args.date:
    filters.append({"range": {"effective_from": {"lte": args.date}}})
    filters.append({"bool": {"should": [
        {"range": {"effective_to": {"gte": args.date}}},
        {"bool": {"must_not": {"exists": {"field": "effective_to"}}}},
    ]}})

# ---- the two ways of ranking ----
keyword = {"standard": {"query": {"bool": {
    "filter": filters,
    "must": [{"match": {"chunk_text": args.question}}],
}}}}

vector = {"knn": {
    "field": "chunk_vector",
    "query_vector": embed([args.question])[0],
    "k": 10,
    "num_candidates": 50,
    "filter": filters,  # inside kNN, so filtering happens before picking the top k
}}

hybrid = {"rrf": {"retrievers": [keyword, vector], "rank_window_size": 50, "rank_constant": 20}}

RETRIEVERS = {"keyword": keyword, "vector": vector, "hybrid": hybrid}


def run(mode):
    response = es.search(index=INDEX, retriever=RETRIEVERS[mode], size=args.top,
                         source_excludes=["chunk_vector"])
    hits = response["hits"]["hits"]
    print(f"\n[{mode.upper()}]  {len(hits)} result(s)")
    for hit in hits:
        c = hit["_source"]
        preview = " ".join(c["chunk_text"].split())[:90]
        print(f"  score {hit['_score']:.3f}  §{c['section_no']:<4} {c['chunk_type']:<14} {preview}...")


print(f'Question: "{args.question}"   filters: cpt={args.cpt} date={args.date} type={args.type}')
for mode in (["keyword", "vector", "hybrid"] if args.mode == "all" else [args.mode]):
    run(mode)
