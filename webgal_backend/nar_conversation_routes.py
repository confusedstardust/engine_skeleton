"""SSO-owned, always-on durable conversation API. Manual schema migration required.

Model execution remains in NarAgent; Forge owns visible messages, idempotency,
turn status, artifact lineage and user permission checks. An uncertain dispatch
is NOT automatically repeated while NarAgent lacks durable idempotency support.
"""
from __future__ import annotations

import os
import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .nar_conversation_store import (
    ConversationConflict, ConversationMissing, NarConversationStore,
)
from .work_store import WorkStore

ID = r"^[0-9a-f]{32}$"


class ConversationUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, max_length=160)
    pinned: bool | None = None


class TurnRequest(BaseModel):
    model_config = {"extra": "forbid"}
    client_request_id: str = Field(pattern=ID)
    prompt: str = Field(min_length=1, max_length=12000, pattern=r"\S")
    mode: Literal["chat", "html", "animation", "edit"] = "chat"
    parent_artifact_id: str | None = Field(default=None, pattern=ID)


class FirstTurnRequest(TurnRequest):
    conversation_id: str = Field(pattern=ID)


class WorkAssociation(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str = Field(pattern=ID)
    work_id: str = Field(pattern=ID)


def create_router(*, user_for_request, store: NarConversationStore | None = None,
                  works: WorkStore | None = None, transport=None):
    router = APIRouter(prefix="/nar-agent", tags=["NarAgent conversation history"])
    ledger = store or NarConversationStore()
    work_store = works or WorkStore()

    async def owner_for(request: Request) -> str:
        user = await run_in_threadpool(user_for_request, request)
        if user.get("auth_type") != "sso" or not user.get("id"):
            raise HTTPException(401, "请先登录 NarrativeOS")
        return str(user["id"])

    def mutate(request: Request):
        if request.headers.get("x-naragent-action") != "chat":
            raise HTTPException(403, "缺少会话操作校验标识")

    async def transaction(action, *args, **kwargs):
        try:
            return await run_in_threadpool(action, *args, **kwargs)
        except ConversationMissing:
            raise HTTPException(404, "会话、轮次或产物不存在") from None
        except ConversationConflict:
            raise HTTPException(409, "当前会话已有任务进行中，请等待完成") from None
        except ValueError:
            raise HTTPException(422, "分页参数或会话参数不正确") from None
        except HTTPException:
            raise
        except Exception:
            # Missing tables, DB outage and untrusted driver errors must not
            # leak credentials/queries in response bodies.
            raise HTTPException(503, "会话数据库不可用或尚未迁移，请先执行 002_nar_conversation_history.sql") from None

    async def agent_request(owner: str, mode: str, payload: dict, *,
                            run_id: str | None = None) -> dict:
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "NarAgent 服务尚未配置")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        kind = "runs" if mode == "chat" else "animations" if mode == "animation" else "html"
        path = f"/v1/{kind}" + (f"/{run_id}" if run_id else "")
        method = "GET" if run_id else "POST"
        try:
            async with httpx.AsyncClient(
                timeout=135 if mode == "chat" and not run_id else 20,
                transport=transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.request(method, base + path, json=payload if not run_id else None,
                    headers={"Authorization": "Bearer " + token, "X-User-ID": owner})
        except httpx.HTTPError:
            raise HTTPException(504, "执行服务响应超时或不可用") from None
        if response.status_code not in (200, 202):
            code = response.status_code if response.status_code in (404, 422, 429) else 503
            raise HTTPException(code, {404: "执行任务不存在或已中断",
                                        422: "创作内容不符合输入约束",
                                        429: "执行服务当前繁忙"}.get(code, "执行服务暂时不可用"))
        try:
            data = response.json()
            if str(data["user_id"]) != owner or not isinstance(data.get("id"), str):
                raise ValueError
            if mode == "chat" and not isinstance(data.get("output"), str):
                raise ValueError
            return {key: data[key] for key in (
                "id", "status", "phase", "output", "error", "error_code", "artifact_id",
                "parent_artifact_id", "timeline", "elapsed_ms", "learning_plan",
                "public_brief", "public_brief_state", "duration_ms"
            ) if key in data}
        except (TypeError, ValueError, KeyError):
            raise HTTPException(502, "执行服务的用户归属或响应内容无效") from None

    @router.get("/conversations/status")
    async def availability(request: Request):
        # The endpoint is authenticated, NOT a feature flag. A missing migration
        # is a visible setup error: the browser must never use local chat instead.
        await owner_for(request)
        if not await run_in_threadpool(ledger.ready):
            raise HTTPException(
                503, "会话数据库未完成迁移或暂时不可用，请先执行 002_nar_conversation_history.sql"
            )
        return {"ready": True}

    @router.get("/conversations")
    async def conversations(request: Request, limit: int = 30, cursor: str | None = None):
        owner = await owner_for(request)
        if not 1 <= limit <= 50:
            raise HTTPException(422, "列表长度需在 1～50 之间")
        return await transaction(ledger.list_conversations, owner, limit, cursor)

    @router.get("/conversations/{cid}")
    async def conversation(cid: str, request: Request):
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        return await transaction(ledger.get_detail, owner, cid)

    @router.patch("/conversations/{cid}")
    async def update_conversation(cid: str, payload: ConversationUpdate, request: Request):
        mutate(request)
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        if payload.title is None and payload.pinned is None:
            raise HTTPException(422, "请提供新的标题或置顶状态")
        return await transaction(ledger.update_metadata, owner, cid,
                                 title=payload.title, pinned=payload.pinned)

    @router.delete("/conversations/{cid}")
    async def delete_conversation(cid: str, request: Request):
        mutate(request)
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        return await transaction(ledger.delete_conversation, owner, cid)

    @router.get("/conversations/{cid}/messages")
    async def messages(cid: str, request: Request, before: int | None = None, limit: int = 30):
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid) or not 1 <= limit <= 50 or (before is not None and before <= 0):
            raise HTTPException(422, "会话或分页参数错误")
        return await transaction(ledger.get_messages, owner, cid, before, limit)

    async def submit_turn(owner: str, cid: str, payload: TurnRequest, *, create=False):
        turn, new = await transaction(ledger.start_turn, owner, cid,
             payload.client_request_id, payload.prompt, payload.mode,
             payload.parent_artifact_id, create=create)
        if not new:
            # Idempotent reads must never re-dispatch a previously submitted turn.
            return {"conversationId": cid, "turn": turn, "reused": True}
        history = await transaction(ledger.model_history, owner, cid, turn["id"])
        request_body = {"prompt": payload.prompt, "history": history}
        if payload.mode == "edit":
            if not payload.parent_artifact_id:
                await transaction(ledger.fail_turn, owner, cid, turn["id"], "MISSING_PARENT")
                return {"conversationId": cid, "turn": {**turn, "status": "FAILED", "errorCode": "MISSING_PARENT"}}
            request_body["parent_artifact_id"] = payload.parent_artifact_id
        try:
            task = await agent_request(owner, payload.mode, request_body)
        except HTTPException as exc:
            # A 4xx means a known refusal. Network/5xx is ambiguous: provider
            # may have accepted it. Never automatically create another run.
            uncertain = exc.status_code not in (404, 422, 429)
            failed = await transaction(ledger.fail_turn, owner, cid, turn["id"],
                 "DISPATCH_UNCERTAIN" if uncertain else "DISPATCH_REJECTED", uncertain=uncertain)
            return {"conversationId": cid, "turn": failed}
        await transaction(ledger.mark_running, owner, cid, turn["id"], task["id"])
        if payload.mode == "chat":
            finished = await transaction(ledger.finish_turn, owner, cid, turn["id"],
                 output=task.get("output", ""), run_id=task["id"])
            return {"conversationId": cid, "turn": finished}
        return {"conversationId": cid, "turn": {**turn, "status": "RUNNING", "runId": task["id"]},
                "task": task}

    @router.post("/conversations", status_code=202)
    async def create_conversation(payload: FirstTurnRequest, request: Request):
        mutate(request)
        owner = await owner_for(request)
        return await submit_turn(owner, payload.conversation_id, payload, create=True)

    @router.post("/conversations/{cid}/turns", status_code=202)
    async def post_turn(cid: str, payload: TurnRequest, request: Request):
        mutate(request)
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        return await submit_turn(owner, cid, payload)

    @router.get("/conversations/{cid}/turns/{tid}")
    async def poll_turn(cid: str, tid: str, request: Request):
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid) or not re.fullmatch(ID, tid):
            raise HTTPException(404, "轮次不存在")
        turn = await transaction(ledger.get_turn, owner, cid, tid)
        if turn["status"] != "RUNNING" or not turn["runId"]:
            return {"turn": turn}
        try:
            task = await agent_request(owner, turn["mode"], {}, run_id=turn["runId"])
        except HTTPException as exc:
            if exc.status_code == 404:
                unknown = await transaction(ledger.fail_turn, owner, cid, tid, "RUN_NOT_RECOVERABLE",
                                            uncertain=True)
                return {"turn": unknown}
            # Don't mark an in-flight task failed solely due to temporary network errors.
            return {"turn": turn}
        if task.get("status") in ("SUCCEEDED", "FAILED"):
            aid = task.get("artifact_id")
            if task["status"] == "SUCCEEDED" and not (
                isinstance(aid, str) and re.fullmatch(ID, aid)
            ):
                failed = await transaction(ledger.fail_turn, owner, cid, tid, "ARTIFACT_MISSING")
                return {"turn": failed, "task": task}
            if task["status"] == "SUCCEEDED":
                work_kind = "animation" if turn["mode"] == "animation" else "html"
                result = await transaction(ledger.finish_turn, owner, cid, tid,
                    output=task.get("output") or "学习作品已完成。",
                    artifact_id=aid if isinstance(aid, str) and re.fullmatch(ID, aid) else None,
                    title=(task.get("public_brief") or "互动学习作品")[:160],
                    kind=work_kind, run_id=turn["runId"],
                    public_metadata={"timeline": task.get("timeline"), "publicBrief": task.get("public_brief"),
                                     "learningPlan": task.get("learning_plan"),
                                     "elapsedMs": task.get("elapsed_ms")})
            else:
                safe_error = task.get("error")
                if not isinstance(safe_error, str) or not safe_error.strip():
                    safe_error = "任务执行失败，请查看错误码并联系维护人员排查。"
                safe_code = str(task.get("error_code") or "GENERATION_FAILED")[:80]
                safe_phase = task.get("phase")
                safe_phase = safe_phase if isinstance(safe_phase, str) else None
                result = await transaction(ledger.fail_turn, owner, cid, tid,
                    safe_code, public_error=safe_error,
                    phase=safe_phase)
            return {"turn": result, "task": task}
        return {"turn": turn, "task": task}

    @router.get("/artifact-history")
    async def artifact_history(request: Request, limit: int = 30, cursor: str | None = None):
        owner = await owner_for(request)
        if not 1 <= limit <= 50:
            raise HTTPException(422, "列表长度需在 1～50 之间")
        return await transaction(ledger.artifact_history, owner, limit, cursor)

    @router.post("/conversations/{cid}/artifacts")
    async def link_work(cid: str, payload: WorkAssociation, request: Request):
        mutate(request)
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        try:
            saved = await run_in_threadpool(work_store.get, owner, payload.work_id)
        except FileNotFoundError:
            raise HTTPException(404, "没有权限访问这件作品") from None
        if not any(version.get("artifact_id") == payload.artifact_id
                   for version in saved.get("versions", [])):
            raise HTTPException(404, "该作品不含指定版本")
        await transaction(ledger.link_work, owner, cid, payload.artifact_id, payload.work_id)
        return {"linked": True}

    return router
