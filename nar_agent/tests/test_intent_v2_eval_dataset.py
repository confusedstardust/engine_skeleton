"""Validate V2 golden-seed integrity without making paid model calls."""
import json
from pathlib import Path
from app.intent_v2 import IntentContext


def test_v2_seed_cases_have_valid_context_and_reference_labels():
    path = Path(__file__).parents[1] / "evals" / "intent_v2_cases.jsonl"
    rows = [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s]
    assert len(rows) == 35  # Curated PR-1 seed, not the 180-case release target.
    assert len({row["case_id"] for row in rows}) == len(rows)
    groups = {}
    for row in rows:
        ctx = IntentContext.model_validate(row["context"])
        expected = row["expected"]
        assert expected["action"] in (
            "answer", "discuss", "evaluate", "create", "revise", "convert", "continue")
        assert expected["desired_output"] in ("text", "html", "animation", "hybrid", "unspecified")
        assert expected["next_step"] in ("respond", "execute", "clarify", "capability_review")
        if expected["candidate_artifact_id"] is not None:
            assert expected["candidate_artifact_id"] in {
                obj.id for obj in ctx.workspace.recent_artifacts}
        groups[row["group"]] = groups.get(row["group"], 0) + 1
    assert len(groups) == 7
    assert all(n == 5 for n in groups.values())
