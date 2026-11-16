"""Forge-side NarAgent V2 context and safe capability planning.

No model calls here. The candidate list MUST originate from an owner-scoped
NarConversationStore query; a client-supplied ID is only a selection hint.
This module is initially used by shadow routing, never as dispatch authority.
"""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "2.0"
DEFAULT_CAPABILITIES = {
    "chat": ["answer", "discuss", "evaluate"],
    "html": ["create", "revise"],
    "animation": ["create", "revise"],
    "hybrid": ["plan_only"],
}
ACTION_SET = {"answer", "discuss", "evaluate", "create", "revise", "convert", "continue"}


def build_context_packet(
    prompt: str, conversation_id: str, recent_dialogue: list[dict],
    owner_scoped_artifacts: list[dict], selected_artifact_id: str | None = None,
    pending_task: dict | None = None, pending_clarification: dict | None = None,
    capabilities: dict[str, list[str]] | None = None,
    owner_scoped_games: list[dict] | None = None,
) -> dict:
    """Never translate recency to selection; no client-supplied owner or kind."""
    candidates = []
    for row in owner_scoped_artifacts[:5]:
        if row.get("kind") not in ("html", "animation"):
            continue
        candidates.append({
            "id": row["artifactId"],
            "kind": row["kind"],
            "title": str(row.get("title") or "")[:200],
            "status": "completed",
        })
    candidate_ids = {item["id"] for item in candidates}
    if selected_artifact_id is not None and selected_artifact_id not in candidate_ids:
        # Explicit selection may be older than the last five; caller must
        # re-fetch it by owner/conversation and include it in candidates.
        raise ValueError("Selected artifact is not owner-scoped")
    games = [{"id": row["id"], "title": str(row.get("title") or "")[:200],
              "status": str(row.get("status") or "created")[:32]}
             for row in (owner_scoped_games or [])[:5]
             if isinstance(row.get("id"), str) and len(row["id"]) == 32]
    dialogue = [
        {"role": row["role"], "content": str(row["content"])[:1800]}
        for row in recent_dialogue[-12:]
        if row.get("role") in ("user", "assistant")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "current_message": prompt,
        "conversation": {
            "id": conversation_id,
            "recent_dialogue": dialogue,
            "pending_task": pending_task,
            "pending_clarification": pending_clarification,
        },
        "workspace": {
            "selected_artifact_id": selected_artifact_id,
            "recent_artifacts": candidates,
            **({"recent_games": games} if games or "game" in (capabilities or {}) else {}),
        },
        "capabilities": capabilities or DEFAULT_CAPABILITIES,
    }


def _confirmed_creation_format(proposal: dict, context: dict) -> bool:
    """A formal answer may resume an *original* new creation, not a conversion.

    This is intentionally narrow: only a server-validated, single option answer to an output-format
    ambiguity with no free text can resume an original create/new/unspecified
    task. Explicit capability reviews always win.
    The model must identify the resulting output; the planner still checks
    real executor capabilities before any work is prepared.
    """
    conversation = context.get("conversation") or {}
    pending = conversation.get("pending_task") or {}
    current_answer = (conversation.get("pending_clarification") or {}).get("current_answer") or {}
    previous = (pending.get("proposal") or {})
    previous_tasks = previous.get("tasks") or []
    proposed_tasks = proposal.get("tasks") or []
    if (pending.get("status") != "pending"
            or previous.get("next_step") != "clarify"
            or previous.get("uncertainty") != "output"
            or proposal.get("next_step") != "execute"
            or len(previous_tasks) != 1 or len(proposed_tasks) != 1
            or len(current_answer.get("selected_option_ids") or []) != 1
            or current_answer.get("custom_text")
            or previous_tasks[0].get("action") != "create"
            or previous_tasks[0].get("target_relation") != "new"
            or previous_tasks[0].get("desired_output") != "unspecified"):
        return False
    task = proposed_tasks[0]
    return (task.get("action") in ("continue", "convert")
            and task.get("target_relation") in ("none", "new")
            and task.get("candidate_artifact_id") is None
            and task.get("candidate_game_job_id") is None
            and task.get("desired_output") in ("html", "animation", "game"))


