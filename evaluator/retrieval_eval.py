"""Offline retrieval evaluation: does search find the right policy section?

For every question in gold/retrieval.jsonl, run keyword, vector and hybrid search
and report Recall@1, Recall@3 and MRR (how high the right answer ranks, 1.0 = always first).

    python -m evaluator.retrieval_eval
"""
import json

from shared.config import ROOT
from shared.embeddings import MODEL_NAME
from shared.policy_search import MODES, search

GOLD = ROOT / "evaluator" / "gold" / "retrieval.jsonl"


def evaluate(k: int = 3) -> dict:
    questions = [json.loads(line) for line in GOLD.read_text().splitlines() if line.strip()]
    results = {}
    for mode in MODES:
        hits1 = hitsk = rr = 0.0
        misses = []
        for q in questions:
            sections = [h["metadata"]["section_no"] for h in search(q["question"], mode=mode, k=k, cpt=q["cpt"])]
            if q["expected_section"] in sections:
                pos = sections.index(q["expected_section"]) + 1
                hitsk += 1
                hits1 += pos == 1
                rr += 1 / pos
            else:
                misses.append(f"{q['question']!r} -> got {sections}, expected §{q['expected_section']}")
        n = len(questions)
        results[mode] = {"recall@1": hits1 / n, f"recall@{k}": hitsk / n, "mrr": rr / n, "misses": misses}
    return {"model": MODEL_NAME, "questions": len(questions), "results": results}


if __name__ == "__main__":
    report = evaluate()
    print(f"Retrieval eval: {report['questions']} questions, model {report['model']}\n")
    print(f"  {'mode':<8} {'recall@1':>9} {'recall@3':>9} {'MRR':>6}")
    for mode, r in report["results"].items():
        print(f"  {mode:<8} {r['recall@1']:>9.0%} {r['recall@3']:>9.0%} {r['mrr']:>6.2f}")
    for mode, r in report["results"].items():
        for miss in r["misses"]:
            print(f"  miss [{mode}] {miss}")
