# MediAudit-X — Proposed Solution

Submission `6a81f25e0d41eacf3be81b30` · Industry Solutions & Vertical Experiences / Healthcare & Insurance Intelligence

---

## 1. The one rule the whole design follows

> **The LLM is not allowed to decide, count, or cite. Elasticsearch does all three. The LLM only phrases the result, and a validator deletes anything it made up.**

Every architectural choice below exists to enforce that rule. This is the thing to say in the pitch, and the thing to demo.

---

## 2. Adjudication pipeline

```
Claim (patient_id, CPT, ICD-10[], date_of_service, payer)
   │
   ├─1─ POLICY RETRIEVAL      hybrid retriever (BM25 term on CPT  ⊕  kNN on policy text) → RRF
   │                          → the governing policy + its pre-compiled criteria JSON
   │
   ├─2─ CRITERIA COMPILATION   criteria JSON → N ES|QL queries      (deterministic, no LLM)
   │
   ├─3─ EVIDENCE EXECUTION     each ES|QL runs over patient-events, bi-temporal, AS OF date_of_service
   │                          → rows = evidence, each with source doc_id + byte offsets
   │
   ├─4─ SAFETY OVERLAY         hybrid search on drug-knowledge: interactions, contraindications,
   │                          FDA boxed warnings for the requested drug/procedure vs active meds
   │
   ├─5─ VERDICT                pure boolean arithmetic over criterion states:
   │                          all MET → APPROVE | any NOT_MET → DENY | any UNKNOWN → PEND
   │
   ├─6─ NARRATIVE              LLM writes the rationale, MUST cite [[ev:3]] style ids.
   │                          Validator: every id ∈ evidence set, every number/date ∈ evidence.
   │                          Fail → regenerate (max 2) → fall back to deterministic template.
   │                          ⇒ worst case hallucination rate is literally 0.
   │
   └─7─ AUDIT RECORD           {claim, policy_version, criteria, ES|QL text, evidence rows,
                               verdict, narrative, prev_hash, sha256} → append-only index
```

Step 5 is why this is defensible. Step 6's fallback is why the hallucination number is a *guarantee*, not a benchmark.

---

## 3. Elasticsearch design (the scoring surface)

### 3.1 `patient-events` — one flat doc per clinical event

The trick is denormalizing FHIR into **one uniform event row** so a single ES|QL shape answers every temporal question.

| field | type | why |
| --- | --- | --- |
| `patient_id` | keyword | filter |
| `event_type` | keyword | `diagnosis` \| `medication` \| `procedure` \| `lab` \| `encounter` \| `note` |
| `code_system` | keyword | `ICD10` \| `CPT` \| `RxNorm` \| `LOINC` \| `SNOMED` |
| `code` | keyword | **exact token — never analyzed.** This is the `E10.9` vs `E11.9` fix |
| `code_text` | text + `.keyword` | BM25 over the human label |
| `note_text` | semantic_text | narrative, chunked |
| `note_vector` | dense_vector, `index_options: {type: bbq_disk}` | cheap ANN at scale |
| `value_num` / `unit` | double / keyword | lab thresholds (`HbA1c >= 9.0`) |
| `event_time` | date | **when it clinically happened** |
| `recorded_at` | date | **when it entered the record** ← bi-temporal axis |
| `source_doc_id`, `byte_start`, `byte_end`, `page` | keyword / int | the citation anchor |

### 3.2 `payer-policies` — chunked policy text + machine-checkable criteria

`policy_id`, `payer`, `version`, `effective_from/to`, `applies_to_cpt[]` (keyword), `applies_to_icd[]`, `chunk_text` (semantic_text + BM25), `criteria` (nested JSON, see §4), plus the same byte-offset anchors.

### 3.3 `drug-knowledge` — RxNorm + openFDA

`rxcui`, `ingredient[]`, `brand_names[]` (keyword, so `Toradol`→`Ketorolac` is a *lookup*, not a guess), `interacts_with_rxcui[]`, `contraindicated_icd[]`, `boxed_warning` (text), `label_vector`.

### 3.4 `audit-log` — append-only, hash-chained, `index.blocks.write` on rollover.

### 3.5 Retrieval shape (one query, both worlds)

