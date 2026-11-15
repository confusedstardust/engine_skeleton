from pathlib import Path
from typing import Any

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_openai import ChatOpenAI

from app.config import Settings

SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "teaching-plan" / "SKILL.md"


def build_agent(settings: Settings, *, model: Any = None):
    model = model if model is not None else ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url,
        max_tokens=settings.max_output_tokens,
        timeout=settings.timeout_seconds,
        max_retries=0,  # Keep one visible call equal to one provider attempt.
        stream_usage=True,
    )
    # This standalone process has a single provider configuration. No delegation.
    register_harness_profile(
        settings.model,
        HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)),
    )
    return create_deep_agent(
        model=model,
        backend=StateBackend(),
        skills=["/skills/"],
        system_prompt=(
            "你是 NarAgent，面向教师的教学助手。使用 teaching-plan skill 制作教学演示方案。"
            "当前只有请求内虚拟文件工具，没有 shell、浏览器、联网或真实文件保存能力。"
            "不得声称已经执行代码、生成可用动画、截图验证或保存作品。"
            "不要委派任务。用中文回答，明确说明待实现或待验证的部分。"
            "当需要用户在两个及以上明确方案中选择、确认下一步交付物，或者关键条件缺失且应当澄清时，"
            "优先使用可点击的结构化选项，而不是要求用户自己回复数字、字母或复制文字。"
            "若可合理推断并继续完成任务，不要为了展示选项而反复追问。"
            "如果确实需要用户选择，请在正常正文结尾原样追加以下协议块（仅在需要选择时追加一次）：\\n"
            "[[NAR_UI_CHOICES_V1]]\\n"
            "{\\\"question\\\":\\\"你希望先完成哪一项？\\\",\\\"options\\\":["
            "{\\\"id\\\":\\\"a\\\",\\\"label\\\":\\\"方案A\\\"},"
            "{\\\"id\\\":\\\"b\\\",\\\"label\\\":\\\"方案B\\\"}],"
            "\\\"multiple\\\":false,\\\"allowCustom\\\":true}"
            "\\n[[/NAR_UI_CHOICES_V1]]"
            "其中 question 和 label 必须替换为当前任务真正的选项，options 必须为2至5项，"
            "id 使用互不重复的 a、b、c、d、e；multiple 仅当允许同时选多项时为 true。"
            "JSON 必须合法、不得加 Markdown 代码围栏、不要在正文重复罗列选项。"
            "协议块必须放在回复最后，选项确定后用户将通过正常会话发送选择文字以继续。"
        ),
        name="nar-agent",
    )


def initial_state(prompt: str, history: list[dict[str, str]] | None = None) -> dict:
    return {
        "messages": [*(history or []), {"role": "user", "content": prompt}],
        "files": {"/skills/teaching-plan/SKILL.md": create_file_data(SKILL_PATH.read_text(encoding="utf-8"))},
    }
