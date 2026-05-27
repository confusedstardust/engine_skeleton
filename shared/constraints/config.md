# Config File Constraints

`public/game/config.txt` is the game's metadata entry. It MUST be fully updated when building a new game. Partial updates are forbidden — if you touch one field, verify all.

---

## Mandatory Fields

| Field | Rule | Example |
|-------|------|---------|
| `Game_name` | Chinese title matching the game's theme | `归去来兮` |
| `Title_img` | Background or CG that fits the game's theme, must exist in `background/` | `cg_homecoming_sunset.webp` |
| `Game_Logo` | Protagonist's mini avatar, must exist in `figure/` | `miniavatar_tao_yuanming.webp` |

---

## Rules

1. **No default assets.** `WebGAL_New_Enter_Image.webp` and `WebGalEnter.webp` are engine defaults — never leave them in a finished game's config.

2. **All referenced files must exist.** `Title_img` must resolve to a file in `public/game/background/`. `Game_Logo` must resolve to a file in `public/game/figure/`.

3. **Update time.** Config MUST be finalized after Phase 2 (assets generated) and before Phase 3 completes (scene writer finishes). The orchestrator is responsible for verifying this.

4. **If you change Game_name, you MUST also check Title_img and Game_Logo.** Touching one config field triggers a full config audit.
