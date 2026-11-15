"""SSO-owned, always-on durable conversation API. Manual schema migration required.

Model execution remains in NarAgent; Forge owns visible messages, idempotency,
turn status, artifact lineage and user permission checks. An uncertain dispatch
is NOT automatically repeated while NarAgent lacks durable idempotency support.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .nar_conversation_store import (
    ConversationConflict, ConversationMissing, NarConversationStore,
)
from .work_store import WorkStore
from .nar_choice_protocol import visible_stream_prefix
from .nar_intent_v2 import build_context_packet, plan_v2
from .nar_pending_v2 import ClarificationAnswer, make_clarification_metadata, validate_clarification_answer
from .nar_billing import NarTurnBilling, safe_usage_metadata
from credit_system import InsufficientCreditsError

ID = r"^[0-9a-f]{32}$"
logger = logging.getLogger(__name__)


def _shadow_v2_enabled(owner: str, cid: str, request_id: str) -> bool:
    """Stable request-level sample; completely disabled by default.

    Config is optional and server-owned. Shadow NEVER authorizes execution.
    """
    try:
        percent = float(os.getenv("NAR_INTENT_V2_SHADOW_PERCENT", "0"))
    except ValueError:
        return False
    if not 0 < percent <= 100:
        return False
    value = int.from_bytes(hashlib.sha256(
        f"{owner}:{cid}:{request_id}".encode("utf-8")).digest()[:8], "big")
    return value / (2 ** 64) < percent / 100




class ConversationUpdate(BaseModel):
    model_config = {"extra": "forbid"}
    title: str | None = Field(default=None, max_length=160)
    pinned: bool | None = None


class TurnRequest(BaseModel):
    model_config = {"extra": "forbid"}
    client_request_id: str = Field(pattern=ID)
    prompt: str = Field(min_length=1, max_length=12000, pattern=r"\S")
    mode: Literal["auto", "chat", "html", "animation", "edit"] = "chat"
    parent_artifact_id: str | None = Field(default=None, pattern=ID)
    selected_artifact_id: str | None = Field(default=None, pattern=ID)
    clarification_answer: ClarificationAnswer | None = None


class FirstTurnRequest(TurnRequest):
    conversation_id: str = Field(pattern=ID)


class WorkAssociation(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str = Field(pattern=ID)
    work_id: str = Field(pattern=ID)


def create_router(*, user_for_request, store: NarConversationStore | None = None,
                  works: WorkStore | None = None, transport=None, billing_factory=None):
    router = APIRouter(prefix="/nar-agent", tags=["NarAgent conversation history"])
    ledger = store or NarConversationStore()
    work_store = works or WorkStore()
    live_chat_jobs: set[asyncio.Task] = set()
    live_shadow_jobs: set[asyncio.Task] = set()
    biller_type = billing_factory or NarTurnBilling

    async def reserve_turn(owner: str, tid: str, mode: str):
        try:
            return await run_in_threadpool(biller_type().reserve, owner, tid, mode)
        except InsufficientCreditsError as exc:
            raise HTTPException(402, "积分不足，本次任务未执行，请充值后重试") from exc
        except Exception:
            raise HTTPException(503, "积分服务暂时不可用，本次任务未执行") from None

    async def finish_billing(owner: str, tid: str, usage: dict | None, *,
                             success: bool, duration_ms: int = 0) -> dict:
        biller = biller_type()
        try:
            reservation = await run_in_threadpool(biller.find, owner, tid)
            if not reservation:
                return safe_usage_metadata(usage, duration_ms=duration_ms)
            return await run_in_threadpool(biller.settle, reservation, usage,
                                           definite_success=success, duration_ms=duration_ms)
        except Exception:
            # A provider response can have completed even if billing is down.
            # Don't invent a credit receipt or refund an uncertain reservation.
            raise HTTPException(503, "积分结算暂时无法确认，请勿重复发起任务") from None

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
            raise HTTPException(503, "会话数据库不可用或尚未迁移，请检查 002_nar_conversation_history.sql 和 003_nar_conversation_pins.sql") from None

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
                "public_brief", "public_brief_state", "duration_ms", "usage", "usage_status"
            ) if key in data}
        except (TypeError, ValueError, KeyError):
            raise HTTPException(502, "执行服务的用户归属或响应内容无效") from None

    async def resolve_intent(owner: str, prompt: str, history: list[dict],
                             current_artifact_kind: str | None) -> str:
        """Classify on NarAgent using the existing model credentials and owner boundary."""
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "NarAgent 服务尚未配置")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        try:
            async with httpx.AsyncClient(
                timeout=30, transport=transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.post(
                    base + "/v1/intent",
                    json={"prompt": prompt, "history": history[-8:],
                          "has_editable_html": current_artifact_kind == "html",
                          "current_artifact_kind": current_artifact_kind},
                    headers={"Authorization": "Bearer " + token, "X-User-ID": owner},
                )
        except httpx.HTTPError:
            raise HTTPException(503, "需求识别暂时不可用，请稍后重试") from None
        if response.status_code == 429:
            raise HTTPException(429, "当前请求较多，请稍后重试")
        if response.status_code != 200:
            raise HTTPException(503, "需求识别暂时不可用，请稍后重试")
        try:
            data = response.json()
            if str(data["user_id"]) != owner or data["mode"] not in (
                "chat", "html", "animation", "edit", "edit_animation"
            ):
                raise ValueError
            return data["mode"]
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "需求识别结果无效") from None

    async def resolve_intent_v2(owner: str, prompt: str, packet: dict) -> dict:
        """Call the opt-in V2 interpreter; its proposal has NO execution authority."""
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise ValueError("V2 shadow unavailable")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        async with httpx.AsyncClient(
            timeout=25, transport=transport, trust_env=False, follow_redirects=False
        ) as client:
            response = await client.post(
                base + "/v1/intent",
                json={"prompt": prompt, "schema_version": "2.0",
                      "context_v2": packet},
                headers={"Authorization": "Bearer " + token, "X-User-ID": owner},
            )
        if response.status_code != 200:
            raise ValueError("V2 shadow service error")
        data = response.json()
        if (data.get("user_id") != owner or data.get("schema_version") != "2.0"
                or not isinstance(data.get("decision"), dict)):
            raise ValueError("V2 shadow returned invalid envelope")
        return data["decision"]

    async def compare_v2_shadow(owner: str, cid: str, payload: TurnRequest,
                                recent: list[dict], legacy_mode: str,
                                selected_id: str | None, *, create: bool):
        """Side-effect free comparison: no extra turn, dispatch, or credit reserve."""
        try:
            candidates = [] if create else await transaction(
                ledger.artifact_candidates, owner, cid, selected_id)
            packet = build_context_packet(
                payload.prompt, cid, recent, candidates, selected_id)
            v2 = await resolve_intent_v2(owner, payload.prompt, packet)
            plan = plan_v2(v2, packet)
            first = v2.get("tasks", [{}])[0]
            logger.info(
                "nar_v2_shadow schema=2.0 action=%s relation=%s output=%s "
                "step=%s planned_mode=%s legacy_mode=%s mismatch=%s",
                first.get("action"), first.get("target_relation"),
                first.get("desired_output"), plan["next_step"], plan["mode"],
                legacy_mode, plan["mode"] is not None and plan["mode"] != legacy_mode,
            )
        except Exception:
            # Shadow failure must not fail, retry, charge or re-route the live turn.
            logger.warning("nar_v2_shadow failed; live V1 dispatch unchanged")

    @router.get("/conversations/status")
    async def availability(request: Request):
        # The endpoint is authenticated, NOT a feature flag. A missing migration
        # is a visible setup error: the browser must never use local chat instead.
        await owner_for(request)
        if not await run_in_threadpool(ledger.ready):
            raise HTTPException(
                503, "会话数据库未完成迁移或暂时不可用，请检查 002_nar_conversation_history.sql 和 003_nar_conversation_pins.sql"
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


    async def stream_chat_turn(owner: str, cid: str, turn: dict, payload: dict):
        """Stream public chunks while a server-owned task persists the full reply.

        The detached pump continues after browser disconnect; only a provider
        interruption is marked UNKNOWN. Browser never retries upstream blindly.
        """
        run_id = "stream-" + turn["id"]
        active = await transaction(ledger.mark_running, owner, cid, turn["id"], run_id)
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        def sse(kind: str, data: dict) -> bytes:
            return ("event: " + kind + "\ndata: " + json.dumps(data, ensure_ascii=False)
                    + "\n\n").encode("utf-8")

        async def pump():
            token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
            base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
            raw, displayed = "", ""
            try:
                if len(token) < 32:
                    raise ValueError("Service token not configured")
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(150, connect=12), transport=transport,
                    trust_env=False, follow_redirects=False,
                ) as client:
                    async with client.stream(
                        "POST", base + "/v1/runs/stream", json=payload,
                        headers={"Authorization": "Bearer " + token, "X-User-ID": owner,
                                 "Accept": "text/event-stream"},
                    ) as response:
                        if response.status_code != 200:
                            raise ValueError("Streaming agent unavailable")
                        event_type, value = "", ""
                        async for line in response.aiter_lines():
                            if line.startswith("event: "):
                                event_type = line[7:].strip()
                            elif line.startswith("data: "):
                                value += line[6:]
                            elif line == "" and event_type:
                                data = json.loads(value)
                                if event_type == "delta":
                                    token_text = data.get("text", "")
                                    if not isinstance(token_text, str):
                                        raise ValueError("Invalid delta")
                                    raw += token_text
                                    if len(raw) > 16000:
                                        raise ValueError("Output exceeds bounds")
                                    safe = visible_stream_prefix(raw)
                                    if safe != displayed:
                                        # Explicit replacement avoids duplicated fragments
                                        # if the model revises an early partial answer.
                                        if safe.startswith(displayed):
                                            await queue.put(("delta", {"text": safe[len(displayed):]}))
                                        else:
                                            await queue.put(("replace", {"text": safe}))
                                        displayed = safe
                                elif event_type == "done":
                                    if str(data.get("user_id")) != owner or not isinstance(data.get("output"), str):
                                        raise ValueError("Invalid output owner")
                                    usage = data.get("usage")
                                    receipt = await finish_billing(
                                        owner, turn["id"], usage if isinstance(usage, dict) else None,
                                        success=True, duration_ms=int(data.get("duration_ms") or 0))
                                    finished = await transaction(ledger.finish_turn, owner, cid, turn["id"],
                                        output=data["output"], run_id=run_id,
                                        public_metadata={"billing": receipt, "elapsedMs": receipt["durationMs"]})
                                    await queue.put(("result", {"conversationId": cid, "turn": finished}))
                                    return
                                elif event_type == "error":
                                    raise ValueError("Agent streaming error")
                                event_type, value = "", ""
                raise ValueError("Streaming agent disconnected before final output")
            except Exception:
                failed = await transaction(
                    ledger.fail_turn, owner, cid, turn["id"], "STREAM_INTERRUPTED",
                    uncertain=True, public_error="本次对话连接中断，结果未确认，请刷新会话查看。",
                )
                await queue.put(("result", {"conversationId": cid, "turn": failed}))
            finally:
                await queue.put(("end", {}))

        job = asyncio.create_task(pump())
        live_chat_jobs.add(job)
        job.add_done_callback(live_chat_jobs.discard)

        async def chunks():
            yield sse("accepted", {"conversationId": cid, "turn": active})
            while True:
                kind, data = await queue.get()
                if kind == "end":
                    break
                yield sse(kind, data)

        return StreamingResponse(chunks(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform",
                                          "X-Accel-Buffering": "no",
                                          "X-Content-Type-Options": "nosniff"})

    async def submit_turn(owner: str, cid: str, payload: TurnRequest, *, create=False, streaming=False):
        mode = payload.mode
        parent_artifact_id = payload.parent_artifact_id
        if mode == "auto":
            # Idempotent retries retain the original mode AND parent; never
            # route or select a different work on the same request ID.
            previous = await transaction(ledger.find_request, owner, cid,
                                         payload.client_request_id)
            if previous:
                mode = previous["mode"]
                parent_artifact_id = previous.get("parentArtifactId")
            else:
                recent = [] if create else (await transaction(
                    ledger.get_messages, owner, cid, None, 10))["items"]
                history = [{"role": row["role"], "content": row["content"]}
                           for row in recent][-10:]
                selected = None
                if not create:
                    selected = await transaction(ledger.latest_artifact, owner, cid,
                                                 parent_artifact_id)
                    if parent_artifact_id and not selected:
                        # Do not edit a deleted, different-user or different-conversation work.
                        raise HTTPException(404, "所选作品在当前对话中不存在，请重新打开作品")
                    if not selected:
                        selected = await transaction(ledger.latest_artifact, owner, cid)
                current_kind = selected["kind"] if selected else None
                choice = await resolve_intent(owner, payload.prompt, history, current_kind)
                if _shadow_v2_enabled(owner, cid, payload.client_request_id):
                    # Original browser parent is an explicit selection hint only;
                    # legacy latest_artifact() fallback is NOT a V2 target.
                    selected_id = parent_artifact_id if parent_artifact_id else None
                    shadow_job = asyncio.create_task(compare_v2_shadow(
                        owner, cid, payload, history, choice,
                        selected_id, create=create))
                    live_shadow_jobs.add(shadow_job)
                    shadow_job.add_done_callback(live_shadow_jobs.discard)
                if choice in ("edit", "edit_animation"):
                    expected = "html" if choice == "edit" else "animation"
                    if selected and selected["kind"] == expected:
                        mode = "edit" if expected == "html" else "animation"
                        parent_artifact_id = selected["artifactId"]
                    else:
                        # No matching artifact: ask an accessible question in chat
                        # rather than start a new builder of the wrong kind.
                        mode, parent_artifact_id = "chat", None
                else:
                    mode, parent_artifact_id = choice, None
        turn, new = await transaction(ledger.start_turn, owner, cid,
             payload.client_request_id, payload.prompt, mode,
             parent_artifact_id, create=create)
        if not new:
            # Idempotent reads must never re-dispatch a previously submitted turn.
            return {"conversationId": cid, "turn": turn, "reused": True}
        # Reserve on a NEW turn only. The original request idempotency key
        # prevents a duplicate charge on browser retries.
        try:
            await reserve_turn(owner, turn["id"], mode)
        except HTTPException as exc:
            await transaction(ledger.fail_turn, owner, cid, turn["id"],
                              "CREDITS_INSUFFICIENT" if exc.status_code == 402 else "BILLING_UNAVAILABLE",
                              public_error=str(exc.detail))
            return {"conversationId": cid, "turn": {**turn, "status": "FAILED",
                "errorCode": "CREDITS_INSUFFICIENT" if exc.status_code == 402 else "BILLING_UNAVAILABLE"}}
        history = await transaction(ledger.model_history, owner, cid, turn["id"])
        request_body = {"prompt": payload.prompt, "history": history}
        if mode == "edit" or (mode == "animation" and parent_artifact_id):
            if not parent_artifact_id:
                await finish_billing(owner, turn["id"], None, success=False)
                await transaction(ledger.fail_turn, owner, cid, turn["id"], "MISSING_PARENT")
                return {"conversationId": cid, "turn": {**turn, "status": "FAILED", "errorCode": "MISSING_PARENT"}}
            request_body["parent_artifact_id"] = parent_artifact_id
        if streaming and mode == "chat":
            return await stream_chat_turn(owner, cid, turn, request_body)
        try:
            task = await agent_request(owner, mode, request_body)
        except HTTPException as exc:
            # A 4xx means a known refusal. Network/5xx is ambiguous: provider
            # may have accepted it. Never automatically create another run.
            uncertain = exc.status_code not in (404, 422, 429)
            if not uncertain:
                await finish_billing(owner, turn["id"], None, success=False)
            failed = await transaction(ledger.fail_turn, owner, cid, turn["id"],
                 "DISPATCH_UNCERTAIN" if uncertain else "DISPATCH_REJECTED", uncertain=uncertain)
            return {"conversationId": cid, "turn": failed}
        await transaction(ledger.mark_running, owner, cid, turn["id"], task["id"])
        if mode == "chat":
            receipt = await finish_billing(owner, turn["id"], task.get("usage"),
                                           success=True, duration_ms=task.get("duration_ms", 0))
            finished = await transaction(ledger.finish_turn, owner, cid, turn["id"],
                 output=task.get("output", ""), run_id=task["id"],
                 public_metadata={"billing": receipt, "elapsedMs": receipt["durationMs"]})
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

    @router.post("/conversations/stream")
    async def create_conversation_stream(payload: FirstTurnRequest, request: Request):
        mutate(request)
        owner = await owner_for(request)
        return await submit_turn(owner, payload.conversation_id, payload,
                                 create=True, streaming=True)

    @router.post("/conversations/{cid}/turns/stream")
    async def post_turn_stream(cid: str, payload: TurnRequest, request: Request):
        mutate(request)
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid):
            raise HTTPException(404, "会话不存在")
        return await submit_turn(owner, cid, payload, streaming=True)

    @router.get("/conversations/{cid}/turns/{tid}")
    async def poll_turn(cid: str, tid: str, request: Request):
        owner = await owner_for(request)
        if not re.fullmatch(ID, cid) or not re.fullmatch(ID, tid):
            raise HTTPException(404, "轮次不存在")
        turn = await transaction(ledger.get_turn, owner, cid, tid)
        if turn["status"] != "RUNNING" or not turn["runId"]:
            return {"turn": turn}
        if turn["mode"] == "chat" and turn["runId"].startswith("stream-"):
            # A process restart can orphan an in-process stream pump. Do not
            # re-dispatch automatically; eventually mark its status uncertain.
            created = datetime.fromisoformat(turn["createdAt"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created > timedelta(minutes=15):
                unknown = await transaction(ledger.fail_turn, owner, cid, tid,
                                            "STREAM_NOT_RECOVERABLE", uncertain=True)
                return {"turn": unknown}
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
                await finish_billing(owner, tid, task.get("usage"), success=False)
                failed = await transaction(ledger.fail_turn, owner, cid, tid, "ARTIFACT_MISSING")
                return {"turn": failed, "task": task}
            receipt = await finish_billing(owner, tid, task.get("usage"),
                                           success=task["status"] == "SUCCEEDED",
                                           duration_ms=task.get("elapsed_ms", 0))
            if task["status"] == "SUCCEEDED":
                work_kind = "animation" if turn["mode"] == "animation" else "html"
                result = await transaction(ledger.finish_turn, owner, cid, tid,
                    output=task.get("output") or "学习作品已完成。",
                    artifact_id=aid if isinstance(aid, str) and re.fullmatch(ID, aid) else None,
                    title=(task.get("public_brief") or "互动学习作品")[:160],
                    kind=work_kind, run_id=turn["runId"],
                    public_metadata={"timeline": task.get("timeline"), "publicBrief": task.get("public_brief"),
                                     "learningPlan": task.get("learning_plan"),
                                     "elapsedMs": task.get("elapsed_ms"), "billing": receipt})
            else:
                safe_error = task.get("error")
                if not isinstance(safe_error, str) or not safe_error.strip():
                    safe_error = "任务执行失败，请查看错误码并联系维护人员排查。"
                safe_code = str(task.get("error_code") or "GENERATION_FAILED")[:80]
                safe_phase = task.get("phase")
                safe_phase = safe_phase if isinstance(safe_phase, str) else None
                result = await transaction(ledger.fail_turn, owner, cid, tid,
                    safe_code, public_error=safe_error,
                    phase=safe_phase, public_metadata={"billing": receipt})
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
