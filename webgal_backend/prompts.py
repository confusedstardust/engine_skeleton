from __future__ import annotations

import json
from typing import Any

from .config import settings
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
    return f"""请严格按照 narrative_plan.schema.json 的结构返回的function argument。

    源材料：
    {source_material}

    请识别源材料中所包含的原著或文学作品，并基于原著内容进行分析与叙事设计，要符合的历史背景。

    如果源材料中不存在明确的文学作品，请自行提炼核心主题，并围绕该主题构建 narrative_plan。

    角色数量限制：
    {character_limits_text()}

    要求：

    不得添加 schema 未定义字段
    不得输出解释说明
    所有字段必须完整且语义合理
    角色关系、情感基调、叙事弧线、冲突结构必须与原著主题一致
    叙事应适合改编为互动叙事游戏
    保持文学性与角色复杂度
    避免现代口语化表达破坏原作气质
    角色id必须基于角色姓名的英文snake_case，严禁泛化 id。
    仅调用 emit_narrative_plan。"""


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
    return f"""基于 narrative_plan.json 中的 characters 节点，并结合 game_design.txt 中每个场景的上下文，生成 assets_manifest.json。

    base_dir 必须严格等于：
    {base_dir}

    Options:
    {json.dumps(options, ensure_ascii=False, indent=2)}

    narrative_plan.json:
    {narrative_block}

    game_design.txt:
    {game_design_block}

    可参考的角色与场景信息：
    {json.dumps(asset_context, ensure_ascii=False, indent=2)}

    严格按照下列结构返回 asset_manifest，不要返回函数调用包装，不要返回 name/arguments：
    {{
    "asset_manifest": {{
        "base_dir": "{base_dir}",
        "model": "{settings.image_model}",
        "images": [
        {{
            "filename": "title_fortress_besieged",
            "subdir": "background",
            "size": "2560x1440",
            "prompt": "Chinese ink wash painting style, warm sepia tones, a lone figure standing on ancient Chinese city wall looking out at misty horizon, the city behind him and open road ahead, melancholic and philosophical atmosphere, 1930s Shanghai aesthetic, no text, no watermark",
            "available_scene": "act1_office.txt"
        }}
        ]
    }}
    }}

    生成要求：
    - 艺术风格关键词、光照和氛围描述要贯穿所有 prompt，注意每个人物一致性保持统一。
    - 背景提示：描述时间、场景、主要景观元素及氛围。
    - 角色立绘提示：描述面部特征、年龄、服装、表情、姿势。
    - 每个 characters 节点中的角色必须有一张立绘。
    - 角色立绘 prompt 必须包含“纯白背景”。
    - 角色立绘 prompt 必须包含“全身可见”。
    - 角色立绘 必须为彩色。
    - 角色立绘使用 subdir "{limits['assets']['figure_subdir']}"，size "{limits['assets']['figure_size']}"，filename 使用 figure_ 前缀。
    - 背景图使用 subdir "{limits['assets']['background_subdir']}"，size "{limits['assets']['background_size']}"，filename 使用 bg_ 或 title_ 前缀。
    - CG 提示：描述场景构图、情感基调、光照。
    - CG 和背景图中可以出现路人，但严禁出现 characters 节点中的角色。
    - asset为立绘时，available_scene为可空
    - 背景和 CG prompt 必须包含 "no text"。
    - filename 必须为英文小写 snake_case，不要使用中文、空格或横杠。"""


def game_design_prompt(narrative_plan: dict[str, Any], options: dict[str, Any]) -> str:
    limits = generation_limits()
    return f"""你是一名互动叙事游戏的场景编剧，请严格基于 narrative_plan.json进行下面的创作。

    请创作出 {limits['scenes']['min']} 到 {limits['scenes']['max']} 个场景，包含结局场景。

    场景设计注意事项：
    - 每个场景的对话行数在 {limits['scenes']['min_lines']} 到 {limits['scenes']['max_lines']} 之间。
    - 从 start.txt 开始写。
    - 对话包括角色对话、内心独白、旁白，每一句不能超过{limits['scenes']['max_line_length']}字。
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
    narrative_plan.json:
    {json.dumps(narrative_plan, ensure_ascii=False, indent=2)}
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


def webgal_script_rewrite_prompt(
    syntax_md: str,
    game_design_completed_text: str,
    background_assets: list[str],
    figure_assets: list[str],
) -> str:
    return f"""你是一个资深 WebGAL 剧本编辑助手，请根据以下语法规则，把游戏脚本改写为可执行的 WebGAL 脚本，并把可用背景和立绘资源以合适的形式自然加入整个剧本。

    语法规则:
    -----
    {syntax_md}
    -----

    可用背景资源 background_assets:
    {json.dumps(background_assets, ensure_ascii=False, indent=2)}

    可用立绘资源 figure_assets:
    {json.dumps(figure_assets, ensure_ascii=False, indent=2)}

    改写要求:
    - 只能使用上方列出的资源文件名，不要编造其他图片文件名。
    - 背景资源只能通过 changeBg 引用。
    - 立绘资源只能通过 changeFigure 引用。
    - 根据每个场景的时间、地点、情绪，把 background_assets 分配到合适场景中；如果资源数量允许，尽量让每个背景资源至少出现一次。
    - 根据角色出场和对话上下文，把 figure_assets 分配到合适位置；如果资源数量允许，尽量让每个立绘资源至少出现一次。
    - 场景开始处优先设置合适背景；角色进入、离开、情绪变化或对话焦点变化时，可以切换立绘。
    - 切换背景和立绘时优先使用 -next，避免打断剧情节奏。
    - 必须保留原有 [scene.txt] 段落名，不要新增、删除、改名场景段落。
    - 必须保留原有剧情含义、角色关系、变量、choose 目标文件名和结局走向。
    - 可以把非 WebGAL 格式的旁白、内心独白、变量变化整理成 syntax.md 中的合法 WebGAL 写法。
    - 每条 WebGAL 语句单独一行，并以英文分号 ; 结尾。
    - 输出完整改写后的脚本。
    - 不要输出解释。
    - 不要使用 Markdown 代码块。

    游戏脚本:
    -----
    {game_design_completed_text}
    -----"""


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
