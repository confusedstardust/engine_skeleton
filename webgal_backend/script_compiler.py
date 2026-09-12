from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import game_design


class ScriptCompileError(ValueError):
    pass


@dataclass(frozen=True)
class ScriptCompilation:
    script: str
    plan: dict[str, Any]


_SCENE_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+\.txt$")
_TARGET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")


def compile_webgal_script(
    game_design_json: dict[str, Any],
    narrative_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
) -> ScriptCompilation:
    """Compile reviewed structured artifacts into deterministic WebGAL text.

    LLMs may decide narrative and asset intent upstream. This boundary owns syntax:

        reviewed JSON + asset bindings -> compile plan -> WebGAL statements

    The compile plan is persisted by the pipeline so every automatic placement is
    inspectable without reverse-engineering the emitted scene files.
    """

    scenes = game_design_json.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ScriptCompileError("game_design_completed.json must contain at least one scene")

    characters = _characters(narrative_plan)
    figures = _figure_assets(asset_manifest, characters)
    backgrounds = _background_assets(asset_manifest)
    warnings: list[str] = []
    plan_scenes: list[dict[str, Any]] = []
    script_sections: list[str] = []

    for scene in scenes:
        if not isinstance(scene, dict):
            raise ScriptCompileError("game_design_completed.json scenes must be objects")
        scene_file = str(scene.get("scene_file") or scene.get("header") or "").strip()
        if not _SCENE_FILE_RE.fullmatch(scene_file):
            raise ScriptCompileError(f"invalid scene filename: {scene_file or '<empty>'}")

        raw_lines = scene.get("lines")
        if not isinstance(raw_lines, list):
            raise ScriptCompileError(f"{scene_file} lines must be a list")
        lines = [line for line in raw_lines if isinstance(line, dict)]
        participant_ids = _scene_participants(lines, characters, figures)
        visible_ids = participant_ids[:3]
        if len(participant_ids) > 3:
            warnings.append(
                f"{scene_file}: {len(participant_ids)} figure-backed speakers found; "
                "only the first three receive stage figures"
            )
        positions = _figure_positions(visible_ids)

        scene_backgrounds = list(backgrounds.get(scene_file, []))
        opening_background, anchored_backgrounds, ignored_backgrounds = _background_placements(
            scene_file, scene_backgrounds, lines
        )
        for asset in ignored_backgrounds:
            warnings.append(
                f"{scene_file}: ignored additional background {asset['filename']} because "
                "insert_before_line_id is missing or invalid"
            )

        output_lines: list[str] = []
        if opening_background:
            output_lines.append(f"changeBg:{opening_background} -next;")
        output_lines.extend(
            [
                "changeFigure:none -next;",
                "changeFigure:none -left -next;",
                "changeFigure:none -right -next;",
            ]
        )

        terminal_choices: list[dict[str, Any]] = []
        shown_figures: set[str] = set()
        for line in lines:
            line_id = str(line.get("id") or "").strip()
            for asset_filename in anchored_backgrounds.get(line_id, []):
                output_lines.append(f"changeBg:{asset_filename} -next;")

            if _is_cross_scene_choice(line):
                terminal_choices.append(line)
                continue

            character_id = _speaker_character_id(line, characters)
            if character_id in positions and character_id not in shown_figures:
                figure = figures[character_id]
                position = positions[character_id]
                position_arg = "" if position == "center" else f" -{position}"
                output_lines.append(f"changeFigure:{figure}{position_arg} -next;")
                shown_figures.add(character_id)

            rendered = _render_line(line, scene_file)
            if rendered:
                output_lines.append(rendered)

        terminal_choice_targets: list[str] = []
        if terminal_choices:
            merged_choice, discarded_options = _merge_cross_scene_choices(terminal_choices)
            terminal_choice_targets = list(
                dict.fromkeys(str(choice.get("target") or "") for choice in merged_choice["choices"])
            )
            if len(terminal_choices) > 1:
                warnings.append(
                    f"{scene_file}: merged {len(terminal_choices)} cross-scene choice groups "
                    f"into {len(merged_choice['choices'])} options across "
                    f"{len(terminal_choice_targets)} destinations; discarded "
                    f"{discarded_options} exact duplicate options"
                )
            output_lines.append(_render_line(merged_choice, scene_file))

        marker = "Ending" if str(scene.get("marker") or "").lower() == "ending" else "Scene"
        if marker == "Ending" and not any(line.strip().lower() == "end;" for line in output_lines):
            output_lines.append("end;")

        script_sections.append("\n".join([f"{marker}:{scene_file}", *output_lines]))
        plan_scenes.append(
            {
                "scene_file": scene_file,
                "background_asset": opening_background or "",
                "anchored_backgrounds": [
                    {"line_id": line_id, "asset": filename}
                    for line_id, filenames in anchored_backgrounds.items()
                    for filename in filenames
                ],
                "figure_slots": [
                    {
                        "character_id": character_id,
                        "asset": figures[character_id],
                        "position": positions[character_id],
                    }
                    for character_id in visible_ids
                ],
                "terminal_choice_moved_to_end": bool(terminal_choices),
                "terminal_choice_groups_merged": len(terminal_choices),
                "terminal_choice_targets": terminal_choice_targets,
            }
        )

    return ScriptCompilation(
        script="\n\n".join(script_sections).rstrip() + "\n",
        plan={
            "version": 1,
            "compiler": "deterministic-webgal-v1",
            "scenes": plan_scenes,
            "warnings": warnings,
        },
    )


