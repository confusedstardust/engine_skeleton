"""Privacy-preserving diagnostics for NarAgent HTML tool orchestration.

Never report model text, tool arguments, source HTML, upstream HTTP responses,
conversation contents, or credentials. Only a fixed set of tool names is exposed.
"""
from langchain_core.messages import AIMessage

HTML_TOOL_NAMES = frozenset({
    "search_html_templates", "render_html_template", "submit_custom_html",
    "read_working_html", "inspect_working_html", "replace_working_html",
    "write_html_chunk", "validate_working_html",
})
FINISH_REASONS = frozenset({"stop", "length", "tool_calls", "content_filter", "function_call"})


def summarize_html_run(messages) -> dict:
    """Return a bounded, non-sensitive summary of the agent's tool selections."""
    ai_messages = [message for message in (messages or []) if isinstance(message, AIMessage)]
    calls = [call for message in ai_messages for call in (message.tool_calls or [])]
    invalid = sum(len(message.invalid_tool_calls or []) for message in ai_messages)
    tool_names = sorted({
        call["name"] for call in calls
        if isinstance(call, dict) and call.get("name") in HTML_TOOL_NAMES
    })
    last = ai_messages[-1] if ai_messages else None
    reason = (last.response_metadata or {}).get("finish_reason") if last else None
    reason = reason if reason in FINISH_REASONS else "unknown"
    return {
        "model_messages": len(ai_messages),
        "tool_calls": len(calls),
        "invalid_tool_calls": invalid,
        "tool_names": tool_names,
        "finish_reason": reason,
    }


NO_BUILD_RECOVERY_INSTRUCTION = (
    "系统检查：你尚未实际调用任何 HTML 构建工具，用户还没有获得作品。"
    "你之前表示将编写自定义网页，现在必须执行，而不是继续描述计划。"
    "如果没有合适模板，直接调用 write_html_chunk(mode='start', html_chunk='...')，"
    "每块不要超过 6000 字节，分次调用 mode='append' 写完 CSS/JS/HTML，"
    "随后调用 validate_working_html 提交浏览器验证；简短作品也可 submit_custom_html。"
    "若已提供可编辑的旧作品，也可调用 replace_working_html。"
    "绝不要在单次工具参数里塞入整个长网页，否则会触发模型输出长度限制。"
    "不要只回复代码块或文字说明。只有得到工具返回的 artifact_id 才能结束。"
    "如无法使用工具，请解释具体阻碍。"
)


# Public error classification is based on exception TYPES and HTTP status only.
# Never forward upstream exception strings, tool arguments, prompts or credentials.
def classify_html_exception(error: BaseException) -> tuple[str, str]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(current, "status_code", None)
        if not isinstance(status, int):
            status = getattr(response, "status_code", None)
        if status in (401, 403):
            return "MODEL_AUTH_FAILED", "模型服务认证或权限验证失败，请检查模型服务凭据与权限。"
        if status == 429:
            return "MODEL_RATE_LIMIT", "模型服务触发了速率或额度限制，请检查配额并稍后再试。"
        if status in (400, 422):
            return "MODEL_REQUEST_REJECTED", "模型服务拒绝了请求，请检查模型及工具调用参数兼容性。"
        if isinstance(status, int) and status >= 500:
            return "MODEL_SERVICE_UNAVAILABLE", "上游模型服务暂时不可用，请检查服务状态。"
        if type(current).__name__ in ("APITimeoutError", "ReadTimeout", "ConnectTimeout", "TimeoutException"):
            return "MODEL_TIMEOUT", "模型服务请求超时，请检查网络或稍后重试。"
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return "AGENT_ERROR", "Agent 编排或模型执行出现异常，请根据任务编号查询服务日志。"
