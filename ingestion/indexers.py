"""Write preprocessed data into Elasticsearch."""
from datetime import datetime, timezone

from elasticsearch import helpers
from langchain_elasticsearch import ElasticsearchStore

from shared.config import CLAIMS_INDEX, EVENTS_INDEX, POLICY_INDEX
from shared.embeddings import MODEL_NAME, get_embeddings
from shared.es import es, index_model


def index_policy_chunks(chunks: list[dict]) -> dict:
    meta = [c["metadata"] for c in chunks]
    policy_id, sha = meta[0]["policy_id"], meta[0]["source_sha256"]

    # Guardrail: never mix embedding models inside one index.
    if index_model(POLICY_INDEX) != MODEL_NAME:
        raise RuntimeError(f"{POLICY_INDEX} was built for {index_model(POLICY_INDEX)!r}, "
                           f"but EMBEDDING_PROVIDER selects {MODEL_NAME!r}. Recreate the index.")

    # Same policy, same bytes, already indexed -> skip (saves embedding credit).
    already = es.count(index=POLICY_INDEX, query={"bool": {"filter": [
        {"term": {"metadata.policy_id": policy_id}},
        {"term": {"metadata.source_sha256": sha}}]}})["count"]
    if already == len(chunks):
        return {"policy_id": policy_id, "chunks": len(chunks), "skipped": "unchanged, already indexed"}

    # Replace older versions of this policy's chunks.
    es.delete_by_query(index=POLICY_INDEX, query={"term": {"metadata.policy_id": policy_id}},
                       refresh=True, conflicts="proceed")

    embeddings = get_embeddings()
    store = ElasticsearchStore(index_name=POLICY_INDEX, client=es, embedding=embeddings,
                               query_field="chunk_text", vector_query_field="chunk_vector")
    # Store raw English, embed title + section + text.
    vectors = embeddings.embed_documents(
        [f"{m['title']}. Section {m['section_no']} {m['section_title']}. {c['text']}" for c, m in zip(chunks, meta)])
    store.add_embeddings(text_embeddings=list(zip([c["text"] for c in chunks], vectors)),
                         metadatas=meta, ids=[m["chunk_id"] for m in meta],
                         create_index_if_not_exists=False)
    return {"policy_id": policy_id, "version": meta[0]["version"], "chunks": len(chunks), "model": MODEL_NAME}


def index_events(patient_id: str, rows: list[dict]) -> dict:
    # A new bundle is the patient's full current record: replace, don't append.
    es.delete_by_query(index=EVENTS_INDEX, query={"term": {"patient_id": patient_id}},
                       refresh=True, conflicts="proceed")
    ok, errors = helpers.bulk(es, ({"_index": EVENTS_INDEX, "_id": r["event_id"], "_source": r} for r in rows),
                              raise_on_error=False, refresh="wait_for")
    if errors:
        raise RuntimeError(f"{len(errors)} event rows failed to index, first: {errors[0]}")
    return {"patient_id": patient_id, "events": ok}


def index_claim(claim: dict, job_id: str) -> dict:
    doc = {**claim, "job_id": job_id, "status": "received",
           "received_at": datetime.now(timezone.utc).isoformat()}
    es.index(index=CLAIMS_INDEX, id=claim["claim_id"], document=doc, refresh="wait_for")
    return claim
