"""Durable V2 clarification envelopes; server-side options are authoritative.

The user sees plain-language options, while the original task and target stay
in server-owned message metadata. These helpers do NOT dispatch jobs.
"""
from __future__ import annotations

from uuid import uuid4
from typing import Any

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .nar_pending_schema_v2 import ClarificationAnswer


def make_clarification_metadata(proposal: dict, *, origin_turn_id: str,
                                verified_target_artifact_id: str | None,
                                clarification_id: str | None = None) -> dict:
    """Construct persistent cards and pending work from a validated proposal.

    Only the Forge caller can supply verified_target_artifact_id. The model's
    candidate_artifact_id must never become an edit parent on its own.
    """
    if proposal.get("schema_version") != "2.0" or proposal.get("next_step") != "clarify":
        raise ValueError("Not a V2 clarification proposal")
    task_list = proposal.get("tasks")
    question = proposal.get("clarification")
    if not isinstance(task_list, list) or not 1 <= len(task_list) <= 4:
        raise ValueError("Invalid pending task")
    if not isinstance(question, dict):
        raise ValueError("Missing clarification")
    labels = question.get("options")
    title = question.get("question")
    if (not isinstance(title, str) or not 0 < len(title.strip()) <= 300
            or not isinstance(labels, list) or not 2 <= len(labels) <= 4
            or any(not isinstance(x, str) or not 0 < len(x.strip()) <= 160 for x in labels)):
        raise ValueError("Invalid clarification options")
    if len(set(labels)) != len(labels):
        raise ValueError("Clarification options must be unique")
    ident = clarification_id or uuid4().hex
    if len(ident) != 32 or any(x not in "0123456789abcdef" for x in ident):
        raise ValueError("Invalid clarification id")
    options = [{"id": f"o{i+1}", "label": label.strip()} for i, label in enumerate(labels)]
    return {
        "choices": {
            "schemaVersion": "2.0", "clarificationId": ident,
            "status": "pending", "question": title.strip(),
            "options": options, "multiple": False,
            "allowCustom": bool(question.get("allow_custom", True)),
        },
        "clarification_v2": {
            "schema_version": "2.0", "clarification_id": ident,
            "origin_turn_id": origin_turn_id, "status": "pending",
            "options": options, "answered_request_id": None,
        },
        "pending_task_v2": {
            "schema_version": "2.0", "origin_turn_id": origin_turn_id,
            "status": "pending",
            "verified_target_artifact_id": verified_target_artifact_id,
            "proposal": proposal,
        },
    }


def validate_clarification_answer(metadata: dict, answer: "ClarificationAnswer") -> dict:
    """Check binding + options. Natural replies like '1' never bind implicitly."""
    clarification = metadata.get("clarification_v2")
    choices = metadata.get("choices")
    pending = metadata.get("pending_task_v2")
    if not all(isinstance(x, dict) for x in (clarification, choices, pending)):
        raise ValueError("Clarification state is missing")
    if (clarification.get("clarification_id") != answer.clarification_id
            or choices.get("clarificationId") != answer.clarification_id
            or pending.get("schema_version") != "2.0"):
        raise ValueError("Clarification does not match pending task")
    if clarification.get("status") != "pending" or pending.get("status") != "pending":
        raise ValueError("Clarification is no longer pending")
    allowed = {item.get("id") for item in clarification.get("options", [])
               if isinstance(item, dict)}
    if not allowed or any(item not in allowed for item in answer.selected_option_ids):
        raise ValueError("Unknown clarification option")
    if not choices.get("multiple", False) and len(answer.selected_option_ids) > 1:
        raise ValueError("This clarification allows only one option")
    if answer.custom_text and not choices.get("allowCustom", False):
        raise ValueError("Free-text answer is not enabled")
    return {
        "clarification_id": answer.clarification_id,
        "selected_option_ids": answer.selected_option_ids,
        "selected_labels": [
            item["label"] for item in clarification["options"]
            if item["id"] in answer.selected_option_ids
        ],
        "custom_text": answer.custom_text,
    }


def mark_clarification_answered(metadata: dict, answer: dict, request_id: str) -> dict:
    """Pure CAS payload builder; database update must be conditional and atomic."""
    updated = {**metadata, "choices": dict(metadata["choices"]),
               "clarification_v2": dict(metadata["clarification_v2"]),
               "pending_task_v2": dict(metadata["pending_task_v2"])}
    updated["choices"]["status"] = "answered"
    updated["clarification_v2"].update(status="answered", answered_request_id=request_id,
                                       answer=answer)
    updated["pending_task_v2"]["status"] = "answered"
    return updated
