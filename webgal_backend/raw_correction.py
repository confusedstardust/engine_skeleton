from __future__ import annotations

import re
from typing import Any


def correct_generated_raw_file(text: str, narrative_plan: dict[str, Any]) -> str:
    protagonist_name = _protagonist_name(narrative_plan)
    corrected_lines = [_correct_raw_line(line, protagonist_name) for line in text.splitlines()]
    return "\n".join(corrected_lines).rstrip() + "\n"


def _correct_raw_line(line: str, protagonist_name: str | None) -> str:
    stripped = line.strip()
    if not stripped:
        return line

    inner = _correct_inner_monologue_line(stripped, protagonist_name)
    if inner is not None:
        return inner

    narration = _correct_narration_marker(stripped)
    if narration is not None:
        return narration

    if _should_keep_raw_line(stripped):
        return line

    if ":" not in stripped and "\uFF1A" not in stripped:
        return f":{_ensure_no_trailing_semicolon(stripped)};"
    return line


def _correct_inner_monologue_line(line: str, protagonist_name: str | None) -> str | None:
    match = re.match(
        r"^\s*[\uFF1A:]?\s*[\(\uFF08](?P<speaker>[^()\uFF08\uFF09\uFF1A:]+?)\s*\u5185\u5FC3(?:os|OS)?[\)\uFF09]\s*(?:[\uFF1A:]\s*)?(?P<text>.*?)\s*;?\s*$",
        line,
    )
    if not match:
        match = re.match(
            r"^\s*[\uFF1A:]?\s*[\(\uFF08](?P<speaker>[^\s()\uFF08\uFF09\uFF1A:]+)\s+(?P<text>[^()\uFF08\uFF09]+?)[\)\uFF09]\s*;?\s*$",
            line,
        )
        if not match or match.group("speaker").strip() != protagonist_name:
            return None
    text = _strip_wrapping_quotes(match.group("text").strip())
    return f"intro:{_ensure_no_trailing_semicolon(text)};"


def _correct_narration_marker(line: str) -> str | None:
    if not line.startswith(">"):
        return None
    text = line[1:].strip()
    text = re.sub(r"^\u65C1\u767D\s*[\uFF1A:]?\s*", "", text)
    if not text:
        return ":;"
    return f":{_ensure_no_trailing_semicolon(text)};"


def _should_keep_raw_line(line: str) -> bool:
    if re.match(r"^\[[A-Za-z0-9_-]+\.txt\]\s*$", line):
        return True
    if re.match(r"^-{3,}$", line):
        return True
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*[+-]\s*\d+\s*;?$", line):
        return True
    command_prefixes = (
        "setVar:",
        "choose:",
        "changeScene:",
        "callScene:",
        "intro:",
        ":",
        "end",
    )
    return line.startswith(command_prefixes)


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'", "\u201C", "\u201D"}:
        return text[1:-1]
    if len(text) >= 2 and text[0] == "\u201C" and text[-1] == "\u201D":
        return text[1:-1]
    return text


def _ensure_no_trailing_semicolon(text: str) -> str:
    return text.rstrip().removesuffix(";").rstrip()


def _protagonist_name(narrative_plan: dict[str, Any]) -> str | None:
    characters = narrative_plan.get("characters", [])
    if not characters:
        return None
    name = str(characters[0].get("name", "")).strip()
    return name or None
