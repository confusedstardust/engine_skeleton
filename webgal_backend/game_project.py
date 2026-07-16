from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from . import game_design


class GameProjectError(ValueError):
    pass


class EdgeKind(StrEnum):
    PLAYER_CHOICE = "PLAYER_CHOICE"
    AUTO_TRANSITION = "AUTO_TRANSITION"
    CONDITIONAL_TRANSITION = "CONDITIONAL_TRANSITION"
    CALL = "CALL"
    MERGE = "MERGE"
    ENDING = "ENDING"


class ProjectLine(BaseModel):
    model_config = ConfigDict(extra="allow")

    line_id: str
    kind: str
    speaker: str = ""
    text: str = ""
    raw_prefix: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ProjectScene(BaseModel):
    model_config = ConfigDict(extra="allow")

    scene_id: str
    scene_file: str
    marker: str = "Scene"
    title: str = ""
    source_node: str = ""
    ending_type: str = ""
    strtype: str = ""
    lines: list[ProjectLine] = Field(default_factory=list)


class SceneEdge(BaseModel):
    model_config = ConfigDict(extra="allow")

    edge_id: str
    source_scene_id: str
    target_scene_id: str
    kind: EdgeKind
    label: str = ""
    position: int = 0
    group_id: str = ""
    condition: str = ""
    order: int = 0


