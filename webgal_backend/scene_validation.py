from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .generation_limits import generation_limits
from .storage import read_json


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    file: str
    line: int | None
    message: str
    autofixable: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "autofixable": self.autofixable,
        }


@dataclass(frozen=True)
class AppliedFix:
    code: str
    file: str
    line: int | None
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class SceneValidationResult:
    issues: list[ValidationIssue]
    fixes: list[AppliedFix]
    total_scenes: int
    total_lines: int


def validate_and_repair_scenes(job_dir: Path) -> SceneValidationResult:
    scene_dir = job_dir / "public" / "game" / "scene"
    scene_files = sorted(scene_dir.glob("*.txt"))
    issues: list[ValidationIssue] = []
    fixes: list[AppliedFix] = []

    if not scene_files:
        issues.append(
            ValidationIssue(
                code="missing_scene_files",
                severity="error",
                file="public/game/scene",
                line=None,
                message="No scene files were generated.",
            )
        )
        return SceneValidationResult(issues=issues, fixes=fixes, total_scenes=0, total_lines=0)

    character_avatars = _character_avatar_map(job_dir)
    vocal_map = _tts_vocal_map(job_dir)
    for scene_path in scene_files:
        relative_file = _relative_scene_file(job_dir, scene_path)
        original_lines = scene_path.read_text(encoding="utf-8").splitlines()
        repaired_lines, file_issues, file_fixes = _repair_scene_lines(
            original_lines,
            relative_file,
            character_avatars,
            vocal_map,
        )
        issues.extend(file_issues)
        fixes.extend(file_fixes)
        if repaired_lines != original_lines:
            scene_path.write_text("\n".join(repaired_lines).rstrip() + "\n", encoding="utf-8")

    scene_files = sorted(scene_dir.glob("*.txt"))
    issues.extend(_validate_scene_structure(job_dir, scene_files))
    total_lines = sum(len(path.read_text(encoding="utf-8").splitlines()) for path in scene_files)
    return SceneValidationResult(
        issues=issues,
        fixes=fixes,
        total_scenes=len(scene_files),
        total_lines=total_lines,
    )


def validation_report(result: SceneValidationResult) -> dict[str, Any]:
    errors = [issue for issue in result.issues if issue.severity == "error"]
    warnings = [issue for issue in result.issues if issue.severity == "warning"]
    return {
        "summary": {
            "total_scenes": result.total_scenes,
            "total_lines": result.total_lines,
            "errors": len(errors),
            "warnings": len(warnings),
            "fixes": len(result.fixes),
            "passed": not errors,
        },
        "checks": {
            "mini_avatar": _check_status(result, "missing_mini_avatar"),
            "vocal_args": _check_status(result, "missing_vocal_arg"),
            "figure_positions": _check_status(result, "duplicate_figure_position"),
            "scene_structure": "failed" if any(issue.code.startswith("missing_") for issue in errors) else "passed",
            "choice_callbacks": _check_status(result, "shared_choice_target"),
            "ending_closure": _check_status(result, "choice_direct_to_ending"),
            "branch_density": _check_status(result, "thin_branch_scene"),
            "template_phrases": _check_status(result, "template_phrase"),
        },
        "errors": [issue.to_json() for issue in errors],
        "warnings": [issue.to_json() for issue in warnings],
        "fixes": [fix.to_json() for fix in result.fixes],
    }


