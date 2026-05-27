# Repair Agent Contract

Phase 5 of the pipeline (conditional). Triggered by the Orchestrator when `validation_report.json` has `errors > 0`. Fixes violations in-place and reports back.

---

## Reads

| Source | Path | Description |
|--------|------|-------------|
| Validation report | `shared/state/validation_report.json` | List of errors to fix |
| All scene files | `public/game/scene/*.txt` | Files that may need repair |
| Characters | `shared/state/characters.json` | For fixing speaker name mismatches |
| Variables | `shared/state/variables.json` | For fixing variable name mismatches |
| Syntax rules | `~/.claude/skills/webgal-game/shared/constraints/syntax.md` | Reference for correct syntax |
| Limits | `~/.claude/skills/webgal-game/shared/constraints/limits.md` | Reference for hard limits |
| Asset manifest | `assets_manifest.json` | For fixing asset references |

---

## Produces (Modifies)

Modified scene files in `public/game/scene/`. Only files with errors are touched.

---

## Repair Strategy by Error Type

### Syntax Errors
| Error | Fix |
|-------|-----|
| `callScene` missing trailing `;` | Add `;` on the line after `callScene` |
| `end;` in sub-scene | Replace with `callScene:next_scene.txt;` + `;` |
| `jumpLabel` to undefined target | Find the correct label or create it |
| Multi-condition `-when=` | Refactor to accumulator pattern |
| Boolean uses true/false | Replace with 1/0 |

### Reference Errors
| Error | Fix |
|-------|-----|
| Missing background file | Search `public/game/background/` for closest match; if none, flag as unfixable |
| Missing figure file | Search `public/game/figure/` for closest match; if none, flag as unfixable |
| Missing mini avatar | Generate from figure using `make_avatar.py`; if figure missing too, flag as unfixable |
| Missing `callScene` target | Check if file exists with different casing; if genuinely missing, report |
| Unknown speaker name | Map to closest character ID from `characters.json` |
| Unused asset in manifest | Match filename keyword to scene (e.g. `cg_slipper_try` → the search scene). Find the emotional high point in that scene (e.g. the moment she slides her foot into the slipper). Insert `changeBg:filename.webp -next;` at that moment, preserving surrounding dialogue. |

### Variable Errors
| Error | Fix |
|-------|-----|
| Undefined variable in `setVar` | Add to `variables.json` if reasonable; otherwise replace with closest match |
| Undefined variable in `-when=` | Same as above |
| Wrong value type | Convert true/false to 1/0, clip attitude vars to [0,100] |

### Ending Errors
| Error | Fix |
|-------|-----|
| Unreachable ending | Trace path backward, add missing `jumpLabel` or `callScene` connection |
| Ending file too short | Add narration/closure content to reach ≥30 lines |

---

## Repair Rules

1. **Minimize changes**: Fix only what the error report flags. Don't rewrite scenes.
2. **Preserve intent**: When guessing a fix, prefer the option closest to the original text.
3. **Report unfixable**: If an error can't be resolved (e.g., missing asset with no close match), mark it `unfixable` and explain why.
4. **Track changes**: Append a summary of all changes made to `shared/state/repair_log.json`:

```json
{
  "cycle": 1,
  "changes": [
    {
      "file": "public/game/scene/act3_homecoming.txt",
      "line": 45,
      "error": "callScene missing ;",
      "fix": "Added ; after callScene"
    }
  ],
  "unfixable": []
}
```

---

## Dependencies

Phase 4 (Validator) MUST complete with `errors > 0` before this Phase runs.

---

## Success Criteria

After repair, orchestrator re-runs Validator. If `errors == 0`, repair was successful.

---

## Limits

- Maximum 3 repair cycles. If errors remain after 3 cycles, stop and ask the user.
- For unfixable errors: do NOT hallucinate fixes. Mark them honestly.
- Do NOT modify `shared/state/` planning artifacts — only `public/game/scene/*.txt` files.
