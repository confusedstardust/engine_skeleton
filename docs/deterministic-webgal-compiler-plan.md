# Deterministic WebGAL compiler migration

## Decision

LLMs remain responsible for narrative and semantic production decisions. Final
WebGAL syntax is produced by a deterministic compiler from reviewed structured
artifacts.

```text
narrative/game-design LLM
          |
          v
game_design_completed.json ----+
assets_manifest.json -----------+--> script compile plan --> WebGAL text
narrative_plan.json ------------+            |                   |
                                              v                   v
                                      human-readable audit   existing validator
```

## What already exists

- `game_design_completed.json` already stores scenes, typed lines and choice targets.
- `assets_manifest.json` already stores filenames, subdirectories and scene bindings.
- `game_design.render_scene_line` already renders basic dialogue, narration and choices.
- `scene_validation.py` already repairs figure slots, cleanup, avatars, vocals and endings.
- Draft publication already copies only changed scopes and rolls back failed validation.

The migration reuses these boundaries rather than introducing a parallel game model.

## Delivery phases

### Phase 1: deterministic compilation

- Add a pure compiler for reviewed JSON artifacts.
- Persist `state/script_compile_plan.json` for placement inspection and warnings.
- Make deterministic compilation the default.
- Keep downstream sound effect, TTS, scene splitting and validation stages unchanged.

### Phase 2: complete explicit staging data

- Require `usage`, `character_id`, and `insert_before_line_id` on new asset manifests.
- Let asset review edit the main-background/CG role and CG insertion anchor.
- Add `character_id` to dialogue lines so display-name cleanup cannot break figure mapping.
- Reject unknown scene, character and line references before image generation.

### Phase 3: retire legacy rewrite

- Compile a representative corpus and compare reachable scenes, assets, dialogue order
  and validation reports with the pre-migration baseline.
- Remove the prompt, environment switch and LLM rewrite branch after the deterministic
  path meets the corpus gate.
- Keep compile-plan artifacts as production diagnostics.

## Compiler rules

1. A scene receives one reviewed `scene_background` at scene start.
2. An `event_cg` is inserted only at its explicit `insert_before_line_id`.
3. Figure assets bind to `character_id`; legacy manifests may infer it from `figure_<id>`.
4. Figures appear before their character's first dialogue. Slots are deterministic:
   one=center, two=left/right, three=center/left/right.
5. Cross-scene choice groups are merged into one terminal `choose` so later dialogue remains
   reachable; reviewed wordings are preserved even when several choices share a destination.
6. Ending scenes receive `end;`.
7. Invalid filenames and choice targets fail compilation instead of producing partial games.
8. More than three figure-backed speakers or unanchored extra backgrounds produce visible
   compile-plan warnings rather than silent arbitrary placement.

## Test coverage

```text
compile_webgal_script
  +-- valid reviewed artifacts
  |     +-- background at opening
  |     +-- anchored CG before exact line
  |     +-- figure mapping and 1/2/3-person slots
  |     +-- dialogue/narration escaping
  |     +-- cross-scene choice moved to terminal position
  |     `-- ending receives end;
  +-- legacy manifest compatibility
  |     +-- infer figure_<character_id>
  |     `-- warn and skip unanchored additional background
  `-- invalid artifacts
        +-- unsafe scene filename -> error
        +-- unsafe choice target -> error
        +-- empty scenes -> error
        `-- multiple cross-scene groups -> one terminal choice without losing reviewed wording

pipeline
  +-- deterministic mode never constructs an LLM client
  +-- compile plan and script artifacts are recorded
  `-- no final-script LLM client is constructed
```

## Failure modes

| Failure | Handling | User-visible evidence |
|---|---|---|
| Asset references an unknown line | Skip extra CG and record a compile warning | `script_compile_plan.json` |
| Choice target is unsafe | Stop the build with a compile error | Job error |
| Speaker display text no longer matches a character | Dialogue remains; stage figure is omitted | Compile plan lacks the binding |
| More than three speakers need stage figures | Render first three and record a warning | `script_compile_plan.json` |
| New compiler regresses a legacy title | Stop the build and repair structured artifacts | Compile error and validation report |

## NOT in scope

- Replacing narrative, dialogue or choice-generation LLM stages.
- Removing semantic LLM planning for sound effects or voices.
- Redesigning the asset-review UI in Phase 1.
- Changing WebGAL Engine runtime syntax.

## Implementation order

Sequential implementation, no parallelization opportunity: compiler core -> pipeline switch ->
schema/prompt bindings -> unit and pipeline tests -> corpus comparison -> legacy removal.