```json
{ "retriever": { "rrf": { "retrievers": [
    { "standard": { "query": { "bool": {
        "filter": [ {"term": {"applies_to_cpt": "29881"}},
                    {"term": {"payer": "AETNA"}} ],
        "should":  [ {"match": {"chunk_text": "conservative therapy knee"}} ] } } } },
    { "knn": { "field": "chunk_vector", "query_vector_builder": {...}, "k": 50, "num_candidates": 200 } }
  ], "rank_window_size": 100, "rank_constant": 20 } } }
```
The `filter` clause is non-negotiable and lexical — semantics can rank, but it can never smuggle in the wrong CPT or the wrong patient.

---

## 4. The criteria DSL — the core IP

Policy prose is compiled **once at ingest** (LLM-assisted, human-reviewable, stored with source offsets) into declarative criteria. At query time it is pure execution.

```json
{
  "criterion_id": "AETNA-0673-C2",
  "label": "≥6 months of conservative therapy prior to arthroscopy",
  "type": "temporal_duration",
  "match": { "event_type": "procedure", "code_system": "CPT",
             "code_in": ["97110","97112","97116","97140","97530"] },
  "window": { "anchor": "date_of_service", "lookback_days": 730 },
  "assert": { "distinct_months_gte": 6, "max_gap_days": 45 },
  "source": { "policy_id": "AETNA-0673", "page": 12,
              "byte_start": 48211, "byte_end": 48644 }
}
```

Five criterion types cover ~90% of real prior-auth policies:

| type | assert keys | example |
| --- | --- | --- |
| `existence` | `min_count` | documented diagnosis of OA knee |
| `temporal_duration` | `distinct_months_gte`, `max_gap_days` | 6 months of PT |
| `temporal_order` | `before`, `min_days_between` | imaging *after* failed therapy |
| `lab_threshold` | `op`, `value`, `within_days` | HbA1c ≥ 9.0 in last 90d |
| `absence` | `not_present_within_days` | no contraindicating anticoagulant |

Each type has **one** ES|QL template. `temporal_duration` compiles to:

```esql
FROM patient-events
| WHERE patient_id == ?pid
    AND event_type == "procedure" AND code_system == "CPT"
    AND code IN ("97110","97112","97116","97140","97530")
    AND event_time >= ?window_start AND event_time <= ?dos
    AND recorded_at <= ?dos                       -- bi-temporal: as-of adjudication
| EVAL month = DATE_TRUNC(1 month, event_time)
| STATS visits = COUNT(*), first_seen = MIN(event_time), last_seen = MAX(event_time),
        srcs = VALUES(source_doc_id) BY month
| SORT month ASC
```
→ Python asserts `distinct months ≥ 6` and max inter-visit gap ≤ 45d. **Counting happens in ES and Python. Never in the model.**

Drop `recorded_at <= ?dos` and re-run to show back-dated chart entries — that's the fraud-detection wow moment, and it's two lines of ES|QL.

---

## 5. Anti-hallucination layer

1. **Structured generation** — LLM gets *only* the evidence rows as JSON, returns `{criterion_id, verdict_supported, rationale}` with `[[ev:N]]` markers.
2. **Citation validator** — regex-extract every `[[ev:N]]`; any N outside the supplied set → reject. Every date/number in the output must appear verbatim in an evidence row → else reject.
3. **Retry ×2, then template fallback** — the deterministic renderer always produces a correct, boring sentence. Ship path never depends on the model.
4. **Report the metric honestly:** `unsupported_statement_rate = rejected_after_retries / total`, with the baseline (raw LLM over raw chart) measured side by side on the same gold set.

---

## 6. Data (no PHI, all synthetic/public)

| need | source |
| --- | --- |
| Longitudinal patients | **Synthea** (`synthea -p 500 Massachusetts`) → FHIR bundles → flatten to `patient-events` |
| Payer policies | Public medical-policy PDFs (Aetna CPB / CMS NCD-LCD), 10–20 documents |
| Drug labels & warnings | **openFDA** drug label API + **RxNorm** RxNav API |
| Gold set | 40–60 hand-labeled claims: ~1/3 approve, ~1/3 deny, ~1/3 pend, incl. adversarial pairs |

