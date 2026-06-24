from __future__ import annotations

import json
import re
from typing import Any


class GameDesignError(ValueError):
    pass


def text_to_json(
    game_design_text: str,
    narrative_plan: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    meta_by_file: dict[str, dict[str, Any]] = {}
    for scene in scene_plan.get("scenes", []):
        scene_file = str(scene.get("scene_file") or "").strip()
        source_node = str(scene.get("source_node") or "").strip()
        meta_by_file[scene_file] = {
            "marker": "Scene",
            "source_node": source_node,
            "ending_type": "",
            "title": str(scene.get("node_name") or source_node or scene_file).strip(),
            "strtype": str(scene.get("strtype") or "").strip(),
        }
    for ending in scene_plan.get("endings", []):
        scene_file = str(ending.get("scene_file") or "").strip()
        ending_type = str(ending.get("ending_type") or "").strip()
        meta_by_file[scene_file] = {
            "marker": "Ending",
            "source_node": "",
            "ending_type": ending_type,
            "title": f"结局：{ending_type}" if ending_type else scene_file,
            "strtype": "",
        }

    scenes = []
    matches = scene_header_matches(game_design_text)
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(game_design_text)
        scene_file = match.group("filename").replace("\\", "/").split("/")[-1]
        meta = dict(meta_by_file.get(scene_file, {}))
        marker = meta.get("marker") or ("Ending" if str(match.group("kind") or "").lower() == "ending" else "Scene")
        lines = []
        source_node = str(meta.get("source_node") or "").strip()
        ending_type = str(meta.get("ending_type") or "").strip()
        for line_index, raw_line in enumerate(game_design_text[body_start:body_end].strip().splitlines()):
            stripped = raw_line.strip()
            if not stripped:
                continue
            source_match = internal_metadata_match(stripped, "source_node")
            if source_match:
                source_node = source_match
                continue
            ending_match = internal_metadata_match(stripped, "ending_type")
            if ending_match:
                ending_type = ending_match
                continue
            parsed_line = parse_line(stripped, f"{scene_file}-{line_index}")
            if parsed_line:
                lines.append(parsed_line)
        if source_node and not meta.get("strtype"):
            meta["strtype"] = story_step_strtype(narrative_plan, source_node)
        scenes.append(
            {
                "marker": marker,
                "scene_file": scene_file,
                "source_node": source_node,
                "ending_type": ending_type,
                "title": meta.get("title") or scene_file.replace(".txt", "").replace("_", " "),
                "strtype": meta.get("strtype") or "",
                "lines": lines,
            }
        )
    return {"version": 1, "scenes": scenes}


def parse_line(line: str, line_id: str) -> dict[str, Any] | None:
    original = line.strip()
    if not original:
        return None
    if original.lower().startswith("choose:") or original.startswith("choose："):
        body = original.split(":", 1)[1] if ":" in original else original.split("：", 1)[1]
        return {
            "id": line_id,
            "kind": "choice",
            "speaker": "分支",
            "text": "",
            "rawPrefix": "choose",
            "choices": parse_choice_options(body),
        }
    if original.startswith(":") and len(original) > 1 and is_branch_label(original[1:].strip().rstrip(";")):
        label = original[1:].strip().rstrip(";")
        return {"id": line_id, "kind": "branch", "speaker": "分支", "text": label, "rawPrefix": "branch", "branchLabel": label}
    trimmed = original[1:].strip() if original.startswith(">") else original

    narration = re.match(r"^(旁白|intro)\s*[:：]\s*(.*?);?$", trimmed)
    if narration:
        prefix = narration.group(1)
        return {
            "id": line_id,
            "kind": "narration",
            "speaker": "旁白",
            "text": clean_line_text(narration.group(2)),
            "rawPrefix": "intro" if prefix == "intro" else "旁白",
        }
    dialogue = re.match(r"^([^:：;]{1,24})[:：]\s*(.*?);?$", trimmed)
    if dialogue and not trimmed.startswith(("setVar", "change", "choose")):
        return {
            "id": line_id,
            "kind": "dialogue",
            "speaker": dialogue.group(1).strip(),
            "text": clean_line_text(dialogue.group(2)),
            "rawPrefix": "",
        }
    return {"id": line_id, "kind": "narration", "speaker": "旁白", "text": clean_line_text(trimmed), "rawPrefix": "intro"}


def render_json(game_design_json: dict[str, Any]) -> str:
    chunks = []
    for scene in game_design_json.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_file = str(scene.get("scene_file") or scene.get("header") or "").strip()
        if not scene_file:
            continue
        marker = "Ending" if str(scene.get("marker") or "").lower() == "ending" else "Scene"
        lines = [f"{marker}:{scene_file}"]
        for line in scene.get("lines", []):
            if isinstance(line, dict):
                rendered = render_scene_line(line)
                if rendered:
                    lines.append(rendered)
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks)


