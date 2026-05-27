# Orchestrator Contract

Root entry point. Invoked when user triggers `/webgal-game`. Does NOT contain syntax reference or writing guides — those live in `~/.claude/skills/webgal-game/shared/constraints/`.

---

## Reads

| Source | Path |
|--------|------|
| User input | (conversation) |
| Constraints | `~/.claude/skills/webgal-game/shared/constraints/*.md` |
| Contracts | `~/.claude/skills/webgal-game/shared/contracts/*.md` |

---

## Gate Conditions

| Transition | Check |
|------------|-------|
| Phase 1 → 2 | All 5 planning JSONs exist in `shared/state/` |
| Phase 2 → 3 | All assets referenced in manifest exist in `public/game/background/` and `public/game/figure/` |
| Phase 3 → 3.5 | All .txt files from scene_graph exist in `public/game/scene/` |
| Phase 3.5 → 4 | BGM files referenced in scene files exist in `public/game/bgm/` |
| Phase 4 → 5 | If `validation_report.json` has `errors > 0`, invoke Repair Agent. If `warnings > 0`, flag to user. If clean, game is complete. |

---

## Produces

Nothing directly. The orchestrator delegates all artifact creation to sub-agents. Its output is a complete, validated WebGAL game

---

## Success Criteria

- All gate conditions pass
- Every ending is reachable via at least one valid choice path
- Every asset referenced in scene files exists on disk

---

## Failure Handling

| Failure | Action |
|---------|--------|
| Any Phase fails | Log error, stop pipeline, report to user |
| Validator finds errors | Invoke Repair Agent, re-validate. Max 3 repair cycles. |
| Repair cycle exceeds 3 | Stop and ask user for guidance |
| Asset generation fails | Stop and report which asset failed |
