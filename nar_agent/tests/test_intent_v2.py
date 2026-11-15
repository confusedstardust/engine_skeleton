"""Contract and security tests for opt-in V2 intent proposals."""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from app.intent_v2 import (
    ContextArtifact, ContextWorkspace, IntentContext, IntentDecision,
    interpret_intent_v2, validate_proposal,
)


A = "a" * 32
B = "b" * 32


def context():
    return IntentContext(
        current_message="再做一个新的函数练习网页",
        workspace=ContextWorkspace(
            selected_artifact_id=A,
            recent_artifacts=[ContextArtifact(id=A, kind="animation", title="马达动画")],
        ),
    )


def proposal(**changes):
    data = {
        "schema_version": "2.0",
        "tasks": [{"action": "create", "target_relation": "new",
                   "candidate_artifact_id": None, "desired_output": "html",
                   "goal": "制作一个函数练习网页", "requirements": []}],
        "next_step": "execute", "uncertainty": "none", "clarification": None,
    }
    data.update(changes)
    return data


def test_contract_new_task_never_inherits_selected_artifact():
    import json
    decision = validate_proposal(json.dumps(proposal(), ensure_ascii=False), context())
    assert decision.tasks[0].target_relation == "new"
    assert decision.tasks[0].candidate_artifact_id is None


def test_contract_rejects_invented_or_disallowed_artifact():
    import json
    item = proposal()
    item["tasks"][0].update(action="revise", target_relation="referenced",
                             candidate_artifact_id=B)
    with pytest.raises(ValueError, match="candidates"):
        validate_proposal(json.dumps(item), context())
    item["tasks"][0].update(target_relation="new", candidate_artifact_id=A)
    with pytest.raises(ValueError, match="New or target-free"):
        validate_proposal(json.dumps(item), context())


def test_contract_rejects_malformed_json_and_unknown_fields():
    with pytest.raises(ValueError):
        validate_proposal('{"tasks": "broken"}', context())
    with pytest.raises(ValidationError):
        IntentDecision.model_validate({**proposal(), "injected": "execute now"})


def test_clarification_requires_question_and_options():
    from app.intent_v2 import IntentDecision
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(proposal(next_step="clarify"))
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(proposal(
            next_step="clarify", clarification={"question":"选哪个？","options":["A","A"]}))


def test_model_called_once_without_keyword_shortcuts(monkeypatch):
    import json
    import app.intent_v2 as module
    calls = []
    class FakeModel:
        def __init__(self, **kwargs):
            pass
        async def ainvoke(self, messages):
            calls.append(messages)
            return SimpleNamespace(content=json.dumps(proposal()))
    monkeypatch.setattr(module, "ChatOpenAI", FakeModel)
    settings = SimpleNamespace(model="test", api_key=SimpleNamespace(
        get_secret_value=lambda: "secret"), base_url="unused", timeout_seconds=20)
    result = asyncio.run(interpret_intent_v2(settings, context()))
    assert result.tasks[0].action == "create"
    assert len(calls) == 1
