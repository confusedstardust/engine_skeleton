# Naming Conventions

All file names, variable names, and asset identifiers MUST follow these conventions. Consistency is required for validator automation to work.

---

## Scene Files

- Location: `public/game/scene/`
- Format: lowercase, underscore_separated, `.txt` extension
- Entry point MUST be `start.txt`
- Pattern: `actN_description.txt` or `ending_description.txt`

```
scene/
  start.txt                  ; Entry point: init vars, intro, callScene prologue
  act1_office.txt            ; Act 1
  act2_journey.txt           ; Act 2
  act3_homecoming.txt        ; Act 3
  act4_pastoral_life.txt     ; Act 4
  act5_climax.txt            ; Act 5
  ending_between_worlds.txt  ; Ending scene
  ending_epilogue.txt        ; Ending scene
```

---

## Asset Files — Game Directory

All assets live under `public/game/`.

### Backgrounds (`background/`)
- Pattern: `bg_<scene_or_location>.webp`
- Size: 2560×1440
- Examples: `bg_office.webp`, `bg_village.webp`, `bg_countryside_road.webp`

### Event CGs (`background/`)
- Pattern: `cg_<event_description>.webp`
- Size: 2560×1440
- Examples: `cg_garden_poetry.webp`, `cg_homecoming.webp`

### Title Art (`background/`)
- Pattern: `title_<game_name>.webp`
- Size: 2560×1440

### Character Sprites (`figure/`)
- Pattern: `figure_<character_name_snake_case>.webp`
- Size: 1440×2560
- Examples: `figure_tao_yuanming.webp`, `figure_old_farmer.webp`

### Mini Avatars (`figure/`)
- Pattern: `miniavatar_<character_name_snake_case>.webp`
- Size: 400×400 (square)
- MUST correspond 1:1 to a `figure_<name>.webp`
- Examples: `miniavatar_tao_yuanming.webp`, `miniavatar_old_farmer.webp`

### BGM (`bgm/`)
- Pattern: descriptive name, `.mp3` extension
- Example: `s_Title.mp3`

### Templates (`template/`)
- Engine UI templates, SCSS files
- Key file: `Stage/TextBox/textbox.scss` (avatar positioning)

---

## Variable Names

- Format: `snake_case`, lowercase
- Use descriptive names that reflect narrative meaning
- Boolean flags: use noun or verb_noun pattern
- Attitude variables: use single abstract noun

```
; Attitude variables (0-100 scale)
respect
empathy
openness
courage
trust

; Event flags (0/1)
shared_poetry
asked_performance
practical_help
shared_story
accepted_invitation
```

### Naming Rules
- No spaces, no special characters except underscore
- No Chinese characters in variable names
- No leading/trailing underscores
- Keep names under 30 characters
- Avoid reserved words: `true`, `false`, `if`, `else`, `and`, `or`, `not`
