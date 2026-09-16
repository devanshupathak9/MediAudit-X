"""Evidence retrieval for one claim. These become the agent's tools.

All patient queries are locked to one patient_id and evaluated AS OF the end of
the date of service: only facts that were in the record by then count
(policy MHP-0673 section 3).
"""
from datetime import date, timedelta

from shared.config import EVENTS_INDEX, POLICY_INDEX
from shared.es import es


def end_of_day(day: str) -> str:
    """'2026-06-01' -> '2026-06-02T00:00:00Z' (use with <)."""
    return f"{date.fromisoformat(day) + timedelta(days=1)}T00:00:00Z"


def esql_rows(query: str, params: list) -> list[dict]:
    resp = es.esql.query(query=query, params=params)
    cols = [c["name"] for c in resp["columns"]]
    return [dict(zip(cols, values)) for values in resp["values"]]


def find_policy_rules(cpt: str, payer: str, date_of_service: str) -> tuple[list[dict], list[str]]:
    """All criterion sections of the policy covering this CPT for this payer on this date."""
    resp = es.search(index=POLICY_INDEX, size=100, source_excludes=["chunk_vector"], query={"bool": {"filter": [
        {"term": {"metadata.applies_to_cpt": cpt}},
        {"term": {"metadata.payer": payer}},
        {"term": {"metadata.chunk_type": "criterion"}},
        {"range": {"metadata.effective_from": {"lte": date_of_service}}},
        {"bool": {"should": [{"range": {"metadata.effective_to": {"gte": date_of_service}}},
                             {"bool": {"must_not": {"exists": {"field": "metadata.effective_to"}}}}]}},
    ]}})
    rules = sorted(({"text": h["_source"]["chunk_text"], **h["_source"]["metadata"]}
                    for h in resp["hits"]["hits"]), key=lambda r: [int(x) for x in r["section_no"].split(".")])
    return rules, sorted({r["policy_id"] for r in rules})


def timeline_as_of(patient_id: str, date_of_service: str) -> list[dict]:
    return esql_rows("""
        FROM patient-events
        | WHERE patient_id == ? AND event_time < ? AND recorded_at < ?
        | SORT event_time ASC
        | KEEP event_id, event_time, recorded_at, event_type, code_system, code, code_text, value_num, value_unit, source_path
        | LIMIT 1000
    """, [patient_id, end_of_day(date_of_service), end_of_day(date_of_service)])


def late_entries(patient_id: str, date_of_service: str) -> list[dict]:
    """Events dated on/before the date of service but entered into the record after it."""
    return esql_rows("""
        FROM patient-events
        | WHERE patient_id == ? AND event_time < ? AND recorded_at >= ?
        | EVAL days_late = DATE_DIFF("days", event_time, recorded_at)
        | SORT event_time ASC
        | KEEP event_id, event_time, recorded_at, days_late, code_system, code, code_text, source_path
    """, [patient_id, end_of_day(date_of_service), end_of_day(date_of_service)])
