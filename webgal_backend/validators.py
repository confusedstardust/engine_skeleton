from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jsonschema

from .config import settings
from .generation_limits import generation_limits
from .storage import read_json


class ValidationFailure(RuntimeError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


def validate_schema(schema_name: str, artifact: dict[str, Any]) -> None:
    schema_path = settings.skill_dir / "references" / "schemas" / schema_name
    schema = read_json(schema_path)
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda error: list(error.path))
    if errors:
        messages = []
        for error in errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            messages.append(f"{location}: {error.message}")
        raise ValidationFailure(messages)


def require_unique(items: list[dict[str, Any]], key: str, label: str) -> list[str]:
    errors = []
    seen = set()
    for item in items:
        value = item.get(key)
        if value in seen:
            errors.append(f"duplicate {label} {key}: {value}")
        seen.add(value)
    return errors


def semantic_narrative(plan: dict[str, Any]) -> None:
    limits = generation_limits()
    errors: list[str] = []
    characters = plan["characters"]
    scenes = plan["scenes"]
    variables = plan["variables"]["attitude"] + plan["variables"]["flags"]
    endings = plan["endings"]

    errors += require_unique(characters, "id", "character")
    errors += require_unique(scenes, "id", "scene")
    errors += require_unique(variables, "id", "variable")
    errors += require_unique(endings, "id", "ending")

    protagonists = [c for c in characters if c["role"] == "protagonist"]
    if len(protagonists) != 1:
        errors.append(f"expected exactly one protagonist, got {len(protagonists)}")

    if not limits["characters"]["min"] <= len(characters) <= limits["characters"]["max"]:
        errors.append(
            f"characters must be {limits['characters']['min']}-{limits['characters']['max']}, got {len(characters)}"
        )

    entry_scenes = [s for s in scenes if s["is_entry"]]
    if len(entry_scenes) != 1:
        errors.append(f"expected exactly one entry scene, got {len(entry_scenes)}")

    if not limits["scenes"]["min"] <= len(scenes) <= limits["scenes"]["max"]:
        errors.append(f"scenes must be {limits['scenes']['min']}-{limits['scenes']['max']}, got {len(scenes)}")

    categories = {ending["category"] for ending in endings}
    expected_categories = set(limits["endings"]["categories"])
    if categories != expected_categories:
        errors.append(f"ending categories must be {sorted(expected_categories)}, got {sorted(categories)}")
    if len(endings) != limits["endings"]["count"]:
        errors.append(f"endings must be exactly {limits['endings']['count']}, got {len(endings)}")

    if len(variables) > limits["variables"]["max_total"]:
        errors.append(f"total variables must be <= {limits['variables']['max_total']}, got {len(variables)}")
    if len(plan["variables"]["attitude"]) > limits["variables"]["attitude_max"]:
        errors.append(
            f"attitude variables must be <= {limits['variables']['attitude_max']}, got {len(plan['variables']['attitude'])}"
        )
    if len(plan["variables"]["flags"]) > limits["variables"]["flag_max"]:
        errors.append(f"flag variables must be <= {limits['variables']['flag_max']}, got {len(plan['variables']['flags'])}")

    for variable in plan["variables"]["attitude"]:
        if variable["min"] != limits["variables"]["attitude_min_value"] or variable["max"] != limits["variables"]["attitude_max_value"]:
            errors.append(
                f"attitude variable {variable['id']} range must be "
                f"{limits['variables']['attitude_min_value']}-{limits['variables']['attitude_max_value']}"
            )
        if not limits["variables"]["attitude_min_value"] <= variable["default"] <= limits["variables"]["attitude_max_value"]:
            errors.append(f"attitude variable {variable['id']} default is outside configured range")

    if not limits["branches"]["min"] <= len(plan["branches"]) <= limits["branches"]["max"]:
        errors.append(f"branches must be {limits['branches']['min']}-{limits['branches']['max']}, got {len(plan['branches'])}")

    scene_ids = {scene["id"] for scene in scenes}
    variable_ids = {variable["id"] for variable in variables}
    character_ids = {character["id"] for character in characters}

    for scene in scenes:
        for character_id in scene["characters_present"]:
            if character_id not in character_ids:
                errors.append(f"scene {scene['id']} references unknown character {character_id}")

    for connection in plan["connections"]:
        if connection["from_scene_id"] not in scene_ids:
            errors.append(f"connection references unknown from_scene_id {connection['from_scene_id']}")
        if connection["to_scene_id"] not in scene_ids:
            errors.append(f"connection references unknown to_scene_id {connection['to_scene_id']}")

    for branch in plan["branches"]:
        if branch["scene_id"] not in scene_ids:
            errors.append(f"branch {branch['id']} references unknown scene {branch['scene_id']}")
        if branch["depth"] > limits["branches"]["max_depth"]:
            errors.append(f"branch {branch['id']} depth must be <= {limits['branches']['max_depth']}")
        if not limits["branches"]["choice_options_min"] <= len(branch["options"]) <= limits["branches"]["choice_options_max"]:
            errors.append(
                f"branch {branch['id']} options must be "
                f"{limits['branches']['choice_options_min']}-{limits['branches']['choice_options_max']}, got {len(branch['options'])}"
            )
        for option in branch["options"]:
            if option["next_scene_id"] not in scene_ids:
                errors.append(f"branch {branch['id']} option references unknown scene {option['next_scene_id']}")
            for assignment in option["sets"] + option["adds"]:
                if assignment["variable_id"] not in variable_ids:
                    errors.append(f"branch {branch['id']} references unknown variable {assignment['variable_id']}")

    for ending in endings:
        for condition in ending["trigger"]["conditions"]:
            if condition["variable_id"] not in variable_ids:
                errors.append(f"ending {ending['id']} references unknown variable {condition['variable_id']}")

    if errors:
        raise ValidationFailure(errors)