Adversarial pairs are the demo: `E10.9` vs `E11.9`, `Toradol` vs `Ketorolac`, 5-months-of-PT (deny) vs 6-months-with-a-gap (pend), and one back-dated chart.

---

## 7. Component build order (do these *before* the 18th)

Each is independently demoable — if you run out of time, you still have working parts.

| # | Component | Deliverable | Blocks |
| --- | --- | --- | --- |
| C0 | `docker-compose` ES + Kibana, `.env`, health check | cluster up | all |
| C1 | **Ingest: Synthea → patient-events** | `ingest/fhir_flatten.py`, mapping JSON, bulk load | C4 |
| C2 | **Ingest: policy PDF → chunks + offsets** | `ingest/policy_chunker.py` preserving byte offsets | C3 |
| C3 | **Criteria compiler (offline)** | policy chunk → criteria JSON, reviewed by hand, checked into `data/criteria/` | C5 |
| C4 | **ES\|QL templates + executor** | `engine/esql.py` — 5 templates, parameterized, returns evidence rows | C5 |
| C5 | **Rule engine + verdict** | `engine/adjudicate.py` — criteria → evidence → MET/NOT_MET/UNKNOWN → verdict | C7 |
| C6 | **Hybrid retriever** | `search/hybrid.py` — RRF policy search + drug lookup | C5 |
| C7 | **Narrative + validator** | `llm/narrate.py`, `llm/validate.py`, template fallback | C8 |
| C8 | **Audit log** | `audit/chain.py` — hash-chained append, verify command | — |
| C9 | **API** | FastAPI `POST /audit/claim`, `GET /audit/{id}`, `GET /evidence/{id}` | C10 |
| C10 | **UI** | Claim in → verdict, per-criterion timeline, click a citation → source text highlighted | demo |
| C11 | **Eval harness** | `eval/run.py` → recall@k, citation validity, latency p50/p95, vs LLM baseline | pitch |

**Day 1 (18th):** C0–C5 working end-to-end on *one* policy + *one* patient, CLI output only.
**Day 2 (19th):** C6–C8 → C9/C10 UI → C11 numbers → rehearse the demo twice.

Build C11 early enough that the slide has real numbers on it. Judges score measured results far above features.

---

## 8. Stack

Python 3.11 · Elasticsearch 9.x (`elasticsearch-py`) · FastAPI · Pydantic v2 (criteria schema = Pydantic models, validated at load) · Claude (`claude-sonnet-5` for narration, `claude-opus-5` for offline criteria compilation) · React + Vite for UI · Docker Compose.

---

## 9. Demo script (4 minutes, rehearse it)

1. **The failure** (30s) — ask a plain LLM the knee-surgery question against the chart. It confidently cites a policy section that doesn't exist. Show the real policy.
2. **MediAudit-X** (60s) — same claim. 6 seconds. `PEND — criterion C2 not met: 4 distinct months of conservative therapy documented, policy requires 6.` Click the citation → the exact sentence in the Aetna PDF and the 4 PT visits on a timeline.
3. **Exact-token** (45s) — swap `E11.9`→`E10.9`. Verdict flips. Show vector-only retrieval returning the *same* top hit for both; hybrid returning the right one.
4. **Safety overlay** (45s) — prescribe Toradol to a patient on warfarin. Hit fires via RxNorm ingredient match plus the FDA boxed warning, with the label quoted.
5. **Bi-temporal** (30s) — re-run as-of the DOS; a PT note recorded 3 weeks *after* the surgery drops out, verdict changes. Nobody else will demo this.
6. **Numbers + audit chain** (30s) — eval table vs baseline; `verify-chain` prints OK; tamper one record; it prints the broken link.

---

## 10. What to say about scoring

- **Technicality:** ES|QL bi-temporal criteria compiler, RRF hybrid with lexical hard-filters, DiskBBQ quantized vectors, hash-chained audit index, validator-gated generation.
- **Implementation:** all 11 components runnable, seeded with one `make demo`, with an eval harness printing the claimed metrics on the judges' own machine.
- **The differentiator sentence:** *"Every other team's system can be wrong confidently. Ours can only be right, or say it doesn't know — and it shows you the byte offset either way."*
