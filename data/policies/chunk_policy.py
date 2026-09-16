#!/usr/bin/env python3
"""Split a policy .txt into retrievable chunks that keep their byte offsets.

Offsets are carried through from the raw bytes so any chunk retrieved from
Elasticsearch can be traced straight back to the exact span of the source
document. Chunk on section boundaries: payer policies are already structured
that way, and a criterion always lives inside one section.

    python3 data/policies/chunk_policy.py data/policies/MHP-0673.criteria.json
"""
import json
import re
import sys
from pathlib import Path

SECTION = re.compile(rb"^SECTION \d+\..*$|^\d+\.\d+ ", re.MULTILINE)


def chunk(criteria_path: Path) -> list[dict]:
    spec = json.loads(criteria_path.read_text())
    policy_path = criteria_path.parent / spec["source_doc_id"]
    raw = policy_path.read_bytes()

    # Split points: every SECTION header and every numbered sub-criterion.
    starts = [m.start() for m in SECTION.finditer(raw)]
    if not starts or starts[0] != 0:
        starts.insert(0, 0)
    bounds = list(zip(starts, starts[1:] + [len(raw)]))

    chunks = []
    for i, (start, end) in enumerate(bounds):
        text = raw[start:end].decode("utf-8").strip()
        if not text:
            continue
        head = text.split("\n", 1)[0]
        label = head.strip()[:60]
        chunks.append({
            "chunk_id": f"{spec['policy_id']}::{i:02d}",
            "policy_id": spec["policy_id"],
            "payer": spec["payer"],
            "version": spec["version"],
            "title": spec["title"],
            "effective_from": spec["effective_from"],
            "effective_to": spec["effective_to"],
            "applies_to_cpt": spec["applies_to_cpt"],
            "applies_to_icd": spec.get("applies_to_icd", []),
            "section": label,
            "chunk_text": text,
            "source_doc_id": spec["source_doc_id"],
            "source_page": 1,
            "byte_start": start,
            "byte_end": end,
        })
    return chunks


if __name__ == "__main__":
    targets = [Path(a) for a in sys.argv[1:]] or sorted(Path("data/policies").glob("*.criteria.json"))
    out = Path("data/policies/policy-chunks.jsonl")
    all_chunks = [c for t in targets for c in chunk(t)]
    out.write_text("".join(json.dumps(c) + "\n" for c in all_chunks))
    print(f"wrote {len(all_chunks)} chunks -> {out}")
    for c in all_chunks:
        print(f"  {c['chunk_id']}  bytes {c['byte_start']:>5}-{c['byte_end']:<5}  {c['section'][:52]}")
