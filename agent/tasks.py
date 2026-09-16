"""Agent worker: runs after all ingestion tasks for a job succeed.

Today: gathers the evidence and writes report.json.
Next:  rule checker (MET/NOT_MET per rule) -> verdict by code -> LLM explanation.

    celery -A shared.queue worker -Q agent -n agent@%h
"""
from datetime import datetime, timezone

from agent.retrieval import find_policy_rules, late_entries, timeline_as_of
from shared.jobs import set_stage, write_json
from shared.queue import app


@app.task(name="agent.audit")
def audit_claim(ingestion_results: list[dict], job_id: str) -> dict:
    set_stage(job_id, "agent", "running")
    try:
        by_kind = {r["kind"]: r for r in ingestion_results}
        claim = by_kind["claim"]["claim"]
        guardrails = []

        # Guardrail: the uploaded history must belong to the claim's patient.
        same_patient = by_kind["history"]["patient_id"] == claim["patient_id"]
        guardrails.append({"check": "history_matches_claim_patient", "passed": same_patient,
                           "detail": f"history={by_kind['history']['patient_id']} claim={claim['patient_id']}"})

        rules, policy_ids = find_policy_rules(claim["cpt"], claim["payer"], claim["date_of_service"])
        # Guardrail: exactly one policy must govern the claim.
        guardrails.append({"check": "exactly_one_policy", "passed": len(policy_ids) == 1,
                           "detail": f"matched {policy_ids}"})

        ok = all(g["passed"] for g in guardrails)
        timeline = timeline_as_of(claim["patient_id"], claim["date_of_service"]) if ok else []
        late = late_entries(claim["patient_id"], claim["date_of_service"]) if ok else []

        report = {
            "job_id": job_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "EVIDENCE_READY" if ok else "BLOCKED_BY_GUARDRAIL",
            "claim": claim,
            "as_of": claim["date_of_service"],
            "guardrails": guardrails,
            "policy": ({"policy_id": rules[0]["policy_id"], "version": rules[0]["version"],
                        "effective_from": rules[0]["effective_from"]} if rules else None),
            "criteria": [{"section_no": r["section_no"], "text": r["text"],
                          "citation": {"source_file": r["source_file"],
                                       "byte_start": r["byte_start"], "byte_end": r["byte_end"]}}
                         for r in rules],
            "timeline_as_of_dos": timeline,
            "late_entries": late,
            "verdict": None,
            "verdict_note": "Not decided yet: rule checker and LLM agent are the next components.",
        }
        write_json(job_id, "report.json", report)
    except Exception as e:
        set_stage(job_id, "agent", "failed", error=f"{type(e).__name__}: {e}")
        raise

    summary = {"status": report["status"], "criteria": len(report["criteria"]),
               "timeline_events": len(timeline), "late_entries": len(late)}
    set_stage(job_id, "agent", "done", result=summary)
    return summary
