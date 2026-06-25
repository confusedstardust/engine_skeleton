from __future__ import annotations

from .prompting import (
    SYSTEM_PROMPT,
    asset_prompt,
    game_design_completion_prompt,
    game_design_prompt,
    narrative_prompt,
    sound_effect_prompt,
    webgal_script_rewrite_prompt,
)
from .prompting.contract import (
    contract_text as _contract_text,
    duration_minutes as _duration_minutes,
    game_design_coverage_text as _game_design_coverage_text,
    generation_contract as _generation_contract,
    narrative_source_context as _narrative_source_context,
    required_int_option as _required_int_option,
)
from .prompting.rules import (
    GAME_DESIGN_RULES,
    INTERACTION_COMPLETION_RULES,
    STORY_TO_GAME_PRINCIPLES,
    WEBGAL_REWRITE_RULES,
)

__all__ = [
    "GAME_DESIGN_RULES",
    "INTERACTION_COMPLETION_RULES",
    "STORY_TO_GAME_PRINCIPLES",
    "SYSTEM_PROMPT",
    "WEBGAL_REWRITE_RULES",
    "asset_prompt",
    "game_design_completion_prompt",
    "game_design_prompt",
    "narrative_prompt",
    "sound_effect_prompt",
    "webgal_script_rewrite_prompt",
]