def _characters(narrative_plan: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for character in narrative_plan.get("characters", []):
        if not isinstance(character, dict):
            continue
        character_id = str(character.get("id") or "").strip()
        name = str(character.get("name") or "").strip()
        if character_id and name:
            result.append({"id": character_id, "name": name})
    return result


def _asset_filename(image: dict[str, Any]) -> str:
    filename = str(image.get("filename") or "").strip()
    if not filename:
        return ""
    return filename if filename.lower().endswith(".webp") else f"{filename}.webp"


def _figure_assets(asset_manifest: dict[str, Any], characters: list[dict[str, str]]) -> dict[str, str]:
    character_ids = {character["id"] for character in characters}
    figures: dict[str, str] = {}
    for image in asset_manifest.get("images", []):
        if not isinstance(image, dict) or str(image.get("subdir") or "") != "figure":
            continue
        filename = _asset_filename(image)
        explicit_id = str(image.get("character_id") or "").strip()
        stem = filename.removesuffix(".webp").removeprefix("figure_")
        character_id = explicit_id if explicit_id in character_ids else ""
        if not character_id:
            matches = [candidate for candidate in character_ids if candidate == stem or candidate in stem]
            character_id = max(matches, key=len) if matches else ""
        if character_id and filename:
            figures.setdefault(character_id, filename)
    return figures


def _background_assets(asset_manifest: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for image in asset_manifest.get("images", []):
        if not isinstance(image, dict) or str(image.get("subdir") or "") != "background":
            continue
        scene_file = str(image.get("available_scene") or "").strip()
        filename = _asset_filename(image)
        if not scene_file or not filename:
            continue
        result.setdefault(scene_file, []).append(
            {
                "filename": filename,
                "usage": str(image.get("usage") or "").strip(),
                "insert_before_line_id": str(image.get("insert_before_line_id") or "").strip(),
            }
        )
    return result


def _background_placements(
    scene_file: str,
    assets: list[dict[str, str]],
    lines: list[dict[str, Any]],
) -> tuple[str | None, dict[str, list[str]], list[dict[str, str]]]:
    line_ids = {str(line.get("id") or "").strip() for line in lines}
    opening_candidates = [asset for asset in assets if asset["usage"] == "scene_background"]
    if not opening_candidates:
        opening_candidates = [asset for asset in assets if asset["filename"].startswith(("bg_", "title_"))]
    opening = (opening_candidates[0] if opening_candidates else (assets[0] if assets else None))

    anchored: dict[str, list[str]] = {}
    ignored: list[dict[str, str]] = []
    for asset in assets:
        if asset is opening:
            continue
        anchor = asset["insert_before_line_id"]
        if anchor and anchor in line_ids:
            anchored.setdefault(anchor, []).append(asset["filename"])
        else:
            ignored.append(asset)
    return opening["filename"] if opening else None, anchored, ignored


def _speaker_character_id(line: dict[str, Any], characters: list[dict[str, str]]) -> str:
    if str(line.get("kind") or "") != "dialogue":
        return ""
    explicit_id = str(line.get("character_id") or "").strip()
    valid_ids = {character["id"] for character in characters}
    if explicit_id in valid_ids:
        return explicit_id
    speaker = str(line.get("speaker") or "").strip()
    matches = [character for character in characters if character["name"] == speaker]
    if not matches:
        matches = [character for character in characters if character["name"] in speaker]
    return max(matches, key=lambda item: len(item["name"]))["id"] if matches else ""


def _scene_participants(
    lines: list[dict[str, Any]],
    characters: list[dict[str, str]],
    figures: dict[str, str],
) -> list[str]:
    result: list[str] = []
    for line in lines:
        character_id = _speaker_character_id(line, characters)
        if character_id and character_id in figures and character_id not in result:
            result.append(character_id)
    return result


def _figure_positions(character_ids: list[str]) -> dict[str, str]:
    layouts = {
        1: ["center"],
        2: ["left", "right"],
        3: ["center", "left", "right"],
    }
    return dict(zip(character_ids, layouts.get(len(character_ids), []), strict=False))


def _is_cross_scene_choice(line: dict[str, Any]) -> bool:
    if str(line.get("kind") or "") != "choice":
        return False
    targets = [
        str(choice.get("target_scene_file") or choice.get("target") or "").strip()
        for choice in line.get("choices", [])
        if isinstance(choice, dict)
    ]
    return bool(targets) and all(target.endswith(".txt") for target in targets)


def _merge_cross_scene_choices(
    lines: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """Build one terminal choice with one meaningful option per destination.

    The upstream choice planner may emit one group per connectable scene pair.
    When a source scene has several destinations, emitting those groups in
    sequence makes every group after the first unreachable in WebGAL. The
    compiler therefore folds them into a single choice. Reviewed options are
    preserved even when several wordings lead to the same destination; only
    exact duplicate text/target pairs are removed.
    """

    choices: list[dict[str, str]] = []
    seen_options: set[tuple[str, str]] = set()
    candidate_count = 0
    for line in lines:
        for choice in line.get("choices", []):
            if not isinstance(choice, dict):
                continue
            target = str(choice.get("target_scene_file") or choice.get("target") or "").strip()
            text = str(choice.get("text") or "").strip()
            if not target or not text:
                continue
            candidate_count += 1
            option_key = (text, target)
            if option_key in seen_options:
                continue
            seen_options.add(option_key)
            choices.append({"text": text, "target": target, "target_scene_file": target})
    if not choices:
        raise ScriptCompileError("cross-scene choice groups contain no usable options")
    return {
        "kind": "choice",
        "speaker": "分支",
        "text": "",
        "rawPrefix": "choose",
        "choices": choices,
    }, candidate_count - len(choices)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace(";", "；").split()).strip()


def _render_line(line: dict[str, Any], scene_file: str) -> str:
    kind = str(line.get("kind") or "narration")
    normalized = dict(line)
    normalized["text"] = _clean_text(line.get("text"))
    if kind == "dialogue":
        speaker = _clean_text(line.get("speaker") or "角色").replace(":", "：")
        normalized["speaker"] = speaker
    elif kind == "choice":
        choices = []
        for choice in line.get("choices", []):
            if not isinstance(choice, dict):
                continue
            target = str(choice.get("target_scene_file") or choice.get("target") or "").strip()
            if not _TARGET_RE.fullmatch(target):
                raise ScriptCompileError(f"{scene_file} contains invalid choice target: {target or '<empty>'}")
            choices.append({"text": _clean_text(choice.get("text")).replace("|", " ").replace(":", "："), "target": target})
        normalized["choices"] = choices
    rendered = game_design.render_scene_line(normalized)
    if kind == "choice" and not rendered:
        raise ScriptCompileError(f"{scene_file} contains an empty choice")
    return rendered
