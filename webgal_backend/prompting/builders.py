from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..generation_limits import generation_limits
from ..scene_plan import build_scene_plan
from .contract import (
    contract_text,
    game_design_coverage_text,
    generation_contract,
    narrative_source_context,
)
from .rules import WEBGAL_REWRITE_RULES


def narrative_prompt(source_material: str, options: dict[str, Any]) -> str:
    contract = generation_contract(options)
    return f"""请严格按照 narrative_plan.schema.json 的结构返回的function argument。

    源材料:
    {narrative_source_context(options)}

    用户提供的文本/知识材料:
    {source_material}

    请识别源材料中所包含的原著或文学作品,并基于原著内容进行分析与叙事设计,要符合原作历史背景和故事创作背景。

    如果源材料中不存在明确的文学作品,请自行提炼核心主题,并围绕该主题构建 narrative_plan。

    要求:
    根据目标游玩时长计算原著保留比例,本次游戏时长为{contract['duration']}分钟
    不要追求覆盖全部剧情,保证玩家在有限课堂场景内能够感受到原著最核心的主题、情感和冲突,即使只保留原著的局部情节,也可以视为成功改编
    结局为2-4个:
        第一优先级-真结局:原著结局或最贴近原著精神
        第二优先级-普通结局:合理完成故事但未达最佳
        第三优先级-分支结局:关键抉择的长期后果
        第四优先级-隐藏结局:原作暗示但未展开的可能性
    规划整体的"节奏曲线",判定整体节奏型(慢热型/开场即高潮型/波浪型/阶梯上升型)
    叙事目的需要写明每个事件为什么必须存在:交代/建立/推进/伏笔/主题/呼应/节奏
    narrative_target 只能写在 story_progression 数组的每个节点内部,禁止在 narrative_plan 根对象添加 narrative_target 或其他 schema 未定义字段
    每个story_progression节点,必须判断其在未来互动改编中的地位:
        strtype为main时,表示该阶段所有玩家都应经历的核心故事阶段
        strtype为branch时,表示该阶段可以作为分支路径存在,可作为未来分支内容扩展的阶段,用于深化角色关系、展示不同观点或丰富体验
        branch类型占比30%,main类型占比70%
    围绕材料,发挥想象、积累创意
    对于narrative_structure节点,组织story_progression节点的各个事件,分析出主干情节和旁路分支,并且用Mermaid绘制出结构图:
        情节使用story_progression.id,结局使用endings.ending_type,绝对禁止捏造创造新的场景
        所有branch节点必须返回到某个main节点
        不允许branch直接形成独立故事线
    充实情节:开始、发展、高潮、结局
    开端要明确目的,通往高潮的过程:完成、推进、加深、额外
    角色数量{contract['character_count']}个;
    角色关系、情感基调、叙事弧线、冲突结构必须与原著主题一致
    叙事应为高沉浸度的叙事游戏剧情
    保持文学性与角色复杂度
    角色id必须基于角色姓名的英文snake_case,严禁泛化 id。
    relationships.with 只能引用 characters 数组中已经存在的真实角色id;禁止使用protagonist、player、main_character、mc等玩家/主角占位id"""


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
        return f"""基于 narrative_plan.json 中的 characters 节点,并结合由 game_design.json 渲染出的每个场景上下文,生成 assets_manifest.json。

        base_dir 必须严格等于:
        {base_dir}

        Options:
        {json.dumps(options, ensure_ascii=False, indent=2)}

        narrative_plan.json:
        {narrative_block}

        game_design.json 渲染文本:
        {game_design_block}

        可参考的角色与场景信息:
        {json.dumps(asset_context, ensure_ascii=False, indent=2)}

        严格按照下列结构返回 asset_manifest,不要返回函数调用包装,不要返回 name/arguments:
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

        
        立绘要求:
            - 角色立绘提示:描述角色+服装+表情+动作姿势+风格+光影+面部特征+年龄
            - 艺术风格关键词、光照和氛围描述要贯穿所有 prompt,注意每个人物一致性保持统一。
            - 角色立绘 prompt 必须包含“纯白背景”。
            - 角色立绘 prompt 必须包含“全身可见”。
            - 角色立绘 必须为彩色。
            - asset为立绘时,available_scene为可空
            - 角色立绘使用 subdir "{limits['assets']['figure_subdir']}",size "{limits['assets']['figure_size']}",filename 使用 figure_ 前缀。
            - 每个 characters 节点中的角色必须有一张立绘。
            样例:1. 清朝末期中国乡村少年,13岁,被阳光晒得黝黑的皮肤,健康有活力的神态,朴素的农民装束,中国传统乡村服饰,明亮的眼睛,自信的微笑,手持钢制叉子,中国教科书插画风格,教育类书籍插画,写实画风
                2. 女性角色,18岁,一头乌黑笔直的长发,浅棕色眼睛,白皙的皮肤,苗条的身材,美丽的容颜,日本夏季校服,白色短袖衬衫,藏青色百褶裙,红色蝴蝶结,温柔的微笑,温暖的眼神,脸颊微红,自然站立,一手提着书包,动漫风格,线条干净利落,眼神细腻,柔和的赛璐珞渲染
        背景要求:
            - 背景提示:描述时间+场景+空间结构+材质细节+关键物品+风格+光照+主要景观元素及氛围。
            - 背景图使用 subdir "{limits['assets']['background_subdir']}",size "{limits['assets']['background_size']}",filename 使用 bg_ 或 title_ 前缀。
            - CG 提示:描述场景构图、情感基调、光照。
            - CG 和背景图中可以出现路人,但严禁出现 characters 节点中的角色。
            - 背景和 CG prompt 必须包含 "no text"。
            - filename 必须为英文小写 snake_case,不要使用中文、空格或横杠。
            样例:1. 黄昏时分,太阳即将沉入地平线,天空呈现由橙金色向深蓝渐变的过渡光影。
                    场景:一座被遗弃的沿海工业港口,海风缓慢吹动,环境安静且略带孤寂感。
                    空间结构:前景为破旧的混凝土码头与生锈的金属栈桥,中景为半沉入水中的旧货轮与起重机剪影,远景为低矮城市天际线与海平面交界。整体呈纵深透视结构,引导视线向远处延展。
                    材质细节:潮湿风化的混凝土表面带有裂纹与青苔,金属结构严重锈蚀并呈现层状剥落,海水表面有轻微波纹与油膜反光,空气中带有微粒雾化质感。
                    关键物品:废弃起重机、断裂缆绳、半沉船体、散落集装箱、漂浮木箱。
                    风格:写实电影感(cinematic realism),带轻微末世废土美学(post-apocalyptic industrial aesthetic),偏向概念艺术级别细节。
                    光照:低角度暖色日落光作为主光源,辅以冷色天空散射光形成冷暖对比,局部金属反射高光明显,整体具有体积光与轻微雾气散射效果。
                    主要景观元素:海港结构遗迹、工业机械残骸、海水与天空的强对比水平线、远处城市轮廓剪影。
                    氛围:寂静、略带忧伤与时间流逝感,同时具有宏大而空旷的空间压迫感与诗意荒凉感。
                2.时间:清晨,薄雾初散,阳光从远山背后缓慢升起。
                    场景:一处古代江南村落的河畔清景,带有课文插图式的叙事画面。
                    空间结构:前景为静静流动的小河与木质石桥,中景为白墙黑瓦的民居与稻田,远景为连绵淡墨色山峦与天空渐变。整体采用层层递进的空间留白结构。
                    材质细节:木桥略显潮湿,带轻微苔痕;瓦片有岁月风化的细微缺口;稻田呈现柔和起伏的麦浪质感。
                    关键物品:渔船一只、岸边垂柳、远处炊烟、石板路、农具(简化描绘)。
                    风格:语文教材插图风格 + 中国水墨写意 + 轻微写实融合,强调“画中有诗”。
                    光照:柔和晨光,雾气散射光线,整体低对比度,高柔光过渡。
                    主要景观元素及氛围:水乡、远山、炊烟、桥影、倒影,整体氛围宁静、含蓄、富有诗意与时间流动感。
            """


