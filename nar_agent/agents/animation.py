import json
from pathlib import Path

import httpx
from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_openai import ChatOpenAI
from langchain.agents.middleware import ModelCallLimitMiddleware

from app.artifacts import ArtifactStore
from app.config import Settings

SKILLS = Path(__file__).resolve().parents[1] / "skills"
PROMPT = """你是 NarAgent 教学动画制作助手。必须读取 /skills/anatomy/SKILL.md 以及相关 kit API/示例后再实现。
目标：单机制、中文、浅色、响应式、可操作的课堂 SVG 演示。只生成 Figure 范围，不做复杂3D。
先说明简化模型与参数。使用 anatomy kit 构建图形，数值与运动由同一模型驱动。
用虚拟文件工具阅读参考。然后调用 build_animation，source 参数为完整 Node ESM 构建脚本。
执行环境内 kit 在 /opt/anatomy/；例如 import * as k from '/opt/anatomy/kit/iso-kit.mjs'。
writeFileSync('/work/index.html', html) 输出一个完整独立HTML，所有CSS/JS内联，不依赖网络、外部文件或CDN。
kitScript() 从 /opt/anatomy/scripts/inline-kit.mjs 导入。必须包含SVG或Canvas和可点击按钮/参数控件，手机不横向溢出。
运行检查工具后，根据实际 report 修复，最多3次构建。只有 passed 且返回 artifact_id 才能称已生成。
不得伪造浏览器、视觉或教学审核结果；当前截图供教师审阅，自动检查不等于教学正确性保证。
最终用中文简洁解释操作方法和简化假设。禁止委派；不能调用宿主shell，不要索要密钥。
"""


def animation_state(prompt: str, history: list[dict]) -> dict:
    files = {}
    for path in (SKILLS / "anatomy").rglob("*"):
        if path.is_file() and path.suffix in {".md", ".mjs", ".ts", ".tsx", ".css", ".json"} and path.stat().st_size < 800000:
            files["/skills/" + path.relative_to(SKILLS).as_posix()] = create_file_data(path.read_text(encoding="utf-8"))
    return {"messages": [*history, {"role": "user", "content": prompt}], "files": files}


def build_animation_agent(settings: Settings, owner: str, progress: dict, store: ArtifactStore, *, model=None):
    attempts = 0

    async def build_animation(source: str) -> str:
        """Build a complete Node ESM script in an isolated container and check its standalone index.html. Returns report and artifact_id only if checks pass."""
        nonlocal attempts
        if attempts >= 3:
            return json.dumps({"error": "Build limit reached. Stop and explain failure."})
        attempts += 1
        progress.update(phase="BUILDING", attempts=attempts)
        try:
            async with httpx.AsyncClient(timeout=125, trust_env=False) as client:
                response = await client.post(settings.execution_url.rstrip("/") + "/execute", headers={"Authorization": "Bearer " + settings.execution_token.get_secret_value()}, json={"source": source})
                response.raise_for_status()
                result = response.json()
            report = result["report"]
            progress.update(phase="CHECKING", last_report=report)
            if report.get("passed"):
                identifier = store.save(owner, result, source)
                progress.update(artifact_id=identifier, phase="FINALIZING")
                return json.dumps({"artifact_id": identifier, "report": report}, ensure_ascii=False)
            return json.dumps({"report": report, "remaining_attempts": 3 - attempts}, ensure_ascii=False)
        except (httpx.HTTPError, ValueError, KeyError):
            return json.dumps({"error": "Execution unavailable or invalid result", "remaining_attempts": 3 - attempts})

    model = model if model is not None else ChatOpenAI(model=settings.model, api_key=settings.api_key.get_secret_value(), base_url=settings.base_url, max_tokens=max(settings.max_output_tokens, 8192), timeout=90, max_retries=0, stream_usage=True)
    register_harness_profile(settings.model, HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    return create_deep_agent(model=model, backend=StateBackend(), skills=["/skills/"], tools=[build_animation], middleware=[ModelCallLimitMiddleware(run_limit=12, exit_behavior="error")], system_prompt=PROMPT, name="nar-animation")
