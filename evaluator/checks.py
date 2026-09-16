"""Checks run on every job report. Each returns {check, passed, detail}."""
import json

from shared.config import POLICY_STORE, ROOT

GOLD_CLAIMS = ROOT / "evaluator" / "gold" / "claims.jsonl"


def check(name, passed, detail):
    return {"check": name, "passed": bool(passed), "detail": detail}


def citation_checks(report: dict) -> list[dict]:
    """Every cited byte range must reproduce the quoted text from the stored original."""
    results = []
    for c in report["criteria"]:
        cite = c["citation"]
        source = POLICY_STORE / cite["source_file"]
        if not source.exists():
            results.append(check(f"citation_§{c['section_no']}", False, f"source file missing: {source.name}"))
            continue
        quoted = source.read_bytes()[cite["byte_start"]:cite["byte_end"]].decode("utf-8")
        results.append(check(f"citation_§{c['section_no']}", quoted == c["text"],
                             f"{cite['source_file']} bytes {cite['byte_start']}-{cite['byte_end']}"))
    return results


def gold_checks(report: dict) -> list[dict]:
    """Compare against the answer key, for the gold row evaluated as of the date of service."""
    claim = report["claim"]
    gold = [json.loads(line) for line in GOLD_CLAIMS.read_text().splitlines() if line.strip()]
    row = next((g for g in gold if g["claim_id"] == claim["claim_id"] and g["as_of"] == claim["date_of_service"]), None)
    if row is None:
        return [check("gold_row_exists", False, f"no gold answer for {claim['claim_id']} as of {claim['date_of_service']}")]

    policy_id = (report.get("policy") or {}).get("policy_id")
    return [
        check("correct_policy", policy_id == row["expected_policy_id"],
              f"got {policy_id}, expected {row['expected_policy_id']}"),
        check("all_criteria_retrieved", len(report["criteria"]) == row["expected_criteria_count"],
              f"got {len(report['criteria'])}, expected {row['expected_criteria_count']}"),
        check("late_entries_detected", len(report["late_entries"]) == row["expected_late_entries"],
              f"got {len(report['late_entries'])}, expected {row['expected_late_entries']}"),
        check("verdict", report["verdict"] == row["expected_verdict"],
              f"got {report['verdict']}, expected {row['expected_verdict']}")
        if report["verdict"] is not None else
        {"check": "verdict", "passed": None, "detail": f"not produced yet (expected {row['expected_verdict']})"},
    ]
