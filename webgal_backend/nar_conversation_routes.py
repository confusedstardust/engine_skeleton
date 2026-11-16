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
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from .nar_conversation_store import (
    ConversationConflict, ConversationMissing, NarConversationStore,
)
from .work_store import WorkStore
from .nar_choice_protocol import visible_stream_prefix
from .nar_intent_v2 import build_context_packet, plan_v2
from .nar_rpg_options import draft_game_spec, compile_webgal_request
from .nar_pending_schema_v2 import ClarificationAnswer
from .nar_pending_v2 import make_clarification_metadata, validate_clarification_answer
from .nar_billing import NarTurnBilling, safe_usage_metadata
from credit_system import InsufficientCreditsError

ID = r"^[0-9a-f]{32}$"
logger = logging.getLogger(__name__)


def _stable_v2_sample(owner: str, cid: str, request_id: str, environment_key: str) -> bool:
    """Deterministic request sampling. Unset, zero or invalid => disabled."""
    try:
        percent = float(os.getenv(environment_key, "0"))
    except ValueError:
        return False
    if not 0 < percent <= 100:
        return False
    value = int.from_bytes(hashlib.sha256(
        f"{owner}:{cid}:{request_id}".encode("utf-8")).digest()[:8], "big")
    return value / (2 ** 64) < percent / 100


def _live_v2_enabled(owner: str, cid: str, request_id: str) -> bool:
    return _stable_v2_sample(owner, cid, request_id, "NAR_INTENT_V2_LIVE_PERCENT")


def _shadow_v2_enabled(owner: str, cid: str, request_id: str) -> bool:
    return _stable_v2_sample(owner, cid, request_id, "NAR_INTENT_V2_SHADOW_PERCENT")



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


class RpgOptionsRequest(BaseModel):
    model_config = {"extra": "forbid"}
    specVersion: int = Field(ge=1)
    durationMinutes: int = Field(ge=5, le=60)
    generateImages: StrictBool
    enableVoice: StrictBool


class RpgConfirmRequest(RpgOptionsRequest):
    acceptedHoldCredits: int = Field(ge=1)


class WorkAssociation(BaseModel):
    model_config = {"extra": "forbid"}
    artifact_id: str = Field(pattern=ID)
    work_id: str = Field(pattern=ID)


