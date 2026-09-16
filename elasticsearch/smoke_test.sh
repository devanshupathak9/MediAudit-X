#!/usr/bin/env bash
# The 9 demo queries. Needs ES running and data indexed. Run: ./smoke_test.sh
set -euo pipefail
ES="${ES_URL:-http://localhost:9200}"
say() { printf '\n\033[1;36m%s\033[0m\n' "$*"; }
esql () { # run an ES|QL query, print the rows as a table
  curl -fsS -XPOST "$ES/_query?format=txt" -H 'Content-Type: application/json' \
    -d "$(jq -n --arg q "$1" '{query:$q}')"
}

# =============================================================== 1
say "1. The whole patient trajectory, one query, sorted in time"
esql '
FROM patient-events
| WHERE patient_id == "P-1042"
| SORT event_time ASC
| KEEP event_time, recorded_at, event_type, code_system, code, code_text
| LIMIT 30'

# =============================================================== 2
say "2. EXACT TOKEN: E11.9 (Type 2) does not match E10.9 (Type 1)"
echo '   `code` is a keyword field, so this is a byte comparison, not a similarity score.'
esql '
FROM patient-events
| WHERE code == "E11.9"
| KEEP patient_id, code, code_text'

# =============================================================== 3
say "3. ...whereas free-text matching CANNOT separate them"
echo '   Same two patients, searched by description instead of code:'
curl -fsS "$ES/patient-events/_search" -H 'Content-Type: application/json' -d '{
  "size": 5,
  "query": { "match": { "code_text": "diabetes mellitus without complications" } },
  "_source": ["patient_id","code","code_text"]
}' | jq -r '.hits.hits[] | "   score \(._score|.*100|round/100)  \(._source.patient_id)  \(._source.code)  \(._source.code_text)"'
echo '   -> Both returned, nearly equal scores. A vector index behaves the same way.'
echo '   -> This is why the criteria engine filters on `code`, never on prose.'

# =============================================================== 4
say "4. CRITERION C2, the NAIVE way -- ignoring when the record was written"
esql '
FROM patient-events
| WHERE patient_id == "P-1042"
    AND event_type == "procedure" AND code_system == "CPT"
    AND code IN ("97110","97112","97116","97140","97530")
    AND event_time >= "2024-06-01" AND event_time <= "2026-06-01"
| EVAL month = DATE_TRUNC(1 month, event_time)
| STATS visits = COUNT(*) BY month
| SORT month ASC'
echo '   -> 6 distinct months. Policy requires 6. This claim APPROVES. $12,400 paid.'

# =============================================================== 5
say "5. CRITERION C2, AS OF THE DATE OF SERVICE -- one extra line"
echo '   The added line is:  AND recorded_at <= "2026-06-01"'
esql '
FROM patient-events
| WHERE patient_id == "P-1042"
    AND event_type == "procedure" AND code_system == "CPT"
    AND code IN ("97110","97112","97116","97140","97530")
    AND event_time >= "2024-06-01" AND event_time <= "2026-06-01"
    AND recorded_at <= "2026-06-01"
| EVAL month = DATE_TRUNC(1 month, event_time)
| STATS visits = COUNT(*) BY month
| SORT month ASC'
echo '   -> 4 distinct months. Same chart. Opposite verdict. This claim DENIES.'

# =============================================================== 6
say "6. Which entries moved the needle, and how late were they?"
esql '
FROM patient-events
| WHERE patient_id == "P-1042" AND code == "97110"
| EVAL days_late = DATE_DIFF("days", event_time, recorded_at)
| WHERE days_late > 1
| KEEP event_id, event_time, recorded_at, days_late, code_text
| SORT days_late DESC'
echo '   -> Two therapy encounters entered ~7 months after they allegedly occurred,'
echo '      and 19 days AFTER the surgery they were meant to justify.'

# =============================================================== 7
say "7. CRITERION C3 (temporal_order): imaging must follow final therapy"
esql '
FROM patient-events
| WHERE patient_id == "P-1042" AND recorded_at <= "2026-06-01"
| EVAL kind = CASE(
    code IN ("97110","97112","97116","97140","97530"), "therapy",
    code IN ("73721","73722","73723"), "imaging",
    "other")
| WHERE kind != "other"
| STATS last_seen = MAX(event_time), n = COUNT(*) BY kind'
echo '   -> imaging 2026-05-04 > therapy 2026-04-20. Order holds, C3 MET.'

# =============================================================== 8
say "8. CRITERION C5 (lab_threshold): most recent BMI under 40.0"
esql '
FROM patient-events
| WHERE patient_id == "P-1042" AND code == "39156-5"
    AND event_time >= "2025-06-01" AND recorded_at <= "2026-06-01"
| SORT event_time DESC
| KEEP event_time, value_num, value_unit
| LIMIT 1'

# =============================================================== 9
say "9. Policy retrieval with a LEXICAL HARD FILTER on the billed CPT"
echo '   Semantics may rank the results; it may never change which CPT applies.'
curl -fsS "$ES/payer-policies/_search" -H 'Content-Type: application/json' -d '{
  "size": 3,
  "query": {
    "bool": {
      "filter": [ { "term": { "metadata.applies_to_cpt": "29881" } },
                  { "term": { "metadata.payer": "MERIDIAN HEALTH PLAN" } } ],
      "should": [ { "match": { "chunk_text": "conservative therapy months prior to surgery" } } ]
    }
  },
  "_source": ["metadata.chunk_id","metadata.section_no","metadata.byte_start","metadata.byte_end"]
}' | jq -r '.hits.hits[] | "   score \(._score|.*100|round/100)  \(._source.metadata.chunk_id)  bytes \(._source.metadata.byte_start)-\(._source.metadata.byte_end)  §\(._source.metadata.section_no)"'

say "Smoke test complete."
echo "The pitch in one sentence: queries 4 and 5 differ by a single line and by \$12,400."
