"""Read-only graph of the playable release, never the editable narrative plan."""
from collections import deque
from pathlib import Path
import re

from .storage import read_json
from .scene_validation import _parse_choose_options


def published_flow(job_dir: Path, revision: int = 0) -> dict:
    backup = job_dir / "state" / "published_game_backup" / "scene"
    root = backup if backup.is_dir() else job_dir / "public" / "game" / "scene"
    paths = sorted(root.glob("*.txt"), key=lambda p: (p.name != "start.txt", p.name))
    snapshot_path = job_dir / "state" / "published_game_design_completed.json"
    snapshot = read_json(snapshot_path) if snapshot_path.is_file() else {}
    metadata = {str(s.get("scene_file") or s.get("header") or ""): s for s in snapshot.get("scenes", [])}
    nodes, edges, warnings = [], [], []
    names = {p.name for p in paths}
    for path in paths:
        meta = metadata.get(path.name, {})
        scene_node = {"id": path.name, "label": meta.get("name") or meta.get("title") or path.stem,
                      "kind": "start" if path.name == "start.txt" else "ending" if meta.get("ending_type") or str(meta.get("marker", "")).lower() == "ending" or path.stem.startswith("ending_") else "scene"}
        nodes.append(scene_node)
        lines = [s.strip() for s in path.read_text(encoding="utf-8-sig").splitlines() if s.strip() and not s.strip().startswith("//")]
        labels = {m.group(1): i for i, line in enumerate(lines) if (m := re.fullmatch(r"label\s*:\s*([^;]+);", line))}
        internal_continuations, internal_loops, internal_loop_labels = set(), set(), set()
        queue, visited = deque([0]), set()
        while queue:
            index = queue.popleft()
            if index in visited or index >= len(lines):
                continue
            visited.add(index)
            line = lines[index]
            conditional = " -when=" in line
            jump = re.match(r"(changeScene|callScene)\s*:\s*([\w-]+\.txt)", line, re.I)
            options = _parse_choose_options(line) if line.startswith("choose:") else []
            routes = options or ([("调用场景" if jump.group(1).lower() == "callscene" else "", jump.group(2))] if jump else [])
            for text, target in routes:
                if target.endswith(".txt"):
                    if target not in names:
                        names.add(target)
                        nodes.append({"id": target, "label": target, "kind": "missing"})
                        warnings.append(f"跳转目标 {target} 不存在。")
                    existing = next((e for e in edges if e["source"] == path.name and e["target"] == target), None)
                    if existing:
                        if text and text not in existing["label"].split(" / "):
                            existing["label"] = " / ".join(filter(None, [existing["label"], text]))
                    else:
                        edges.append({"id": f"release-{len(edges)}", "source": path.name, "target": target, "label": text})
                elif target in labels:
                    route = (index, target)
                    if labels[target] <= index:
                        internal_loops.add(route)
                        internal_loop_labels.add(text.strip() or f"跳转到 {target}")
                    else:
                        internal_continuations.add(route)
                    queue.append(labels[target])
                else:
                    warnings.append(f"{path.name} 的分支目标 {target} 不存在。")
            local_jump = re.match(r"jumpLabel\s*:\s*([^;\s]+)", line)
            if local_jump and local_jump.group(1) in labels:
                target = local_jump.group(1)
                route = (index, target)
                if labels[target] <= index:
                    internal_loops.add(route)
                    internal_loop_labels.add(f"跳转到 {target}")
                else:
                    internal_continuations.add(route)
                queue.append(labels[target])
            terminal = bool(options) or bool(local_jump) or bool(jump and jump.group(1).lower() == "changescene") or line.lower() == "end;"
            if not terminal or conditional:
                queue.append(index + 1)
        if internal_continuations:
            scene_node["internalContinuationCount"] = len(internal_continuations)
        if internal_loops:
            scene_node["internalLoopCount"] = len(internal_loops)
            scene_node["internalLoopLabels"] = sorted(internal_loop_labels)
    return {"nodes": nodes, "edges": edges, "warnings": list(dict.fromkeys(warnings)), "revision": revision}
