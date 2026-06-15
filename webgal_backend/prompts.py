from __future__ import annotations

import json


STORY_TO_GAME_PRINCIPLES = """

    叙事改编总原则：
    - 写场景前，必须先在内部建立原作索引：事件链、角色卡、场景表、关键道具、可复用关键句。
    - 写场景前，必须先提取风格锚点：叙述温度、对白节奏、人称视角、节奏类型和禁用表达。
    - 每一个选项都必须从当前情境自然长出，不要写成测验题、真假题或明显的正确/错误选项。
    - 每一个选项都必须有玩家可读到的文本回响。变量变化、flag、跳转目标都不等于回响；下一屏必须明确承接玩家刚才的选择。
    - 分支可以汇合，但汇合时必须携带玩家状态，通过对白、可见选项、氛围、后果或变量条件体现差异。
    - 结局应主要由路径 flag 和关键决定驱动。数值可以影响语气和细节，但不能成为好/坏结局的唯一判定依据。
    - 选项不要直接跳到非草率结局。结局前必须先有 closure 收束场景：后果落地、人物反应、关系变化、物件/意象回收，然后再进入结局。
    - 不要压缩承载信息的内容。凡是承担剧情、关系、氛围或人物变化的过渡、对白轮次、场景质感和人物反应，都必须保留。
    """


STORY_DESIGN_RULES = """

    story_design 必须包含的设计层：
    1. 原作索引：压缩事件链，并标注因果目的；列出主要角色、主要场景、关键道具和重要句子。
    2. 风格锚点：给出可执行的叙述、对白、节奏、人称视角和禁区规则。
    3. 分支拓扑：说明选择发生在哪里，哪些是态度分支、路径分支、命运分支，在哪里汇合，每条分支为什么存在。
    4. 分支文学大纲：每条路线和每个结局线都要有自己的故事弧线，不能只给节点清单。
    5. 状态计划：设计主状态值、变量、flags、重要 flags 和结局触发条件。
    """


GAME_DESIGN_RULES = """

    场景设计规则：
    - 只有在 story_design 的结构已经稳定后，才开始输出具体 `[scene.txt]` 场景。
    - 必须从 `start.txt` 开始。开头前 2-3 个场景/屏幕内要建立时间、地点、玩家身份、目标和核心疑问。
    - 每一条 `choose` 的目标场景，开头都必须承接玩家刚才选择的动作或台词。
    - 如果多个选项最终要汇合，必须先为每个选项创建独立的短 callback 场景，再跳到共同场景。
    - 每个分支场景都必须有存在理由：新信息、关系变化、氛围变化，或后续会被引用的路径/flag。
    - 每条结局线在进入 ending 文件前，都必须有 closure 收束场景。ending 文件应该像最终判词，不要变成剧情摘要。
    - 场景文件名必须保持小写 snake_case，并以 `.txt` 结尾。
    """


INTERACTION_COMPLETION_RULES = """

    互动补全规则：
    - 不要只添加变量。每个选项之后都必须补出玩家可见的后果。
    - `choose` 选项应该是玩家此刻能做的直接动作，或能说出口的直接台词。
    - 选项中不要提到尚未在当前或相邻上下文中建立的人名、地点、道具或概念。
    - 避免模板词和元叙事词，例如“玩家”“节点”“分支”“选项A”“把事情推到极端”“把话咽回去”“顺着这条分支继续”。
    - 分支路径必须完整。即使是草率结局，也需要一小段因果链，不能一行文字就进入结局。
    - 必须保留已有 `[scene.txt]` 标题，并创建所有被引用的目标文件。
    """


WEBGAL_REWRITE_RULES = """

    WebGAL 改写质量规则：
    - 必须严格保留分支拓扑：choose 目标、变量变化、flags、结局走向和场景标题都不能改变含义。
    - 插入素材时，不要压缩或删除 callback 场景和 closure 场景。
    - 不要重命名、合并、拆分、新增或删除 `[scene.txt]` 段落。
    - 不要编造素材文件名，只能使用提供的资源列表。
    """

from .config import settings
from .generation_limits import generation_limits


def _required_int_option(options: dict, key: str, minimum: int, maximum: int) -> int:
    try:
        value = int(options[key])
    except (TypeError, ValueError):
        raise ValueError(f"options.{key} must be an integer")
    return max(minimum, min(maximum, value))


