from __future__ import annotations

import json
from typing import Any

from .generation_limits import character_limits_text, generation_limits


SYSTEM_PROMPT = """Your primary responsibility is deep narrative decomposition and interactive adaptation design.
,Analyze the source material as a narrative architect:
- identify emotional core
- identify characters
- identify relationship dynamics
- identify story arc
- identify conflict structure
- identify story progression
Focus first on narrative understanding and emotional structure."""


def narrative_prompt(source_material: str, options: dict[str, Any]) -> str:
    return f"""Return the narrative_plan function argument strictly according to narrative_plan.schema.json.

Source material:
{source_material}

Identify the literary works contained in the source material,Analysis and narration based on the original work; if the source material does not contain any literary works, identify the theme yourself.

Character limit:
{character_limits_text()}
Call emit_narrative_plan only."""


def asset_prompt(
    asset_context: dict[str, Any],
    base_dir: str,
    options: dict[str, Any],
    game_design_text: str | None = None,
    narrative_plan: dict[str, Any] | None = None,
) -> str:
    limits = generation_limits()
    narrative_block = json.dumps(narrative_plan or asset_context, ensure_ascii=False, indent=2)
    game_design_block = game_design_text or ""
    return f"""Create an asset manifest derived from this narrative plan.

The manifest base_dir must be exactly:
{base_dir}

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

narrative_plan.json:
{narrative_block}

game_design.txt:
{game_design_block}

Asset source ids:
{json.dumps(asset_context, ensure_ascii=False, indent=2)}

Hard requirements:
- One figure for every character.
- One background for every non-ending major scene where a new setting appears.
- Optional CGs only for meaningful event scenes.
- source_ref.type="character" must use character ids from Asset source ids.
- source_ref.type="scene" must use scene ids from Asset source ids.
- Character figure prompts must include "clean plain white background", "full body visible", and "no text, no watermark".
- Background and CG prompts must include "no text, no watermark".
- figure assets use subdir "{limits['assets']['figure_subdir']}" and size "{limits['assets']['figure_size']}".
- background and cg assets use subdir "{limits['assets']['background_subdir']}" and size "{limits['assets']['background_size']}"."""


def game_design_prompt(narrative_plan: dict[str, Any], options: dict[str, Any]) -> str:
    limits = generation_limits()
    return f"""你是一名互动叙事游戏的场景编剧，请严格基于 narrative_plan.json进行下面的创作。

narrative_plan.json:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

请创作出 {limits['scenes']['min']} 到 {limits['scenes']['max']} 个场景，包含结局场景。

场景设计注意事项：
- 每个场景的对话行数在 {limits['scenes']['min_lines']} 到 {limits['scenes']['max_lines']} 之间。
- 从 start.txt 开始写。
- 对话包括角色对话、内心独白、旁白。
- 出现的角色来自于narrative_plan.json中。
- 场景之间要有明显过渡，确保故事连贯性。
- 命名规则示例：start.txt, act1_office.txt, ending_epilogue.txt。

结局设计注意事项：
- 为故事创建 {limits['endings']['count']} 个符合逻辑与情节的结局。
- 原著结局或最贴近原著精神的结局优先级最高。

返回的结构下列内容：

规则：
    - 场景格式为:[场景名.txt]
    - 旁白格式为:>旁白
    - 角色内心活动为:(角色名 内心os)
    - 结尾场景格式为[ending_xxx.txt]

返回内容与下列示例格式严格一致
    示例：
        [xx.txt]
        >旁白:这是一个关于勇气与冒险的故事。"
        角色A:"我听说在那座山的另一边有一个神秘的宝藏，我们应该去寻找它！"
        角色B:"你说的没错!!"
        (角色C 内心os):其实我不太想去
"""


def game_design_completion_prompt(narrative_plan: dict[str, Any], game_design_text: str, options: dict[str, Any]) -> str:
    limits = generation_limits()
    option_count = limits["branches"]["choice_options_min"]
    variable_count = limits["variables"]["max_total"]
    return f"""你是一名互动叙事游戏的场景编剧，请根据以下对话内容，基于narrative_plan.json，在start.txt开始时初始化合适的变量，变量数为{variable_count}，在每个场景中合适的地方插入选项。确保选项符合以下设计原则：
- 每个选项都必须影响至少一个变量
- 选项不得明显存在正确或错误之分
- 选项必须体现角色不同的人格立场，而不仅仅是外观上的替换
- 选项数为{option_count}个
- 玩家不同的选择会导致不同的结局

narrative_plan.json:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

变量的格式为：
        初始化：setVar:health=0;
                setVar:experience=0;
选项的格式为:
        choose:喝下中药:branch_1.txt|倒掉中药:branch_2.txt;

并且为每个分支书写适合上下文的内容，确保故事的连贯性和逻辑性。创作的内容包含在下面的-----内：

eg:
-----
[branch_1.txt]
health+10
角色A:"把药给我吧，我要全喝完"
角色B:"你很快会恢复健康的！"
(角色A 内心os):"药好苦啊"


[branch_2.txt]
experience+10
角色A:"我觉得这药太苦了，我不想喝了"
角色B:"没关系，我们可以试试其他方法。"
(角色A 内心os):"或许我的身体需要这个药，但我真的不想喝"
-----

需要补全的对话内容：
-----
{game_design_text}
-----

只返回补全后的完整文本。不要解释，不要使用 Markdown 代码块。"""


def scene_prompt(
    narrative_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    existing_assets: list[str],
    options: dict[str, Any],
) -> str:
    limits = generation_limits()
    return f"""Create compact scene blueprints as structured data.

Options:
{json.dumps(options, ensure_ascii=False, indent=2)}

Narrative plan:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Asset manifest:
{json.dumps(asset_manifest, ensure_ascii=False, indent=2)}

Assets currently on disk:
{json.dumps(existing_assets, ensure_ascii=False, indent=2)}

Hard requirements:
- Produce one scene object for every scene in the narrative plan.
- scene.file must exactly match the narrative plan file.
- Do NOT write WebGAL syntax.
- Do NOT return full .txt file contents.
- Put story material in beats only: {limits['scene_batch']['beats_min']} to {limits['scene_batch']['beats_max']} short beats per scene.
- Each beat text must be at most {limits['scene_batch']['beat_text_max_length']} characters.
- Each beat text must be plain Chinese prose or dialogue, no escaped script commands.
- Only reference asset filenames from the manifest or derived miniavatar filenames.
- Only reference variables from the narrative plan."""


def repair_prompt(
    validation_report: dict[str, Any],
    scenes: dict[str, str],
    narrative_plan: dict[str, Any],
    asset_manifest: dict[str, Any],
    cycle: int,
) -> str:
    return f"""Create a targeted repair plan for validation errors.

Repair cycle: {cycle}

Validation report:
{json.dumps(validation_report, ensure_ascii=False, indent=2)}

Narrative plan:
{json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

Asset manifest:
{json.dumps(asset_manifest, ensure_ascii=False, indent=2)}

Current scene files:
{json.dumps(scenes, ensure_ascii=False, indent=2)}

Hard requirements:
- Repair only errors from the validation report.
- Touch only public/game/scene/*.txt files.
- Prefer exact find/replace repairs.
- Mark genuinely unfixable issues in unfixable.
- Do not rewrite unflagged scenes."""
