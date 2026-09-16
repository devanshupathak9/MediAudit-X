"""Playground: search policy sections three ways and compare.

  keyword : matches words (English analyzer: "months" == "month")
  vector  : matches meaning ("weight" finds "body mass index")
  hybrid  : both, merged with RRF

    python elasticsearch/search_policies.py "patient weight too high" --mode all
    python elasticsearch/search_policies.py "was the MRI done at the right time" --cpt 29881 --date 2026-06-01 --type criterion
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root, for `shared`

from shared.embeddings import MODEL_NAME  # noqa: E402
from shared.policy_search import MODES, search  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("question")
parser.add_argument("--mode", choices=[*MODES, "all"], default="hybrid")
parser.add_argument("--cpt", help="only policies covering this procedure code, e.g. 29881")
parser.add_argument("--date", help="only policies in effect on this date, e.g. 2026-06-01")
parser.add_argument("--type", help="only this chunk type, e.g. criterion")
parser.add_argument("--top", type=int, default=3)
args = parser.parse_args()

print(f'Question: "{args.question}"   model: {MODEL_NAME}   filters: cpt={args.cpt} date={args.date} type={args.type}')
for mode in (MODES if args.mode == "all" else [args.mode]):
    hits = search(args.question, mode=mode, k=args.top, cpt=args.cpt, date=args.date, chunk_type=args.type)
    print(f"\n[{mode.upper()}]  {len(hits)} result(s)")
    for h in hits:
        label = f"rank {h['rank']}" if h["score"] is None else f"score {h['score']:.3f}"
        m = h["metadata"]
        print(f"  {label:<11}  §{m['section_no']:<4} {m['chunk_type']:<14} {' '.join(h['text'].split())[:90]}...")