def render_scene_line(line: dict[str, Any]) -> str:
    kind = str(line.get("kind") or "narration")
    if kind == "choice":
        choices = []
        for choice in line.get("choices", []):
            if not isinstance(choice, dict):
                continue
            text = str(choice.get("text") or "").strip().replace("|", " ")
            target = str(choice.get("target") or "").strip().replace("|", "_")
            if text and target:
                choices.append(f"{text}:{target}")
        return f"choose:{'|'.join(choices)};" if choices else ""
    if kind == "branch":
        label = str(line.get("branchLabel") or line.get("text") or "").strip()
        if is_branch_label(label):
            return f":{label}"
        text = clean_line_text(label)
        return f"旁白:{text};" if text else ""
    text = str(line.get("text") or "").strip().rstrip(";")
    if not text:
        return ""
    if kind == "dialogue":
        speaker = str(line.get("speaker") or "角色").strip()
        return f"{speaker}:{text};"
    prefix = "intro" if str(line.get("rawPrefix") or "") == "intro" else "旁白"
    return f"{prefix}:{text};"


def extract_outline(
    game_design_json: dict[str, Any],
    narrative_plan: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    sections = {
        str(scene.get("scene_file") or "").strip(): "\n".join(
            render_scene_line(line)
            for line in scene.get("lines", [])
            if isinstance(line, dict) and render_scene_line(line)
        )
        for scene in game_design_json.get("scenes", [])
        if isinstance(scene, dict)
    }
    scenes = []
    for scene in scene_plan.get("scenes", []):
        scene_file = str(scene.get("scene_file") or "").strip()
        scenes.append(
            {
                "scene_file": scene_file,
                "scene_name": str(scene.get("source_node") or "").strip(),
                "content": sections.get(scene_file, ""),
                "strtype": str(scene.get("strtype") or "").strip(),
            }
        )
    endings = []
    for ending in scene_plan.get("endings", []):
        ending_file = str(ending.get("scene_file") or "").strip()
        endings.append(
            {
                "ending_file": ending_file,
                "ending_type": str(ending.get("ending_type") or "").strip(),
                "content": sections.get(ending_file, ""),
            }
        )
    return {
        "scene": scenes,
        "endings": endings,
        "connectable_pairs": narrative_connectable_pairs(narrative_plan, scene_plan, sections),
        "narrative_structure": str(narrative_plan.get("narrative_structure") or ""),
    }


def narrative_connectable_pairs(
    narrative_plan: dict[str, Any],
    scene_plan: dict[str, Any],
    sections: dict[str, str],
) -> list[dict[str, Any]]:
    scene_by_node: dict[str, dict[str, Any]] = {}
    for scene in scene_plan.get("scenes", []):
        source_node = str(scene.get("source_node") or "").strip()
        if source_node:
            scene_by_node[source_node] = scene
            scene_by_node[source_node.lower()] = scene

    ending_by_node: dict[str, dict[str, Any]] = {}
    for index, ending in enumerate(scene_plan.get("endings", []), start=1):
        for key in ending_structure_ids(ending, index):
            ending_by_node[key] = ending
            ending_by_node[key.lower()] = ending

    pairs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge_index, edge in enumerate(mermaid_edges(str(narrative_plan.get("narrative_structure") or "")), start=1):
        source_scene = resolve_structure_scene(edge["source"], scene_by_node)
        target_scene = resolve_structure_scene(edge["target"], scene_by_node)
        target_ending = resolve_structure_ending(edge["target"], ending_by_node)
        target_item = target_scene or target_ending
        if not source_scene or not target_item:
            continue
        source_file = str(source_scene.get("scene_file") or "").strip()
        target_file = str(target_item.get("scene_file") or "").strip()
        if not source_file or not target_file or source_file == target_file:
            continue
        signature = (source_file, target_file, str(edge.get("label") or ""))
        if signature in seen:
            continue
        seen.add(signature)
        pairs.append(
            {
                "id": f"{source_file.removesuffix('.txt')}_to_{target_file.removesuffix('.txt')}_{edge_index}",
                "source_node": str(source_scene.get("source_node") or edge["source"]).strip(),
                "source_scene_file": source_file,
                "source_title": str(source_scene.get("node_name") or "").strip(),
                "source_strtype": str(source_scene.get("strtype") or "").strip(),
                "source_content": sections.get(source_file, ""),
                "target_node": str(target_scene.get("source_node") or edge["target"]).strip()
                if target_scene
                else str(target_ending.get("ending_type") or edge["target"]).strip(),
                "target_scene_file": target_file,
                "target_title": str((target_scene.get("node_name") if target_scene else target_ending.get("ending_type")) or "").strip(),
                "target_kind": "Ending" if target_ending else "Scene",
                "target_strtype": str(target_scene.get("strtype") or "").strip() if target_scene else "",
                "target_content": sections.get(target_file, ""),
                "relationship_label": str(edge.get("label") or "").strip(),
            }
        )
    return pairs


def normalize_choices(
    parsed: dict[str, Any],
    scene_plan: dict[str, Any],
    game_design_outline: dict[str, Any],
) -> dict[str, Any]:
    valid_files = {
        str(item.get("scene_file") or item.get("ending_file") or "").strip()
        for item in [*game_design_outline.get("scene", []), *game_design_outline.get("endings", [])]
        if str(item.get("scene_file") or item.get("ending_file") or "").strip()
    }
    line_counts = {
        str(item.get("scene_file") or item.get("ending_file") or "").strip(): len(str(item.get("content") or "").splitlines())
        for item in [*game_design_outline.get("scene", []), *game_design_outline.get("endings", [])]
    }
    raw_groups = parsed.get("choices_group", parsed.get("choice_groups", []))
    if not isinstance(raw_groups, list):
        raise GameDesignError("game_design_choices must contain a choices_group list")

    normalized_groups = []
    for group_index, group in enumerate(raw_groups, start=1):
        if not isinstance(group, dict):
            continue
        scene_file = str(group.get("scene_file") or "").strip()
        if scene_file not in valid_files:
            continue
        try:
            insert_index = int(group.get("insert_index", 0))
        except (TypeError, ValueError):
            insert_index = 0
        insert_index = max(0, min(insert_index, line_counts.get(scene_file, 0)))

        choices = []
        for choice in group.get("choices", []):
            if isinstance(choice, dict):
                text = str(choice.get("text") or "").strip()
                target_scene_file = str(
                    choice.get("target_scene_file") or choice.get("targetSceneFile") or group.get("target_scene_file") or ""
                ).strip()
                target = str(choice.get("target") or target_scene_file or "").strip()
            else:
                text = str(choice or "").strip()
                target_scene_file = str(group.get("target_scene_file") or "").strip()
                target = target_scene_file
            if not text:
                continue
            if target_scene_file and target_scene_file not in valid_files:
                target_scene_file = ""
                target = ""
            choices.append({"text": text, "target": target, "target_scene_file": target_scene_file})

        if choices:
            normalized_choices: list[str | dict[str, str]] = []
            for choice in choices[:3]:
                if choice["target_scene_file"]:
                    normalized_choices.append(
                        {
                            "text": choice["text"],
                            "target": choice["target"],
                            "target_scene_file": choice["target_scene_file"],
                        }
                    )
                else:
                    normalized_choices.append(choice["text"])
            normalized_groups.append(
                {
                    "id": str(group.get("id") or f"{scene_file.replace('.txt', '')}_choice_{group_index}"),
                    "scene_file": scene_file,
                    "insert_index": insert_index,
                    "content": str(group.get("content") or "").strip(),
                    "target_scene_file": str(group.get("target_scene_file") or "").strip(),
                    "choices": normalized_choices,
                }
            )

    if not normalized_groups and scene_plan.get("required_scene_count", 0) > 1:
        raise GameDesignError("game_design_choices did not contain any valid choices_group")
    return {"choices_group": normalized_groups}


def apply_choices_to_json(game_design_json: dict[str, Any], choices_payload: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(game_design_json, ensure_ascii=False))
    groups_by_file: dict[str, list[dict[str, Any]]] = {}
    for group in choices_payload.get("choices_group", choices_payload.get("choice_groups", [])):
        if isinstance(group, dict):
            scene_file = str(group.get("scene_file") or "").strip()
            if scene_file:
                groups_by_file.setdefault(scene_file, []).append(group)

    for scene in result.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_file = str(scene.get("scene_file") or "").strip()
        groups = groups_by_file.get(scene_file, [])
        if not groups:
            continue
        lines = list(scene.get("lines", []))
        for group in sorted(groups, key=lambda item: int(item.get("insert_index", 0) or 0), reverse=True):
            try:
                insert_index = int(group.get("insert_index", 0))
            except (TypeError, ValueError):
                insert_index = 0
            insert_index = max(0, min(insert_index, len(lines)))
            rendered = choice_group_to_scene_lines(group)
            if rendered:
                lines[insert_index:insert_index] = rendered
        scene["lines"] = lines
    return result


def choice_group_to_scene_lines(group: dict[str, Any]) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    group_id = safe_branch_label(str(group.get("id") or "choice"))
    content = str(group.get("content") or "").strip()
    if content:
        lines.append({"id": f"{group_id}_content", "kind": "narration", "speaker": "旁白", "text": content, "rawPrefix": "旁白"})

    choices = []
    for choice_index, choice in enumerate(group.get("choices", []), start=1):
        if isinstance(choice, dict):
            text = str(choice.get("text") or "").strip()
            target_scene_file = str(choice.get("target_scene_file") or choice.get("targetSceneFile") or "").strip()
            target = str(choice.get("target") or target_scene_file or "").strip()
        else:
            text = str(choice or "").strip()
            target_scene_file = ""
            target = ""
        if not text:
            continue
        target_value = target_scene_file or safe_branch_label(target) or f"{group_id}_{choice_index}"
        choices.append({"text": text, "target": target_value, "target_scene_file": target_scene_file})
    if not choices:
        return lines

    lines.append({"id": f"{group_id}_choose", "kind": "choice", "speaker": "分支", "text": "", "rawPrefix": "choose", "choices": choices})
    for choice in choices:
        if choice.get("target_scene_file"):
            continue
        target = choice["target"]
        lines.append({"id": f"{target}_label", "kind": "branch", "speaker": "分支", "text": target, "rawPrefix": "branch", "branchLabel": target})
        lines.append({"id": f"{target}_body", "kind": "narration", "speaker": "旁白", "text": choice["text"], "rawPrefix": "旁白"})
    return lines


def apply_choices_to_text(game_design_text: str, choices_payload: dict[str, Any]) -> str:
    groups_by_location: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for group in choices_payload.get("choices_group", choices_payload.get("choice_groups", [])):
        if not isinstance(group, dict):
            continue
        scene_file = str(group.get("scene_file") or "").strip()
        try:
            insert_index = int(group.get("insert_index", 0))
        except (TypeError, ValueError):
            insert_index = 0
        groups_by_location.setdefault(scene_file, {}).setdefault(insert_index, []).append(group)

    matches = scene_header_matches(game_design_text)
    if not matches:
        return game_design_text

    chunks = []
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(game_design_text)
        header = format_scene_header(match.group("filename"))
        filename = match.group("filename").replace("\\", "/").split("/")[-1]
        body_lines = [
            line.rstrip()
            for line in game_design_text[body_start:body_end].strip().splitlines()
            if not is_internal_scene_metadata(line)
        ]
        for insert_index, groups in sorted(groups_by_location.get(filename, {}).items(), reverse=True):
            rendered_groups = []
            for group in groups:
                rendered = render_choice_group(group)
                if rendered:
                    rendered_groups.extend(rendered)
            if rendered_groups:
                body_lines[insert_index:insert_index] = rendered_groups
        chunks.append("\n".join([header, *body_lines]).rstrip())
    return "\n\n".join(chunks)


def game_design_sections(text: str) -> dict[str, str]:
    matches = scene_header_matches(text)
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        filename = match.group("filename").replace("\\", "/").split("/")[-1]
        lines = [line.rstrip() for line in text[body_start:body_end].strip().splitlines() if not is_internal_scene_metadata(line)]
        sections[filename] = "\n".join(lines).strip()
    return sections


def parse_choice_options(text: str) -> list[dict[str, str]]:
    choices = []
    for part in text.strip().rstrip(";").split("|"):
        item = part.strip()
        if not item or ":" not in item:
            continue
        choice_text, target = item.rsplit(":", 1)
        choice_text = choice_text.strip()
        target = target.strip()
        if choice_text and target:
            choices.append({"text": choice_text, "target": target})
    return choices


def render_choice_group(group: dict[str, Any]) -> list[str]:
    choices = []
    group_id = safe_branch_label(str(group.get("id") or "choice"))
    for choice_index, choice in enumerate(group.get("choices", []), start=1):
        if isinstance(choice, dict):
            text = str(choice.get("text") or "").strip()
            target_scene_file = str(choice.get("target_scene_file") or choice.get("targetSceneFile") or "").strip()
            target = str(choice.get("target") or target_scene_file or "").strip()
        else:
            text = str(choice or "").strip()
            target_scene_file = ""
            target = ""
        if not text:
            continue
        choices.append(
            {
                "text": text,
                "target": target_scene_file or safe_branch_label(target) or f"{group_id}_{choice_index}",
                "target_scene_file": target_scene_file,
            }
        )
    if not choices:
        return []
    lines = []
    content = str(group.get("content") or "").strip().rstrip(";")
    if content:
        lines.append(f">旁白:{content};")
    lines.append("choose:" + "|".join(f"{choice['text']}:{choice['target']}" for choice in choices) + ";")
    branch_by_label = {
        str(branch["label"]): branch
        for branch in group.get("branches", [])
        if isinstance(branch, dict) and branch.get("label")
    }
    for choice in choices:
        if choice.get("target_scene_file"):
            continue
        branch = branch_by_label.get(choice["target"])
        branch_lines = [f":{choice['target']}"]
        if not branch:
            branch_lines.append(f">旁白:{choice['text']};")
            lines.extend(["", *branch_lines])
            continue
        for line in branch.get("lines", []):
            rendered = render_choice_branch_line(line)
            if rendered:
                branch_lines.append(rendered)
        if len(branch_lines) > 1:
            lines.extend(["", *branch_lines])
    return lines


def render_choice_branch_line(line: dict[str, Any]) -> str:
    kind = str(line.get("kind") or "narration")
    text = str(line.get("text") or "").strip().rstrip(";")
    if not text:
        return ""
    if kind == "dialogue":
        speaker = str(line.get("speaker") or "").strip() or "角色"
        return f"{speaker}:{text};"
    if kind == "intro":
        return f"intro:{text};"
    return f">旁白:{text};"


def mermaid_edges(narrative_structure: str) -> list[dict[str, str]]:
    node = r"[A-Za-z_][A-Za-z0-9_-]*"
    shape = r"(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?"
    edge_re = re.compile(
        rf"(?P<source>{node}){shape}\s*(?:-->|==>|-\.->)\s*(?:\|(?P<label>[^|]+)\|\s*)?(?P<target>{node}){shape}"
    )
    edges = []
    for line in narrative_structure.splitlines():
        cleaned = line.strip().rstrip(";")
        if not cleaned or cleaned.startswith(("%%", "#")):
            continue
        for match in edge_re.finditer(cleaned):
            edges.append(
                {
                    "source": match.group("source").strip(),
                    "target": match.group("target").strip(),
                    "label": (match.group("label") or "").strip(),
                }
            )
    return edges


def resolve_structure_scene(node_id: str, scene_by_node: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = node_id.strip()
    candidates = [key, key.lower(), re.sub(r"[A-Z]+$", "", key), re.sub(r"_[a-z]$", "", key.lower())]
    for candidate in candidates:
        if candidate in scene_by_node:
            return scene_by_node[candidate]
    for source_node, scene in sorted(scene_by_node.items(), key=lambda item: len(item[0]), reverse=True):
        if key.startswith(source_node) and len(key) > len(source_node):
            return scene
    return None


def resolve_structure_ending(node_id: str, ending_by_node: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    key = node_id.strip()
    return ending_by_node.get(key) or ending_by_node.get(key.lower())


def ending_structure_ids(ending: dict[str, Any], index: int) -> set[str]:
    ending_type = str(ending.get("ending_type") or "").strip()
    identifiers = {ending_type, safe_branch_label(ending_type), f"ending_{index}"}
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


def clean_line_text(text: str) -> str:
    return text.strip().lstrip(":：").strip().rstrip(";").strip()


def internal_metadata_match(line: str, key: str) -> str:
    match = re.match(rf"^\s*;?\s*{key}\s*[:：]\s*(.+)$", line, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def story_step_strtype(narrative_plan: dict[str, Any], source_node: str) -> str:
    for step in narrative_plan.get("story_progression", []):
        if str(step.get("id") or "").strip() == source_node or str(step.get("name") or "").strip() == source_node:
            return str(step.get("strtype") or "").strip()
    return ""


def safe_branch_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_")
    if not label:
        return ""
    if not re.match(r"^[A-Za-z_]", label):
        label = f"branch_{label}"
    return label


def is_branch_label(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value.strip()))


def is_internal_scene_metadata(line: str) -> bool:
    return bool(re.match(r"^\s*;?\s*(source_node|ending_type)\s*[:：]", line.strip(), flags=re.IGNORECASE))


def scene_header_matches(text: str):
    pattern = re.compile(
        r"""^\s*
        (?:\#{1,6}\s*)?
        (?:
            (?P<kind>Scene|Ending)\s*[:：]\s*
            |
            (?:[\[【「『]\s*)?
            (?:(?:场景|文件|scene|file)(?:\s*[:：]\s*|\s+))?
        )
        (?P<filename>[A-Za-z0-9_-]+\.txt)
        (?:\s*[\]】」』])?
        \s*[:：]?\s*$
        """,
        flags=re.IGNORECASE | re.MULTILINE | re.VERBOSE,
    )
    return list(pattern.finditer(text))


def format_scene_header(filename: str) -> str:
    prefix = "Ending" if filename.replace("\\", "/").split("/")[-1].startswith("ending_") else "Scene"
    return f"{prefix}:{filename}"
