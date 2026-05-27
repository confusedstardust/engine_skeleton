# Function-Call Protocol

This skill replaces free-form phase outputs with forced function calls.

## Call Pattern

For each phase:

1. Load `references/openai-tools.json`.
2. Build an API-ready version with `python scripts/build_openai_tools.py references/openai-tools.json references/openai-tools.built.json`.
3. Select exactly one function from `references/openai-tools.built.json`.
4. Force `tool_choice` to that function.
5. Require `strict: true`.
6. Parse only the function arguments.
7. Validate the arguments against the matching schema in `references/schemas/`.
8. Write the validated artifact to disk.

If the model emits prose, ignores the function, or includes invalid arguments, retry the same phase with the validation error and the same forced function.

## Phase Functions

| Phase | Function | Schema | Output file |
|---|---|---|---|
| Narrative | `emit_narrative_plan` | `narrative_plan.schema.json` | `state/narrative_plan.json` |
| Assets | `emit_asset_manifest` | `asset_manifest.schema.json` | `assets_manifest.json` |
| Scenes | `emit_scene_batch` | `scene_batch.schema.json` | `public/game/scene/*.txt` |
| Validation | `emit_validation_report` | `validation_report.schema.json` | `state/validation_report.json` |
| Repair | `emit_repair_plan` | `repair_plan.schema.json` | applied patches + `state/repair_log.json` |

## Retry Policy

Use at most 2 schema retries per phase before reporting the blocked field list to the user.

The retry prompt should include only:

- the function name,
- the schema validation errors,
- the prior invalid arguments,
- the instruction to return a corrected function call.

Do not relax the schema during retry.

## Deterministic Gates

Function calls stabilize structure, but they do not prove semantic correctness. After schema validation, run deterministic gates:

- IDs referenced by branches, endings, and connections must exist.
- Exactly one character has role `protagonist`.
- Exactly one scene has `is_entry: true`.
- Exactly 5 endings exist, with one per category.
- Total global variables must be no more than 12.
- All scene files listed by the scene graph must be produced.
- Every referenced asset must exist on disk before scene generation completes.

## Suggested OpenAI API Shape

Use the built `references/openai-tools.built.json` entries as `tools`.

```json
{
  "model": "gpt-4.1",
  "tools": ["<one function definition from openai-tools.json>"],
  "tool_choice": {
    "type": "function",
    "function": { "name": "emit_narrative_plan" }
  }
}
```

Only trust `tool_calls[0].function.arguments` after JSON parsing and schema validation.