def create_router(*, user_for_request, store: NarConversationStore | None = None,
                  works: WorkStore | None = None, transport=None, billing_factory=None,
                  rpg_create=None, rpg_get=None, rpg_run=None,
                  rpg_quote=None, rpg_balance=None):
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
                "public_brief", "public_brief_state", "duration_ms", "usage", "usage_status",
                "usage_events"
            ) if key in data}
        except (TypeError, ValueError, KeyError):
            raise HTTPException(502, "执行服务的用户归属或响应内容无效") from None

    def metering_sample(owner: str, cid: str, request_id: str) -> bool:
        """Stable company-side telemetry sampling, independent of live billing."""
        try:
            percent = max(0, min(100, int(os.getenv("NAR_BILLING_V2_METER_SHADOW_PERCENT", "0"))))
        except ValueError:
            percent = 0
        if percent == 0:
            return False
        digest = hashlib.sha256(
            ("nar-billing-v2:" + owner + ":" + cid + ":" + request_id).encode()
        ).digest()
        return int.from_bytes(digest[:4], "big") % 100 < percent

    async def persist_metering_events(owner: str, cid: str, request_id: str,
                                      events: list | None, *, turn_id: str | None = None,
                                      shadow: bool = False, sampled: bool | None = None) -> None:
        """Append company telemetry only. No charges and no V1 settlement changes.

        Migration 006 must be installed before enabling this opt-in feature.
        """
        if not isinstance(events, list) or not (
            sampled if sampled is not None else metering_sample(owner, cid, request_id)
        ):
            return
        try:
            from credit_system.config import CreditDatabaseConfig
            from forge_database import mysql_connection_factory
            from .nar_usage_store_v2 import ModelUsageEvent, NarUsageEventStore
            from .nar_metering_v2 import normalize_provider_usage

            def save():
                store = NarUsageEventStore(mysql_connection_factory(CreditDatabaseConfig.from_env()))
                for item in events[:200]:
                    if not isinstance(item, dict):
                        continue
                    call_id = item.get("call_id")
                    stage = "intent_shadow" if shadow else item.get("stage")
                    provider = item.get("provider")
                    if not all(isinstance(k, str) for k in (call_id, stage, provider)):
                        continue
                    usage = normalize_provider_usage(item.get("usage"), provider)
                    event_key = "narmeter." + hashlib.sha256(
                        (owner + "|" + cid + "|" + request_id + "|" + stage + "|" + call_id)
                        .encode()).hexdigest()
                    store.record(ModelUsageEvent(
                        event_key=event_key, owner_user_id=owner,
                        conversation_id=cid, turn_id=turn_id, call_id=call_id,
                        stage=stage, provider=provider,
                        requested_model=item.get("requested_model"),
                        actual_model=item.get("actual_model"), usage=usage,
                        billable_to_user=False,
                    ))
            await run_in_threadpool(save)
        except Exception:
            logger.warning("NarAgent V2 telemetry persistence failed; V1 user billing unchanged")

    async def resolve_intent(owner: str, prompt: str, history: list[dict],
                             current_artifact_kind: str | None, *,
                             metering_enabled: bool = False,
                             usage_sink: list | None = None) -> str:
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
                          "current_artifact_kind": current_artifact_kind,
                          **({"metering_enabled": True} if metering_enabled else {})},
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
            if usage_sink is not None and isinstance(data.get("usage_events"), list):
                usage_sink.extend(data["usage_events"])
            return data["mode"]
        except (ValueError, KeyError, TypeError):
            raise HTTPException(502, "需求识别结果无效") from None

    async def resolve_intent_v2(owner: str, prompt: str, packet: dict, *,
                                metering_enabled: bool = False,
                                usage_sink: list | None = None,
                                shadow: bool = False) -> dict:
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
                      "context_v2": packet,
                      **({"metering_enabled": True,
                          "metering_role": "shadow" if shadow else "live"}
                         if metering_enabled else {})},
                headers={"Authorization": "Bearer " + token, "X-User-ID": owner},
            )
        if response.status_code != 200:
            raise ValueError("V2 shadow service error")
        data = response.json()
        if (data.get("user_id") != owner or data.get("schema_version") != "2.0"
                or not isinstance(data.get("decision"), dict)):
            raise ValueError("V2 shadow returned invalid envelope")
        if usage_sink is not None and isinstance(data.get("usage_events"), list):
            usage_sink.extend(data["usage_events"])
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
            usage_events = []
            metered = metering_sample(owner, cid, payload.client_request_id)
            v2 = await resolve_intent_v2(owner, payload.prompt, packet,
                                         metering_enabled=metered,
                                         usage_sink=usage_events, shadow=True)
            await persist_metering_events(owner, cid, payload.client_request_id,
                                          usage_events, shadow=True)
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

    async def fetch_v2_capabilities(owner: str) -> dict[str, list[str]]:
        """Fetch authenticated service truth; never trust browser capability flags."""
        token = os.getenv("NAR_AGENT_SERVICE_TOKEN", "")
        if len(token) < 32:
            raise HTTPException(503, "无法验证当前创作能力，本次未执行")
        base = os.getenv("NAR_AGENT_URL", "http://127.0.0.1:8020").rstrip("/")
        try:
            async with httpx.AsyncClient(
                timeout=10, transport=transport, trust_env=False, follow_redirects=False
            ) as client:
                response = await client.get(base + "/v1/capabilities",
                    headers={"Authorization": "Bearer " + token, "X-User-ID": owner})
            if response.status_code != 200:
                raise ValueError("Capability endpoint unavailable")
            data = response.json()
            caps = data.get("capabilities")
            allowed = {
                "chat": {"answer", "discuss", "evaluate"},
                "html": {"create", "revise"},
                "animation": {"create", "revise"},
                "hybrid": {"plan_only"},
            }
            if data.get("schema_version") != "2.0" or not isinstance(caps, dict):
                raise ValueError("Invalid capability schema")
            if set(caps) != set(allowed):
                raise ValueError("Incomplete capabilities")
            for name, values in caps.items():
                if not isinstance(values, list) or any(
                    not isinstance(item, str) or item not in allowed[name]
                    for item in values):
                    raise ValueError("Invalid capability value")
            # RPG is a first-party Forge/WebGAL capability, not an optional
            # feature flag. Advertise it whenever the real integration is wired.
            if rpg_ready():
                return {**caps, "game": ["create", "edit_link"]}
            return caps
        except (httpx.HTTPError, ValueError, TypeError):
            raise HTTPException(503, "执行能力检查暂不可用，本次没有开始创作") from None

    async def resolve_v2_live(owner: str, cid: str, payload: TurnRequest,
                              *, create: bool) -> dict:
        """Evaluate V2 without mutating state or reserving credits."""
        selected_id = payload.selected_artifact_id
        if create and selected_id is not None:
            raise HTTPException(422, "新会话不能引用其他会话的作品")
        recent = [] if create else (await transaction(
            ledger.get_messages, owner, cid, None, 12))["items"]
        history = [{"role": row["role"], "content": row["content"]}
                   for row in recent][-12:]
        candidates = [] if create else await transaction(
            ledger.artifact_candidates, owner, cid, selected_id)
        pending = None
        answer_data = None
        if not create:
            pending = await transaction(ledger.get_pending_clarification,
                                        owner, cid,
                                        payload.clarification_answer.clarification_id
                                        if payload.clarification_answer else None)
        if payload.clarification_answer:
            if not pending:
                raise HTTPException(404, "原来的选择问题已不存在，请重新描述需求")
            try:
                answer_data = validate_clarification_answer(
                    pending["metadata"], payload.clarification_answer)
            except ValueError:
                raise HTTPException(409, "这个选择已经失效，请刷新对话后再操作") from None
        task = pending["metadata"].get("pending_task_v2") if pending else None
        pending_question = pending["metadata"].get("clarification_v2") if pending else None
        if answer_data:
            pending_question = {**(pending_question or {}),
                                "current_answer": answer_data}
        service_caps = await fetch_v2_capabilities(owner)
        games = (await transaction(ledger.recent_rpg_games, owner, cid)) if (
            not create and "game" in service_caps) else []
        packet = build_context_packet(
            payload.prompt, cid, history, candidates, selected_id,
            pending_task=task, pending_clarification=pending_question,
            capabilities=service_caps, owner_scoped_games=games,
        )
        usage_events = []
        metered = metering_sample(owner, cid, payload.client_request_id)
        try:
            proposal = await resolve_intent_v2(owner, payload.prompt, packet,
                                                metering_enabled=metered,
                                                usage_sink=usage_events)
        except Exception:
            raise HTTPException(503, "需求识别暂时不可用，本次未执行任何创作") from None
        plan = plan_v2(proposal, packet)
        if plan["mode"] in ("edit", "animation") and plan["parent_artifact_id"]:
            parent_id = plan["parent_artifact_id"]
            saved = await run_in_threadpool(work_store.find_by_artifact, owner, parent_id)
            if saved:
                current = next((v for v in saved.get("versions", [])
                                if v.get("id") == saved.get("current_version_id")), None)
                if not current or current.get("artifact_id") != parent_id:
                    raise HTTPException(409, "作品版本已更新，请重新打开最新版本")
        return {"proposal": proposal, "plan": plan, "packet": packet,
                "pending": pending, "answer": answer_data,
                "usage_events": usage_events}

    def first_is_independent_game(proposal: dict) -> bool:
        first = (proposal.get("tasks") or [{}])[0]
        return first.get("action") == "create" and first.get("target_relation") == "new"

    def v2_clarification_proposal(proposal: dict, packet: dict) -> dict:
        """Supply one accessible question if the model omitted crucial detail."""
        if (proposal.get("next_step") == "clarify"
                and isinstance(proposal.get("clarification"), dict)):
            return proposal
        candidates = packet["workspace"]["recent_artifacts"]
        task = proposal["tasks"][0]
        games = packet["workspace"].get("recent_games", [])
        if task.get("desired_output") == "game" and task.get("action") == "revise":
            labels = [item["title"] or ("游戏 " + item["id"][:6]) for item in games[:4]]
            if len(labels) < 2:
                labels = ["编辑当前游戏", "另做一个新的互动剧情游戏"]
            question = "你要编辑哪一款游戏？如果没有对应项，请直接描述游戏名称。"
        elif task.get("action") == "revise" and len(candidates) > 1:
            labels = [item["title"] or ("作品 " + item["id"][:6])
                      for item in candidates[:4]]
            question = "你想修改哪一件作品？"
        elif task.get("desired_output") == "unspecified":
            labels = ["做成可以操作的互动网页", "做成教学动画", "做成可选择剧情的互动游戏"]
            question = "你希望最终得到哪一种作品？"
        else:
            labels = ["继续修改现有作品", "新建一份独立作品"]
            question = "你希望我接下来怎么做？"
        if len(set(labels)) != len(labels):
            labels = [f"作品 {i+1}：" + name for i, name in enumerate(labels)]
        return {**proposal, "next_step": "clarify", "clarification": {
            "question": question, "options": labels, "allow_custom": True}}

    def rpg_ready() -> bool:
        """Game creation uses Forge's existing WebGAL service callbacks."""
        return all(callable(fn) for fn in (
            rpg_create, rpg_get, rpg_run, rpg_quote, rpg_balance
        ))

    def ensure_rpg_available() -> None:
        # Fail closed only if WebGAL is genuinely not wired, never because
        # somebody forgot to set an unrelated environment variable.
        if not rpg_ready():
            raise HTTPException(503, "RPG 工作台服务尚未配置")

    def public_rpg_card(card: dict) -> dict:
        rpg = card["rpg"]
        spec = rpg.get("spec") or {}
        prompt = card.get("original_prompt") or ""
        return {
            "messageId": card["message_id"], "state": rpg.get("state"),
            "specVersion": rpg.get("spec_version", 1),
            "spec": {
                "topic": spec.get("topic") or "互动叙事游戏",
                "sourceSummary": f"引用本轮创作要求和材料（{len(prompt)} 字）",
                "durationMinutes": spec.get("duration_minutes", 20),
                "generateImages": spec.get("generate_images", True),
                "enableVoice": spec.get("enable_voice", False),
            },
            "jobId": rpg.get("job_id"), "canConfirm": rpg.get("state") == "PREPARED",
            "confirmedOptions": rpg.get("confirmed_options"),
            "lastErrorCode": rpg.get("last_error_code"),
        }

    def confirmed_choices(payload: RpgOptionsRequest) -> dict:
        return {"durationMinutes": payload.durationMinutes,
                "generateImages": payload.generateImages, "enableVoice": payload.enableVoice}

    def compile_confirmed(card: dict, payload: RpgOptionsRequest) -> dict:
        if card["rpg"].get("spec_version") != payload.specVersion:
            raise HTTPException(409, "SPEC_VERSION_CHANGED")
        try:
            origin = card["original_prompt"]
            resume = card["rpg"].get("continued_requirements")
            if isinstance(resume, str) and resume.strip():
                origin = ("用户在前轮对话中的原始创作要求和选择：\n"
                          + resume[:3000] + "\n本轮回复：\n" + origin)
            return compile_webgal_request(
                card["rpg"]["spec"], original_prompt=origin,
                duration_minutes=payload.durationMinutes,
                generate_images=payload.generateImages, enable_voice=payload.enableVoice)
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc)[:240]) from None

    async def owned_rpg_card(owner: str, cid: str, mid: str) -> dict:
        if not re.fullmatch(ID, cid) or not re.fullmatch(ID, mid):
            raise HTTPException(404, "游戏任务不存在")
        return await transaction(ledger.get_owned_rpg_message, owner, cid, mid)

    @router.get("/conversations/{cid}/messages/{mid}/rpg")
    async def get_rpg_card(cid: str, mid: str, request: Request):
        owner = await owner_for(request)
        card = await owned_rpg_card(owner, cid, mid)
        job_id = card["rpg"].get("job_id")
        if job_id:
            if not callable(rpg_get):
                raise HTTPException(503, "游戏工作台查询暂不可用")
            await run_in_threadpool(rpg_get, owner, job_id)
        return public_rpg_card(card)

    async def rpg_price_and_balance(owner: str, options: dict) -> tuple[int, int]:
        """Use the existing RPG price and balance; never leak credit-store exceptions."""
        try:
            hold, balance = await asyncio.gather(
                run_in_threadpool(rpg_quote, options),
                run_in_threadpool(rpg_balance, owner))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "RPG 报价或积分系统暂时不可用，请稍后再试") from None
        if type(hold) is not int or hold < 1 or type(balance) is not int:
            raise HTTPException(503, "RPG 报价或积分返回值无效")
        return hold, balance

    @router.post("/conversations/{cid}/messages/{mid}/rpg/quote")
    async def quote_rpg(cid: str, mid: str, payload: RpgOptionsRequest, request: Request):
        mutate(request)
        ensure_rpg_available()
        owner = await owner_for(request)
        card = await owned_rpg_card(owner, cid, mid)
        if card["rpg"].get("state") != "PREPARED":
            raise HTTPException(409, "ALREADY_CONFIRMED_OR_CANCELLED")
        request_body = compile_confirmed(card, payload)
        hold, balance = await rpg_price_and_balance(owner, request_body["options"])
        return {"holdCredits": hold, "optionsValid": True,
                "sufficientBalance": balance >= hold,
                "description": "预计预冻结积分，最终按 WebGAL 原有规则结算"}

    @router.post("/conversations/{cid}/messages/{mid}/rpg/confirm", status_code=202)
    async def confirm_rpg(cid: str, mid: str, payload: RpgConfirmRequest,
                          request: Request, background_tasks: BackgroundTasks):
        mutate(request)
        ensure_rpg_available()
        owner = await owner_for(request)
        card = await owned_rpg_card(owner, cid, mid)
        choices = confirmed_choices(payload)
        current = card["rpg"]
        if current.get("state") != "PREPARED":
            if (current.get("confirmed_options") == choices
                    and current.get("confirmed_hold_credits") == payload.acceptedHoldCredits):
                return public_rpg_card(card)
            raise HTTPException(409, "ALREADY_CONFIRMED")
        request_body = compile_confirmed(card, payload)
        hold, balance = await rpg_price_and_balance(owner, request_body["options"])
        if payload.acceptedHoldCredits != hold:
            raise HTTPException(409, "PRICE_CHANGED")
        if balance < hold:
            raise HTTPException(402, "积分不足，请充值后重新确认")
        won = await transaction(ledger.claim_rpg_message, owner, cid, mid,
                                version=payload.specVersion,
                                confirmed_options=choices, hold=hold)
        if not won:
            refreshed = await owned_rpg_card(owner, cid, mid)
            current = refreshed["rpg"]
            if (current.get("confirmed_options") == choices
                    and current.get("confirmed_hold_credits") == hold):
                return public_rpg_card(refreshed)
            raise HTTPException(409, "SPEC_VERSION_CHANGED_OR_ALREADY_CONFIRMED")
        # Only the successful CAS winner is allowed to create and start a Job.
        job_id = None
        try:
            job = await run_in_threadpool(rpg_create, owner, request_body)
            job_id = str(job["id"])
            if not re.fullmatch(ID, job_id):
                raise ValueError("Invalid WebGAL Job ID")
            await transaction(ledger.attach_rpg_job, owner, cid, mid, job_id)
            await transaction(ledger.transition_rpg_message, owner, cid, mid,
                              "JOB_CREATED", "STARTING")
        except Exception as exc:
            # May have created a Job before the response/metadata failed.
            # Do not log the source text, credentials or credit details.
            logger.error(
                "nar_rpg_create_or_bind_uncertain cid=%s mid=%s job_id=%s error_type=%s",
                cid, mid, job_id, type(exc).__name__,
            )
            try:
                latest = await owned_rpg_card(owner, cid, mid)
                latest_state = latest["rpg"].get("state")
                if latest_state in ("CLAIMED", "JOB_CREATED"):
                    await transaction(ledger.transition_rpg_message, owner, cid, mid,
                                      latest_state, "NEEDS_REVIEW", "CREATE_RESULT_UNCERTAIN")
            except HTTPException:
                # The conversation may have been deleted. Never create again.
                logger.warning("nar_rpg_manual_review cid=%s mid=%s job_id=%s",
                               cid, mid, job_id)
            return public_rpg_card(await owned_rpg_card(owner, cid, mid))
        try:
            await run_in_threadpool(rpg_run, job_id, request, background_tasks)
        except HTTPException as exc:
            # 409 may mean another worker/manual workbench started the SAME Job:
            # check its authoritative state, never label it a definite failure.
            state = "START_REJECTED" if exc.status_code in (402, 404, 422) else "NEEDS_REVIEW"
            logger.warning(
                "nar_rpg_run_rejected cid=%s mid=%s job_id=%s http_status=%s state=%s",
                cid, mid, job_id, exc.status_code, state,
            )
            await transaction(ledger.transition_rpg_message, owner, cid, mid,
                              "STARTING", state, "RUN_REJECTED" if state == "START_REJECTED"
                              else "RUN_RESULT_UNKNOWN")
        except Exception as exc:
            logger.error("nar_rpg_run_uncertain cid=%s mid=%s job_id=%s error_type=%s",
                         cid, mid, job_id, type(exc).__name__)
            await transaction(ledger.transition_rpg_message, owner, cid, mid,
                              "STARTING", "NEEDS_REVIEW", "RUN_RESULT_UNKNOWN")
        else:
            await transaction(ledger.transition_rpg_message, owner, cid, mid,
                              "STARTING", "STARTED")
        return public_rpg_card(await owned_rpg_card(owner, cid, mid))

    @router.post("/conversations/{cid}/messages/{mid}/rpg/cancel")
    async def cancel_rpg(cid: str, mid: str, request: Request):
        mutate(request)
        ensure_rpg_available()
        owner = await owner_for(request)
        await owned_rpg_card(owner, cid, mid)
        await transaction(ledger.cancel_rpg_message, owner, cid, mid)
        return public_rpg_card(await owned_rpg_card(owner, cid, mid))

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
                                    if isinstance(data.get("usage_events"), list):
                                        await persist_metering_events(
                                            owner, cid, turn["id"], data["usage_events"],
                                            turn_id=turn["id"], sampled=True)
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
        v2_live = None
        intent_usage_events = []
        metering_enabled = metering_sample(owner, cid, payload.client_request_id)
        if payload.clarification_answer and mode != "auto":
            raise HTTPException(422, "澄清答复必须通过自动路由提交")
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
                # V2 is the ONLY official auto-intent route. Never sample per
                # request, dispatch to V1, or silently downgrade on V2 errors.
                # Legacy V1 dispatch (resolve_intent -> html/animation/edit)
                # is intentionally disabled; see git history for rollback.
                v2_live = await resolve_v2_live(owner, cid, payload, create=create)
                intent_usage_events.extend(v2_live.get("usage_events") or [])
                plan = v2_live["plan"]
                mode = plan["mode"] or "chat"
                parent_artifact_id = plan["parent_artifact_id"]
        if mode in ("rpg.prepare", "rpg.edit_link"):
            ensure_rpg_available()
            if mode == "rpg.edit_link":
                game_id = v2_live["plan"].get("game_job_id") if v2_live else None
                if not game_id:
                    raise HTTPException(404, "未能确定要编辑哪一款游戏")
                try:
                    await run_in_threadpool(rpg_get, owner, game_id)
                except FileNotFoundError:
                    raise HTTPException(404, "游戏不存在或没有访问权限") from None
            # Existing nar_turns.mode ENUM has no RPG member.
            # The confirmed game runs separately, outside ConversationTurn.
            mode = "chat"
        turn, new = await transaction(ledger.start_turn, owner, cid,
             payload.client_request_id, payload.prompt, mode,
             parent_artifact_id, create=create)
        if not new:
            # Idempotent reads must never re-dispatch a previously submitted turn.
            return {"conversationId": cid, "turn": turn, "reused": True}
        if metering_enabled and intent_usage_events:
            await persist_metering_events(owner, cid, payload.client_request_id,
                                          intent_usage_events, turn_id=turn["id"])
        if v2_live:
            plan = v2_live["plan"]
            if v2_live["answer"]:
                # The answer is consumed with owner-scoped CAS; only this request
                # can resume the original task. No work is dispatched before CAS.
                try:
                    await transaction(ledger.claim_clarification_answer, owner, cid,
                                      payload.client_request_id,
                                      payload.clarification_answer.model_dump())
                except HTTPException:
                    await transaction(ledger.fail_turn, owner, cid, turn["id"],
                                      "CLARIFICATION_CONFLICT")
                    raise
            proposal = v2_live["proposal"]
            if plan["next_step"] in ("clarify", "capability_review"):
                if plan["next_step"] == "clarify":
                    proposal = v2_clarification_proposal(proposal, v2_live["packet"])
                    metadata = make_clarification_metadata(
                        proposal, origin_turn_id=turn["id"],
                        verified_target_artifact_id=plan["parent_artifact_id"])
                    response_text = metadata["choices"]["question"]
                else:
                    metadata = {"intent_v2": {"schema_version": "2.0",
                                             "next_step": "capability_review"}}
                    response_text = (
                        "这项需求涉及转换作品格式、组合多个产物或当前暂不支持的操作。"
                        "我不会未经你同意改用另一种工具重新制作。"
                        "你可以单独提出制作网页、制作动画，或先让我讨论实现方案。")
                finished = await transaction(
                    ledger.finish_turn, owner, cid, turn["id"],
                    output=response_text, public_metadata=metadata)
                return {"conversationId": cid, "turn": finished}
            # RPG only prepares a short, durable Assistant message. It does not
            # reserve NarAgent chat credits or create a WebGAL Job.
            if plan["mode"] == "rpg.prepare":
                spec_source = payload.prompt
                source_turn_id = None
                if v2_live["answer"] and v2_live["pending"]:
                    pending_task = v2_live["pending"]["metadata"].get("pending_task_v2") or {}
                    source_turn_id = pending_task.get("origin_turn_id")
                    # Preserve original pasted material, not just a compressed
                    # model goal, when the user replies "choose first option".
                    previous = await transaction(
                        ledger.get_turn_original_prompt, owner, cid, source_turn_id)
                    spec_source = previous + "\n" + payload.prompt
                spec = draft_game_spec(spec_source, proposal["tasks"][0])
                metadata = {"card_type": "rpg", "rpg": {
                    "schema_version": 1, "state": "PREPARED", "spec_version": 1,
                    "spec": spec, "job_id": None, "confirmed_options": None,
                    "confirmed_hold_credits": None, "last_error_code": None,
                }}
                if source_turn_id:
                    metadata["rpg"]["source_turn_id"] = source_turn_id
                if v2_live["answer"] and v2_live["pending"]:
                    original = (v2_live["pending"]["metadata"]
                                .get("pending_task_v2") or {}).get("proposal") or {}
                    previous = (original.get("tasks") or [{}])[0]
                    goal = str(previous.get("goal") or "")[:500]
                    requirements = "；".join(
                        str(item)[:200] for item in (previous.get("requirements") or [])[:12])
                    selected = "、".join(v2_live["answer"].get("selected_labels") or [])
                    custom = str(v2_live["answer"].get("custom_text") or "")[:2000]
                    metadata["rpg"]["continued_requirements"] = (
                        f"目标：{goal}\n原要求：{requirements}\n已确认选项：{selected}\n用户补充：{custom}"
                    )[:3000]
                finished = await transaction(
                    ledger.finish_turn, owner, cid, turn["id"],
                    output="已整理好互动剧情游戏配置，请确认选项和积分后开始制作。",
                    public_metadata=metadata)
                if (not v2_live["answer"] and first_is_independent_game(proposal)
                        and v2_live["pending"]):
                    await transaction(ledger.supersede_pending_clarification, owner, cid)
                return {"conversationId": cid, "turn": finished}
            if plan["mode"] == "rpg.edit_link":
                job_id = plan["game_job_id"]
                # Owner was checked above before this Turn was created.
                finished = await transaction(
                    ledger.finish_turn, owner, cid, turn["id"],
                    output="这款游戏可以在教师工作台中直接修改，点击下方入口即可打开编辑页面。",
                    public_metadata={"rpg_edit_link": {"job_id": job_id}})
                return {"conversationId": cid, "turn": finished}
            # Independent new work replaces an unfinished clarification only
            # after our new turn has successfully claimed its idempotency key.
            first = proposal.get("tasks", [{}])[0]
            if (not v2_live["answer"] and first.get("action") == "create"
                    and first.get("target_relation") == "new"
                    and v2_live["pending"]):
                await transaction(ledger.supersede_pending_clarification, owner, cid)
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
        if metering_enabled:
            request_body["metering_enabled"] = True
        if v2_live and v2_live["answer"] and v2_live["pending"]:
            previous = v2_live["pending"]["metadata"]["pending_task_v2"]["proposal"]
            task = previous["tasks"][0]
            goal = str(task["goal"])
            requirements = "；".join(task.get("requirements") or [])
            request_body["prompt"] = (
                f"继续完成之前尚未交付的任务：{goal}\n"
                f"原任务要求：{requirements}\n"
                f"用户已确认的选择：{', '.join(v2_live['answer']['selected_labels'])}\n"
                f"用户补充：{v2_live['answer']['custom_text']}\n"
                f"最新用户消息：{payload.prompt}"
            )[:12000]
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
            if isinstance(task.get("usage_events"), list):
                await persist_metering_events(
                    owner, cid, turn["id"], task["usage_events"],
                    turn_id=turn["id"], sampled=True)
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
            if isinstance(task.get("usage_events"), list):
                await persist_metering_events(
                    owner, cid, tid, task["usage_events"],
                    turn_id=tid, sampled=True)
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
