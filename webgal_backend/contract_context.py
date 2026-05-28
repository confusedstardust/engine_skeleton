from __future__ import annotations

import json
from pathlib import Path

from .config import settings
from .generation_limits import generation_limits, prompt_limits_text


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

    if function_name == "emit_narrative_plan":
        return "\n\n".join(
            [
                "Current phase function: " + function_name,
                "Current phase JSON Schema:",
                _compact_schema(resources["schema"]),
                _phase_specific_rules(function_name),
            ]
        )

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
    limits = generation_limits()
    if function_name == "emit_narrative_plan":
        return f"""Configured generation limits override any copied contract examples above:
{prompt_limits_text()}

Narrative phase additions:
- Return only the high-level narrative design described by the schema.
- Do not create scene files, variables, branches, endings, asset prompts, or WebGAL script text here.
- story_progression should be a compact phase outline; backend will expand it into internal scene structure later.
- Keep text fields concise but specific."""
    if function_name == "emit_asset_manifest":
        return f"""Configured generation limits override any copied contract examples above:
- Figure assets: subdir {limits['assets']['figure_subdir']}, size {limits['assets']['figure_size']}.
- Background/CG assets: subdir {limits['assets']['background_subdir']}, size {limits['assets']['background_size']}.

Asset phase additions:
- Every character must have exactly one figure asset.
- Use bg_ prefix for backgrounds, figure_ prefix for sprites, cg_ prefix for event CGs.
- Sprite prompts must include: clean plain white background, full body visible, no text, no watermark."""
    if function_name == "emit_scene_batch":
        return f"""Configured generation limits override any copied contract examples above:
- Use {limits['scene_batch']['beats_min']} to {limits['scene_batch']['beats_max']} beats per scene.
- Keep beat text <= {limits['scene_batch']['beat_text_max_length']} characters.
- Rendered scene files must be {limits['scenes']['min_lines']} to {limits['scenes']['max_lines']} lines.

Scene phase additions:
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