def game_design_prompt(
    narrative_plan: dict[str, Any],
    options: dict[str, Any],
    scene_plan: dict[str, Any] | None = None,
    ) -> str:
        scene_plan = scene_plan or build_scene_plan(narrative_plan)
        contract = generation_contract(options)
        coverage_text = game_design_coverage_text(narrative_plan, scene_plan)
        return f"""你是一名互动叙事游戏的场景编剧,请严格基于 narrative_plan.json进行下面的创作。
        只允许创作每个场景名,对话,旁白和内心独白。严禁创作选择点和分支场景。

        场景设计注意事项:
        - 本阶段不根据游戏时长压缩场景数量,必须严格按照 scene_plan.json 全量生成所有场景。
        - 每个 scene_plan.scenes 条目必须对应一个独立 Scene,不允许把多个 source_node 合并进同一个场景。
        - 每个 scene_plan.endings 条目必须对应一个独立 Ending,不允许只在普通 Scene 中用几句话概括结局。
        - 每个场景的对话行数不超过{contract['line_min']}行
        - 从 Scene:start.txt 开始写。
        - 对话包括角色对话、内心独白、旁白,每一句不能超过{contract['line_length']}字
        - 角色台词行必须稳定使用 `角色名:台词正文`,冒号后直接写台词,不得写成 `角色名:(动作/语气)台词`
        - 动作、神态、语气提示不要写在角色台词行内;如果必须表现动作,请改写成独立旁白行 `>旁白:...`
        - 内心独白不得超过3句,并且只能出现在主角
        - 旁白每个场景不得超过5句
        - 出现的角色来自于narrative_plan.json中
            - 必须先明确:开端->发展->高潮->结局
        - 故事结构设计采用三幕式结构。
            第一幕:开端
                建立目标
                建立疑问
                建立动机
            第二幕:发展
                持续推进冲突
                深化角色关系
                提高投入感
            第三幕:高潮与结局
                兑现期待
                解决冲突
                完成角色成长
        开端必须完成三个目标 1.告诉玩家目标,如:拯救某人;2.让玩家知道如何影响故事,如:选项影响结局;3.创造核心问题,如:她为什么讨厌我？
        - 场景之间要有明显过渡,确保故事连贯性
        - 命名规则示例:普通场景 `Scene:start.txt`, `Scene:act1_office.txt`;结局场景 `Ending:ending_epilogue.txt`。

        返回的结构为下列内容:

        scene_plan.json(必须使用其中的 scene_file,不要自行改名;source_node/ending_type 只用于理解来源,不需要输出为注释):
        {json.dumps(scene_plan or {}, ensure_ascii=False, indent=2)}

        必须覆盖的场景清单:
        {coverage_text}

        规则:
            - 普通场景格式为:Scene:act1_meeting.txt
            - 不要输出 source_node 注释
            - 角色台词格式为:角色名:台词正文。错误示例:角色名:(叹息)台词正文
            - 旁白格式为:>旁白
            - 角色内心活动为:(角色名 内心os)
            - 结尾场景格式为Ending:ending_xxx.txt
            - 不要输出 ending_type 注释

        返回内容与下列示例格式严格一致
            示例:
                Scene:start.txt
                >旁白:这是一个关于勇气与冒险的故事。"
                角色A:我听说在那座山的另一边有一个神秘的宝藏,我们应该去寻找它！
                角色B:你说的没错！
                (角色C 内心os):其实我不太想去
                
                Ending:ending_1.txt
                >旁白:冒险结束后,他们终于明白了勇气真正的含义。"
        narrative_plan.json:
        {json.dumps(narrative_plan, ensure_ascii=False, indent=2)}

        本次生成参数:
        {contract_text(options)}
        """


