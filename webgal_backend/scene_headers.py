"""Shared scene-header grammar for design, compilation, music and speech."""
from __future__ import annotations

import re

_HEADER_RE = re.compile(
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


def scene_header_matches(text: str) -> list[re.Match[str]]:
    return list(_HEADER_RE.finditer(text))


def scene_header_match(line: str) -> re.Match[str] | None:
    return _HEADER_RE.fullmatch(line.strip())


def scene_header_kind(match: re.Match[str]) -> str:
    return match.group("kind") or ("Ending" if match.group("filename").startswith("ending_") else "Scene")


def format_scene_header(filename: str) -> str:
    prefix = "Ending" if filename.replace("\\", "/").split("/")[-1].startswith("ending_") else "Scene"
    return f"{prefix}:{filename}"


def scene_sections(text: str) -> list[tuple[str, str]]:
    matches = scene_header_matches(text)
    return [
        (match.group("filename"), text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)].strip())
        for index, match in enumerate(matches)
    ]