def _repair_scene_lines(
    lines: list[str],
    relative_file: str,
    character_avatars: dict[str, str],
    vocal_map: dict[tuple[str, int], str],
) -> tuple[list[str], list[ValidationIssue], list[AppliedFix]]:
    issues: list[ValidationIssue] = []
    fixes: list[AppliedFix] = []
    repaired: list[str] = []
    stage_positions: dict[str, str | None] = {"left": None, "center": None, "right": None}
    lines, prelude_cleanup_fixes = _remove_expanded_scene_prelude_clears(lines, relative_file)
    fixes.extend(prelude_cleanup_fixes)

    for line_index, original_line in enumerate(lines):
        original_index = line_index + 1
        line = original_line
        normalized_line = _normalize_center_clear_line(line)
        if normalized_line != line:
            line = normalized_line
            fixes.append(
                AppliedFix(
                    code="normalize_center_figure_clear",
                    file=relative_file,
                    line=original_index,
                    message="Normalized center figure clear to changeFigure:none;.",
                )
            )

        figure_change = _parse_change_figure(line)
        transition_line: str | None = None
        if figure_change:
            figure, position = figure_change
            if _is_figure_clear(figure):
                stage_positions[position] = None
            else:
                duplicate_positions = [
                    old_position
                    for old_position, old_figure in stage_positions.items()
                    if old_position != position and old_figure == figure
                ]
                for old_position in duplicate_positions:
                    repaired.append(_clear_figure_line(old_position))
                    fixes.append(
                        AppliedFix(
                            code="duplicate_figure_position",
                            file=relative_file,
                            line=original_index,
                            message=f"Cleared duplicate {figure} from {old_position} before placing it at {position}.",
                        )
                    )
                    stage_positions[old_position] = None
                stage_positions[position] = figure
                transition_line = _transition_line_for_change_figure(line, position, lines[line_index + 1 :])

        vocal_filename = vocal_map.get((relative_file.replace("public/game/scene/", ""), original_index))
        if vocal_filename and _dialogue_speaker(line) and not _has_vocal_arg(line):
            line = _add_vocal_arg(line, vocal_filename)
            fixes.append(
                AppliedFix(
                    code="missing_vocal_arg",
                    file=relative_file,
                    line=original_index,
                    message=f"Inserted vocal argument {vocal_filename}.",
                )
            )

        speaker = _dialogue_speaker(line)
        if speaker and speaker in character_avatars:
            avatar_line = f"miniAvatar:{character_avatars[speaker]};"
            if not _previous_effective_line_is(repaired, avatar_line):
                repaired.append(avatar_line)
                fixes.append(
                    AppliedFix(
                        code="missing_mini_avatar",
                        file=relative_file,
                        line=original_index,
                        message=f"Inserted mini avatar for speaker {speaker}.",
                    )
                )
        elif speaker and speaker not in character_avatars:
            issues.append(
                ValidationIssue(
                    code="unknown_speaker_avatar",
                    severity="warning",
                    file=relative_file,
                    line=original_index,
                    message=f"No mini avatar mapping found for speaker {speaker}.",
                )
            )

        repaired.append(line)
        if transition_line:
            repaired.append(transition_line)
            fixes.append(
                AppliedFix(
                    code="missing_figure_transition",
                    file=relative_file,
                    line=original_index,
                    message="Inserted transition immediately after changeFigure.",
                )
            )

    repaired, ending_fixes = _ensure_scene_ending_clears(repaired, relative_file)
    fixes.extend(ending_fixes)
    return repaired, issues, fixes