def game_design_completion_prompt(
    narrative_plan: dict[str, Any],
    game_design_outline: dict[str, Any],
    options: dict[str, Any],
    scene_plan: dict[str, Any] | None = None,
) -> str:
    scene_plan = scene_plan or build_scene_plan(narrative_plan)
    contract = generation_contract(options)
    schema_example = {
        "choices_group": [
            {
                "id": "start_choice_1",
                "scene_file": "start.txt",
                "insert_index": 3,
                "content":"小白甩开小红的手，转身走开",
                "choices": [
                    {"text": "接过锄头", "target_scene_file": "phase1.txt"},
                    {"text": "稍作推辞", "target_scene_file": "phase2.txt"}
                ]
            }
                ]
        }
    return """你是一名互动叙事游戏的分支与选项设计师。你的任务是根据 Raw_Scene.json.connectable_pairs 中给出的可衔接场景关系,为当前场景插入互动选项和承接文本。

        返回要求:
        - 只返回严格 JSON
        - 不要新增、删除或改名任何 scene_file / ending_file
        - scene_file 必须来自 Raw_Scene.json.connectable_pairs[].source_scene_file
        - target_scene_file 必须来自同一个 choices_group 对应的 connectable_pairs[].target_scene_file,不要编造目标
        - insert_index 表示插入到当前场景 content 的第几行之后,0 表示插入在场景正文开头之后
        - 每组选项必须从当前scene_file的content中自然长出
        - 每组选项必须服务于 source_scene_file 到 target_scene_file 的衔接,不能违背 narrative_structure
        - content 写的是选项出现前的一句过渡旁白,用于把当前场景推到选择点
        - choices 可以返回字符串数组,也可以返回对象数组;如果能判断目标场景,优先返回 {{"text": "...", "target_scene_file": "..."}}
        - 页面展示选项时只展示 text,例如 choose: 接过锄头 | 稍作推辞; target_scene_file 只用于后续脚本跳转
        - 每个选项要能承接当前场景,应体现不同态度、情绪、欲望、恐惧或误判,不要明显分成正确/错误
        - 不要重写 source_content 或 target_content,只生成需要追加的 content 和 choices

        JSON 结构示例:
        {schema_example}
        Raw_Scene.json:
        {outline_json}
        """.format(
                schema_example=json.dumps(schema_example, ensure_ascii=False, indent=2),
                scene_plan_json=json.dumps(scene_plan or {}, ensure_ascii=False, indent=2),
                outline_json=json.dumps(game_design_outline, ensure_ascii=False, indent=2),
                contract_text=contract_text(options),
            )

