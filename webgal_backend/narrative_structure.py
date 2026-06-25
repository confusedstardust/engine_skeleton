from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from .llm import LLMError, OpenAIFunctionClient


class NarrativeStructureError(RuntimeError):
    pass


def narrative_structure_issues(narrative_plan: dict[str, Any]) -> list[dict[str, str]]:
    known_nodes = narrative_structure_known_nodes(narrative_plan)
    issues = []
    for node_id in narrative_structure_node_ids(str(narrative_plan.get("narrative_structure") or "")):
        if node_id not in known_nodes:
            issues.append({"node": node_id, "reason": "not found in story_progression or endings"})
    return issues


def narrative_structure_known_nodes(narrative_plan: dict[str, Any]) -> set[str]:
    known: set[str] = set()
    for phase in narrative_plan.get("story_progression", []):
        if not isinstance(phase, dict):
            continue
        for key in ("id", "name"):
            value = str(phase.get(key) or "").strip()
            if value:
                known.add(value)
                known.add(safe_mermaid_id(value))

    for index, ending in enumerate(narrative_plan.get("endings", []), start=1):
        if not isinstance(ending, dict):
            continue
        ending_type = str(ending.get("ending_type") or "").strip()
        if not ending_type:
            continue
        known.update(ending_structure_ids(ending_type, index))
    return {node for node in known if node}


def narrative_structure_node_ids(narrative_structure: str) -> list[str]:
    nodes: list[str] = []
    seen: set[str] = set()
    for source, target in mermaid_edge_node_pairs(narrative_structure):
        for node in (source, target):
            if node not in seen:
                seen.add(node)
                nodes.append(node)

    for node in mermaid_standalone_nodes(narrative_structure):
        if node not in seen:
            seen.add(node)
            nodes.append(node)
    return nodes


def repair_narrative_structure_if_needed(
    *,
    narrative_plan: dict[str, Any],
    job_dir: Path,
    llm_factory: Callable[..., OpenAIFunctionClient],
) -> dict[str, Any]:
    issues = narrative_structure_issues(narrative_plan)
    if not issues:
        return narrative_plan

    try:
        try:
            llm = llm_factory(trace_dir=job_dir / "state" / "llm_traces")
        except TypeError:
            llm = llm_factory()
    except LLMError as exc:
        raise NarrativeStructureError(str(exc)) from exc

    prompt = repair_prompt(narrative_plan, issues)
    try:
        text = llm.call_text(
            "repair_narrative_structure",
            "你是互动叙事大纲结构校对器。你只能修正 narrative_structure，并且必须返回严格 JSON。",
            prompt,
            thinking="disabled",
        )
        parsed = llm.parse_json_text(text, "repair_narrative_structure")
    except LLMError as exc:
        raise NarrativeStructureError(str(exc)) from exc

    repaired_structure = extract_repaired_structure(parsed)
    repaired_plan = dict(narrative_plan)
    repaired_plan["narrative_structure"] = repaired_structure

    remaining = narrative_structure_issues(repaired_plan)
    if remaining:
        raise NarrativeStructureError(
            "repaired narrative_structure still references unknown nodes: "
            + ", ".join(issue["node"] for issue in remaining)
        )
    return repaired_plan


def repair_prompt(narrative_plan: dict[str, Any], issues: list[dict[str, str]]) -> str:
    valid_story_nodes = [
        {"id": phase.get("id"), "name": phase.get("name")}
        for phase in narrative_plan.get("story_progression", [])
        if isinstance(phase, dict)
    ]
    valid_endings = [
        {"ending_type": ending.get("ending_type"), "mermaid_id": safe_mermaid_id(str(ending.get("ending_type") or ""))}
        for ending in narrative_plan.get("endings", [])
        if isinstance(ending, dict)
    ]
    return f"""这是当前生成的完整 narrative_plan.json:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

检查发现 narrative_structure 中有节点不存在于 story_progression 或 endings:
{json.dumps(issues, ensure_ascii=False, indent=2)}

可用 story_progression 节点:
{json.dumps(valid_story_nodes, ensure_ascii=False, indent=2)}

可用 endings 节点:
{json.dumps(valid_endings, ensure_ascii=False, indent=2)}

请只修改 narrative_structure,不要修改 story_progression、characters、endings 或其他字段。
要求:
- story_progression 节点必须使用 story_progression[].id。
- ending 节点可以使用 endings[].ending_type 的 Mermaid 安全 id,例如 true ending 可写成 true_ending[true ending]。
- 不要创造不存在的新阶段或新结局。
- 返回严格 JSON,不要 Markdown,格式如下:
{{
  "narrative_structure": "flowchart TD\\n  phase0 --> phase1\\n  phase1 --> true_ending[true ending]"
}}"""


