"""Policy section search (keyword / vector / hybrid) through LangChain.

Used by the playground CLI (elasticsearch/search_policies.py), the agent, and
the evaluator -- one implementation, so what we evaluate is what we run.
"""
from langchain_elasticsearch import BM25Strategy, DenseVectorStrategy, ElasticsearchStore

from shared.config import POLICY_INDEX
from shared.embeddings import MODEL_NAME, get_embeddings
from shared.es import es, index_model

MODES = ("keyword", "vector", "hybrid")

_embeddings = None


def build_filters(cpt=None, date=None, chunk_type=None, payer=None) -> list[dict]:
    """Exact filters. Applied before ranking, in every mode."""
    filters = []
    if cpt:
        filters.append({"term": {"metadata.applies_to_cpt": cpt}})
    if payer:
        filters.append({"term": {"metadata.payer": payer}})
    if chunk_type:
        filters.append({"term": {"metadata.chunk_type": chunk_type}})
    if date:
        filters.append({"range": {"metadata.effective_from": {"lte": date}}})
        filters.append({"bool": {"should": [
            {"range": {"metadata.effective_to": {"gte": date}}},
            {"bool": {"must_not": {"exists": {"field": "metadata.effective_to"}}}},
        ]}})
    return filters


def search(question: str, mode: str = "hybrid", k: int = 3, **filter_args) -> list[dict]:
    """Return [{rank, score, text, metadata}]. score is None for hybrid (RRF gives ranks only)."""
    global _embeddings
    if index_model(POLICY_INDEX) != MODEL_NAME:
        raise RuntimeError(f"{POLICY_INDEX} was built with {index_model(POLICY_INDEX)!r} "
                           f"but EMBEDDING_PROVIDER selects {MODEL_NAME!r}. Re-index or switch back.")
    _embeddings = _embeddings or get_embeddings()

    strategy = {
        "keyword": BM25Strategy(),
        "vector": DenseVectorStrategy(),
        "hybrid": DenseVectorStrategy(hybrid=True, rrf={"rank_constant": 20, "rank_window_size": 50}),
    }[mode]
    store = ElasticsearchStore(index_name=POLICY_INDEX, client=es, embedding=_embeddings,
                               query_field="chunk_text", vector_query_field="chunk_vector", strategy=strategy)
    filters = build_filters(**filter_args)

    if mode == "hybrid":
        pairs = [(doc, None) for doc in store.similarity_search(question, k=k, filter=filters)]
    else:
        pairs = store.similarity_search_with_score(question, k=k, filter=filters)

    return [{"rank": i, "score": score, "text": doc.page_content, "metadata": doc.metadata}
            for i, (doc, score) in enumerate(pairs, 1)]
