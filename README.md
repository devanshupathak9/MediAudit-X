# MediAudit-X

> Zero-hallucination clinical claims auditing — exact-token search + bi-temporal reasoning over Elasticsearch, so every approval or denial is backed by a byte-offset citation instead of a model's opinion.

**Theme:** Industry Solutions & Vertical Experiences · **Problem statement:** Healthcare & Insurance Intelligence

---

## The problem

A nurse reviewer spends ~45 minutes reading an 80+ page chart to answer one question: *does this claim meet the payer's criteria?* e.g. "did the patient complete 6 months of conservative therapy before this knee arthroscopy?"

Two obvious solutions both fail:

| Approach | Why it fails |
| --- | --- |
| LLM over the chart | Hallucinates policy citations (15–18% in our baseline); can't count months; no audit trail |
| Pure vector DB | `Type 1 diabetes` and `Type 2 diabetes` are near-identical in embedding space, clinically and financially opposite. `E10.9` vs `E11.9` is a 1-char difference a cosine score cannot respect |

## The approach

**The LLM never decides anything.** Elasticsearch decides; the LLM only writes the sentence, and a validator rejects any sentence containing a fact that isn't in the retrieved evidence set.

1. **Bi-temporal trajectory search (ES|QL)** — every clinical event carries both `event_time` (when it happened) and `recorded_at` (when it entered the record), so criteria are evaluated *as of* the adjudication date and back-dated documentation is detectable.
2. **Hybrid lexical + semantic retrieval (BM25 + DiskBBQ kNN, fused with RRF)** — exact `term` matching on CPT/ICD-10/RxNorm codes, semantic matching on messy narrative notes. "Toradol" finds "Ketorolac"; "Type 1" never matches "Type 2".
3. **Deterministic criteria engine** — payer policy text is compiled *at ingest* into a machine-checkable criteria JSON, and each criterion compiles to an ES|QL query. The verdict is arithmetic over rows, not inference.
4. **Immutable, citation-anchored audit trail** — every decision stores the exact ES|QL executed, the evidence rows returned, and `doc_id + byte_start/byte_end` into the source record, hash-chained so it can't be silently edited.

**Target:** <10s per claim, 96%+ retrieval recall, <0.5% unsupported-statement rate.

## Status

Pre-hackathon component build. See [docs/PROPOSAL.md](docs/PROPOSAL.md) for the full architecture, index mappings, build order and demo script.