def semantic_asset_manifest(manifest: dict[str, Any], plan: dict[str, Any], expected_base_dir: str) -> None:
    limits = generation_limits()
    errors: list[str] = []
    if Path(manifest["base_dir"]).resolve() != Path(expected_base_dir).resolve():
        errors.append(f"base_dir must be {expected_base_dir}, got {manifest['base_dir']}")

    character_ids = {character["id"] for character in plan["characters"]}
    scene_ids = {scene["id"] for scene in plan["scenes"]}

    figure_refs = set()
    for image in manifest["images"]:
        kind = image["kind"]
        filename = image["filename"]
        if kind == "figure":
            if image["subdir"] != limits["assets"]["figure_subdir"] or image["size"] != limits["assets"]["figure_size"]:
                errors.append(f"{filename} figure must use {limits['assets']['figure_subdir']}/{limits['assets']['figure_size']}")
            if image["source_ref"]["type"] != "character" or image["source_ref"]["id"] not in character_ids:
                errors.append(f"{filename} references unknown character source")
            figure_refs.add(image["source_ref"]["id"])
        if kind in {"background", "cg"}:
            if image["subdir"] != limits["assets"]["background_subdir"] or image["size"] != limits["assets"]["background_size"]:
                errors.append(f"{filename} {kind} must use {limits['assets']['background_subdir']}/{limits['assets']['background_size']}")
            if image["source_ref"]["type"] == "scene" and image["source_ref"]["id"] not in scene_ids:
                errors.append(f"{filename} references unknown scene source")

    missing_figures = character_ids - figure_refs
    if missing_figures:
        errors.append(f"missing figure assets for characters: {sorted(missing_figures)}")

    if errors:
        raise ValidationFailure(errors)


