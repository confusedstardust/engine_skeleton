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

# A selectable question is a final assistant turn. The existing conversation
# persists its text and can resume via the next normal user message.
CHOICE_INSTRUCTIONS = """
当需要用户在两个及以上明确方案中选择、确认下一步交付物，或者关键条件缺失且应当澄清时，
请使用可点击的结构化选项，而不是要求用户自己回复数字、字母或复制选项文字。
若可根据当前需求合理继续完成任务，不要为了展示选项而反复追问。

若需要用户选择，请在正常正文最后附加一次以下协议块。
将 question 和 label 替换为真实问题和选项；选项必须有 2～5 个，id 依次使用 a、b、c、d、e。
multiple 仅在确实允许用户同时选择多项时设为 true；allowCustom 建议为 true。
[[NAR_UI_CHOICES_V1]]
{"question":"你希望先完成哪一项？","options":[{"id":"a","label":"方案A"},{"id":"b","label":"方案B"}],"multiple":false,"allowCustom":true}
[[/NAR_UI_CHOICES_V1]]

保证 JSON 合法；不要把协议块放进 Markdown 代码围栏，也不要在正文重复列出全部选项。
协议块只能出现在回复结尾，不能出现在工具调用中。
选项提交会作为后续用户消息进入原会话，因此要确保每个选项的标签清楚、自包含。
"""


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
            + CHOICE_INSTRUCTIONS
        ),
        name="nar-agent",
    )


def initial_state(prompt: str, history: list[dict[str, str]] | None = None) -> dict:
    return {
        "messages": [*(history or []), {"role": "user", "content": prompt}],
        "files": {"/skills/teaching-plan/SKILL.md": create_file_data(SKILL_PATH.read_text(encoding="utf-8"))},
    }
