from __future__ import annotations

import json

from .config import settings
from .generation_limits import generation_limits, prompt_limits_text


PHASE_RESOURCES = {
    "emit_narrative_plan": {
        "schema": "narrative_plan.schema.json",
    },
    "emit_asset_manifest": {
        "schema": "asset_manifest.schema.json",
    },
}


GLOBAL_RULES = """Global non-negotiable rules:
- Return only the requested structured artifact. Do not answer in prose.
- Function arguments or JSON text must be valid JSON, not Markdown.
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
    parts.append(_phase_specific_rules(function_name))
    return "\n\n".join(parts)


def _compact_schema(schema_name: str) -> str:
    path = settings.contracts_dir / "schemas" / schema_name
    if not path.exists():
        return f"(schema missing: {schema_name})"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return json.dumps(schema, ensure_ascii=False, separators=(",", ":"))


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
    return ""