class GameProject(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: int = 1
    revision: int = 1
    scenes: list[ProjectScene]
    edges: list[SceneEdge] = Field(default_factory=list)
    topology_issues: list[str] = Field(default_factory=list)


def game_project_from_completed(
    completed: dict[str, Any],
    previous: GameProject | dict[str, Any] | None = None,
    *,
    strict: bool = True,
) -> GameProject:
    if not isinstance(completed, dict) or not isinstance(completed.get("scenes"), list):
        raise GameProjectError("completed game design must contain a scenes list")
    previous_project = _coerce_previous(previous)
    previous_by_file = {scene.scene_file: scene for scene in previous_project.scenes} if previous_project else {}

    raw_scenes = [scene for scene in completed["scenes"] if isinstance(scene, dict)]
    scene_files = [_scene_file(scene) for scene in raw_scenes]
    duplicates = [name for name, count in Counter(scene_files).items() if name and count > 1]
    if duplicates:
        raise GameProjectError("duplicate scene files: " + ", ".join(sorted(duplicates)))
    if any(not name for name in scene_files):
        raise GameProjectError("every scene must have a scene_file")

    scenes: list[ProjectScene] = []
    raw_by_scene_id: dict[str, dict[str, Any]] = {}
    for raw_scene, scene_file in zip(raw_scenes, scene_files):
        previous_scene = previous_by_file.get(scene_file)
        scene_id = str(raw_scene.get("scene_id") or "").strip()
        if not scene_id and previous_scene:
            scene_id = previous_scene.scene_id
        scene_id = scene_id or _stable_id("scene", scene_file)
        project_scene = ProjectScene(
            scene_id=scene_id,
            scene_file=scene_file,
            marker="Ending" if str(raw_scene.get("marker") or "").lower() == "ending" else "Scene",
            title=str(raw_scene.get("title") or scene_file.removesuffix(".txt")).strip(),
            source_node=str(raw_scene.get("source_node") or "").strip(),
            ending_type=str(raw_scene.get("ending_type") or "").strip(),
            strtype=str(raw_scene.get("strtype") or "").strip(),
            lines=[],
        )
        scenes.append(project_scene)
        raw_by_scene_id[scene_id] = raw_scene

    scene_id_by_file = {scene.scene_file: scene.scene_id for scene in scenes}
    edges: list[SceneEdge] = []
    for scene in scenes:
        raw_scene = raw_by_scene_id[scene.scene_id]
        previous_scene = previous_by_file.get(scene.scene_file)
        previous_lines = previous_scene.lines if previous_scene else []
        content_position = 0
        for raw_index, raw_line in enumerate(raw_scene.get("lines", [])):
            if not isinstance(raw_line, dict):
                continue
            explicit_line_id = str(raw_line.get("line_id") or raw_line.get("id") or "").strip()
            line_id = explicit_line_id or _previous_line_id(previous_lines, raw_line, content_position)
            line_id = line_id or _stable_id(
                "line",
                scene.scene_id,
                str(raw_index),
                json.dumps(raw_line, ensure_ascii=False, sort_keys=True),
            )
            kind = str(raw_line.get("kind") or "narration").strip()
            if kind == "choice":
                group_id = str(raw_line.get("group_id") or line_id).strip()
                for choice_index, choice in enumerate(raw_line.get("choices", [])):
                    if not isinstance(choice, dict):
                        continue
                    target_file = _target_file(choice)
                    target_id = scene_id_by_file.get(target_file)
                    if not target_id:
                        raise GameProjectError(f"unknown choice target: {scene.scene_file}->{target_file}")
                    label = str(choice.get("text") or "").strip()
                    edges.append(
                        SceneEdge(
                            edge_id=str(choice.get("edge_id") or "").strip()
                            or _stable_id("edge", scene.scene_id, target_id, group_id, str(choice_index)),
                            source_scene_id=scene.scene_id,
                            target_scene_id=target_id,
                            kind=EdgeKind.PLAYER_CHOICE,
                            label=label,
                            position=content_position,
                            group_id=group_id,
                            order=choice_index,
                        )
                    )
                continue

            transition = _transition_from_line(raw_line)
            if transition:
                transition_kind, target_file, condition = transition
                target_id = scene_id_by_file.get(target_file)
                if not target_id:
                    raise GameProjectError(f"unknown transition target: {scene.scene_file}->{target_file}")
                edges.append(
                    SceneEdge(
                        edge_id=str(raw_line.get("edge_id") or "").strip()
                        or _stable_id("edge", scene.scene_id, target_id, line_id),
                        source_scene_id=scene.scene_id,
                        target_scene_id=target_id,
                        kind=transition_kind,
                        position=content_position,
                        group_id=line_id,
                        condition=condition,
                    )
                )
                continue

            payload = dict(raw_line)
            payload.pop("id", None)
            payload.pop("line_id", None)
            scene.lines.append(
                ProjectLine(
                    line_id=line_id,
                    kind=kind,
                    speaker=str(raw_line.get("speaker") or ""),
                    text=str(raw_line.get("text") or ""),
                    raw_prefix=str(raw_line.get("rawPrefix") or raw_line.get("raw_prefix") or ""),
                    payload=payload,
                )
            )
            content_position += 1

    revision = int(completed.get("revision") or 1)
    project = GameProject(schema_version=1, revision=revision, scenes=scenes, edges=edges)
    if previous_project:
        previous_content = previous_project.model_dump(mode="json", exclude={"revision", "topology_issues"})
        current_content = project.model_dump(mode="json", exclude={"revision", "topology_issues"})
        project.revision = previous_project.revision + 1 if current_content != previous_content else previous_project.revision
    errors = game_project_topology_errors(project)
    project.topology_issues = errors
    if strict and errors:
        raise GameProjectError("invalid game project topology: " + ", ".join(errors))
    return project


def completed_from_game_project(project: GameProject | dict[str, Any]) -> dict[str, Any]:
    project = _coerce_project(project)
    scene_by_id = {scene.scene_id: scene for scene in project.scenes}
    edges_by_source: dict[str, list[SceneEdge]] = defaultdict(list)
    for edge in project.edges:
        edges_by_source[edge.source_scene_id].append(edge)

    completed_scenes: list[dict[str, Any]] = []
    for scene in project.scenes:
        lines = [_legacy_line(line) for line in scene.lines]
        grouped_edges: dict[tuple[int, str, EdgeKind], list[SceneEdge]] = defaultdict(list)
        for edge in edges_by_source.get(scene.scene_id, []):
            grouped_edges[(edge.position, edge.group_id, edge.kind)].append(edge)
        offset = 0
        for (position, group_id, kind), group in sorted(grouped_edges.items(), key=lambda item: (item[0][0], item[0][2].value, item[0][1])):
            insert_at = max(0, min(len(lines), position + offset))
            if kind == EdgeKind.PLAYER_CHOICE:
                control_line = {
                    "id": group_id or _stable_id("choice", scene.scene_id, str(position)),
                    "kind": "choice",
                    "speaker": "branch",
                    "text": "",
                    "rawPrefix": "choose",
                    "group_id": group_id,
                    "choices": [
                        {
                            "text": edge.label,
                            "target": scene_by_id[edge.target_scene_id].scene_file,
                            "target_scene_file": scene_by_id[edge.target_scene_id].scene_file,
                            "edge_id": edge.edge_id,
                        }
                        for edge in sorted(group, key=lambda item: item.order)
                    ],
                }
            else:
                edge = sorted(group, key=lambda item: item.order)[0]
                control_line = {
                    "id": group_id or edge.edge_id,
                    "kind": "transition",
                    "transition_kind": edge.kind.value,
                    "target_scene_file": scene_by_id[edge.target_scene_id].scene_file,
                    "condition": edge.condition,
                    "edge_id": edge.edge_id,
                }
            lines.insert(insert_at, control_line)
            offset += 1
        completed_scenes.append(
            {
                "scene_id": scene.scene_id,
                "marker": scene.marker,
                "scene_file": scene.scene_file,
                "source_node": scene.source_node,
                "ending_type": scene.ending_type,
                "title": scene.title,
                "strtype": scene.strtype,
                "lines": lines,
            }
        )
    return {"version": 2, "revision": project.revision, "scenes": completed_scenes}


def compile_game_project(
    project: GameProject | dict[str, Any],
    asset_operations: list[dict[str, Any]] | None = None,
) -> str:
    project = _coerce_project(project)
    completed = completed_from_game_project(project)
    operations_by_anchor: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for operation in asset_operations or []:
        if not isinstance(operation, dict):
            continue
        scene_id = str(operation.get("scene_id") or "").strip()
        line_id = str(operation.get("line_id") or "").strip()
        position = str(operation.get("position") or "before").strip()
        command = str(operation.get("command") or "").strip()
        if scene_id and command:
            operations_by_anchor[(scene_id, line_id, position)].append(command)
    chunks: list[str] = []
    for project_scene, scene in zip(project.scenes, completed["scenes"]):
        marker = "Ending" if str(scene.get("marker") or "").lower() == "ending" else "Scene"
        lines = [f"{marker}:{scene['scene_file']}"]
        lines.extend(operations_by_anchor.get((project_scene.scene_id, "", "scene_start"), []))
        for line in scene.get("lines", []):
            line_id = str(line.get("line_id") or line.get("id") or "").strip()
            lines.extend(operations_by_anchor.get((project_scene.scene_id, line_id, "before"), []))
            if line.get("kind") == "transition":
                target = str(line.get("target_scene_file") or "")
                transition_kind = str(line.get("transition_kind") or EdgeKind.AUTO_TRANSITION.value)
                condition = str(line.get("condition") or "").strip()
                if transition_kind == EdgeKind.CALL.value:
                    rendered = f"callScene:{target};"
                elif transition_kind == EdgeKind.CONDITIONAL_TRANSITION.value and condition:
                    rendered = f"if:{condition} -then=changeScene:{target};"
                else:
                    rendered = f"changeScene:{target};"
            else:
                rendered = game_design.render_scene_line(line)
            if rendered:
                lines.append(rendered)
            lines.extend(operations_by_anchor.get((project_scene.scene_id, line_id, "after"), []))
        lines.extend(operations_by_anchor.get((project_scene.scene_id, "", "scene_end"), []))
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def game_project_topology_errors(project: GameProject | dict[str, Any]) -> list[str]:
    project = _coerce_project(project)
    scene_ids = [scene.scene_id for scene in project.scenes]
    scene_files = [scene.scene_file for scene in project.scenes]
    valid_ids = set(scene_ids)
    endings = {scene.scene_id for scene in project.scenes if scene.marker.lower() == "ending"}
    errors: list[str] = []
    for value, count in Counter(scene_ids).items():
        if count > 1:
            errors.append(f"duplicate_scene_id:{value}")
    for value, count in Counter(scene_files).items():
        if count > 1:
            errors.append(f"duplicate_scene_file:{value}")
    line_ids = [line.line_id for scene in project.scenes for line in scene.lines]
    for value, count in Counter(line_ids).items():
        if count > 1:
            errors.append(f"duplicate_line_id:{value}")
    edge_ids = [edge.edge_id for edge in project.edges]
    for value, count in Counter(edge_ids).items():
        if count > 1:
            errors.append(f"duplicate_edge_id:{value}")

    outgoing: dict[str, set[str]] = defaultdict(set)
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in project.edges:
        if edge.source_scene_id not in valid_ids or edge.target_scene_id not in valid_ids:
            errors.append(f"unknown_edge_endpoint:{edge.edge_id}")
            continue
        if edge.kind == EdgeKind.PLAYER_CHOICE and not edge.label.strip():
            errors.append(f"empty_choice_label:{edge.edge_id}")
        outgoing[edge.source_scene_id].add(edge.target_scene_id)
        reverse[edge.target_scene_id].add(edge.source_scene_id)

    for ending in sorted(endings):
        if outgoing.get(ending):
            errors.append(f"ending_has_outgoing_edge:{ending}")
        if not reverse.get(ending):
            errors.append(f"orphan_ending:{ending}")
    for scene_id in sorted(valid_ids - endings):
        if not outgoing.get(scene_id):
            errors.append(f"dead_end_scene:{scene_id}")

    start = next((scene.scene_id for scene in project.scenes if scene.scene_file == "start.txt"), "")
    if not start:
        errors.append("missing_start_scene:start.txt")
        return errors
    reachable = {start}
    frontier = [start]
    while frontier:
        source = frontier.pop()
        for target in outgoing.get(source, set()):
            if target not in reachable:
                reachable.add(target)
                frontier.append(target)
    for scene_id in sorted(valid_ids - reachable):
        errors.append(f"unreachable_scene:{scene_id}")

    can_reach_ending = set(endings)
    frontier = list(endings)
    while frontier:
        target = frontier.pop()
        for source in reverse.get(target, set()):
            if source not in can_reach_ending:
                can_reach_ending.add(source)
                frontier.append(source)
    for scene_id in sorted((reachable - endings) - can_reach_ending):
        errors.append(f"no_ending_path:{scene_id}")
    return errors


def _legacy_line(line: ProjectLine) -> dict[str, Any]:
    payload = dict(line.payload)
    payload.update(
        {
            "id": line.line_id,
            "line_id": line.line_id,
            "kind": line.kind,
            "speaker": line.speaker,
            "text": line.text,
            "rawPrefix": line.raw_prefix,
        }
    )
    return payload


def _transition_from_line(line: dict[str, Any]) -> tuple[EdgeKind, str, str] | None:
    if str(line.get("kind") or "") == "transition":
        target = _target_file(line)
        raw_kind = str(line.get("transition_kind") or EdgeKind.AUTO_TRANSITION.value)
        try:
            kind = EdgeKind(raw_kind)
        except ValueError:
            kind = EdgeKind.AUTO_TRANSITION
        return (kind, target, str(line.get("condition") or "").strip()) if target else None
    rendered = game_design.render_scene_line(line)
    targets = game_design.scene_targets_from_line(rendered)
    if not targets:
        return None
    kind = EdgeKind.CALL if rendered.lower().startswith("callscene:") else EdgeKind.AUTO_TRANSITION
    return kind, targets[0], ""


def _target_file(value: dict[str, Any]) -> str:
    target = str(value.get("target_scene_file") or value.get("target") or "").strip()
    return target.replace("\\", "/").split("/")[-1]


def _scene_file(scene: dict[str, Any]) -> str:
    value = str(scene.get("scene_file") or scene.get("header") or "").strip()
    return value.replace("\\", "/").split("/")[-1]


def _previous_line_id(previous_lines: list[ProjectLine], raw_line: dict[str, Any], position: int) -> str:
    if position < len(previous_lines):
        previous = previous_lines[position]
        if previous.kind == str(raw_line.get("kind") or "narration"):
            return previous.line_id
    return ""


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


def _coerce_previous(value: GameProject | dict[str, Any] | None) -> GameProject | None:
    if value is None:
        return None
    return _coerce_project(value)


def _coerce_project(value: GameProject | dict[str, Any]) -> GameProject:
    if isinstance(value, GameProject):
        return value
    try:
        return GameProject.model_validate(value)
    except Exception as exc:
        raise GameProjectError(f"invalid game project: {exc}") from exc
