from __future__ import annotations

from collections import defaultdict
from typing import Any

from .game_project import GameProject, completed_from_game_project


ALLOWED_OPERATION_TYPES = {"background", "figure", "clear_figure"}
ALLOWED_POSITIONS = {"scene_start", "before", "after", "scene_end"}
ALLOWED_SLOTS = {"left", "center", "right"}


def normalize_asset_operations(
    payload: dict[str, Any],
    project: GameProject,
    *,
    background_assets: list[str],
    figure_assets: list[str],
    max_per_scene: int = 12,
    max_total: int = 100,
) -> dict[str, Any]:
    raw_operations = payload.get("operations", [])
    if not isinstance(raw_operations, list):
        return {"operations": [], "rejected": [{"reason": "operations_must_be_a_list"}]}

    completed = completed_from_game_project(project)
    scene_by_id = {scene.scene_id: scene for scene in project.scenes}
    scene_id_by_file = {scene.scene_file: scene.scene_id for scene in project.scenes}
    line_ids_by_scene: dict[str, set[str]] = defaultdict(set)
    for project_scene, legacy_scene in zip(project.scenes, completed["scenes"]):
        for line in legacy_scene.get("lines", []):
            line_id = str(line.get("line_id") or line.get("id") or "").strip()
            if line_id:
                line_ids_by_scene[project_scene.scene_id].add(line_id)

    allowed_backgrounds = set(background_assets)
    allowed_figures = set(figure_assets)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    per_scene: dict[str, int] = defaultdict(int)
    seen: set[tuple[str, str, str, str]] = set()

    for index, raw in enumerate(raw_operations):
        if len(accepted) >= max_total:
            rejected.append({"index": index, "reason": "max_total_exceeded"})
            continue
        if not isinstance(raw, dict):
            rejected.append({"index": index, "reason": "operation_must_be_an_object"})
            continue
        scene_id = str(raw.get("scene_id") or "").strip()
        if not scene_id:
            scene_id = scene_id_by_file.get(str(raw.get("scene_file") or "").strip(), "")
        if scene_id not in scene_by_id:
            rejected.append({"index": index, "reason": "unknown_scene"})
            continue
        if per_scene[scene_id] >= max_per_scene:
            rejected.append({"index": index, "reason": "max_per_scene_exceeded", "scene_id": scene_id})
            continue

        operation_type = str(raw.get("type") or "").strip().lower()
        if operation_type not in ALLOWED_OPERATION_TYPES:
            rejected.append({"index": index, "reason": "unsupported_type", "scene_id": scene_id})
            continue
        line_id = str(raw.get("line_id") or "").strip()
        position = str(raw.get("position") or ("before" if line_id else "scene_start")).strip().lower()
        if position not in ALLOWED_POSITIONS:
            rejected.append({"index": index, "reason": "unsupported_position", "scene_id": scene_id})
            continue
        if position in {"before", "after"} and line_id not in line_ids_by_scene[scene_id]:
            rejected.append({"index": index, "reason": "unknown_line", "scene_id": scene_id, "line_id": line_id})
            continue
        if position in {"scene_start", "scene_end"}:
            line_id = ""

        asset = str(raw.get("asset") or "").strip()
        slot = str(raw.get("slot") or "center").strip().lower()
        if slot not in ALLOWED_SLOTS:
            slot = "center"
        if operation_type == "background":
            if asset not in allowed_backgrounds:
                rejected.append({"index": index, "reason": "unknown_background_asset", "asset": asset})
                continue
            command = f"changeBg:{asset} -next;"
        elif operation_type == "figure":
            if asset not in allowed_figures:
                rejected.append({"index": index, "reason": "unknown_figure_asset", "asset": asset})
                continue
            command = f"changeFigure:{asset} -{slot} -next;"
        else:
            command = f"changeFigure:none -{slot};"

        marker = (scene_id, line_id, position, command)
        if marker in seen:
            rejected.append({"index": index, "reason": "duplicate_operation", "scene_id": scene_id})
            continue
        seen.add(marker)
        accepted.append(
            {
                "scene_id": scene_id,
                "scene_file": scene_by_id[scene_id].scene_file,
                "line_id": line_id,
                "position": position,
                "type": operation_type,
                "asset": asset,
                "slot": slot,
                "command": command,
            }
        )
        per_scene[scene_id] += 1
    return {"operations": accepted, "rejected": rejected}
