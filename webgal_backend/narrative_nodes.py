from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Literal

from .llm import LLMError, OpenAIFunctionClient


NarrativeNodeKind = Literal["phase", "ending", "character"]


class NarrativeNodeError(RuntimeError):
    pass


def generate_narrative_node(
    *,
    job_dir: Path,
    llm_factory: Callable[..., OpenAIFunctionClient],
    kind: NarrativeNodeKind,
    user_prompt: str,
    narrative_plan: dict[str, Any],
) -> dict[str, Any]:
    try:
        try:
            llm = llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = llm_factory()
    except LLMError as exc:
        raise NarrativeNodeError(str(exc)) from exc

    kind_label = {"phase": "阶段", "ending": "结局", "character": "角色"}[kind]
    schema = narrative_node_schema(kind)
    prompt = (
        "这是我当前的故事设计大纲：\n"
        f"{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}\n\n"
        f"我要再添加一个{kind_label}，要求如下：\n{user_prompt.strip()}\n\n"
        f"把新添加的{kind_label}节点以严格的 JSON 格式返回给我。"
        "只返回 JSON，不要 Markdown，不要解释。\n"
        f"JSON 格式如下：\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )
    try:
        text = llm.call_text(
            f"narrative_node_{kind}",
            "你是互动叙事游戏大纲编辑器。你必须只返回合法 JSON，且结构必须匹配用户要求。",
            prompt,
        )
        parsed = llm.parse_json_text(text, f"narrative_node_{kind}")
    except LLMError as exc:
        raise NarrativeNodeError(str(exc)) from exc

    node = normalize_narrative_node(kind, parsed)
    validate_narrative_node(kind, node)
    return node


def narrative_node_schema(kind: NarrativeNodeKind) -> dict[str, Any]:
    if kind == "phase":
        return {
            "id": "phase4",
            "name": "阶段名称",
            "content": "这个阶段发生的关键事件、情绪变化和玩家选择。",
            "narrative_target": "这个阶段在叙事中的目标。",
            "strtype": "main",
        }
    if kind == "ending":
        return {
            "ending_type": "结局类型",
            "description": "结局描述。",
        }
    return {
        "id": "character_id",
        "name": "角色名",
        "gender": "性别或身份表达",
        "personality": "性格描述",
        "motivation": "角色动机",
        "speech_style": "说话方式",
        "emotional_arc": "情感变化",
        "relationships": [{"with": "existing_character_id", "dynamic": "关系动态"}],
    }


def normalize_narrative_node(kind: NarrativeNodeKind, parsed: dict[str, Any]) -> dict[str, Any]:
    wrapper_keys = {
        "phase": ["phase", "story_step", "story_progression"],
        "ending": ["ending", "endings"],
        "character": ["character", "characters"],
    }[kind]
    for key in wrapper_keys:
        value = parsed.get(key)
        if isinstance(value, dict):
            return value
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return parsed


def validate_narrative_node(kind: NarrativeNodeKind, node: dict[str, Any]) -> None:
    required = {
        "phase": ["id", "name", "content", "narrative_target", "strtype"],
        "ending": ["ending_type", "description"],
        "character": [
            "id",
            "name",
            "gender",
            "personality",
            "motivation",
            "speech_style",
            "emotional_arc",
            "relationships",
        ],
    }[kind]
    missing = [key for key in required if key not in node or node[key] in ("", None)]
    if missing:
        raise NarrativeNodeError(f"generated {kind} node is missing required fields: {', '.join(missing)}")
    if kind == "character" and not isinstance(node.get("relationships"), list):
        raise NarrativeNodeError("generated character node relationships must be a list")
