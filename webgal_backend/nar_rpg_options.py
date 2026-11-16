"""Minimal, deterministic NarAgent -> existing WebGAL Auto input compiler.

This is not a second game generator. The owner-scoped origin message is the
authoritative source of creative requirements; only confirmed switches win.
"""
from __future__ import annotations

import re
from typing import Any

from .job_options import normalize_generation_options

DEFAULT_VOICE_PRESET = "多角色配音"
DEFAULT_DURATION_MINUTES = 20
MIN_DURATION_MINUTES = 5
MAX_DURATION_MINUTES = 60


def draft_game_spec(original_prompt: str, intent_task: dict[str, Any]) -> dict[str, Any]:
    """Extract safe defaults without inventing an upload or running another LLM."""
    goal = str(intent_task.get("goal") or "").strip()
    title_match = re.search(r"《([^》]{1,100})》", original_prompt)
    topic = title_match.group(1) if title_match else goal[:160] or original_prompt.strip()[:160]
    minutes = re.search(r"(?<!\d)(\d{1,2})\s*(?:分钟|分鐘|minutes?)(?!\w)",
                        original_prompt, flags=re.IGNORECASE)
    duration = int(minutes.group(1)) if minutes else DEFAULT_DURATION_MINUTES
    duration = max(MIN_DURATION_MINUTES, min(MAX_DURATION_MINUTES, duration))
    no_images = re.search(r"(?:不|无|免|无需|不要|不需要|不用|关闭).{0,3}(?:配图|图片|插画|生图|绘图)", original_prompt)
    no_voice = re.search(r"(?:不|无|免|无需|不要|不需要|不用|关闭).{0,3}(?:配音|语音|朗读|旁白|TTS)", original_prompt, flags=re.IGNORECASE)
    wants_voice = re.search(r"(?:配音|语音|朗读|旁白|TTS)", original_prompt, flags=re.IGNORECASE)
    return {
        "topic": topic or "互动叙事游戏",
        "source_ref": {"type": "origin_user_message"},
        "duration_minutes": duration,
        "generate_images": not bool(no_images),
        "enable_voice": bool(wants_voice) and not bool(no_voice),
    }


def compile_webgal_request(
    spec: dict[str, Any], *,
    original_prompt: str,
    duration_minutes: int,
    generate_images: bool,
    enable_voice: bool,
    derived: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Reuse GenerationOptions validation and preserve *all* user story constraints."""
    if type(duration_minutes) is not int or not MIN_DURATION_MINUTES <= duration_minutes <= MAX_DURATION_MINUTES:
        raise ValueError("游戏体验时长应为 5～60 分钟")
    if type(generate_images) is not bool or type(enable_voice) is not bool:
        raise ValueError("图片和配音选项必须明确确认")
    if not isinstance(original_prompt, str) or not original_prompt.strip():
        raise ValueError("原始游戏创作要求不存在")
    if not isinstance(spec, dict):
        raise ValueError("游戏草稿不存在")
    topic = str(spec.get("topic") or "").strip()[:160]
    if not topic:
        raise ValueError("缺少游戏主题")
    derived = derived or {}
    # The last line resolves conflicting historic voice/image instructions:
    # server-confirmed switches are authoritative, not earlier prompt text.
    source = "\n".join((
        f"游戏主题：{topic}",
        "用户原始游戏创作要求（保留角色、分支、结局、故事素材等全部细节）：",
        original_prompt.strip(),
        f"用户最终确认的媒体配置（高于原话中的媒体开关）：配图={'开启' if generate_images else '关闭'}；配音={'开启' if enable_voice else '关闭'}。",
    ))
    options = {
        "classroom_topic": topic,
        "grade": derived.get("grade") or "适用学习者",
        "difficulty": derived.get("difficulty") or "基础至中等",
        "teacher_goal": derived.get("teacher_goal") or f"围绕{topic}构建可探索的互动学习体验。",
        "student_goal": derived.get("student_goal") or f"通过互动选择理解{topic}的主要内容。",
        "duration": f"{duration_minutes}分钟",
        "narrative_mode": derived.get("narrative_mode") or "互动叙事与角色选择",
        "generation_mode": "auto",
        "generate_assets": generate_images,
        "voice_enabled": enable_voice,
        "generate_tts": enable_voice,
        "voice_preset": DEFAULT_VOICE_PRESET if enable_voice else None,
    }
    return {"source_material": source, "options": normalize_generation_options(options)}
