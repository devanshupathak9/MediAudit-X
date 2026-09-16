#!/usr/bin/env bash
# Bulk-load the demo dataset. Idempotent: documents are keyed by their own ids.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
require_es

bulk_load () { # <index> <jsonl file> <id field>
  local idx="$1" file="$2" idf="$3"
  [ -f "$file" ] || die "missing $file -- run the builder script first"
  local payload; payload=$(mktemp)
  jq -c --arg idx "$idx" --arg idf "$idf" \
     '{index:{_index:$idx,_id:.[$idf]}}, .' "$file" > "$payload"
  local resp; resp=$(curl -fsS -XPOST "$ES/_bulk" \
       -H 'Content-Type: application/x-ndjson' --data-binary "@$payload")
  rm -f "$payload"
  if echo "$resp" | jq -e '.errors == true' >/dev/null; then
    echo "$resp" | jq '[.items[].index | select(.error)] | .[0:3]' >&2
    die "bulk load into $idx reported errors"
  fi
  ok "$idx <- $(wc -l < "$file" | tr -d ' ') docs"
}

say "Loading demo data"
bulk_load patient-events "$ROOT/data/patients/demo-patients.events.jsonl" event_id
bulk_load payer-policies "$ROOT/data/policies/policy-chunks.jsonl"        chunk_id

curl -fsS -XPOST "$ES/patient-events,payer-policies/_refresh" >/dev/null
say "Counts"
for idx in patient-events payer-policies; do
  n=$(curl -fsS "$ES/$idx/_count" | jq .count)
  printf '  %-16s %s docs\n' "$idx" "$n"
done