def semantic_scene_batch(batch: dict[str, Any], plan: dict[str, Any], manifest: dict[str, Any]) -> None:
    limits = generation_limits()
    errors: list[str] = []
    expected = {scene["id"]: scene["file"] for scene in plan["scenes"]}
    produced = {scene["scene_id"]: scene["file"] for scene in batch["scenes"]}
    if produced != expected:
        errors.append(f"scene batch files must match narrative scenes; expected {expected}, got {produced}")

    variable_ids = {variable["id"] for variable in plan["variables"]["attitude"] + plan["variables"]["flags"]}
    asset_names = set()
    for image in manifest["images"]:
        asset_names.add(f"{image['filename']}.webp")
        if image["kind"] == "figure":
            asset_names.add(f"miniavatar_{image['filename'].removeprefix('figure_')}.webp")

    for scene in batch["scenes"]:
        beats = scene["beats"]
        if not limits["scene_batch"]["beats_min"] <= len(beats) <= limits["scene_batch"]["beats_max"]:
            errors.append(
                f"{scene['file']} beats must be "
                f"{limits['scene_batch']['beats_min']}-{limits['scene_batch']['beats_max']}, got {len(beats)}"
            )
        for beat in beats:
            if len(beat["text"]) > limits["scene_batch"]["beat_text_max_length"]:
                errors.append(
                    f"{scene['file']} beat text must be <= {limits['scene_batch']['beat_text_max_length']} characters"
                )
        if scene["speaker_character_id"] not in {character["id"] for character in plan["characters"]}:
            errors.append(f"{scene['file']} references unknown speaker_character_id {scene['speaker_character_id']}")
        for variable_id in scene["referenced_variables"]:
            if variable_id not in variable_ids:
                errors.append(f"{scene['file']} references unknown variable {variable_id}")
        if scene["background_asset"] not in asset_names:
            errors.append(f"{scene['file']} references background not in manifest: {scene['background_asset']}")
        for asset in scene["referenced_assets"]:
            if asset.endswith(".webp") and asset not in asset_names:
                errors.append(f"{scene['file']} references asset not in manifest: {asset}")

    if errors:
        raise ValidationFailure(errors)


def deterministic_validate(job_dir: Path, plan: dict[str, Any], manifest: dict[str, Any], allow_missing_assets: bool) -> dict[str, Any]:
    limits = generation_limits()
    scene_dir = job_dir / "public" / "game" / "scene"
    background_dir = job_dir / "public" / "game" / "background"
    figure_dir = job_dir / "public" / "game" / "figure"
    bgm_dir = job_dir / "public" / "game" / "bgm"

    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    ending_files = {ending["file"] for ending in plan["endings"]}
    scene_files = sorted(scene_dir.glob("*.txt"))
    variable_ids = {variable["id"] for variable in plan["variables"]["attitude"] + plan["variables"]["flags"]}
    speaker_names = {character["name"] for character in plan["characters"]}

    def add_issue(code: str, file: str | None, line: int | None, message: str, repair_hint: str | None = None) -> None:
        issues.append({
            "code": code,
            "severity": "error",
            "file": file,
            "line": line,
            "message": message,
            "repair_hint": repair_hint,
        })

    def add_warning(code: str, file: str | None, line: int | None, message: str, repair_hint: str | None = None) -> None:
        warnings.append({
            "code": code,
            "severity": "warning",
            "file": file,
            "line": line,
            "message": message,
            "repair_hint": repair_hint,
        })

    expected_files = {scene["file"] for scene in plan["scenes"]}
    actual_files = {path.name for path in scene_files}
    for missing in sorted(expected_files - actual_files):
        add_issue("missing_scene_file", f"public/game/scene/{missing}", None, f"missing scene file {missing}")

    total_lines = 0
    for path in scene_files:
        rel = f"public/game/scene/{path.name}"
        lines = path.read_text(encoding="utf-8").splitlines()
        total_lines += len(lines)
        if not re.match(r"^[a-z][a-z0-9_]+\.txt$", path.name):
            add_issue("bad_scene_filename", rel, None, f"scene filename must be lowercase snake_case: {path.name}")
        if len(lines) < limits["scenes"]["min_lines"] or len(lines) > limits["scenes"]["max_lines"]:
            add_issue(
                "bad_scene_line_count",
                rel,
                None,
                f"scene must be {limits['scenes']['min_lines']}-{limits['scenes']['max_lines']} lines, got {len(lines)}",
            )

        labels = {
            line.removeprefix("label:").removesuffix(";").strip()
            for line in lines
            if line.strip().startswith("label:")
        }
        for index, line in enumerate(lines):
            stripped = line.strip()
            line_no = index + 1
            if stripped.startswith("callScene:"):
                next_non_empty = None
                for later in lines[index + 1:]:
                    if later.strip():
                        next_non_empty = later.strip()
                        break
                if next_non_empty != ";":
                    add_issue("callscene_missing_barrier", rel, line_no, "callScene must be followed by ;", "Insert ; on the next non-empty line.")
            if stripped == "end;" and path.name != "start.txt" and path.name not in ending_files:
                add_issue("end_in_subscene", rel, line_no, "end; only allowed in start.txt and ending files")
            if stripped.startswith("jumpLabel:"):
                target = stripped.removeprefix("jumpLabel:").split(" ", 1)[0].removesuffix(";")
                if target not in labels:
                    add_issue("undefined_label", rel, line_no, f"jumpLabel target not found in same file: {target}")
            if "-when=" in stripped and any(token in stripped for token in ["&&", "||", " AND ", " OR "]):
                add_issue("multi_condition_when", rel, line_no, "WebGAL -when= must contain only one condition")
            if "=true" in stripped or "=false" in stripped:
                add_issue("boolean_literal", rel, line_no, "Use 0/1 integers, not true/false")

            check_references(stripped, rel, line_no, background_dir, figure_dir, bgm_dir, variable_ids, speaker_names, add_issue, add_warning, allow_missing_assets)

    check_groups = {
        "syntax": ["callscene_missing_barrier", "end_in_subscene", "undefined_label", "multi_condition_when", "boolean_literal"],
        "references": ["missing_background", "missing_figure", "missing_miniavatar", "missing_bgm", "unknown_speaker"],
        "variables": ["undefined_variable"],
        "endings": ["missing_scene_file"],
        "limits": ["bad_scene_line_count"],
        "naming": ["bad_scene_filename"],
        "figures": [],
    }

    checks = {}
    for name, codes in check_groups.items():
        check_errors = [issue for issue in issues if issue["code"] in codes]
        check_warnings = [issue for issue in warnings if issue["code"] in codes]
        checks[name] = {"passed": not check_errors, "errors": check_errors, "warnings": check_warnings}

    return {
        "summary": {
            "total_scenes": len(scene_files),
            "total_lines": total_lines,
            "errors": len(issues),
            "warnings": len(warnings),
            "passed": len(issues) == 0,
        },
        "checks": checks,
        "errors": issues,
        "warnings": warnings,
    }