def webgal_script_rewrite_prompt(
    syntax_md: str,
    game_design_completed_text: str,
    background_assets: list[str],
    figure_assets: list[str],
) -> str:
    return f"""你是一个资深 WebGAL 剧本编辑助手,请根据以下语法规则,把游戏脚本改写为可执行的 WebGAL 脚本,并把可用背景和立绘资源以合适的形式自然加入整个剧本。

        语法规则:
        -----
        {syntax_md}
        -----

        可用背景资源 background_assets:
        {json.dumps(background_assets, ensure_ascii=False, indent=2)}

        可用立绘资源 figure_assets:
        {json.dumps(figure_assets, ensure_ascii=False, indent=2)}

        改写要求:
        - 只能使用上方列出的资源文件名,不要编造其他图片文件名
        - 背景资源只能通过 changeBg 引用
        - 立绘资源只能通过 changeFigure 引用
        - 根据每个场景的时间、地点、情绪,把 background_assets 分配到合适场景中;尽量让每个背景资源至少出现一次
        - 根据角色出场和对话上下文,把 figure_assets 分配到合适位置;如果资源数量允许,尽量让每个立绘资源至少出现一次
        - 场景开始处优先设置合适背景;角色进入、离开、情绪变化或对话焦点变化时,可以切换立绘
        - 切换背景和立绘时优先使用 -next,避免打断剧情节奏
        - 禁止执行任何以下操作:新增、删除、修改、合并或拆分 Scene:xxx.txt / Ending:xxx.txt 段落
        - Scene:xxx.txt / Ending:xxx.txt 被视为不可变场景标题
        - 必须保留原有剧情含义、角色关系、变量、choose 目标文件名和结局走向
        - 角色台词行必须稳定使用 `角色名:台词正文`,如果看到 `角色名:(动作/语气)台词`,必须删除括号动作并保留台词正文
        - 可以把非 WebGAL 变量变化整理成 syntax.md 中的合法形式
        - 每条 WebGAL 语句单独一行,并以英文分号 ; 结尾
        - 输出完整改写后的脚本

        游戏脚本:
        -----
        {game_design_completed_text}
        -----

        {WEBGAL_REWRITE_RULES}"""


def sound_effect_prompt(game_design_completed_text: str, sound_effect_assets: list[dict[str, Any]]) -> str:
    return f"""你是一名游戏音频编排师。对于文本中的场景、环境变化、重大事件、动作节点、情绪转折点:
    - 判断是否需要音频。
    - 从提供的音效资产中选择最匹配的资源。
    - 找到最适合作为触发点的文本锚点。
    - anchor 必须是剧本中的原文片段,最长不超过 20 个中文字符。
    - 不要为每一句都加音效,只选择真正能增强体验的位置。
    - 环境声优先使用 loop,短促事件音使用 once。


    playback 只能是以下值之一:
    - once:一次性音效。
    - loop:循环音效。

    返回要求:
    - 严格返回 JSON 数组
    - asset 必须严格来自音效资产列表中的 filename。
    - anchor 必须严格来自剧本原文,不要改写。
    - 同一个 anchor 最多安排一个音效。
    - 数量保持克制,通常每个场景 0-3 个。

    sample:
    [
    {{
        "anchor": "雨声敲在窗沿",
        "asset": "rain-on-window.mp3",
        "category": "ambient",
        "operation": "start",
        "playback": "loop"
    }}
    ]

    可用音效资产:
    {json.dumps(sound_effect_assets, ensure_ascii=False, indent=2)}

    剧本:
    -----
    {game_design_completed_text}
    -----
    """
