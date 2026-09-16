"""Job folders on disk: raw inputs, per-stage status, final report.

storage/jobs/<job_id>/
    inputs/            the files exactly as they arrived
    stages/<stage>.json  one file per stage -> parallel tasks never overwrite each other
    report.json        written by the agent
    evaluation.json    written by the evaluator

A backend can later expose these as GET /jobs/<id>.
"""
import json
from datetime import datetime, timezone

from shared.config import JOBS_DIR


def job_dir(job_id: str):
    return JOBS_DIR / job_id


def write_json(job_id: str, name: str, data: dict):
    path = job_dir(job_id) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")
    return path


def set_stage(job_id: str, stage: str, status: str, **detail):
    write_json(job_id, f"stages/{stage}.json", {
        "stage": stage, "status": status,
        "at": datetime.now(timezone.utc).isoformat(), **detail})


def read_status(job_id: str) -> dict:
    stages_dir = job_dir(job_id) / "stages"
    stages = {p.stem: json.loads(p.read_text()) for p in sorted(stages_dir.glob("*.json"))} if stages_dir.exists() else {}
    return {"job_id": job_id, "stages": stages}
