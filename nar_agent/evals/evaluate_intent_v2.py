"""Manual live-model V2 intent evaluation. Run from nar_agent/:

    uv run python -m evals.evaluate_intent_v2 --limit 35

Requires a configured model API key. Never logs private conversation bodies.
Evaluation data is a curated seed, not the complete 180-case release gate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from time import perf_counter

from app.config import Settings
from app.intent_v2 import IntentContext, interpret_intent_v2

CASES = Path(__file__).with_name("intent_v2_cases.jsonl")
LABELS = ("action", "target_relation", "desired_output", "next_step", "candidate_artifact_id")


def macro_f1(expected: list[str], actual: list[str]) -> float:
    classes = set(expected) | set(actual)
    if not classes:
        return 0.0
    scores = []
    for label in classes:
        tp = sum(x == label and y == label for x, y in zip(expected, actual))
        fp = sum(x != label and y == label for x, y in zip(expected, actual))
        fn = sum(x == label and y != label for x, y in zip(expected, actual))
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return sum(scores) / len(scores)


async def evaluate(limit: int):
    rows = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[:limit]
    settings = Settings()
    if not settings.api_key.get_secret_value():
        raise SystemExit("Set NAR_AGENT_API_KEY before evaluating")
    results = []
    for row in rows:
        begin = perf_counter()
        try:
            context = IntentContext.model_validate(row["context"])
            proposal = await interpret_intent_v2(settings, context)
            task = proposal.tasks[0]
            got = {**task.model_dump(), "next_step": proposal.next_step}
            valid = True
        except Exception:
            got, valid = {}, False
        elapsed_ms = round((perf_counter() - begin) * 1000)
        expect = row["expected"]
        match = {key: got.get(key) == expect.get(key) for key in LABELS}
        results.append({"id": row["case_id"], "group": row["group"], "valid": valid,
                        "match": match, "predicted": {key: got.get(key) for key in LABELS},
                        "latency_ms": elapsed_ms})
        print(row["case_id"], "valid=" + str(valid),
              "exact=" + str(valid and all(match.values())),
              "latency_ms=" + str(elapsed_ms))
    print("\nEvaluated:", len(results))
    print("Schema valid:", sum(x["valid"] for x in results), "/", len(results))
    print("Exact labels:", sum(x["valid"] and all(x["match"].values()) for x in results))
    for key in LABELS:
        print(key, "accuracy:", round(sum(x["match"][key] for x in results) / len(results), 3))
    for key in ("action", "target_relation", "desired_output", "next_step"):
        gold = [row["expected"][key] for row in rows]
        # Invalid output is an explicit error class, not converted to chat/html.
        predicted = [x["predicted"].get(key) if x["valid"] else "__invalid__"
                     for x in results]
        print(key, "macro-F1:", round(macro_f1(gold, predicted), 3))
    print("Groups:", dict(Counter(x["group"] for x in results)))
    print("Invalid and mismatched cases:", [x["id"] for x in results
                                           if not x["valid"] or not all(x["match"].values())])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=35)
    args = parser.parse_args()
    asyncio.run(evaluate(max(1, args.limit)))
