---
name: webgal-game-function-call
description: Generate structured WebGAL visual novels using strict OpenAI-style function calls and JSON Schema contracts. Use when converting source material into a WebGAL game, creating a branching visual novel, stabilizing LLM planning output, or replacing free-form WebGAL skill artifacts with schema-validated phase outputs.
---

# WebGAL Function-Call Pipeline

## Core Rule

All model-produced structure must come from function-call arguments that validate against the bundled JSON Schemas. Do not accept free-form JSON, Markdown tables, or prose as a phase artifact.

Load these resources before executing:

- `references/function-calls.md`: phase protocol and gate rules
- `references/openai-tools.json`: source function definitions
- `references/schemas/*.schema.json`: standalone validation schemas

## Workflow

Run the pipeline sequentially. A phase may start only after the previous phase passes its gate.

1. Narrative plan
   - Force the model to call `emit_narrative_plan`.
   - Validate the returned `narrative_plan` against `references/schemas/narrative_plan.schema.json`.
   - Write `state/narrative_plan.json`.
   - Optionally derive legacy files from the plan: `characters.json`, `variables.json`, `scene_graph.json`, `branch_map.json`, `ending_matrix.json`.

2. Asset manifest
   - Force the model to call `emit_asset_manifest`.
   - Validate against `references/schemas/asset_manifest.schema.json`.
   - Write `assets_manifest.json`.
   - Generate images with the existing WebGAL asset scripts or the local project equivalent.

3. Scene files
   - Force the model to call `emit_scene_batch`.
   - Validate against `references/schemas/scene_batch.schema.json`.
   - Write each `scenes[].content` to `public/game/scene/{scenes[].file}`.
   - Do not let the model write files directly before validation.

4. Validation
   - Prefer deterministic validation scripts for syntax, references, variables, endings, naming, and limits.
   - If using a model to classify validation output, force `emit_validation_report`.
   - Validate against `references/schemas/validation_report.schema.json`.
   - Write `state/validation_report.json`.

5. Repair
   - If `validation_report.summary.errors > 0`, force `emit_repair_plan`.
   - Validate against `references/schemas/repair_plan.schema.json`.
   - Apply only the listed repairs, then re-run validation.
   - Stop after 3 repair cycles and report remaining errors.

## Gate Policy

- Schema validation failure is a phase failure.
- Missing required files are phase failures.
- Unknown scene IDs, variable IDs, character IDs, or asset filenames are phase failures.
- Never infer a missing required field from prose outside the function-call arguments.
- Never continue with partially valid artifacts.

## Stability Defaults

- Use `tool_choice` to force exactly one function per phase.
- Use `strict: true` function definitions.
- Set `additionalProperties: false` on all object schemas.
- Run `scripts/build_openai_tools.py` before using tools with an API, so local schema references are inlined.
- Prefer enum fields over open-ended labels where categories are known.
- Use machine IDs in `snake_case`; keep display text separate from IDs.
- Keep cross-file references by ID first, filename second.

## Output Layout

Use this project layout unless the user provides a different one:

```text
state/
  narrative_plan.json
  validation_report.json
  repair_log.json
assets_manifest.json
public/game/
  background/
  figure/
  bgm/
  scene/
```

## Boundaries

- Do not generate WebGAL scene text during the narrative phase.
- Do not invent asset filenames after the asset manifest is validated.
- Do not let repair rewrite unflagged scenes.
- Do not use boolean `true` or `false` for WebGAL event flags; use `0` or `1`.
