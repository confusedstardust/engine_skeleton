"""Durable V2 clarification contract: options and task binding."""
import pytest
from pydantic import ValidationError

from webgal_backend.nar_pending_v2 import (
    ClarificationAnswer, make_clarification_metadata,
    mark_clarification_answered, validate_clarification_answer,
)

TID = "c" * 32
AID = "a" * 32
CID = "d" * 32


def envelope():
    proposal = {"schema_version": "2.0", "next_step": "clarify",
                "uncertainty": "target", "tasks": [
                  {"action": "revise", "target_relation": "ambiguous",
                   "candidate_artifact_id": None, "desired_output": "animation",
                   "goal": "将画面移到中间", "requirements": []}],
                "clarification": {
                  "question": "你想修改哪件作品？",
                  "options": ["马达原理动画", "一次函数网页"],
                  "allow_custom": True}}
    return make_clarification_metadata(
        proposal, origin_turn_id=TID, verified_target_artifact_id=None,
        clarification_id=CID)


def test_persistent_choice_has_formal_id_and_original_task():
    data = envelope()
    assert data["choices"]["clarificationId"] == CID
    assert data["pending_task_v2"]["proposal"]["tasks"][0]["action"] == "revise"
    assert data["pending_task_v2"]["verified_target_artifact_id"] is None
    assert data["choices"]["options"] == [
        {"id": "o1", "label": "马达原理动画"},
        {"id": "o2", "label": "一次函数网页"},
    ]


def test_answer_is_bound_by_id_not_by_bare_number_or_random_option():
    data = envelope()
    with pytest.raises(ValidationError):
        ClarificationAnswer(clarification_id=CID, selected_option_ids=[])
    with pytest.raises(ValueError):
        validate_clarification_answer(data, ClarificationAnswer(
            clarification_id=CID, selected_option_ids=["other"]))
    with pytest.raises(ValueError):
        validate_clarification_answer(data, ClarificationAnswer(
            clarification_id="b" * 32, selected_option_ids=["o1"]))
    value = validate_clarification_answer(data, ClarificationAnswer(
        clarification_id=CID, selected_option_ids=["o1"]))
    assert value["selected_labels"] == ["马达原理动画"]


def test_answered_card_is_disabled_and_preserves_history():
    data = envelope()
    ans = validate_clarification_answer(data, ClarificationAnswer(
        clarification_id=CID, selected_option_ids=["o2"]))
    marked = mark_clarification_answered(data, ans, "e" * 32)
    assert marked["choices"]["status"] == "answered"
    assert marked["pending_task_v2"]["status"] == "answered"
    assert data["choices"]["status"] == "pending"
    with pytest.raises(ValueError):
        validate_clarification_answer(marked, ClarificationAnswer(
            clarification_id=CID, selected_option_ids=["o1"]))


def test_invalid_proposal_does_not_form_executable_pending_task():
    with pytest.raises(ValueError):
        make_clarification_metadata(
            {"schema_version": "2.0", "next_step": "execute"},
            origin_turn_id=TID, verified_target_artifact_id=AID)