def check_references(
    line: str,
    rel: str,
    line_no: int,
    background_dir: Path,
    figure_dir: Path,
    bgm_dir: Path,
    variable_ids: set[str],
    speaker_names: set[str],
    add_issue,
    add_warning,
    allow_missing_assets: bool,
) -> None:
    def missing(code: str, message: str) -> None:
        if allow_missing_assets and code in {"missing_background", "missing_figure", "missing_miniavatar", "missing_bgm"}:
            add_warning(code, rel, line_no, message)
        else:
            add_issue(code, rel, line_no, message)

    if match := re.search(r"changeBg:([^\s;]+)", line):
        filename = match.group(1)
        if not (background_dir / filename).exists():
            missing("missing_background", f"background file does not exist: {filename}")
    if match := re.search(r"changeFigure:([^\s;]+)", line):
        filename = match.group(1)
        if filename != "none" and not (figure_dir / filename).exists():
            missing("missing_figure", f"figure file does not exist: {filename}")
    if match := re.search(r"miniAvatar:([^;]+)", line):
        filename = match.group(1).strip()
        if not (figure_dir / filename).exists():
            missing("missing_miniavatar", f"mini avatar file does not exist: {filename}")
    if match := re.search(r"bgm:([^\s;]+)", line):
        filename = match.group(1)
        if not (bgm_dir / filename).exists():
            missing("missing_bgm", f"bgm file does not exist: {filename}")
    for match in re.finditer(r"(?:setVar:|-when=)([a-z][a-z0-9_]*)", line):
        variable_id = match.group(1)
        if variable_id not in variable_ids and not variable_id.endswith("check"):
            add_issue("undefined_variable", rel, line_no, f"undefined variable: {variable_id}")
    if ":" in line and not line.startswith((";", ":", "choose:", "label:", "callScene:", "jumpLabel:", "setVar:", "change", "miniAvatar:", "bgm:", "intro:")):
        speaker = line.split(":", 1)[0].strip()
        if speaker and speaker not in speaker_names:
            add_issue("unknown_speaker", rel, line_no, f"unknown speaker: {speaker}")
