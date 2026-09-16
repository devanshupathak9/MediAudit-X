#!/usr/bin/env python3
"""Resolve each criterion's `source.quote` to real byte offsets in the policy file.

Citations must never be hand-typed: a typo'd offset is a silent lie in an audit
trail. This locates the quote in the source bytes and writes back
`byte_start` / `byte_end` / `line`. Run it whenever a policy or quote changes;
it fails loudly if a quote is missing or ambiguous.

    python3 data/policies/anchor_citations.py data/policies/MHP-0673.criteria.json
"""
import json
import sys
from pathlib import Path


def anchor(criteria_path: Path) -> int:
    spec = json.loads(criteria_path.read_text())
    policy_path = criteria_path.parent / spec["source_doc_id"]
    raw = policy_path.read_bytes()

    errors = []
    for crit in spec["criteria"]:
        src = crit["source"]
        quote = src["quote"]
        needle = quote.encode("utf-8")

        hits = []
        start = raw.find(needle)
        while start != -1:
            hits.append(start)
            start = raw.find(needle, start + 1)

        if not hits:
            errors.append(f"{crit['criterion_id']}: quote not found in {policy_path.name}: {quote!r}")
            continue
        if len(hits) > 1:
            errors.append(f"{crit['criterion_id']}: quote is ambiguous ({len(hits)} matches), lengthen it: {quote!r}")
            continue

        src["byte_start"] = hits[0]
        src["byte_end"] = hits[0] + len(needle)
        src["line"] = raw[: hits[0]].count(b"\n") + 1

    if errors:
        for e in errors:
            print(f"FAIL  {e}", file=sys.stderr)
        return 1

    criteria_path.write_text(json.dumps(spec, indent=2) + "\n")
    for crit in spec["criteria"]:
        s = crit["source"]
        print(f"  {crit['criterion_id']:<16} §{s['section']:<5} line {s['line']:>3}  bytes {s['byte_start']}-{s['byte_end']}")
    print(f"OK    anchored {len(spec['criteria'])} citations into {criteria_path.name}")
    return 0


if __name__ == "__main__":
    targets = [Path(a) for a in sys.argv[1:]] or sorted(Path("data/policies").glob("*.criteria.json"))
    sys.exit(max(anchor(t) for t in targets))