def extract_repaired_structure(parsed: dict[str, Any]) -> str:
    candidates = [
        parsed.get("narrative_structure"),
        parsed.get("narrativeStructure"),
        parsed.get("structure"),
    ]
    if isinstance(parsed.get("narrative_plan"), dict):
        candidates.append(parsed["narrative_plan"].get("narrative_structure"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    raise NarrativeStructureError("repair_narrative_structure must return a narrative_structure string")


def build_synced_narrative_structure(narrative_plan: dict[str, Any]) -> str:
    """Build a complete Mermaid flowchart from the current outline.

    This deterministic sync is used after users edit stages/endings so the
    visible outline graph never references stale nodes.
    """
    phases = [
        phase
        for phase in narrative_plan.get("story_progression", [])
        if isinstance(phase, dict) and str(phase.get("id") or "").strip()
    ]
    endings = [
        ending
        for ending in narrative_plan.get("endings", [])
        if isinstance(ending, dict) and str(ending.get("ending_type") or "").strip()
    ]

    lines = ["flowchart TD"]
    for index, phase in enumerate(phases):
        node_id = safe_mermaid_id(str(phase.get("id") or f"phase{index}"))
        label = _mermaid_label(str(phase.get("name") or phase.get("id") or f"\u9636\u6bb5 {index + 1}"))
        lines.append(f'  {node_id}["{label}"]')

    for index, ending in enumerate(endings, start=1):
        ending_type = str(ending.get("ending_type") or f"ending_{index}")
        node_id = safe_mermaid_id(ending_type) or f"ending_{index}"
        label = _mermaid_label(f"\u7ed3\u5c40\uff1a{ending_type}")
        lines.append(f'  {node_id}["{label}"]')

    for previous, current in zip(phases, phases[1:]):
        source = safe_mermaid_id(str(previous.get("id") or ""))
        target = safe_mermaid_id(str(current.get("id") or ""))
        if source and target:
            lines.append(f"  {source} --> {target}")

    if phases and endings:
        source = safe_mermaid_id(str(phases[-1].get("id") or ""))
        for index, ending in enumerate(endings, start=1):
            target = safe_mermaid_id(str(ending.get("ending_type") or "")) or f"ending_{index}"
            if source and target:
                lines.append(f"  {source} --> {target}")

    if len(lines) == 1:
        lines.append('  outline["\u6545\u4e8b\u5927\u7eb2"]')
    return "\n".join(lines)


def _mermaid_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()


def mermaid_edge_node_pairs(narrative_structure: str) -> list[tuple[str, str]]:
    node = r"[A-Za-z_][A-Za-z0-9_-]*"
    shape = r"(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?"
    edge_re = re.compile(
        rf"(?P<source>{node}){shape}\s*(?:-->|==>|-\.->)\s*(?:\|[^|]+\|\s*)?(?P<target>{node}){shape}"
    )
    pairs = []
    for line in narrative_structure.splitlines():
        cleaned = line.strip().rstrip(";")
        if not cleaned or cleaned.startswith(("%%", "#")):
            continue
        for match in edge_re.finditer(cleaned):
            pairs.append((match.group("source").strip(), match.group("target").strip()))
    return pairs


def mermaid_standalone_nodes(narrative_structure: str) -> list[str]:
    node_re = re.compile(r"^\s*(?P<node>[A-Za-z_][A-Za-z0-9_-]*)\s*(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?\s*$")
    nodes = []
    for line in narrative_structure.splitlines():
        cleaned = line.strip().rstrip(";")
        if not cleaned or cleaned.startswith(("%%", "#")) or "-->" in cleaned or "==>" in cleaned or "-.->" in cleaned:
            continue
        match = node_re.match(cleaned)
        if match:
            node = match.group("node")
            if node not in MERMAID_KEYWORDS:
                nodes.append(node)
    return nodes


def ending_structure_ids(ending_type: str, index: int) -> set[str]:
    identifiers = {ending_type, safe_mermaid_id(ending_type), f"ending_{index}"}
    normalized = ending_type.lower()
    if "true" in normalized or "真" in ending_type:
        identifiers.add("true_ending")
    if "normal" in normalized or "普通" in ending_type:
        identifiers.add("normal_ending")
    if "branch" in normalized or "分支" in ending_type:
        identifiers.add("branch_ending")
    if "hidden" in normalized or "隐藏" in ending_type or "隱藏" in ending_type:
        identifiers.add("hidden_ending")
    return {item for item in identifiers if item}


def safe_mermaid_id(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_")
    if not label:
        return ""
    if not re.match(r"^[A-Za-z_]", label):
        label = f"node_{label}"
    return label


MERMAID_KEYWORDS = {
    "flowchart",
    "graph",
    "TD",
    "TB",
    "BT",
    "RL",
    "LR",
    "subgraph",
    "end",
}