def _dialogue_speaker(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(";") or stripped.startswith("//"):
        return None
    if stripped.startswith((":", "intro:", "choose:", "change", "miniAvatar:", "setVar:", "unlock", "pixi", "bgm:", "playEffect:", "end")):
        return None
    match = re.match(r"^(?P<speaker>[^:\uFF1A;\s][^:\uFF1A;]*?)\s*[\uFF1A:]", stripped)
    if not match:
        return None
    speaker = match.group("speaker").strip()
    if speaker in {"if", "label", "jumpLabel", "callScene"}:
        return None
    return speaker or None


def _add_vocal_arg(line: str, filename: str) -> str:
    stripped = line.rstrip()
    suffix = f" -{filename}"
    if stripped.endswith(";"):
        return f"{stripped[:-1]}{suffix};"
    return f"{stripped}{suffix};"


def _has_vocal_arg(line: str) -> bool:
    if "-vocal=" in line:
        return True
    return bool(re.search(r"\s-[^\s;]+\.(mp3|wav|ogg|m4a)(\s|;|$)", line, flags=re.IGNORECASE))


def _parse_change_figure(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if stripped.startswith(";"):
        stripped = stripped[1:].strip()
    match = re.match(r"^changeFigure\s*:\s*(?P<figure>[^;\s]*)(?P<args>[^;]*)", stripped)
    if not match:
        return None
    args = match.group("args") or ""
    position = "center"
    if re.search(r"(^|\s)-left(\s|=|$)", args):
        position = "left"
    elif re.search(r"(^|\s)-right(\s|=|$)", args):
        position = "right"
    return match.group("figure").strip(), position


def _transition_line_for_change_figure(line: str, position: str, following_lines: list[str]) -> str | None:
    if _has_inline_transition_arg(line):
        return None
    if _next_effective_line_is_set_transition(following_lines, _figure_target(line, position)):
        return None
    target = _figure_target(line, position)
    enter = {
        "left": "enter-from-left",
        "center": "enter-from-bottom",
        "right": "enter-from-right",
    }[position]
    return f"setTransition: -target={target} -enter={enter} -exit=exit;"


def _has_inline_transition_arg(line: str) -> bool:
    return bool(re.search(r"(^|\s)-(enter|exit)=", line))


def _next_effective_line_is_set_transition(lines: list[str], target: str) -> bool:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        return stripped.startswith("setTransition:") and f"-target={target}" in stripped
    return False


def _figure_target(line: str, position: str) -> str:
    id_match = re.search(r"(^|\s)-id=(?P<id>[^\s;]+)", line)
    if id_match:
        return id_match.group("id")
    return {
        "left": "fig-left",
        "center": "fig-center",
        "right": "fig-right",
    }[position]


def _normalize_center_clear_line(line: str) -> str:
    match = re.match(r"^\s*changeFigure\s*:\s*none(?P<args>[^;]*?)\s*;\s*$", line)
    if match and re.search(r"(^|\s)-center(\s|=|$)", match.group("args") or ""):
        args = _remove_position_arg(match.group("args") or "", "center")
        return f"changeFigure:none{args};"
    return line


def _change_figure_args(line: str) -> str:
    match = re.match(r"^\s*changeFigure\s*:\s*none(?P<args>[^;]*?)\s*;\s*$", line)
    if not match:
        return ""
    args = _remove_position_arg(match.group("args") or "", "center").strip()
    return f" {args}" if args else ""


def _remove_position_arg(args: str, position: str) -> str:
    return re.sub(rf"(^|\s)-{position}(\s|=|$)", " ", args).strip()


def _clear_figure_line(position: str) -> str:
    if position == "center":
        return "changeFigure:none;"
    return f"changeFigure:none -{position};"


def _is_figure_clear(figure: str) -> bool:
    return figure in {"", "none"}


def _previous_effective_line_is(lines: list[str], expected: str) -> bool:
    for line in reversed(lines):
        if not line.strip():
            continue
        return line.strip() == expected
    return False


def _ensure_scene_ending_clears(lines: list[str], relative_file: str) -> tuple[list[str], list[AppliedFix]]:
    if not lines:
        return lines, []

    clear_lines = ["changeFigure:none;", "changeFigure:none -left;", "changeFigure:none -right;"]
    insertion_index = _ending_clear_insertion_index(lines)
    existing_window_start = max(0, insertion_index - len(clear_lines))
    existing_window = [line.strip() for line in lines[existing_window_start:insertion_index]]
    missing = [line for line in clear_lines if line not in existing_window]
    if not missing:
        return lines, []

    repaired = [*lines[:insertion_index], *missing, *lines[insertion_index:]]
    return repaired, [
        AppliedFix(
            code="scene_ending_clear_figures",
            file=relative_file,
            line=insertion_index + 1,
            message="Inserted scene-ending figure clears for center, left, and right positions.",
        )
    ]


def _remove_expanded_scene_prelude_clears(lines: list[str], relative_file: str) -> tuple[list[str], list[AppliedFix]]:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _starts_story_content(stripped):
            return lines, []
        if not _is_center_clear_line(line):
            continue
        next_two = [item.strip() for item in lines[index + 1 : index + 3]]
        if next_two != ["changeFigure:none -left -next;", "changeFigure:none -right -next;"]:
            continue
        repaired = [*lines[: index + 1], *lines[index + 3 :]]
        return repaired, [
            AppliedFix(
                code="remove_scene_prelude_clear_expansion",
                file=relative_file,
                line=index + 2,
                message="Removed expanded scene-opening left/right clears; scene endings now clear figures.",
            )
        ]
    return lines, []


def _starts_story_content(line: str) -> bool:
    command_prefixes = (
        "setVar:",
        "changeBg:",
        "changeFigure:",
        "miniAvatar:",
        "bgm:",
        "playEffect:",
        "unlock",
        "pixi",
    )
    return not line.startswith(command_prefixes)


def _is_center_clear_line(line: str) -> bool:
    stripped = line.strip()
    return stripped in {"changeFigure:none;", "changeFigure:none -next;"}


def _ending_clear_insertion_index(lines: list[str]) -> int:
    for index in range(len(lines) - 1, -1, -1):
        stripped = lines[index].strip()
        if not stripped:
            continue
        if stripped.startswith(("end", "choose:", "changeScene:")):
            return index
        return index + 1
    return len(lines)


def _character_avatar_map(job_dir: Path) -> dict[str, str]:
    plan_path = job_dir / "state" / "narrative_plan.json"
    manifest_path = job_dir / "assets_manifest.json"
    if not plan_path.exists() or not manifest_path.exists():
        return {}

    plan = read_json(plan_path)
    manifest = read_json(manifest_path)
    suffix_to_avatar = _manifest_avatar_map(manifest)
    mapping: dict[str, str] = {}
    for character in plan.get("characters", []):
        character_id = str(character.get("id", "")).strip()
        character_name = str(character.get("name", "")).strip()
        avatar = suffix_to_avatar.get(character_id)
        if not avatar:
            avatar = _find_avatar_by_suffix(character_id, suffix_to_avatar)
        if avatar and character_name:
            mapping[character_name] = avatar
    return mapping


def _tts_vocal_map(job_dir: Path) -> dict[tuple[str, int], str]:
    manifest_path = job_dir / "state" / "tts_manifest.json"
    vocal_dir = job_dir / "public" / "game" / "vocal"
    if not manifest_path.exists() or not vocal_dir.exists():
        return {}

    manifest = read_json(manifest_path)
    mapping: dict[tuple[str, int], str] = {}
    for item in manifest.get("items", []):
        status = item.get("status")
        filename = str(item.get("filename", "")).strip()
        scene = str(item.get("scene", "")).strip()
        line_no = item.get("line_no")
        if status not in {"completed", "skipped_existing"} or not filename or not scene:
            continue
        if not isinstance(line_no, int):
            continue
        if not (vocal_dir / filename).exists():
            continue
        mapping[(scene, line_no)] = filename
    return mapping


def _manifest_avatar_map(manifest: dict[str, Any]) -> dict[str, str]:
    figure_subdir = generation_limits()["assets"]["figure_subdir"]
    mapping: dict[str, str] = {}
    for image in manifest.get("images", []):
        if image.get("subdir") != figure_subdir:
            continue
        filename = str(image.get("filename", "")).strip()
        if not filename:
            continue
        stem = filename.removesuffix(".webp")
        suffix = stem.removeprefix("figure_")
        mapping[suffix] = f"miniavatar_{suffix}.webp"
    return mapping


def _find_avatar_by_suffix(character_id: str, suffix_to_avatar: dict[str, str]) -> str | None:
    if not character_id:
        return None
    for suffix, avatar in suffix_to_avatar.items():
        if character_id in suffix or suffix in character_id:
            return avatar
    return None


def _validate_scene_structure(job_dir: Path, scene_files: list[Path]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    relative_files = {_relative_scene_file(job_dir, path) for path in scene_files}
    names = {path.name for path in scene_files}
    limits = generation_limits()

    if "start.txt" not in names:
        issues.append(
            ValidationIssue(
                code="missing_start_scene",
                severity="error",
                file="public/game/scene",
                line=None,
                message="start.txt is required.",
            )
        )
    if len(scene_files) < limits["scenes"]["min"] or len(scene_files) > limits["scenes"]["max"]:
        issues.append(
            ValidationIssue(
                code="scene_count_out_of_range",
                severity="warning",
                file="public/game/scene",
                line=None,
                message=f"Scene count {len(scene_files)} is outside configured range {limits['scenes']['min']}-{limits['scenes']['max']}.",
            )
        )

    for path in scene_files:
        relative_file = _relative_scene_file(job_dir, path)
        if not re.match(r"^[a-z][a-z0-9_]*\.txt$", path.name):
            issues.append(
                ValidationIssue(
                    code="invalid_scene_filename",
                    severity="error",
                    file=relative_file,
                    line=None,
                    message="Scene filename must be lowercase snake_case and end with .txt.",
                )
            )
        lines = path.read_text(encoding="utf-8").splitlines()
        if not any(line.strip() for line in lines):
            issues.append(
                ValidationIssue(
                    code="empty_scene_file",
                    severity="error",
                    file=relative_file,
                    line=None,
                    message="Scene file is empty.",
                )
            )
        issues.extend(_validate_scene_references(relative_file, lines, names, relative_files))
        issues.extend(_validate_story_quality(relative_file, lines))
    return issues


def _validate_scene_references(
    relative_file: str,
    lines: list[str],
    scene_names: set[str],
    relative_files: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for line_no, line in enumerate(lines, start=1):
        for target in _scene_targets(line):
            normalized = target.replace("\\", "/").split("/")[-1]
            if normalized and normalized not in scene_names and target not in relative_files:
                issues.append(
                    ValidationIssue(
                        code="missing_scene_reference",
                        severity="error",
                        file=relative_file,
                        line=line_no,
                        message=f"Referenced scene does not exist: {target}",
                    )
                )
    return issues


def _validate_story_quality(relative_file: str, lines: list[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    story_lines = _story_content_lines(lines)
    scene_name = relative_file.replace("\\", "/").split("/")[-1]

    if scene_name.startswith("branch_") and len(story_lines) < 3:
        issues.append(
            ValidationIssue(
                code="thin_branch_scene",
                severity="warning",
                file=relative_file,
                line=None,
                message="Branch scene has fewer than 3 story lines; branches should show a visible consequence, not only change variables.",
            )
        )

    if scene_name.startswith("ending_") and len(story_lines) < 5:
        issues.append(
            ValidationIssue(
                code="thin_ending_scene",
                severity="warning",
                file=relative_file,
                line=None,
                message="Ending scene is very short; endings should usually have closure before the final verdict.",
            )
        )

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", ";")):
            continue

        choose_options = _parse_choose_options(stripped)
        if choose_options:
            targets: dict[str, list[str]] = {}
            for text, target in choose_options:
                targets.setdefault(target, []).append(text)
                for pattern, label in _TEMPLATE_PHRASES:
                    if re.search(pattern, text, flags=re.IGNORECASE):
                        issues.append(
                            ValidationIssue(
                                code="template_phrase",
                                severity="warning",
                                file=relative_file,
                                line=line_no,
                                message=f'Choice "{text}" contains template/meta wording ({label}); rewrite it as in-world dialogue or action.',
                            )
                        )
                if target.replace("\\", "/").split("/")[-1].startswith("ending_"):
                    issues.append(
                        ValidationIssue(
                            code="choice_direct_to_ending",
                            severity="warning",
                            file=relative_file,
                            line=line_no,
                            message=f'Choice "{text}" jumps directly to ending "{target}". Add a closure scene before non-rash endings.',
                        )
                    )
                if _looks_like_instruction_choice(text):
                    issues.append(
                        ValidationIssue(
                            code="instructional_choice_text",
                            severity="warning",
                            file=relative_file,
                            line=line_no,
                            message=f'Choice "{text}" reads like an instruction/summary. Prefer direct dialogue or an immediate action.',
                        )
                    )

            for target, texts in targets.items():
                if len(texts) > 1:
                    issues.append(
                        ValidationIssue(
                            code="shared_choice_target",
                            severity="warning",
                            file=relative_file,
                            line=line_no,
                            message=f'{len(texts)} choices share target "{target}". Use separate callback scenes before merging.',
                        )
                    )
            continue

        for pattern, label in _TEMPLATE_PHRASES:
            if re.search(pattern, stripped, flags=re.IGNORECASE):
                issues.append(
                    ValidationIssue(
                        code="template_phrase",
                        severity="warning",
                        file=relative_file,
                        line=line_no,
                        message=f"Line contains template/meta wording ({label}); rewrite it as in-world narration or dialogue.",
                    )
                )
    return issues


_TEMPLATE_PHRASES: tuple[tuple[str, str], ...] = (
    (r"\bplayer\b|玩家", "player"),
    (r"\bnode\b|节点", "node"),
    (r"\bbranch\b|分支", "branch"),
    (r"option\s*[ABCD]|选项\s*[A-DＡ-Ｄ]", "option label"),
    (r"push (?:things|it) to the extreme|把事情推到极端", "push to extreme"),
    (r"swallow (?:the )?words|把话咽回去", "swallow words"),
    (r"continue along|顺着.*继续|带着.*继续", "continue along"),
)


def _story_content_lines(lines: list[str]) -> list[str]:
    return [
        line
        for line in lines
        if line.strip()
        and not line.strip().startswith((
            "//",
            ";",
            "setVar:",
            "changeBg:",
            "changeFigure:",
            "setTransition:",
            "miniAvatar:",
            "bgm:",
            "playEffect:",
            "unlock",
            "pixi",
            "choose:",
            "changeScene:",
            "callScene:",
            "end",
        ))
    ]


def _parse_choose_options(line: str) -> list[tuple[str, str]]:
    choose_match = re.match(r"^choose\s*:\s*(?P<body>.*?);?\s*$", line)
    if not choose_match:
        return []
    options: list[tuple[str, str]] = []
    for option in choose_match.group("body").split("|"):
        parts = option.split(":")
        if len(parts) < 2:
            continue
        text = ":".join(parts[:-1]).strip()
        target = parts[-1].strip()
        if text and target:
            options.append((text, target))
    return options


def _looks_like_instruction_choice(text: str) -> bool:
    instruction_prefixes = (
        "说",
        "问",
        "让",
        "声明",
        "告诉",
        "询问",
        "继续问",
        "选择",
        "say ",
        "ask ",
        "tell ",
        "declare ",
        "choose ",
    )
    stripped = text.strip().lower()
    return any(stripped.startswith(prefix) for prefix in instruction_prefixes)


def _scene_targets(line: str) -> list[str]:
    stripped = line.strip()
    targets: list[str] = []
    choose_match = re.match(r"^choose\s*:\s*(?P<body>.*?);?\s*$", stripped)
    if choose_match:
        for option in choose_match.group("body").split("|"):
            parts = option.split(":")
            if len(parts) >= 2 and parts[-1].strip().endswith(".txt"):
                targets.append(parts[-1].strip())
    for command in ("changeScene", "callScene"):
        match = re.match(rf"^{command}\s*:\s*(?P<target>[^;\s]+)", stripped)
        if match and match.group("target").endswith(".txt"):
            targets.append(match.group("target"))
    return targets


def _relative_scene_file(job_dir: Path, scene_path: Path) -> str:
    return str(scene_path.relative_to(job_dir)).replace("\\", "/")


def _check_status(result: SceneValidationResult, code: str) -> str:
    if any(issue.code == code and issue.severity == "error" for issue in result.issues):
        return "failed"
    if any(issue.code == code for issue in result.issues):
        return "warning"
    if any(fix.code == code for fix in result.fixes):
        return "fixed"
    return "passed"
