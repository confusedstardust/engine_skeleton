"""Lower option-owned dialogue to ordinary WebGAL labels and explicit exits."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def has_responses(line: dict[str, Any]) -> bool:
    return line.get("kind") == "choice" and any(
        isinstance(option, dict) and bool(option.get("response_lines"))
        for option in line.get("choices", [])
    )


def response_label(scene: str, line_id: str, option_id: str) -> str:
    digest = hashlib.sha256(f"{scene}\0{line_id}\0{option_id}".encode()).hexdigest()[:24]
    return f"response_{digest}"


def lower_choice_responses(lines: list[dict[str, Any]], scene: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    labels = {str(line.get("branchLabel") or line.get("text") or "") for line in lines if line.get("kind") == "branch"}
    used_ids: set[str] = set()
    for index, line in enumerate(lines):
        if line.get("kind") != "choice":
            result.append(line)
            continue
        options = line.get("choices", [])
        if not isinstance(options, list):
            raise ValueError(f"{scene}: choice options must be a list")
        for option in options:
            if not isinstance(option, dict):
                continue
            responses = option.get("response_lines", [])
            if not isinstance(responses, list):
                raise ValueError(f"{scene}: response_lines must be a list")
            for response in responses:
                if not isinstance(response, dict) or response.get("kind") not in {"dialogue", "narration"}:
                    raise ValueError(f"{scene}: option responses only support dialogue and narration")
                if not str(response.get("text") or "").strip():
                    raise ValueError(f"{scene}: option response text cannot be empty")
                if response.get("kind") == "dialogue" and not str(response.get("speaker") or "").strip():
                    raise ValueError(f"{scene}: option response speaker cannot be empty")
        if not has_responses(line):
            result.append(line)
            continue
        line_id = str(line.get("id") or f"choice_{index}")
        branches = []
        lowered_options = []
        for option_index, option in enumerate(options):
            if not isinstance(option, dict):
                raise ValueError(f"{scene}: choice options must be objects")
            option_id = str(option.get("id") or f"option_{option_index}")
            identity = f"{line_id}\0{option_id}"
            if identity in used_ids:
                raise ValueError(f"{scene}: duplicate choice option id: {option_id}")
            used_ids.add(identity)
            entry = response_label(scene, line_id, option_id)
            if entry in labels:
                raise ValueError(f"{scene}: generated response label collides with existing label")
            labels.add(entry)
            target = str(option.get("target_scene_file") or option.get("targetSceneFile") or option.get("target") or "")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", target):
                raise ValueError(f"{scene}: invalid response exit: {target}")
            if not str(option.get("text") or "").strip():
                raise ValueError(f"{scene}: choice text cannot be empty")
            lowered_options.append({**option, "target": entry, "target_scene_file": "", "targetSceneFile": "", "response_lines": []})
            branches.append({"id": entry, "kind": "branch", "text": entry, "branchLabel": entry})
            for response in option.get("response_lines", []):
                branches.append({**response,
                    "text": " ".join(str(response.get("text") or "").replace(";", "；").split()),
                    "speaker": " ".join(str(response.get("speaker") or "旁白").replace(";", "；").replace(":", "：").split())})
            command = "changeScene" if target.endswith(".txt") else "jumpLabel"
            branches.append({"id": f"{entry}_exit", "kind": "command", "text": f"{command}:{target};"})
        result.append({**line, "choices": lowered_options})
        result.extend(branches)
    return result
