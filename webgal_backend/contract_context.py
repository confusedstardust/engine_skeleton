from __future__ import annotations

import json
from pathlib import Path

from .config import settings


ORIGINAL_WEBGAL_SKILL_DIR = Path(__file__).resolve().parent.parent / "shared"

PHASE_RESOURCES = {
    "emit_narrative_plan": {
        "schema": "narrative_plan.schema.json",
        "contract": "narrative-designer.md",
        "constraints": ["limits.md", "naming.md"],
    },
    "emit_asset_manifest": {
        "schema": "asset_manifest.schema.json",
        "contract": "asset-planner.md",
        "constraints": ["limits.md", "naming.md"],
    },
    "emit_scene_batch": {
        "schema": "scene_batch.schema.json",
        "contract": "scene-writer.md",
        "constraints": ["limits.md", "naming.md", "syntax.md"],
    },
    "emit_validation_report": {
        "schema": "validation_report.schema.json",
        "contract": "validator.md",
        "constraints": ["limits.md", "naming.md", "syntax.md"],
    },
    "emit_repair_plan": {
        "schema": "repair_plan.schema.json",
        "contract": "repair-agent.md",
        "constraints": ["limits.md", "naming.md", "syntax.md"],
    },
}


GLOBAL_RULES = """Global non-negotiable rules:
- Return exactly one function call. Do not answer in prose.
- Function arguments must be valid JSON, not Markdown.
- Use lowercase snake_case machine IDs.
- Use Chinese display text when the source material is Chinese.
- Use 0/1 integer flags, never true/false for WebGAL variables.
- Keep IDs, filenames, variable names, and referenced assets consistent across phases.
- If a field can be inferred, still include it explicitly in the function arguments.
"""


def build_phase_context(function_name: str) -> str:
    resources = PHASE_RESOURCES.get(function_name)
    if not resources:
        return GLOBAL_RULES

    parts = [GLOBAL_RULES]
    parts.append("Current phase function: " + function_name)
    parts.append("Current phase JSON Schema:")
    parts.append(_compact_schema(resources["schema"]))

    contract = _read_original("contracts", resources["contract"])
    if contract:
        parts.append("Current phase contract:")
        parts.append(_trim_text(contract, 7000))

    constraint_chunks = []
    for file_name in resources["constraints"]:
        text = _read_original("constraints", file_name)
        if text:
            constraint_chunks.append(f"## {file_name}\n{_trim_text(text, 5000)}")
    if constraint_chunks:
        parts.append("Relevant hard constraints:")
        parts.append("\n\n".join(constraint_chunks))

    parts.append(_phase_specific_rules(function_name))
    return "\n\n".join(parts)


def _compact_schema(schema_name: str) -> str:
    path = settings.skill_dir / "references" / "schemas" / schema_name
    if not path.exists():
        return f"(schema missing: {schema_name})"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


def _read_original(folder: str, file_name: str) -> str:
    path = ORIGINAL_WEBGAL_SKILL_DIR / folder / file_name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _trim_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...(truncated; obey the same rules)..."


def _phase_specific_rules(function_name: str) -> str:
    if function_name == "emit_narrative_plan":
        return """Narrative phase additions:
- Keep total scenes including endings <= 25.
- Create exactly 5 endings: best, emotional, character, failure, default.
- Include ending scenes in scenes[] with is_ending=true and file fields.
- Entry scene should normally be file=start.txt.
- At least 1 choice point is acceptable; 3 is preferred for richer stories.
- Do not create WebGAL script text here."""
    if function_name == "emit_asset_manifest":
        return """Asset phase additions:
- Every character must have exactly one figure asset.
- Use bg_ prefix for backgrounds, figure_ prefix for sprites, cg_ prefix for event CGs.
- Sprite prompts must include: clean plain white background, full body visible, no text, no watermark."""
    if function_name == "emit_scene_batch":
        return """Scene phase additions:
- Return compact blueprints, not complete WebGAL script files.
- beats[].text must be plain story prose/dialogue only.
- Do not include commands like changeBg, callScene, miniAvatar, sleep, bgi_fadeIn, or JavaScript-style calls in beats.
- Backend will render WebGAL syntax deterministically."""
    if function_name == "emit_repair_plan":
        return """Repair phase additions:
- Only repair errors listed in validation_report.
- Touch only public/game/scene/*.txt files.
- Prefer exact find/replace patches."""
    return ""
