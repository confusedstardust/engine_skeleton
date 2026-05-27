# Validator Contract

Phase 4 of the pipeline. Validates the complete game against all constraints. Produces a structured validation report consumed by the Orchestrator (and Repair Agent if needed).

---

## Reads

| Source | Path | Description |
|--------|------|-------------|
| All scene files | `public/game/scene/*.txt` | Every .txt file to validate |
| Characters | `shared/state/characters.json` | Verify speaker names |
| Variables | `shared/state/variables.json` | Verify variable names and types |
| Scene graph | `shared/state/scene_graph.json` | Verify all scenes exist |
| Branch map | `shared/state/branch_map.json` | Verify all branches are implemented |
| Ending matrix | `shared/state/ending_matrix.json` | Verify all endings are reachable |
| Syntax rules | `~/.claude/skills/webgal-game/shared/constraints/syntax.md` | Validate against critical syntax rules |
| Limits | `~/.claude/skills/webgal-game/shared/constraints/limits.md` | Validate against all hard limits |
| Naming | `~/.claude/skills/webgal-game/shared/constraints/naming.md` | Validate naming conventions |
| Assets (disk) | `public/game/background/`, `public/game/figure/` | Verify asset references resolve |

---

## Produces

`shared/state/validation_report.json`:

```json
{
  "summary": {
    "total_scenes": 10,
    "total_lines": 1500,
    "errors": 0,
    "warnings": 0,
    "passed": true
  },
  "checks": {
    "syntax": { "passed": true, "errors": [], "warnings": [] },
    "references": { "passed": true, "errors": [], "warnings": [] },
    "variables": { "passed": true, "errors": [], "warnings": [] },
    "endings": { "passed": true, "errors": [], "warnings": [] },
    "limits": { "passed": true, "errors": [], "warnings": [] },
    "naming": { "passed": true, "errors": [], "warnings": [] },
    "figures": { "passed": true, "errors": [], "warnings": [] }
  },
  "errors": [],
  "warnings": [],
  "unreachable_endings": [],
  "missing_assets": [],
  "undefined_variables": [],
  "undefined_speakers": [],
  "figure_violations": []
}
```

---

## Validation Checks

### 1. Syntax (`checks.syntax`)
- [ ] Every `callScene` is followed by `;`
- [ ] `end;` only in `start.txt` and ending files
- [ ] `jumpLabel` targets exist in the same file
- [ ] No `-when=` with multiple conditions (only single condition allowed)
- [ ] Boolean values are 0/1, never true/false
- [ ] `choose` options are pipe-separated, each has a label

### 2. References (`checks.references`)
- [ ] Every `changeBg:*.webp` filename exists in `public/game/background/`
- [ ] Every `changeFigure:*.webp` filename exists in `public/game/figure/`
- [ ] Every `miniAvatar:*.webp` filename exists in `public/game/figure/`
- [ ] Every `bgm:*.mp3` filename exists in `public/game/bgm/`
- [ ] Every `callScene:*.txt` target exists in `public/game/scene/`
- [ ] All speaker names match character IDs in `characters.json`

### 3. Variables (`checks.variables`)
- [ ] All `setVar` variable names are declared in `variables.json`
- [ ] All `-when=` variable names are declared in `variables.json`
- [ ] Attitude variables use numeric ranges (not true/false)
- [ ] No more than 12 global variables defined
- [ ] No undefined variables referenced

### 4. Endings (`checks.endings`)
- [ ] Exactly 5 endings in `ending_matrix.json`
- [ ] Every ending is reachable (trace path from start to end)
- [ ] Every ending file exists on disk and has ≥30 lines

### 5. Limits (`checks.limits`)
- [ ] 3-7 characters
- [ ] Branch depth ≤ 2
- [ ] Max 5 major branches
- [ ] Each scene 30-300 lines
- [ ] Min 5 choice points
- [ ] 3-4 options per choice point

### 6. Naming (`checks.naming`)
- [ ] Scene files use lowercase snake_case
- [ ] Background files use `bg_*` prefix
- [ ] Figure files use `figure_*` prefix
- [ ] Mini avatar files use `miniavatar_*` prefix

### 7. Figures (`checks.figures`)
- [ ] Every scene opens with `changeFigure:none -left -next;` and `changeFigure:none -right -next;` after `changeBg`
- [ ] Every named speaker has a `changeFigure` call before their first line in the scene
- [ ] Every scene ends with `changeFigure:none -left -next;` and `changeFigure:none -right -next;` before `callScene`
- [ ] Mid-scene `changeBg` does NOT have figure clears after it (only at open/close)

---

## Error Levels

| Level | Definition | Action |
|-------|-----------|--------|
| **Error** | Game will crash, won't run, or hard constraint violated | Must fix (invoke Repair Agent) |
| **Warning** | Does what's expected but deviates from best practice | Flag to user, optional fix |

---

## Dependencies

Phase 3 (Scene Writer) MUST complete before this Phase. All `.txt` scene files must exist.

---

## Success Criteria

- `validation_report.json` written to `shared/state/`
- `checks.figures` validates open-clear/show/close-clear for every scene
- `figure_violations` lists scenes missing figure lifecycle management
- `summary.errors == 0` means game is ready
- `summary.warnings > 0` means game runs but should be reviewed

---

## Boundaries

- Do NOT fix any issues — that's the Repair Agent's job
- Do NOT modify scene files or planning artifacts
- Report ONLY — never patch
