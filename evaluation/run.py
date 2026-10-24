"""Small synthetic A/B/C smoke evaluation, not a research benchmark."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from stat_agent.agents import KnowledgeAgent, ProfileValidationAgent, RelationsAgent, StructureAgent, TaskUnderstandingAgent
from stat_agent.io import read_table
from stat_agent.retrieval import LexicalEncoder, SentenceEncoder, retrieve


def metrics(ranked: list[str], relevant: list[str], k=3):
    if not relevant:
        return {"recall_at_k": None, "mrr": None, "ndcg_at_k": None, "top1_correct": not ranked}
    hits = [int(item in relevant) for item in ranked[:k]]
    dcg = sum(hit / math.log2(i + 2) for i, hit in enumerate(hits))
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(relevant))))
    ranks = [i + 1 for i, item in enumerate(ranked) if item in relevant]
    return {"recall_at_k": sum(hits) / len(relevant), "mrr": 1 / min(ranks) if ranks else 0,
            "ndcg_at_k": dcg / ideal, "top1_correct": bool(ranked and ranked[0] in relevant)}


def evaluate(encoder=None):
    root = Path(__file__).resolve().parents[1]
    cases_path = root / "evaluation" / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    knowledge = KnowledgeAgent().run()
    encoder = encoder or LexicalEncoder()
    results = []
    for case in cases:
        frame, source = read_table(root / "examples" / "data" / case["file"])
        if case.get("mutation") == "infinite":
            frame = frame.astype(float)
            frame.loc[0, "x1"] = np.inf
        if case.get("mutation") == "categorical":
            frame["x1"] = ["a", "b"] * (len(frame) // 2)
        # Mutated fixtures have a separate source hash; never reuse the original file hash for changed facts.
        source.sha256 = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()
        source.extraction_method += "; evaluation in-memory fixture, hash of canonical CSV"
        task = TaskUnderstandingAgent().run(case["goal"], task_type=case["task"],
                    predictors=case["predictors"], targets=case.get("targets", []))
        profile = ProfileValidationAgent().run(frame, source, task, StructureAgent().run(frame, source), RelationsAgent().run(frame, task))
        for mode in ["A", "B", "C"]:
            start = time.perf_counter()
            ranking = retrieve(task, profile, knowledge, encoder, mode=mode)
            ranked = [c.knowledge_id for c in ranking.ranked]
            results.append({"case": case["id"], "mode": mode, "relevant": case["relevant"],
                            "ranked": ranked, "seconds": time.perf_counter() - start,
                            **metrics(ranked, case["relevant"])})
    summary = {}
    for mode in ["A", "B", "C"]:
        rows = [r for r in results if r["mode"] == mode]
        positive = [r for r in rows if r["relevant"]]
        negative = [r for r in rows if not r["relevant"]]
        summary[mode] = {key: sum(r[key] for r in positive) / len(positive) for key in ["recall_at_k", "mrr", "ndcg_at_k"]}
        summary[mode].update(selection_accuracy=sum(r["top1_correct"] for r in rows) / len(rows),
                             incompatible_recommendation_rate=sum(bool(r["ranked"]) for r in negative) / len(negative))
    return {"scope": "synthetic lexical smoke test; not semantic-retrieval or statistical-validity evidence",
            "encoder": encoder.name, "k": 3, "alpha": 1, "penalty_lambda": .5,
            "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "case_count": len(cases), "summary": summary, "results": results,
            "limitations": ["One candidate per task: cannot establish benefit of soft penalties within a task.",
                            "Labels are authored signature checks, not independently reviewed statistical gold labels.",
                            "MANOVA/LDA cases do not certify applicability without design/class information.",
                            "No DARE comparison, LLM costs or multi-agent improvement measured."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("evaluation/results/smoke.json"))
    parser.add_argument("--model", help="Optional pretrained model ID/path; default is lexical smoke only")
    parser.add_argument("--revision")
    args = parser.parse_args()
    result = evaluate(SentenceEncoder(args.model, args.revision) if args.model else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
