from __future__ import annotations

from typing import Any

from ..generation_limits import generation_limits
from ..job_options import GenerationOptions, normalize_generation_options
from ..scene_plan import build_scene_plan, scene_plan_coverage_text


OptionsLike = dict[str, Any] | GenerationOptions


def _options_dict(options: OptionsLike) -> dict[str, Any]:
    return normalize_generation_options(options)


def required_int_option(options: OptionsLike, key: str, minimum: int, maximum: int) -> int:
    options = _options_dict(options)
    try:
        value = int(options[key])
    except (TypeError, ValueError):
        raise ValueError(f"options.{key} must be an integer")
    return max(minimum, min(maximum, value))


def duration_minutes(options: OptionsLike) -> int:
    options = _options_dict(options)
    raw = str(options["duration"]).strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise ValueError("options.duration must contain minutes, e.g. '20分钟'")
    return max(5, min(60, int(digits)))


def generation_contract(options: OptionsLike) -> dict[str, Any]:
    options = _options_dict(options)
    limits = generation_limits()
    duration = duration_minutes(options)
    character_count = required_int_option(options, "character_count", 1, 8)
    interactive_task_count = required_int_option(options, "interactive_task_count", 1, 12)

    ending_count = max(2, min(5, 2 + interactive_task_count // 4))
    option_count = max(
        limits["branches"]["choice_options_min"],
        min(limits["branches"]["choice_options_max"], 3),
    )

    return {
        "duration": duration,
        "character_count": character_count,
        "interactive_task_count": interactive_task_count,
        "option_count": option_count,
        "variable_count": limits["variables"]["max_total"],
        "ending_count": ending_count,
        "line_min": limits["scenes"]["min_lines"],
        "line_max": limits["scenes"]["max_lines"],
        "line_length": limits["scenes"]["max_line_length"],
    }


def contract_text(options: OptionsLike) -> str:
    options = _options_dict(options)
    contract = generation_contract(options)
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
            "- 场景文件数量：不按游戏时长压缩或限制；必须完整覆盖 narrative_plan.story_progression 和 narrative_plan.endings。",
            f"- 每个选择点建议 {contract['option_count']} 个选项。",
            f"- 结局数量：建议 {contract['ending_count']} 个。",
            f"- 角色配音：{'开启' if options.get('voice_enabled') or options.get('generate_tts') else '关闭'}，预设：{options.get('voice_preset') or '未指定'}。",
            f"- 生成图片素材：{'开启' if options.get('generate_assets') else '关闭'}。",
        ]
    )


def narrative_source_context(options: OptionsLike) -> str:
    options = _options_dict(options)
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


def game_design_coverage_text(
    narrative_plan: dict[str, Any],
    scene_plan: dict[str, Any] | None = None,
) -> str:
    return scene_plan_coverage_text(scene_plan or build_scene_plan(narrative_plan))
