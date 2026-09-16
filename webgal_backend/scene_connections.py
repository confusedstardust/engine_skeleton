from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

from .game_design import (
    ending_structure_ids,
    mermaid_edges,
    narrative_connectable_pairs,
    resolve_structure_ending,
    resolve_structure_scene,
)
from .scene_validation import _parse_choose_options, _split_unescaped
from .storage import read_json


def check_scene_connections(job_dir: Path) -> dict[str, Any]:
    """Connect unambiguous scene tails and verify routes from start.txt."""
    narrative_path = job_dir / "state" / "narrative_plan.json"
    scene_plan_path = job_dir / "state" / "scene_plan.json"
    if not narrative_path.exists() or not scene_plan_path.exists():
        return {"status": "failed", "checks": [], "fixes": [], "errors": [{"code": "missing_connection_inputs", "message": "narrative_plan.json and scene_plan.json are required for scene connection checking."}], "reachable": []}

    narrative = read_json(narrative_path)
    scene_plan = read_json(scene_plan_path)
    if not isinstance(narrative, dict) or not isinstance(scene_plan, dict):
        return {"status": "failed", "checks": [], "fixes": [], "errors": [{"code": "invalid_scene_plan", "message": "Narrative and scene plans must be JSON objects."}], "reachable": []}

    structure = str(narrative.get("narrative_structure") or "")
    edges = mermaid_edges(structure)
    if not edges:
        return {"status": "failed", "checks": [], "fixes": [], "errors": [{"code": "missing_flow_edges", "message": "The narrative flowchart has no readable scene connections."}], "reachable": []}

    expected_files = {
        str(item.get("scene_file") or "").strip()
        for item in [*scene_plan.get("scenes", []), *scene_plan.get("endings", [])]
        if isinstance(item, dict) and str(item.get("scene_file") or "").strip()
    }
    if "start.txt" not in expected_files:
        return {"status": "failed", "checks": [], "fixes": [], "errors": [{"code": "missing_start_plan", "message": "scene_plan.json must include start.txt."}], "reachable": []}
    ending_files = {
        str(item.get("scene_file") or "").strip()
        for item in scene_plan.get("endings", [])
        if isinstance(item, dict) and str(item.get("scene_file") or "").strip()
    }
    scene_by_node: dict[str, dict[str, Any]] = {}
    for item in scene_plan.get("scenes", []):
        if isinstance(item, dict) and str(item.get("source_node") or "").strip():
            node = str(item["source_node"]).strip()
            scene_by_node[node] = item
            scene_by_node[node.lower()] = item
    ending_by_node: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(scene_plan.get("endings", []), start=1):
        if isinstance(item, dict):
            for node in ending_structure_ids(item, index):
                ending_by_node[node] = item
                ending_by_node[node.lower()] = item
    graph_errors: list[dict[str, str]] = []
    for edge in edges:
        source = resolve_structure_scene(edge["source"], scene_by_node) or resolve_structure_ending(edge["source"], ending_by_node)
        target = resolve_structure_scene(edge["target"], scene_by_node) or resolve_structure_ending(edge["target"], ending_by_node)
        if not source or not target:
            graph_errors.append(_error("unmapped_flow_edge", edge["source"], f"Flowchart edge {edge['source']} → {edge['target']} has a node without a scene file."))
        elif str(source.get("scene_file") or "") in ending_files:
            graph_errors.append(_error("ending_has_outgoing_edge", str(source["scene_file"]), f"Ending should not jump to {edge['target']}."))
    expected_outgoing: dict[str, set[str]] = {name: set() for name in expected_files}
    for pair in narrative_connectable_pairs(narrative, scene_plan, {}):
        expected_outgoing.setdefault(str(pair["source_scene_file"]), set()).add(str(pair["target_scene_file"]))

    scene_dir = job_dir / "public" / "game" / "scene"
    actual_files = {path.name for path in scene_dir.glob("*.txt")}
    checks: list[dict[str, Any]] = []
    fixes: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = list(graph_errors)
    actual_outgoing: dict[str, set[str]] = {}
    pending_writes: dict[Path, list[str]] = {}
    for scene_file in sorted(actual_files - expected_files):
        errors.append(_error("unplanned_scene_file", scene_file, "Scene file is not listed in scene_plan.json."))

    for scene_file in sorted(expected_files):
        path = scene_dir / scene_file
        expected = expected_outgoing.get(scene_file, set())
        if scene_file not in actual_files:
            errors.append(_error("missing_scene_file", scene_file, "Expected scene file does not exist."))
            continue

        lines = path.read_text(encoding="utf-8").splitlines()
        last_index = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
        if last_index is None:
            errors.append(_error("empty_scene_file", scene_file, "Scene file is empty."))
            continue
        terminal = lines[last_index].strip()
        cleaned = re.sub(r"(?:&#x20;)+\s*$", "", terminal, flags=re.IGNORECASE).rstrip()
        if cleaned != terminal and cleaned.endswith(";"):
            lines[last_index] = cleaned
            pending_writes[path] = lines
            fixes.append({"code": "remove_html_space_after_command", "scene_file": scene_file, "line": last_index + 1})
            terminal = cleaned

        if scene_file in ending_files:
            if terminal.lower() != "end;":
                errors.append(_error("ending_not_closed", scene_file, "Ending scene must finish with end;."))
            actual_outgoing[scene_file] = set()
            checks.append({"scene_file": scene_file, "status": "ending", "targets": []})
            continue

        if not expected:
            errors.append(_error("missing_flow_edge", scene_file, "Flowchart does not identify the next scene."))
            actual_outgoing[scene_file] = set()
            continue

        if re.fullmatch(r"end\s*;", terminal, flags=re.IGNORECASE):
            errors.append(_error("premature_end", scene_file, "Scene ends before its planned next scene."))
            actual_outgoing[scene_file] = set()
            continue

        change = re.fullmatch(r"changeScene\s*:\s*([A-Za-z0-9_-]+\.txt)\s*;", terminal, flags=re.IGNORECASE)
        if change:
            targets = {change.group(1)}
        elif terminal.startswith("choose:"):
            if not terminal.endswith(";"):
                errors.append(_error("invalid_terminal_choice", scene_file, "Final choose command is missing its semicolon."))
                actual_outgoing[scene_file] = set()
                continue
            body = terminal[len("choose:") : -1]
            options = _parse_choose_options(terminal)
            raw_options = _split_unescaped(body, "|")
            if not options or len(options) != len(raw_options):
                errors.append(_error("invalid_terminal_choice", scene_file, "Final choose command has an invalid option."))
                actual_outgoing[scene_file] = set()
                continue
            if not all(re.fullmatch(r"[A-Za-z0-9_-]+\.txt", target) for _, target in options):
                errors.append(_error("local_choice_needs_review", scene_file, "Choices that jump to labels need branch-by-branch review."))
                actual_outgoing[scene_file] = set()
                continue
            targets = {target for _, target in options}
        else:
            if any(line.strip().startswith("choose:") for line in lines):
                errors.append(_error("local_choice_needs_review", scene_file, "A choice occurs before the scene tail; check every branch before adding a jump."))
                actual_outgoing[scene_file] = set()
                continue
            if len(expected) != 1:
                errors.append(_error("missing_branch_choice", scene_file, f"Flowchart has {len(expected)} next scenes; add a choose command for the branches."))
                actual_outgoing[scene_file] = set()
                continue
            target = next(iter(expected))
            lines.append(f"changeScene:{target};")
            pending_writes[path] = lines
            fixes.append({"code": "append_change_scene", "scene_file": scene_file, "target": target, "line": len(lines)})
            targets = {target}

        actual_outgoing[scene_file] = targets
        checks.append({"scene_file": scene_file, "status": "fixed" if fixes and fixes[-1].get("scene_file") == scene_file and fixes[-1]["code"] == "append_change_scene" else "connected", "targets": sorted(targets)})
        for target in sorted(targets - actual_files):
            errors.append(_error("missing_scene_reference", scene_file, f"Jump target does not exist: {target}"))
        if targets != expected:
            errors.append(_error("flow_target_mismatch", scene_file, f"Flowchart expects {sorted(expected)}; scene jumps to {sorted(targets)}."))

    reachable: set[str] = set()
    pending = deque(["start.txt"])
    while pending:
        scene_file = pending.popleft()
        if scene_file in reachable or scene_file not in actual_files:
            continue
        reachable.add(scene_file)
        pending.extend(actual_outgoing.get(scene_file, set()) - reachable)
    for scene_file in sorted(expected_files - reachable):
        errors.append(_error("unreachable_scene", scene_file, "Scene is not reachable from start.txt through checked scene jumps."))

    if not errors:
        for path, lines in pending_writes.items():
            path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return {
        "status": "failed" if errors else "passed",
        "checks": checks,
        "fixes": fixes if not errors else [],
        "suggested_fixes": fixes if errors else [],
        "errors": errors,
        "reachable": sorted(reachable),
        "expected_scene_count": len(expected_files),
    }


def _error(code: str, scene_file: str, message: str) -> dict[str, str]:
    return {"code": code, "scene_file": scene_file, "message": message}
