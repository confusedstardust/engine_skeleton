"""Authenticated gateway: ownership comes from NarrativeOS login."""
import os
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from starlette.concurrency import run_in_threadpool


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatInput(BaseModel):
    model_config = {"extra": "forbid"}
    prompt: str = Field(min_length=1, max_length=12000, pattern=r"\S")
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded_context(self):
        if sum(len(m.content) for m in self.history) + len(self.prompt) > 36000:
            raise ValueError("对话过长，请开始新对话")
        return self


class HtmlInput(ChatInput):
    parent_artifact_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def create_router(*, user_for_request, transport=None):
    router = APIRouter(prefix="/nar-agent", tags=["NarAgent"])

    @router.post("/chat")
    async def chat(payload: ChatInput, request: Request):
        if request.headers.get("x-naragent-action") != "chat":
            raise HTTPException(403, "缺少对话请求校验标识")
        user = await run_in_threadpool(user_for_request, request)
        if user.get("auth_type") != "sso":
            raise HTTPException(401, "请先登录 NarrativeOS 后使用讲练工具")
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        if len(token) < 32:
            raise HTTPException(503, "讲练助手尚未配置，请联系管理员启动 NarAgent 服务")
        try:
            async with httpx.AsyncClient(timeout=135, transport=transport, follow_redirects=False, trust_env=False) as client:
                response = await client.post(base + "/v1/runs", headers={
                    "Authorization": f"Bearer {token}", "X-User-ID": str(user["id"]),
                }, json=payload.model_dump())
        except httpx.TimeoutException:
            raise HTTPException(504, "助手响应超时，请稍后重试") from None
        except httpx.HTTPError:
            raise HTTPException(503, "讲练助手暂时无法连接，请稍后重试") from None
        if response.status_code != 200:
            messages = {429: "助手当前繁忙，请稍后重试", 504: "助手响应超时，请稍后重试", 422: "对话内容过长或格式不正确，请开始新对话"}
            code = response.status_code if response.status_code in messages else 503
            raise HTTPException(code, messages.get(code, "讲练助手暂时不可用，请联系管理员检查服务配置"))
        try:
            data = response.json()
            if data.get("user_id") != user["id"] or not isinstance(data.get("output"), str):
                raise ValueError("invalid owner or response")
            return {"id": data["id"], "output": data["output"], "duration_ms": data.get("duration_ms"), "artifact_generated": False}
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(502, "助手返回格式异常，请稍后重试") from None

    async def forward(request: Request, method: str, path: str, payload=None):
        if method == "POST" and request.headers.get("x-naragent-action") != "chat":
            raise HTTPException(403, "缺少请求校验标识")
        user = await run_in_threadpool(user_for_request, request)
        if user.get("auth_type") != "sso":
            raise HTTPException(401, "请先登录 NarrativeOS")
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "NarAgent 服务尚未配置")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=15, transport=transport, follow_redirects=False, trust_env=False) as client:
                response = await client.request(method, base + path, headers={"Authorization": "Bearer " + token, "X-User-ID": str(user["id"])}, json=payload)
        except httpx.HTTPError:
            raise HTTPException(503, "NarAgent 服务暂时无法连接") from None
        if response.status_code not in {200, 202}:
            status = response.status_code if response.status_code in {404, 422, 429} else 503
            raise HTTPException(status, {404: "任务或产物不存在", 422: "输入不符合要求", 429: "已有作品正在制作，请稍后再试"}.get(status, "创作执行环境尚未就绪，请联系管理员"))
        return user, response

    def public_result(user, response):
        try:
            data = response.json()
            if data["user_id"] != user["id"]:
                raise ValueError("owner mismatch")
            return {key: data[key] for key in ["id", "status", "phase", "attempts", "output", "error", "artifact_id", "artifact_generated", "last_report", "parent_artifact_id", "strategy"] if key in data}
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "动画服务响应异常") from None

    @router.post("/animations", status_code=202)
    async def start_animation(payload: ChatInput, request: Request):
        user, response = await forward(request, "POST", "/v1/animations", payload.model_dump())
        return public_result(user, response)

    @router.get("/animations/{identifier}")
    async def animation_status(identifier: str, request: Request):
        import re
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise HTTPException(404, "任务不存在")
        user, response = await forward(request, "GET", "/v1/animations/" + identifier)
        return public_result(user, response)

    @router.post("/html", status_code=202)
    async def start_html(payload: dict, request: Request):
        try:
            validated = HtmlInput.model_validate(payload)
        except Exception:
            raise HTTPException(422, "HTML 创作输入不符合要求") from None
        user, response = await forward(request, "POST", "/v1/html", validated.model_dump())
        return public_result(user, response)

    @router.get("/html/{identifier}")
    async def html_status(identifier: str, request: Request):
        import re
        if not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise HTTPException(404, "任务不存在")
        user, response = await forward(request, "GET", "/v1/html/" + identifier)
        return public_result(user, response)

    @router.get("/artifacts/{identifier}/{filename}")
    async def preview(identifier: str, filename: str, request: Request):
        import re
        if not re.fullmatch(r"[0-9a-f]{32}", identifier) or filename not in {"index.html", "preview.png", "mobile.png"}:
            raise HTTPException(404, "产物不存在")
        _, response = await forward(request, "GET", f"/v1/artifacts/{identifier}/{filename}")
        return Response(response.content, media_type="text/html" if filename == "index.html" else "image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'",
        })

    return router