def _duration_minutes(options: dict) -> int:
    raw = str(options["duration"]).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise ValueError("options.duration must contain minutes, e.g. '20分钟'")
    return max(5, min(60, int(digits)))


def _generation_contract(options: dict) -> dict:
    limits = generation_limits()
    duration = _duration_minutes(options)
    character_count = _required_int_option(
        options,
        "character_count",
        1,
        8,
    )
    interactive_task_count = _required_int_option(
        options,
        "interactive_task_count",
        1,
        12,
    )

    duration_scene_targets = {
        5: (3, 4),
        10: (4, 6),
        20: (6, 9),
        40: (9, 14),
    }
    scene_range = duration_scene_targets.get(duration)
    if scene_range:
        scene_min, scene_max = scene_range
    else:
        scene_min = max(limits["scenes"]["min"], min(limits["scenes"]["max"], duration // 5 + 2))
        scene_max = max(scene_min, min(16, scene_min + 3))

    ending_count = max(2, min(5, 2 + interactive_task_count // 4))
    option_count = max(
        limits["branches"]["choice_options_min"],
        min(limits["branches"]["choice_options_max"], 3),
    )

    return {
        "duration": duration,
        "character_count": character_count,
        "interactive_task_count": interactive_task_count,
        "scene_min": scene_min,
        "scene_max": scene_max,
        "option_count": option_count,
        "variable_count": limits["variables"]["max_total"],
        "ending_count": ending_count,
        "line_min": limits["scenes"]["min_lines"],
        "line_max": limits["scenes"]["max_lines"],
        "line_length": limits["scenes"]["max_line_length"],
    }


def _contract_text(options: dict) -> str:
    contract = _generation_contract(options)
    return "\n".join(
        [
            "本次 UI 传入的生成约束（优先级高于默认 generation_limits.json）：",
            f"- 课堂主题：{options.get('classroom_topic') or '未指定'}",
            f"- 适用年级/课程体系：{options.get('grade') or '未指定'}",
            f"- 学习难度：{options.get('difficulty') or '未指定'}",
            f"- 教学目标：{options.get('teacher_goal') or '未指定'}",
            f"- 学生学习目标：{options.get('student_goal') or '未指定'}",
            f"- 游戏时长：{contract['duration']} 分钟",
            f"- 叙事模式：{options.get('narrative_mode') or '未指定'}",
            f"- 主要角色数量：严格围绕 {contract['character_count']} 个 AI 角色设计，除非源材料强烈要求，否则不要超出。",
            f"- 互动任务/关键选择点：目标为 {contract['interactive_task_count']} 个。",
            f"- 场景文件数量：建议 {contract['scene_min']} 到 {contract['scene_max']} 个，包含结局场景。",
            f"- 每个选择点建议 {contract['option_count']} 个选项。",
            f"- 结局数量：建议 {contract['ending_count']} 个。",
            f"- 角色配音：{'开启' if options.get('voice_enabled') or options.get('generate_tts') else '关闭'}，预设：{options.get('voice_preset') or '未指定'}。",
            f"- 生成图片素材：{'开启' if options.get('generate_assets') else '关闭'}。",
        ]
    )


def _narrative_source_context(options: dict) -> str:
    return "\n".join(
        [
            "课堂生成上下文：",
            f"- 课堂主题：{options.get('classroom_topic') or '未指定'}",
            f"- 适用年级/课程体系：{options.get('grade') or '未指定'}",
            f"- 学习难度：{options.get('difficulty') or '未指定'}",
            f"- 教学目标：{options.get('teacher_goal') or '未指定'}",
            f"- 学生学习目标：{options.get('student_goal') or '未指定'}",
            f"- 叙事模式：{options.get('narrative_mode') or '未指定'}",
        ]
    )


SYSTEM_PROMPT = """你是互动游戏项目中的叙事设计师，职责是设计故事架构
    - 故事是玩家体验的设计，所有设计必须围绕玩家体验曲线展开。
    - 理解->产生疑问->进入代入->获得意外->产生期待->迎来高潮->获得余韵，所有章节、场景、选项都必须服务于这条体验曲线。
    - 必须先明确：开端->发展->高潮->结局
    - 故事结构设计采用三幕式结构。
        第一幕：开端
            建立目标
            建立疑问
            建立动机
        第二幕：发展
            持续推进冲突
            深化角色关系
            提高投入感
        第三幕：高潮与结局
            兑现期待
            解决冲突
            完成角色成长
    开端必须完成三个目标 1.告诉玩家目标，如：拯救某人；2.让玩家知道如何影响故事，如：选项影响结局；3.创造核心问题，如：她为什么讨厌我？
    - 确定情感核心
    - 确定角色
    - 确定人物关系动态
    - 确定故事弧
    - 确定冲突结构
    - 确定故事发展脉络
    - 应聚焦于对叙事的理解和情感结构。"""


def narrative_prompt(source_material: str, options: dict[str, Any]) -> str:
    contract = _generation_contract(options)
    return f"""请严格按照 narrative_plan.schema.json 的结构返回的function argument。

    源材料：
    {_narrative_source_context(options)}

    用户提供的文本/知识材料：
    {source_material}

    请识别源材料中所包含的原著或文学作品，并基于原著内容进行分析与叙事设计，要符合原作历史背景和故事创作背景。

    如果源材料中不存在明确的文学作品，请自行提炼核心主题，并围绕该主题构建 narrative_plan。

    要求：
    根据目标游玩时长计算原著保留比例，本次游戏时长为{contract['duration']}分钟
    不要追求覆盖全部剧情，保证玩家在有限课堂场景内能够感受到原著最核心的主题、情感和冲突，即使只保留原著的局部情节，也可以视为成功改编
    结局为2-4个：
        第一优先级-真结局：原著结局或最贴近原著精神
        第二优先级-普通结局：合理完成故事但未达最佳
        第三优先级-分支结局：关键抉择的长期后果
        第四优先级-隐藏结局：原作暗示但未展开的可能性
    规划整体的"节奏曲线"，判定整体节奏型（慢热型/开场即高潮型/波浪型/阶梯上升型）
    叙事目的需要写明每个事件为什么必须存在：交代/建立/推进/伏笔/主题/呼应/节奏
    每个story_progression节点，必须判断其在未来互动改编中的地位：
        strtype为main时，表示该阶段所有玩家都应经历的核心故事阶段
        strtype为branch时，表示该阶段可以作为分支路径存在，可作为未来分支内容扩展的阶段，用于深化角色关系、展示不同观点或丰富体验
        branch类型占比30%，main类型占比70%
    围绕材料，发挥想象、积累创意
    对于narrative_structure节点，组织story_progression节点的各个事件，分析出主干情节和旁路分支，并且用Mermaid绘制出结构图：
        情节使用story_progression.id,结局使用endings.ending_type
        所有branch节点必须返回到某个main节点
        不允许branch直接形成独立故事线
    充实情节：开始、发展、高潮、结局
    开端要明确目的，通往高潮的过程：完成、推进、加深、额外
    角色数量{contract['character_count']}个；
    角色关系、情感基调、叙事弧线、冲突结构必须与原著主题一致
    叙事应为高沉浸度的叙事游戏剧情
    保持文学性与角色复杂度
    角色id必须基于角色姓名的英文snake_case，严禁泛化 id。
    relationships.with 只能引用 characters 数组中已经存在的真实角色id；禁止使用protagonist、player、main_character、mc等玩家/主角占位id"""


def story_design_prompt(narrative_plan: dict[str, Any], options: dict[str, Any]) -> str:
    contract = _generation_contract(options)
    return f"""你是一名视觉小说主笔和互动叙事设计师。请严格基于 narrative_plan.json，设计一份精彩、完整、有戏剧张力的 story_design。

    目标：
    - 这个阶段只做故事设计，不写 WebGAL 命令，不写素材 prompt，不拆成最终脚本。
    - 输出应当成为后续 game_design 阶段的故事蓝图。
    - 故事必须适合视觉小说：有清晰目标、持续悬念、关系推进、关键选择、多结局主题差异。

    必须包含以下部分：
    1. 故事一句话核心 logline。
    2. 玩家体验曲线：理解 -> 产生疑问 -> 代入 -> 获得意外 -> 形成期待 -> 迎来高潮 -> 获得余韵。
    3. 主角外在目标、内在缺口、最终成长或失败方式。
    4. 每个主要角色的戏剧功能、秘密/误解/欲望、与主角关系变化。
    5. 三幕式结构：第一幕建立目标、疑问、动机；第二幕推进冲突、深化关系、提高投入；第三幕兑现期待、解决冲突、完成成长。
    6. 关键选择设计：每个选择影响什么价值取向或角色关系，不要只是对错题。
    7. 多结局设计：每个结局对应不同主题判断和情感余味。
    8. 高光场景：至少 3 个必须被玩家记住的戏剧瞬间。
    9. 反复出现的意象、道具、主题句或声音，用来加强文学性和统一感。
    10. 给后续 game_design 的场景拆分建议，但不要输出 [xxx.txt] 标题。

    约束：
    - 不得新增 narrative_plan.json 中不存在的主要角色。
    - 不得背离 narrative_plan.json 的主题、人物关系和情感弧线。
    - 必须让故事有清晰的开端、发展、高潮、结局。
    - 只返回 story_design 正文，不要解释，不要 Markdown 代码块。

    本次生成参数：
    {_contract_text(options)}

    设计数量要求：
    - 围绕 {contract['character_count']} 个主要 AI 角色组织戏剧关系。
    - 设计约 {contract['interactive_task_count']} 个互动任务/关键选择点，选择应服务于课堂理解目标。
    - 结局建议 {contract['ending_count']} 个，必须有主题差异和课堂讨论价值。

    Raw options:
    {json.dumps(options, ensure_ascii=False, indent=2)}

    narrative_plan.json:
    {json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

    {STORY_TO_GAME_PRINCIPLES}
    {STORY_DESIGN_RULES}
    """


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

    
    立绘要求：
        - 角色立绘提示：描述角色+服装+表情+动作姿势+风格+光影+面部特征+年龄
        - 艺术风格关键词、光照和氛围描述要贯穿所有 prompt，注意每个人物一致性保持统一。
        - 角色立绘 prompt 必须包含“纯白背景”。
        - 角色立绘 prompt 必须包含“全身可见”。
        - 角色立绘 必须为彩色。
        - asset为立绘时，available_scene为可空
        - 角色立绘使用 subdir "{limits['assets']['figure_subdir']}"，size "{limits['assets']['figure_size']}"，filename 使用 figure_ 前缀。
        - 每个 characters 节点中的角色必须有一张立绘。
        样例：1. 清朝末期中国乡村少年，13岁，被阳光晒得黝黑的皮肤，健康有活力的神态，朴素的农民装束，中国传统乡村服饰，明亮的眼睛，自信的微笑，手持钢制叉子，中国教科书插画风格，教育类书籍插画，写实画风
              2. 女性角色，18岁，一头乌黑笔直的长发，浅棕色眼睛，白皙的皮肤，苗条的身材，美丽的容颜，日本夏季校服，白色短袖衬衫，藏青色百褶裙，红色蝴蝶结，温柔的微笑，温暖的眼神，脸颊微红，自然站立，一手提着书包，动漫风格，线条干净利落，眼神细腻，柔和的赛璐珞渲染
    背景要求：
        - 背景提示：描述时间+场景+空间结构+材质细节+关键物品+风格+光照+主要景观元素及氛围。
        - 背景图使用 subdir "{limits['assets']['background_subdir']}"，size "{limits['assets']['background_size']}"，filename 使用 bg_ 或 title_ 前缀。
        - CG 提示：描述场景构图、情感基调、光照。
        - CG 和背景图中可以出现路人，但严禁出现 characters 节点中的角色。
        - 背景和 CG prompt 必须包含 "no text"。
        - filename 必须为英文小写 snake_case，不要使用中文、空格或横杠。
        样例：1. 黄昏时分，太阳即将沉入地平线，天空呈现由橙金色向深蓝渐变的过渡光影。
                场景：一座被遗弃的沿海工业港口，海风缓慢吹动，环境安静且略带孤寂感。
                空间结构：前景为破旧的混凝土码头与生锈的金属栈桥，中景为半沉入水中的旧货轮与起重机剪影，远景为低矮城市天际线与海平面交界。整体呈纵深透视结构，引导视线向远处延展。
                材质细节：潮湿风化的混凝土表面带有裂纹与青苔，金属结构严重锈蚀并呈现层状剥落，海水表面有轻微波纹与油膜反光，空气中带有微粒雾化质感。
                关键物品：废弃起重机、断裂缆绳、半沉船体、散落集装箱、漂浮木箱。
                风格：写实电影感（cinematic realism），带轻微末世废土美学（post-apocalyptic industrial aesthetic），偏向概念艺术级别细节。
                光照：低角度暖色日落光作为主光源，辅以冷色天空散射光形成冷暖对比，局部金属反射高光明显，整体具有体积光与轻微雾气散射效果。
                主要景观元素：海港结构遗迹、工业机械残骸、海水与天空的强对比水平线、远处城市轮廓剪影。
                氛围：寂静、略带忧伤与时间流逝感，同时具有宏大而空旷的空间压迫感与诗意荒凉感。
              2.时间：清晨，薄雾初散，阳光从远山背后缓慢升起。
                场景：一处古代江南村落的河畔清景，带有课文插图式的叙事画面。
                空间结构：前景为静静流动的小河与木质石桥，中景为白墙黑瓦的民居与稻田，远景为连绵淡墨色山峦与天空渐变。整体采用层层递进的空间留白结构。
                材质细节：木桥略显潮湿，带轻微苔痕；瓦片有岁月风化的细微缺口；稻田呈现柔和起伏的麦浪质感。
                关键物品：渔船一只、岸边垂柳、远处炊烟、石板路、农具（简化描绘）。
                风格：语文教材插图风格 + 中国水墨写意 + 轻微写实融合，强调“画中有诗”。
                光照：柔和晨光，雾气散射光线，整体低对比度，高柔光过渡。
                主要景观元素及氛围：水乡、远山、炊烟、桥影、倒影，整体氛围宁静、含蓄、富有诗意与时间流动感。
        """


def game_design_prompt(narrative_plan: dict[str, Any], options: dict[str, Any], story_design_text: str | None = None) -> str:
    contract = _generation_contract(options)
    return f"""你是一名互动叙事游戏的场景编剧，请严格基于 narrative_plan.json进行下面的创作。

    请创作出 {contract['scene_min']} 到 {contract['scene_max']} 个场景，包含结局场景。

    场景设计注意事项：
    - 每个场景的对话行数在 {contract['line_min']} 到 {contract['line_max']} 之间
    - 从 start.txt 开始写。
    - 对话包括角色对话、内心独白、旁白，每一句不能超过{contract['line_length']}字
    - 内心独白不得超过3句，并且只能出现在主角
    - 旁白每个场景不得超过5句
    - 出现的角色来自于narrative_plan.json中
        - 必须先明确：开端->发展->高潮->结局
    - 故事结构设计采用三幕式结构。
        第一幕：开端
            建立目标
            建立疑问
            建立动机
        第二幕：发展
            持续推进冲突
            深化角色关系
            提高投入感
        第三幕：高潮与结局
            兑现期待
            解决冲突
            完成角色成长
    - 存在多个结局时：共同开端->共同发展->关键分歧点->角色路线->路线高潮->路线结局
    开端必须完成三个目标 1.告诉玩家目标，如：拯救某人；2.让玩家知道如何影响故事，如：选项影响结局；3.创造核心问题，如：她为什么讨厌我？
    - 场景之间要有明显过渡，确保故事连贯性
    - 命名规则示例：start.txt, act1_office.txt, ending_epilogue.txt。

    结局设计注意事项：
    - 为故事创建约 {contract['ending_count']} 个符合逻辑与情节的结局。
    - 原著结局或最贴近原著精神的结局优先级最高
    - 互动任务/关键选择点目标为 {contract['interactive_task_count']} 个，必须围绕教学目标和叙事模式设计。

    返回的结构下列内容：

    规则：
        - 场景格式为:[act1_meeting.txt]
        - 旁白格式为:>旁白
        - 角色内心活动为:(角色名 内心os) 注意只有主角可以有，且总内心os活动不宜超过5条
        - 结尾场景格式为[ending_xxx.txt]

    返回内容与下列示例格式严格一致
        示例：
            [ending_1.txt]
            >旁白:这是一个关于勇气与冒险的故事。"
            角色A:"我听说在那座山的另一边有一个神秘的宝藏，我们应该去寻找它！"
            角色B:"你说的没错!!"
            (角色C 内心os):其实我不太想去
    narrative_plan.json:
    {json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

    本次生成参数：
    {_contract_text(options)}

    story_design.txt:
    {story_design_text or ""}

    {STORY_TO_GAME_PRINCIPLES}
    {GAME_DESIGN_RULES}
    """


def game_design_completion_prompt(narrative_plan: dict[str, Any], game_design_text: str, options: dict[str, Any]) -> str:
    contract = _generation_contract(options)
    option_count = contract["option_count"]
    variable_count = contract["variable_count"]
    return f"""你是一名互动叙事游戏的场景编剧，根据以下对话，基于narrative_plan.json，在[start.txt]开始时初始化合适的变量，变量数为{variable_count}，在每个场景中合适的地方插入选项。确保选项符合以下设计原则：
    - 每个选项都必须影响至少一个变量
    - 选项不得明显存在正确或错误之分
    - 选项必须体现角色不同的人格立场
    - 选项数为{option_count}个
    - 玩家不同的选择会导致不同的结局
    - 严禁修改任何已有内容
    - 保持互动节奏。通常 1-5 句左右就让玩家点一次选项。
    - 每个选择都必须从当前场景自然长出
    - 每个后果都必须被世界认真承接。
    - 不要把所有选择都写成真假题。好的选项应该暴露玩家的态度、欲望、恐惧或误判。

    narrative_plan.json:
    {json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

    本次生成参数：
    {_contract_text(options)}

    Raw options:
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

    {STORY_TO_GAME_PRINCIPLES}
    {INTERACTION_COMPLETION_RULES}

    只返回补全后的完整文本"""


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
        - 只能使用上方列出的资源文件名，不要编造其他图片文件名
        - 背景资源只能通过 changeBg 引用
        - 立绘资源只能通过 changeFigure 引用
        - 根据每个场景的时间、地点、情绪，把 background_assets 分配到合适场景中；尽量让每个背景资源至少出现一次
        - 根据角色出场和对话上下文，把 figure_assets 分配到合适位置；如果资源数量允许，尽量让每个立绘资源至少出现一次
        - 场景开始处优先设置合适背景；角色进入、离开、情绪变化或对话焦点变化时，可以切换立绘
        - 切换背景和立绘时优先使用 -next，避免打断剧情节奏
        - 禁止执行任何以下操作：新增、删除、修改、合并或拆分 [xxx]
        - [xxx] 被视为 不可变语法标记
        - 必须保留原有剧情含义、角色关系、变量、choose 目标文件名和结局走向
        - 可以把非 WebGAL 变量变化整理成 syntax.md 中的合法形式
        - 每条 WebGAL 语句单独一行，并以英文分号 ; 结尾
        - 输出完整改写后的脚本

        游戏脚本:
        -----
        {game_design_completed_text}
        -----

        {WEBGAL_REWRITE_RULES}"""


def sound_effect_prompt(game_design_completed_text: str, sound_effect_assets: list[dict[str, Any]]) -> str:
    return f"""你是一名游戏音频编排师。对于文本中的场景、环境变化、重大事件、动作节点、情绪转折点：
    - 判断是否需要音频。
    - 从提供的音效资产中选择最匹配的资源。
    - 找到最适合作为触发点的文本锚点。
    - anchor 必须是剧本中的原文片段，最长不超过 20 个中文字符。
    - 不要为每一句都加音效，只选择真正能增强体验的位置。
    - 环境声优先使用 loop，短促事件音使用 once。


    playback 只能是以下值之一：
    - once：一次性音效。
    - loop：循环音效。

    返回要求：
    - 严格返回 JSON 数组
    - asset 必须严格来自音效资产列表中的 filename。
    - anchor 必须严格来自剧本原文，不要改写。
    - 同一个 anchor 最多安排一个音效。
    - 数量保持克制，通常每个场景 0-3 个。

    sample:
    [
    {{
        "anchor": "暮色笼罩荒村",
        "asset": "night_village.mp3",
        "playback": "loop"
    }}
    ]

    剧本为：
    -----
    {game_design_completed_text}
    -----

    音效资产为：
    {json.dumps(sound_effect_assets, ensure_ascii=False, indent=2)}
    """
