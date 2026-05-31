# WebGAL Forge Project Flowchart

```mermaid
flowchart TD
  U["User opens frontend"] --> C["POST /jobs"]
  C --> J["jobs/{job_id}/job.json"]
  J --> R["POST /jobs/{job_id}/run"]
  R --> P["WebGALPipeline.run_all"]

  P --> N["1. Theme analysis<br/>emit_narrative_plan"]
  N --> NP["state/narrative_plan.json"]

  NP --> GD["2. Game structure design<br/>plain text LLM"]
  GD --> GDT["state/game_design.txt"]

  GDT --> DC["3. Story design<br/>plain text LLM"]
  DC --> GDC["state/game_design_completed.txt"]

  GDC --> AM["4. Asset preparation<br/>emit_asset_manifest"]
  AM --> MF["assets_manifest.json"]

  MF --> AG{"5. Asset generation<br/>options.generate_assets?"}
  AG -- "Yes" --> IMG["public/game/background/*.webp<br/>public/game/figure/*.webp"]
  AG -- "No" --> SKIP["stage marked skipped"]

  IMG --> RW["6. Insert assets<br/>plain text LLM"]
  SKIP --> RW
  RW --> WGT["state/game_design_webgal.txt"]
  RW --> SAL["state/script_assets.json"]

  WGT --> SC["Scene writing<br/>split [scene.txt] sections"]
  SC --> TXT["public/game/scene/*.txt"]
  SC --> CFG["public/game/config.txt"]
  SC --> SF["state/scene_files.json"]

  TXT --> V["7. Validation + deterministic repair"]
  V --> VR["state/validation_report.json"]
  VR --> OK{"errors == 0?"}

  OK -- "Yes" --> DONE["status=DONE"]
  OK -- "No" --> FAIL["status=FAILED"]
```

## Artifact Layout

```text
jobs/{job_id}/
  job.json
  assets_manifest.json
  state/
    narrative_plan.json
    game_design.txt
    game_design_completed.txt
    game_design_webgal.txt
    script_assets.json
    scene_files.json
    validation_report.json
    llm_traces/
      *.json
      stage_timings.jsonl
  public/game/
    config.txt
    background/*.webp
    figure/*.webp
    scene/*.txt
```

## Key Design Rule

Structured artifacts use backend contracts and schema validation. Long-form script writing stays as text generation. `run_scenes` writes final WebGAL scene files, and validation applies deterministic repairs before reporting remaining errors.
