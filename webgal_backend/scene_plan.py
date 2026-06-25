from __future__ import annotations

import re
from typing import Any


def build_scene_plan(narrative_plan: dict[str, Any]) -> dict[str, Any]:
    scenes = []
    used_files: set[str] = set()
    for index, node in enumerate(narrative_plan.get("story_progression", [])):
        node_id = str(node.get("id") or f"phase{index}").strip()
        base_name = "start" if index == 0 else _safe_filename_stem(node_id or f"phase{index}")
        scene_file = _unique_filename(base_name, used_files)
        scenes.append(
            {
                "kind": "Scene",
                "scene_file": scene_file,
                "source_node": node_id,
                "source_index": index,
                "node_name": str(node.get("name") or "").strip(),
                "strtype": str(node.get("strtype") or "").strip(),
                "purpose": str(node.get("narrative_target") or "").strip(),
                "summary": str(node.get("content") or "").strip(),
            }
        )

    endings = []
    for index, ending in enumerate(narrative_plan.get("endings", []), start=1):
        ending_type = str(ending.get("ending_type") or f"ending_{index}").strip()
        scene_file = _unique_filename(f"ending_{index}", used_files)
        endings.append(
            {
                "kind": "Ending",
                "scene_file": scene_file,
                "ending_type": ending_type,
                "source_index": index - 1,
                "description": str(ending.get("description") or "").strip(),
            }
        )

    return {
        "version": 1,
        "scenes": scenes,
        "endings": endings,
        "required_scene_count": len(scenes) + len(endings),
    }


def scene_plan_coverage_text(scene_plan: dict[str, Any]) -> str:
    lines = [
        "game_design output must strictly follow scene_plan.json; do not merge, skip, or summarize required scenes:",
        "story_progression scenes:",
    ]
    for scene in scene_plan.get("scenes", []):
        lines.append(
            "- {source_node} ({node_name}, {strtype}): generate standalone {kind}:{scene_file}.".format(
                kind=scene.get("kind", "Scene"),
                scene_file=scene.get("scene_file", ""),
                source_node=scene.get("source_node", ""),
                node_name=scene.get("node_name", ""),
                strtype=scene.get("strtype", ""),
            )
        )
    lines.append("ending scenes:")
    for ending in scene_plan.get("endings", []):
        lines.append(
            "- {ending_type}: generate standalone {kind}:{scene_file}.".format(
                kind=ending.get("kind", "Ending"),
                scene_file=ending.get("scene_file", ""),
                ending_type=ending.get("ending_type", ""),
            )
        )
    lines.append(
        "minimum scene file count = {scene_count} story_progression Scene + {ending_count} Ending = {required_count}.".format(
            scene_count=len(scene_plan.get("scenes", [])),
            ending_count=len(scene_plan.get("endings", [])),
            required_count=scene_plan.get("required_scene_count", 0),
        )
    )
    return "\n".join(lines)

def expected_scene_files(scene_plan: dict[str, Any]) -> list[str]:
    return [
        str(item.get("scene_file", "")).strip()
        for item in [*scene_plan.get("scenes", []), *scene_plan.get("endings", [])]
        if str(item.get("scene_file", "")).strip()
    ]


def expected_source_nodes(scene_plan: dict[str, Any]) -> list[str]:
    return [
        str(scene.get("source_node", "")).strip()
        for scene in scene_plan.get("scenes", [])
        if str(scene.get("source_node", "")).strip()
    ]


def expected_ending_types(scene_plan: dict[str, Any]) -> list[str]:
    return [
        str(ending.get("ending_type", "")).strip()
        for ending in scene_plan.get("endings", [])
        if str(ending.get("ending_type", "")).strip()
    ]


def _safe_filename_stem(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    if not normalized:
        normalized = "scene"
    if not re.match(r"^[a-z]", normalized):
        normalized = "scene_" + normalized
    return normalized


def _unique_filename(stem: str, used_files: set[str]) -> str:
    clean_stem = _safe_filename_stem(stem)
    candidate = f"{clean_stem}.txt"
    suffix = 2
    while candidate in used_files:
        candidate = f"{clean_stem}_{suffix}.txt"
        suffix += 1
    used_files.add(candidate)
    return candidate

