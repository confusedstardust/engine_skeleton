# Scene Writer Contract

Phase 3 of the pipeline. Writes all WebGAL `.txt` scene files based on the narrative architecture and generated assets.

---

## Reads

| Source | Path | Description |
|--------|------|-------------|
| Characters | `shared/state/characters.json` | Who speaks, speech style, emotional arc |
| Variables | `shared/state/variables.json` | Which variables to set/check in scripts |
| Scene graph | `shared/state/scene_graph.json` | Which files to create, flow between them |
| Branch map | `shared/state/branch_map.json` | Choice points and variable logic |
| Ending matrix | `shared/state/ending_matrix.json` | Ending triggers and conditions |
| Syntax rules | `~/.claude/skills/webgal-game/shared/constraints/syntax.md` | WebGAL syntax reference and critical rules |
| Limits | `~/.claude/skills/webgal-game/shared/constraints/limits.md` | File and content size limits |
| Assets (disk) | `public/game/background/`, `public/game/figure/` | Verify which asset filenames exist before referencing them |
| Asset manifest | `assets_manifest.json` | Complete list of all generated assets — every entry MUST be used in at least one scene |

---

## Produces

All `.txt` scene files in `public/game/scene/`.

The file list is derived from `scene_graph.json`. Each scene node with a `file` field must produce exactly one `.txt` file.

### File Structure Convention

Every scene file should follow this pattern:

```
; [Scene Name]
; Characters present: [list]

; --- Entry point ---
changeBg:bg_xxx.webp -next;
bgm:music.mp3 -volume=80;

; --- Opening narration ---
:旁白内容;

; --- Dialogue ---
Speaker:对话内容;

; --- Choice point (if applicable) ---
setVar:flag_name=1;
choose:选项A:labelA|选项B:labelB|选项C:labelC;
label:labelA;
...
jumpLabel:next_scene_converge;
label:labelB;
...
jumpLabel:next_scene_converge;
label:labelC;
...
label:next_scene_converge;

; --- Scene transition ---
callScene:next_scene.txt;
;
```

### Asset Utilization Rule (MANDATORY)

Before writing begins, read `assets_manifest.json` and create a checklist from every entry in `images[]`. The checklist format is:

```
[ ] bg_cinderella_home
[ ] bg_garden
[ ] figure_cinderella
[ ] cg_fairy_transformation
...
```

As each scene is written, mark off assets as they are referenced via `changeBg`, `changeFigure`, or `miniAvatar`. When all scenes are written, the checklist MUST be empty. If any assets remain unchecked, go back and find the appropriate scene to insert them — do NOT leave assets unused.

A CG with `cg_slipper_try` in the filename belongs in the scene where the slipper is tried on. A figure belongs in any scene where that character speaks. This mapping from filename to scene is straightforward — match the action/character in the filename to the scene description in `scene_graph.json`.

1. Every `callScene` MUST be followed by `;` on its own line to prevent fall-through
2. `end;` is ONLY used in the main scene (`start.txt`) or ending files. Never use it in sub-scenes called via `callScene`.
3. `jumpLabel` only works within the same file. Use `callScene` for cross-file navigation.
4. Speaker names MUST match the character `name` field from `characters.json`.
5. Asset filenames in `changeBg`/`changeFigure` MUST match actual filenames on disk.
6. Every `choose` option MUST lead to unique content before converging.
7. For `changeFigure`: use `-left` or `-right` to specify position. Use `-next` for instant transition (omit for fade).

### Avatar Rule

When a character first speaks in a scene, or when the speaker changes, include `miniAvatar`:

```
miniAvatar:miniavatar_tao_yuanming.webp;
陶渊明:采菊东篱下，悠然见南山。;
```

### Figure Lifecycle Rule (MANDATORY)

`changeBg` does NOT clear figures. Every scene is self-contained:

1. **Clear first.** After `changeBg`, clear all positions:
   ```
   changeFigure:none -left -next;
   changeFigure:none -right -next;
   ```
2. **Show before speak.** Every named speaker MUST have `changeFigure` before their first line.
3. **Clear last.** Before `callScene`, clear all positions (same two lines as step 1).

Exception: mid-scene `changeBg` does not require re-clearing. One clear at open, one at close.

---

## Dependencies

Phase 2 (Asset Planner) MUST complete before this Phase. All asset files must exist on disk so the writer can verify filenames.

---

## Success Criteria

- Every scene node in `scene_graph.json` has a corresponding `.txt` file
- Every `.txt` file is at least 30 lines
- No `.txt` file exceeds 300 lines
- All `changeBg`/`changeFigure`/`miniAvatar` references point to existing files
- All speaker names match `characters.json`
- All variable names match `variables.json`
- All endings are reachable via valid choice paths
- `start.txt` exists and is the entry point
- `end;` only appears in `start.txt` and ending scene files
- Every scene opens with figure clear, shows needed figures before dialogue, clears before `callScene`
- Every asset in `assets_manifest.json` is referenced in at least one scene file (zero unused assets)

---

## Boundaries

- Do NOT modify narrative planning artifacts
- Do NOT generate or modify assets
- Do NOT validate — that's the Validator's job (Phase 4)
- Reference ONLY assets that exist on disk — never invent filenames
