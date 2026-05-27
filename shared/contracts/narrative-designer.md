# Narrative Designer Contract

Phase 1 of the pipeline. Designs the high-level narrative architecture. Produces structured planning artifacts consumed by Asset Planner and Scene Writer.

---

## Reads

| Source | Path |
|--------|------|
| Source material | (conversation) |
| Limits | `~/.claude/skills/webgal-game/shared/constraints/limits.md` |

---

## Produces (all to `current project path/state/`)

| File | Description |
|------|-------------|
| `characters.json` | 3-7 characters with name, role, personality, motivation, speech style, emotional arc |
| `variables.json` | Attitude variables (0-100 range) + event flags (0/1 boolean). Max 12 total. |
| `scene_graph.json` | All scenes as nodes + connections. Min 5 major scenes, max 15 total. |
| `branch_map.json` | All choice points with options and consequences. Min 5 choice points. Max depth 2. |
| `ending_matrix.json` | Exactly 5 endings with trigger conditions, emotional tone, narrative meaning |

---

## Output Schemas

See `~/.claude/skills/webgal-game/shared/schemas/` for exact JSON schemas. Minimal required fields:

### characters.json
```json
{
  "characters": [
    {
      "id": "tao_yuanming",
      "name": "陶渊明",
      "role": "protagonist",
      "personality": "...",
      "motivation": "...",
      "speech_style": "...",
      "emotional_arc": "..."
    }
  ]
}
```

### variables.json
```json
{
  "attitude_variables": [
    { "id": "empathy", "range": [0, 100], "description": "..." }
  ],
  "event_flags": [
    { "id": "shared_secret", "values": [0, 1], "description": "..." }
  ]
}
```

### scene_graph.json
```json
{
  "scenes": [
    { "id": "act1_office", "file": "act1_office.txt", "description": "..." }
  ],
  "connections": [
    { "from": "act1_office", "to": "act2_journey", "condition": null }
  ]
}
```

### branch_map.json
```json
{
  "branches": [
    {
      "id": "choice_visit_garden",
      "scene": "act3_homecoming",
      "options": [
        { "label": "去花园", "sets": { "visit_garden": 1 }, "next_scene": "act4_garden" },
        { "label": "留在家", "sets": {}, "next_scene": "act4_home" }
      ]
    }
  ]
}
```

### ending_matrix.json
```json
{
  "endings": [
    {
      "id": "ending_epilogue",
      "category": "default",
      "emotional_tone": "平静释然",
      "trigger": { "type": "fallback" },
      "narrative_meaning": "..."
    }
  ]
}
```

---

## Dependencies

None. This is the first Phase in the pipeline.

---

## Success Criteria

- All 5 JSON files written to `current project path/state/`
- All characters have distinct roles (no duplicates)
- Exactly 5 endings, all reachable
- All variables use 0/1 for booleans, not true/false
- Branch depth does not exceed 2
- No more than 12 global variables

---

## Boundaries

- Do NOT write .txt scene files
- Do NOT generate image prompts or asset descriptions
- Do NOT produce WebGAL syntax (choose/jumpLabel/etc.)
- Do NOT validate anything — that's the Validator's job
- This agent defines narrative architecture ONLY
