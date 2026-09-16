"""Ingestion worker tasks. Run in parallel for one job; the agent starts when all finish.

    celery -A shared.queue worker -Q ingestion -n ingestion@%h
"""
import json
import shutil
from pathlib import Path

from ingestion.claim_parser import parse_claim
from ingestion.fhir_flattener import flatten_bundle
from ingestion.indexers import index_claim, index_events, index_policy_chunks
from ingestion.policy_parser import build_chunks
from shared.config import POLICY_STORE
from shared.jobs import set_stage
from shared.queue import app


def run_stage(job_id, stage, work):
    """Record running/done/failed around a stage so failures are visible, not silent."""
    set_stage(job_id, stage, "running")
    try:
        result = work()
    except Exception as e:
        set_stage(job_id, stage, "failed", error=f"{type(e).__name__}: {e}")
        raise
    set_stage(job_id, stage, "done", result=result)
    return result


@app.task(name="ingestion.policy")
def ingest_policy(job_id: str, path: str) -> dict:
    def work():
        src = Path(path)
        chunks = build_chunks(src)
        # Keep the original file where citations can always find it.
        POLICY_STORE.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, POLICY_STORE / src.name)
        return {"kind": "policy", **index_policy_chunks(chunks)}
    return run_stage(job_id, "ingest_policy", work)


@app.task(name="ingestion.history")
def ingest_history(job_id: str, path: str) -> dict:
    def work():
        src = Path(path)
        patient_id, rows, warnings = flatten_bundle(json.loads(src.read_text()), src.name)
        return {"kind": "history", **index_events(patient_id, rows), "warnings": warnings}
    return run_stage(job_id, "ingest_history", work)


@app.task(name="ingestion.claim")
def ingest_claim(job_id: str, path: str) -> dict:
    def work():
        claim = parse_claim(json.loads(Path(path).read_text()))
        return {"kind": "claim", "claim": index_claim(claim, job_id)}
    return run_stage(job_id, "ingest_claim", work)
