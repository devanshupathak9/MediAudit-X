# Elasticsearch layer

Everything here is about one question: **can the data answer the policy's
questions exactly, without a language model guessing?**

## Run it

```bash
make demo          # start ES, build data, create indices, load, run proof queries
```

Or step by step:

```bash
make up            # docker compose up + wait for green
make data          # regenerate JSONL from the builder scripts
make indices       # PUT mappings
make load          # bulk load
make smoke         # the nine proof queries
make kibana        # optional UI at localhost:5601
```

Teardown: `make down` keeps the data, `make reset` wipes it.

## Why docker-compose and not a Dockerfile

Elastic publishes an official image and we add nothing to it — no plugins, no
custom entrypoint. Everything we need is configuration, which belongs in
`environment:`. A Dockerfile here would be an empty `FROM` line.

Security is **off** (`xpack.security.enabled=false`) so `curl localhost:9200`
works with no token. That is correct for a laptop and wrong for anything else.

## Indices

| index | one doc = | the point |
| --- | --- | --- |
| `patient-events` | one clinical event | every FHIR resource flattened into the same row shape, so one ES\|QL template answers every temporal question |
| `payer-policies` | one policy section | chunked with byte offsets preserved, so a retrieved chunk traces back to exact source bytes |
| `drug-knowledge` | one drug | RxNorm ingredient + brand as `keyword`, so Toradol→ketorolac is a lookup, not a guess |
| `audit-log` | one decision | append-only, hash-chained; `criteria_results`/`evidence` are `enabled:false` (stored verbatim, never re-interpreted by a query) |

Two mapping decisions carry most of the weight:

- **`code` is `keyword`, never `text`.** `E10.9` and `E11.9` are one character
  apart and financially opposite. Smoke test query 3 shows BM25 giving them
  *identical* scores — an embedding model does no better. Exactness has to come
  from the field type, not from ranking.
- **`dynamic: "strict"`.** A typo'd field name fails the load instead of
  silently creating a field nothing queries. In an audit system, silent data
  loss is the worst possible failure.

## Bi-temporal, concretely

Every event carries two dates:

- `event_time` — when it clinically happened
- `recorded_at` — when it entered the record

Smoke test queries **4 and 5** are the same query, one line apart:

```
AND recorded_at <= "2026-06-01"     -- as of the date of service
```

Query 4 finds 6 distinct months of therapy → **approve, $12,400 paid.**
Query 5 finds 4 → **deny.**

The difference is two physical-therapy encounters entered on 2026-06-20 but
dated to Nov/Dec 2025 — 19 days *after* the surgery they were meant to justify.
Query 6 surfaces them with `DATE_DIFF`, 215 and 187 days late.

This is not a trick: policy `MHP-0673` §3 requires criteria be substantiated by
documentation present in the record *as of the date of service*. The as-of query
is literal compliance with the written policy.

## Poking at it yourself

```bash
curl -s localhost:9200/_cat/indices?v

# any ES|QL query, rendered as a table
curl -s -XPOST 'localhost:9200/_query?format=txt' -H 'Content-Type: application/json' -d '{
  "query": "FROM patient-events | WHERE patient_id == \"P-1042\" | STATS n = COUNT(*) BY event_type"
}'
```

In Kibana, **Discover → ES|QL** gives the same thing with autocomplete — the
fastest way to develop a new criterion template.
