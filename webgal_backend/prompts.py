from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """You are a WebGAL visual novel generation engine.
You must call exactly the required function. Do not answer in prose.
All IDs must be lowercase snake_case. Keep display text separate from machine IDs.
Use 0/1 integers for event flags, never true/false for WebGAL game variables.
Respect all schema constraints and do not invent files outside the requested project layout."""


def narrative_prompt(source_material: str, options: dict[str, Any]) -> str:
    return f"""Create the complete narrative architecture for a WebGAL visual novel.

Source material:
{source_material}

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

Hard requirements:
- 3 to 7 characters.
- Exactly one protagonist.
- No more than 15 global variables total.
- 5 to 25 scenes including ending scenes.
- At least 1 meaningful choice point; use more only when the story needs them.
- Choice points must have 3 or 4 options.
- Exactly 5 endings: best, emotional, character, failure, default.
- Each ending must also have a matching scene in scenes[] with is_ending=true.
- Exactly one entry scene.
- Branch depth must not exceed 2.
- Do not generate WebGAL script text in this phase.
- Keep metadata, character, scene, and ending text fields concise (1-2 short sentences each) so the full JSON fits in one response."""


def asset_prompt(narrative_plan: dict[str, Any], base_dir: str, options: dict[str, Any]) -> str:
    return f"""Create an asset manifest derived from this narrative plan.

The manifest base_dir must be exactly:
{base_dir}

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

Narrative plan:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Hard requirements:
- One figure for every character.
- One background for every non-ending major scene where a new setting appears.
- Optional CGs only for meaningful event scenes.
- Character figure prompts must include "clean plain white background", "full body visible", and "no text, no watermark".
- Background and CG prompts must include "no text, no watermark".
- figure assets use subdir "figure" and size "1440x2560".
- background and cg assets use subdir "background" and size "2560x1440"."""


def scene_prompt(
    narrative_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    existing_assets: list[str],
    options: dict[str, Any],
) -> str:
    return f"""Create compact scene blueprints as structured data.

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

Narrative plan:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Asset manifest:
{json.dumps(asset_manifest, ensure_ascii=False, indent=2)}

Assets currently on disk:
{json.dumps(existing_assets, ensure_ascii=False, indent=2)}

Hard requirements:
- Produce one scene object for every scene in the narrative plan.
- scene.file must exactly match the narrative plan file.
- Do NOT write WebGAL syntax.
- Do NOT return full .txt file contents.
- Put story material in beats only: 8 to 18 short beats per scene.
- Each beat text must be plain Chinese prose or dialogue, no escaped script commands.
- Only reference asset filenames from the manifest or derived miniavatar filenames.
- Only reference variables from the narrative plan."""


def repair_prompt(
    validation_report: dict[str, Any],
    scenes: dict[str, str],
    narrative_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    cycle: int,
) -> str:
    return f"""Create a targeted repair plan for validation errors.

Repair cycle: {cycle}

Validation report:
{json.dumps(validation_report, ensure_ascii=False, indent=2)}

Narrative plan:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Asset manifest:
{json.dumps(asset_manifest, ensure_ascii=False, indent=2)}

Current scene files:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

Hard requirements:
- Repair only errors from the validation report.
- Touch only public/game/scene/*.txt files.
- Prefer exact find/replace repairs.
- Mark genuinely unfixable issues in unfixable.
- Do not rewrite unflagged scenes."""
