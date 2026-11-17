"""Safe NarAgent public error classification; stdlib only for isolated tests."""

# Public exception classification never discloses provider values.
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
