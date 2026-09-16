"""Submit a job: policy + patient history (FHIR) + claim.

This is what the backend will call when files are uploaded.

  1. save the raw files under storage/jobs/<job_id>/inputs/
  2. ingestion: policy, history and claim tasks run IN PARALLEL
  3. when all three succeed -> agent builds the report
  4. then -> evaluator checks the report

    python -m pipeline.submit --policy data/policies/MHP-0673-knee-arthroscopy.txt \\
                              --history data/fhir/P-1042.bundle.json \\
                              --claim data/claims/CLM-0001.json --wait
"""
import argparse
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import chain, group

from agent.tasks import audit_claim
from evaluator.tasks import evaluate_job
from ingestion.tasks import ingest_claim, ingest_history, ingest_policy
from shared.jobs import job_dir, read_status, set_stage


def submit(policy: Path, history: Path, claim: Path) -> str:
    job_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    inputs = job_dir(job_id) / "inputs"
    inputs.mkdir(parents=True)
    stored = {}
    for kind, src in (("policy", policy), ("history", history), ("claim", claim)):
        dst = inputs / src.name
        shutil.copyfile(src, dst)
        stored[kind] = str(dst)
    set_stage(job_id, "submitted", "done", inputs={k: Path(v).name for k, v in stored.items()})

    workflow = chain(
        group(
            ingest_policy.si(job_id, stored["policy"]),
            ingest_history.si(job_id, stored["history"]),
            ingest_claim.si(job_id, stored["claim"]),
        ),
        audit_claim.s(job_id),      # receives the list of 3 ingestion results
        evaluate_job.s(job_id),     # receives the agent summary
    )
    workflow.apply_async()
    return job_id


def wait(job_id: str, timeout: int = 300):
    seen = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        for name, stage in read_status(job_id)["stages"].items():
            if seen.get(name) != stage["status"]:
                seen[name] = stage["status"]
                detail = stage.get("error") or stage.get("result") or ""
                print(f"  {stage['at'][11:19]}  {name:<15} {stage['status']:<8} {json.dumps(detail, default=str)[:110]}")
        if seen.get("evaluator") == "done" or "failed" in seen.values():
            return
        time.sleep(0.5)
    print(f"  timed out after {timeout}s -- are the workers running? (make workers)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--history", type=Path, required=True)
    p.add_argument("--claim", type=Path, required=True)
    p.add_argument("--wait", action="store_true", help="follow progress until the evaluator finishes")
    args = p.parse_args()

    for f in (args.policy, args.history, args.claim):
        if not f.exists():
            raise SystemExit(f"file not found: {f}")

    job_id = submit(args.policy, args.history, args.claim)
    print(f"job {job_id} submitted -> storage/jobs/{job_id}/")
    if args.wait:
        wait(job_id)
        print(f"\n  report:     storage/jobs/{job_id}/report.json")
        print(f"  evaluation: storage/jobs/{job_id}/evaluation.json")
