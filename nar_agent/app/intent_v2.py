"""NarAgent V2 semantic intent contract.

The interpreter proposes *meaning*, never a final executor or edit authority.
Forge resolves references, validates owners/versions and makes routing decisions.
This module is opt-in; legacy /v1/intent requests retain their V1 contract.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import Settings
from app.metering import record_direct_intent_response

Action = Literal["answer", "discuss", "create", "revise", "convert", "evaluate", "continue"]
Relation = Literal["none", "new", "selected", "referenced", "ambiguous"]
Output = Literal["text", "html", "animation", "game", "hybrid", "unspecified"]
NextStep = Literal["respond", "execute", "clarify", "capability_review"]
Uncertainty = Literal["none", "target", "goal", "output", "capability"]


class TaskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Action
    target_relation: Relation
    candidate_artifact_id: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{32}$")
    candidate_game_job_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    desired_output: Output
    goal: str = Field(min_length=1, max_length=500)
    requirements: list[str] = Field(default_factory=list, max_length=12)


class ClarificationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=300)
    options: list[str] = Field(min_length=2, max_length=4)
    allow_custom: bool = True

    @model_validator(mode="after")
    def valid_options(self):
        if any(not label.strip() or len(label) > 160 for label in self.options):
            raise ValueError("Invalid user-facing clarification option")
        if len({label.strip() for label in self.options}) != len(self.options):
            raise ValueError("Duplicate clarification options")
        return self


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    schema_version: Literal["2.0"] = "2.0"
    tasks: list[TaskIntent] = Field(min_length=1, max_length=4)
    next_step: NextStep
    uncertainty: Uncertainty
    clarification: ClarificationProposal | None = None

    @model_validator(mode="after")
    def consistent_decision(self):
        if self.next_step == "clarify" and self.clarification is None:
            raise ValueError("Clarification details required")
        if self.next_step != "clarify" and self.clarification is not None:
            raise ValueError("Unexpected clarification outside clarify step")
        if self.next_step == "execute" and any(
            task.target_relation == "ambiguous" for task in self.tasks
        ):
            raise ValueError("Cannot execute against ambiguous target")
        return self


class ContextArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    kind: Literal["html", "animation"]
    title: str = Field(default="", max_length=200)
    status: str = Field(default="completed", max_length=32)
    version: int | None = Field(default=None, ge=1)


class ContextConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=191)
    recent_dialogue: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    pending_task: dict | None = None
    pending_clarification: dict | None = None

    @model_validator(mode="after")
    def bounded_history(self):
        for row in self.recent_dialogue:
            if set(row) != {"role", "content"}:
                raise ValueError("Invalid history keys")
            if row["role"] not in ("user", "assistant") or len(row["content"]) > 1800:
                raise ValueError("Invalid history item")
        return self


class ContextGame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[0-9a-f]{32}$")
    title: str = Field(default="", max_length=200)
    status: str = Field(default="created", max_length=32)


class ContextWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_artifact_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    recent_artifacts: list[ContextArtifact] = Field(default_factory=list, max_length=5)
    recent_games: list[ContextGame] = Field(default_factory=list, max_length=5)


class IntentContext(BaseModel):
    """Forge must construct this from owner-scoped server data, not browser claims."""
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["2.0"] = "2.0"
    current_message: str = Field(min_length=1, max_length=12000)
    conversation: ContextConversation = Field(default_factory=ContextConversation)
    workspace: ContextWorkspace = Field(default_factory=ContextWorkspace)
    capabilities: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_context(self):
        if sum(len(x["content"]) for x in self.conversation.recent_dialogue) + len(self.current_message) > 36000:
            raise ValueError("Context exceeds input bound")
        if len(self.capabilities) > 6 or any(
            len(name) > 40 or len(actions) > 12 or
            any(len(action) > 40 for action in actions)
            for name, actions in self.capabilities.items()
        ):
            raise ValueError("Capabilities exceed bounds")
        # A UI selection is evidence, never an editable parent or ownership proof.
        return self


PROMPT_VERSION = "intent_v2@1.1.1"
PROMPT_FILE = Path(__file__).with_name("prompts") / "intent_v2.md"


def validate_proposal(raw: str, context: IntentContext) -> IntentDecision:
    """Fail closed on malformed JSON, invented IDs and unsupported references."""
    try:
        proposal = IntentDecision.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise ValueError("Invalid IntentDecision V2 JSON") from exc
    candidates = {a.id for a in context.workspace.recent_artifacts}
    game_ids = {game.id for game in context.workspace.recent_games}
    if context.workspace.selected_artifact_id:
        candidates.add(context.workspace.selected_artifact_id)
    for task in proposal.tasks:
        if task.candidate_artifact_id and task.candidate_artifact_id not in candidates:
            raise ValueError("Proposed artifact ID not in the owner-scoped candidates")
        if task.candidate_game_job_id and task.candidate_game_job_id not in game_ids:
            raise ValueError("Proposed game ID not in the owner-scoped candidates")
        if task.candidate_game_job_id and task.candidate_artifact_id:
            raise ValueError("Game and artifact references are mutually exclusive")
        if task.target_relation in ("none", "new") and (
            task.candidate_artifact_id or task.candidate_game_job_id
        ):
            raise ValueError("New or target-free request cannot bind an existing artifact or game")
        if task.candidate_game_job_id and task.desired_output != "game":
            raise ValueError("Game job references require game output")
    return proposal


async def interpret_intent_v2(settings: Settings, context: IntentContext) -> IntentDecision:
    """One model call. No regex short-circuit and no fallback to HTML/chat."""
    model = ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url,
        temperature=0,
        max_tokens=1000,
        timeout=min(20, settings.timeout_seconds),
        max_retries=0,
    )
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    payload = context.model_dump(exclude_none=True)
    response = await model.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ])
    record_direct_intent_response(response)
    if not isinstance(response.content, str):
        raise ValueError("Intent V2 did not produce text JSON")
    return validate_proposal(response.content, context)