def plan_v2(proposal: dict, context: dict) -> dict:
    """Pure, fail-closed capability planner. A result is never edit authorization.

    Live dispatch must additionally check latest artifact versions, idempotency,
    capabilities and persistent pending-task state before accepting a plan.
    """
    outcome = {"next_step": "capability_review", "mode": None,
               "parent_artifact_id": None, "reason": "unresolved"}
    if not isinstance(proposal, dict) or proposal.get("schema_version") != SCHEMA_VERSION:
        return {**outcome, "reason": "invalid_schema"}
    tasks = proposal.get("tasks")
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 4:
        return {**outcome, "reason": "invalid_tasks"}
    if len(tasks) != 1:
        return {**outcome, "reason": "multi_task_requires_planning"}
    task = tasks[0]
    if not isinstance(task, dict) or task.get("action") not in ACTION_SET:
        return {**outcome, "reason": "invalid_action"}
    requested_step = proposal.get("next_step")
    if requested_step not in ("respond", "execute", "clarify", "capability_review"):
        return {**outcome, "reason": "invalid_next_step"}
    if requested_step == "clarify":
        return {**outcome, "next_step": requested_step, "reason": "model_requested_review"}
    action, relation, output = (task.get(k) for k in ("action", "target_relation", "desired_output"))
    # In a confirmed format choice the user is *still creating* the original
    # independent work. Do not treat the selected output medium as a request
    # to convert an existing artifact, or as a free-standing 'continue' task.
    resumed_creation = _confirmed_creation_format(proposal, context)
    if resumed_creation:
        action, relation = "create", "new"
    elif requested_step == "capability_review":
        # A model-reported unsupported feature must never be overridden by
        # a user clicking a format choice. Format choice != capability approval.
        return {**outcome, "next_step": requested_step, "reason": "model_requested_review"}
    artifacts = {item["id"]: item for item in context.get("workspace", {}).get("recent_artifacts", [])}
    selected = context.get("workspace", {}).get("selected_artifact_id")
    candidate = task.get("candidate_artifact_id")
    game_candidate = task.get("candidate_game_job_id")
    if action in ("answer", "discuss", "evaluate") and output in ("text", "unspecified"):
        return {"next_step": "respond", "mode": "chat", "parent_artifact_id": None,
                "reason": "non_creative_request"}
    if action == "create":
        if relation not in ("none", "new") or candidate or game_candidate:
            return {**outcome, "reason": "create_must_not_inherit_parent"}
        if output == "game" and "create" in context["capabilities"].get("game", []):
            return {"next_step": "execute", "mode": "rpg.prepare",
                    "parent_artifact_id": None, "reason": "new_game"}
        if output == "html" and "create" in context["capabilities"].get("html", []):
            return {"next_step": "execute", "mode": "html",
                    "parent_artifact_id": None, "reason": "new_html"}
        if output == "animation" and "create" in context["capabilities"].get("animation", []):
            return {"next_step": "execute", "mode": "animation",
                    "parent_artifact_id": None, "reason": "new_animation"}
        if output == "text":
            return {"next_step": "respond", "mode": "chat",
                    "parent_artifact_id": None, "reason": "text_creation"}
        return {**outcome, "next_step": "clarify" if output == "unspecified" else "capability_review",
                "reason": "output_not_executable"}
    if action == "revise":
        if output == "game":
            games = {item["id"]: item for item in context.get("workspace", {}).get("recent_games", [])}
            if relation != "referenced" or not game_candidate or game_candidate not in games:
                return {**outcome, "next_step": "clarify", "reason": "game_target_not_identified"}
            if candidate or "edit_link" not in context["capabilities"].get("game", []):
                return {**outcome, "reason": "game_edit_link_unavailable"}
            return {"next_step": "execute", "mode": "rpg.edit_link",
                    "parent_artifact_id": None, "game_job_id": game_candidate,
                    "reason": "verified_game_edit_link_candidate"}
        if game_candidate:
            return {**outcome, "reason": "game_reference_for_non_game"}
        if relation == "selected":
            if not selected or candidate not in (None, selected):
                return {**outcome, "next_step": "clarify", "reason": "selected_target_mismatch"}
            candidate = selected
        elif relation != "referenced" or not candidate:
            return {**outcome, "next_step": "clarify", "reason": "target_not_identified"}
        target = artifacts.get(candidate)
        if not target or target.get("kind") not in ("html", "animation"):
            return {**outcome, "next_step": "clarify", "reason": "target_not_owner_scoped"}
        kind = target["kind"]
        if output not in (kind, "unspecified"):
            return {**outcome, "reason": "cross_generator_conversion_requires_review"}
        if "revise" not in context["capabilities"].get(kind, []):
            return {**outcome, "reason": "executor_cannot_revise"}
        return {"next_step": "execute", "mode": "edit" if kind == "html" else "animation",
                "parent_artifact_id": candidate, "reason": "verified_same_kind_revision"}
    return {**outcome, "reason": "conversion_or_continuation_not_auto_executable"}
