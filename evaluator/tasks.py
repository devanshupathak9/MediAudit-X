"""Evaluator worker: checks each finished report, writes evaluation.json.

    celery -A shared.queue worker -Q evaluator -n evaluator@%h
"""
import json
from datetime import datetime, timezone

from evaluator.checks import citation_checks, gold_checks
from shared.jobs import job_dir, set_stage, write_json
from shared.queue import app


@app.task(name="evaluator.job")
def evaluate_job(agent_summary: dict, job_id: str) -> dict:
    set_stage(job_id, "evaluator", "running")
    report = json.loads((job_dir(job_id) / "report.json").read_text())

    checks = report["guardrails"] + citation_checks(report) + gold_checks(report)
    scored = [c for c in checks if c["passed"] is not None]
    passed = sum(c["passed"] for c in scored)

    evaluation = {
        "job_id": job_id,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "score": f"{passed}/{len(scored)}",
        "all_passed": passed == len(scored),
        "checks": checks,
    }
    write_json(job_id, "evaluation.json", evaluation)
    set_stage(job_id, "evaluator", "done", result={"score": evaluation["score"]})
    return {"score": evaluation["score"], "all_passed": evaluation["all_passed"]}
