# Asset Planner Contract

Phase 2 of the pipeline. Translates narrative planning artifacts into a concrete asset manifest, then generates all visual assets via the Python toolchain.

---

## Reads

| Source | Path | Description |
|--------|------|-------------|
| Characters | `shared/state/characters.json` | Every character needs a sprite + mini avatar |
| Scene graph | `shared/state/scene_graph.json` | Every scene needs a background |
| Limits | `~/.claude/skills/webgal-game/shared/constraints/limits.md` | Asset dimension and format constraints |
| Naming | `~/.claude/skills/webgal-game/shared/constraints/naming.md` | File naming conventions |

---

## Produces

### Step 1: Manifest

Write `assets_manifest.json` to the project root. Structure:

```json
{
  "base_dir": "c:/path/to/project/public/game",
  "model": "doubao-seedream-4-0-250828",
  "images": [
    {
      "filename": "bg_office",
      "subdir": "background",
      "size": "2560x1440",
      "prompt": "anime style, soft watercolor, ancient Chinese government office, wooden desk, scrolls on shelves, afternoon light through paper windows, no text, no watermark"
    },
    {
      "filename": "figure_tao_yuanming",
      "subdir": "figure",
      "size": "1440x2560",
      "prompt": "anime style, soft watercolor, full-body character portrait of Tao Yuanming, a middle-aged Chinese poet in simple white robes, standing pose, clean plain white background, gentle expression, no text, no watermark"
    },
    {
      "filename": "cg_homecoming",
      "subdir": "background",
      "size": "2560x1440",
      "prompt": "anime style, soft watercolor, CG illustration: Tao Yuanming returning to his rural home at sunset, no text, no watermark"
    }
  ]
}
```

**Field descriptions:**

| Field | Description |
|-------|-------------|
| `base_dir` | Absolute path to `public/game/` — script downloads to `{base_dir}/{subdir}/{filename}.webp` |
| `model` | ARK model ID. Default: `doubao-seedream-4-0-250828`. Change only if a different model is needed. |
| `images` | Flat array of all images (backgrounds, figures, CGs). No distinction at the manifest level. |
| `images[].filename` | Output filename **without** `.webp` extension. Script appends `.webp` automatically. |
| `images[].subdir` | Target subdirectory: `"background"` or `"figure"`. CGs go in `"background"`. |
| `images[].size` | `"2560x1440"` for backgrounds/CGs, `"1440x2560"` for character sprites. |
| `images[].prompt` | Generation prompt. Must include art style keywords for consistency. Background prompts: describe time, setting, atmosphere. Sprite prompts: describe face, age, clothing, expression, pose. Must include `"clean plain white background"` (needed for background removal). Must include `"no text, no watermark"`. |

**Naming rules:**
- Backgrounds: filename starts with `bg_` (e.g. `bg_office`)
- Character sprites: filename starts with `figure_` (e.g. `figure_tao_yuanming`)
- Event CGs: filename starts with `cg_` (e.g. `cg_homecoming`)
- Mini avatars: derived automatically by `make_avatar.py` — `figure_tao_yuanming.webp` → `miniavatar_tao_yuanming.webp`

### Step 2: Generate Assets

```bash
python ~/.claude/skills/webgal-game/script/generate_assets.py assets_manifest.json
```

Uses 火山引擎 ARK (豆包 Seedream) via OpenAI-compatible API. The script:
- Reads `base_dir` from manifest to locate `public/game/`
- Creates `background/` and `figure/` subdirectories if needed
- Downloads each generated image as `{base_dir}/{subdir}/{filename}.webp`
- Runs up to 3 parallel generations
- Skips already-existing files (safe to re-run on partial failures)

API key is read from `ARK_API_KEY` env var, or from `.env` file in `base_dir`, or uses the built-in default key.

### Step 3: Remove Backgrounds

```bash
python ~/.claude/skills/webgal-game/script/remove_bg.py public/game/figure/figure_*.webp
```

Uses `rembg` with `u2netp` model. Overwrites originals with lossless WebP (alpha channel preserved).

### Step 4: Generate Mini Avatars

```bash
python ~/.claude/skills/webgal-game/script/make_avatar.py public/game/figure/figure_*.webp
```

Produces `miniavatar_*.webp` in `public/game/figure/`. Naming: `figure_tao_yuanming.webp` → `miniavatar_tao_yuanming.webp`.

---

## Gate Check

Before proceeding to Phase 3, verify:
- Every background in the manifest exists as a .webp file in `public/game/background/`
- Every figure in the manifest exists as a .webp file in `public/game/figure/`
- Every figure has a corresponding `miniavatar_*.webp` in `public/game/figure/`

---

## Dependencies

Phase 1 (Narrative Designer) MUST complete before this Phase. All 5 planning JSONs must exist in `shared/state/`.

---

## Success Criteria

- `assets_manifest.json` exists at project root
- All listed backgrounds exist on disk at correct dimensions
- All listed figures exist on disk at correct dimensions
- All figures have background removed (transparent)
- All figures have mini avatars generated

---

## Boundaries

- Do NOT write scene files
- Do NOT modify narrative planning artifacts
- Do NOT skip the Python scripts — manual asset placement is NOT allowed
- If any script fails, stop and report the error; do NOT attempt manual workarounds
