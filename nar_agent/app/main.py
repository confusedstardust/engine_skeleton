import asyncio
import logging
import secrets
import traceback
from time import monotonic
from uuid import uuid4
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.messages import HumanMessage
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from pydantic import BaseModel, Field, model_validator

from agents.teaching import build_agent, initial_state
from app.config import Settings
from app.artifacts import ArtifactStore
from app.progress_events import enter_phase, close_phase, public_elapsed_ms
from app.progress_stream import stream_progress
from app.public_brief import stream_public_brief
from app.html_diagnostics import NO_BUILD_RECOVERY_INSTRUCTION, summarize_html_run
from agents.animation import animation_state, build_animation_agent
from agents.html_builder import build_html_agent, html_initial_state

logger = logging.getLogger(__name__)


def animation_failure_diagnostics(error: Exception) -> str:
    # Provider exception messages/bodies can contain prompts or credentials.
    # Record frame locations without source lines, locals or exception values.
    entries = []
    seen = set()
    while error is not None and id(error) not in seen and len(seen) < 5:
        seen.add(id(error))
        status = getattr(error, "status_code", None)
        frames = traceback.extract_tb(error.__traceback__)[-12:]
        entries.append(type(error).__name__ + (f" HTTP={status}" if isinstance(status, int) else "") + " " + " -> ".join(f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames))
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return " | caused_by: ".join(entries)


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class RunInput(BaseModel):
    model_config = {"extra": "forbid"}
    prompt: str = Field(min_length=1, max_length=12000, pattern=r"\S")
    history: list[HistoryMessage] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def bounded_context(self):
        if sum(len(m.content) for m in self.history) + len(self.prompt) > 36000:
            raise ValueError("Conversation too long")
        return self


class HtmlInput(RunInput):
    parent_artifact_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def create_app(settings: Settings | None = None, *, agent_factory=build_agent, animation_factory=build_animation_agent, html_factory=build_html_agent) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="NarAgent", version="0.1.0")
    app.state.active_runs = 0
    app.state.animations = {}
    app.state.animation_handles = set()
    app.state.animation_active = False
    app.state.html_runs = {}
    app.state.html_handles = set()
    app.state.html_active = False

    async def principal(
        authorization: str = Header(default=""),
        x_user_id: str = Header(default="", min_length=1, max_length=191),
    ) -> str:
        token = settings.service_token.get_secret_value()
        if len(token) < 32 or token.startswith("replace-with-"):
            raise HTTPException(503, "Service authentication is not configured")
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "Invalid service credentials")
        if not x_user_id.strip():
            raise HTTPException(400, "Trusted caller must supply X-User-ID")
        return x_user_id

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "development", "execution": "isolated-container-broker" if settings.animation_enabled else "virtual-files-only"}

    @app.get("/ready")
    async def ready():
        if not settings.ready:
            raise HTTPException(503, "Configure service token and model API key")
        if (settings.animation_enabled or settings.html_builder_enabled) and len(settings.execution_token.get_secret_value()) < 32:
            raise HTTPException(503, "Configure execution token")
        return {"status": "configured", "provider_connectivity": "not_checked"}

    @app.post("/v1/animations", status_code=202)
    async def create_animation(payload: RunInput, user_id: str = Depends(principal)):
        if not settings.ready or not settings.animation_enabled or len(settings.execution_token.get_secret_value()) < 32:
            raise HTTPException(503, "Animation execution is not configured")
        if app.state.animation_active or app.state.html_active:
            raise HTTPException(429, "An execution task is already active")
        if len(app.state.animations) >= 100:
            finished = [key for key, item in app.state.animations.items() if item["status"] != "RUNNING"]
            for key in finished[:50]:
                del app.state.animations[key]
        identifier = uuid4().hex
        state = {"id": identifier, "user_id": user_id, "status": "RUNNING", "phase": "DESIGNING", "attempts": 0, "artifact_generated": False}
        enter_phase(state, "DESIGNING", detail="正在理解这次学习创作需求：" + payload.prompt.strip()[:110])
        app.state.animations[identifier] = state
        app.state.animation_active = True

        async def work():
            usage = UsageMetadataCallbackHandler()
            try:
                async with asyncio.timeout(settings.animation_timeout_seconds):
                    store = ArtifactStore(settings.artifact_dir)
                    brief = ""
                    if settings.public_brief_enabled:
                        try:
                            brief = await asyncio.wait_for(stream_public_brief(settings, payload.prompt, state), timeout=16)
                        except Exception as exc:
                            state["public_brief_state"] = "UNAVAILABLE"
                            logger.info("Optional public learning brief unavailable: %s", type(exc).__name__)
                    effective_prompt = payload.prompt + (
                        "\n\n[已向用户呈现的初步教学需求理解，若不准确应以用户原话为准]\n" + brief
                        if brief else ""
                    )
                    graph = animation_factory(settings, user_id, state, store)
                    result = await graph.ainvoke(animation_state(effective_prompt, [m.model_dump() for m in payload.history]), config={"callbacks": [usage], "recursion_limit": 80, "metadata": {"nar_run_id": identifier, "owner_user_id": user_id}})
                    content = result["messages"][-1].content
                    state["output"] = content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
                    state["artifact_generated"] = bool(state.get("artifact_id"))
                    state["status"] = "SUCCEEDED" if state["artifact_generated"] else "FAILED"
                    if not state["artifact_generated"]:
                        state["error"] = "未获得通过检查的动画，请调整提示词后重试。"
            except ModelCallLimitExceededError:
                logger.warning("Animation model call limit reached id=%s phase=%s attempts=%s", identifier, state["phase"], state["attempts"])
                state.update(status="FAILED", error="动画设计达到模型调用次数上限，尚未完成产物。请缩小演示范围后重试。")
            except TimeoutError:
                state.update(status="FAILED", error="动画制作超时，请缩小演示范围后重试。")
            except asyncio.CancelledError:
                state.update(status="FAILED", error="服务停止，动画任务已中断。")
                raise
            except Exception as error:
                logger.warning("Animation failed id=%s phase=%s attempts=%s diagnostics=%s", identifier, state["phase"], state["attempts"], animation_failure_diagnostics(error))
                state.update(status="FAILED", error="动画制作失败，请检查执行服务或稍后重试。")
            finally:
                state.update(usage=usage.usage_metadata, usage_status="reported" if usage.usage_metadata else "unknown")
                close_phase(state, failed=state.get("status") != "SUCCEEDED")
                app.state.animation_active = False

        handle = asyncio.create_task(work())
        app.state.animation_handles.add(handle)
        handle.add_done_callback(app.state.animation_handles.discard)
        return {"id": identifier, "user_id": user_id, "status": "RUNNING"}

    @app.get("/v1/animations/{identifier}")
    async def animation_status(identifier: str, user_id: str = Depends(principal)):
        state = app.state.animations.get(identifier)
        if not state or state["user_id"] != user_id:
            raise HTTPException(404, "Animation not found")
        return {**state, "elapsed_ms": public_elapsed_ms(state)}

    @app.get("/v1/animations/{identifier}/events")
    async def animation_events(identifier: str, user_id: str = Depends(principal)):
        state = app.state.animations.get(identifier)
        if not state or state["user_id"] != user_id:
            raise HTTPException(404, "Animation not found")
        return StreamingResponse(stream_progress(state), media_type="text/event-stream", headers={
            "Cache-Control": "private, no-cache, no-transform", "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        })

    @app.post("/v1/html", status_code=202)
    async def create_html(payload: HtmlInput, user_id: str = Depends(principal)):
        if not settings.ready or not settings.html_builder_enabled or len(settings.execution_token.get_secret_value()) < 32:
            raise HTTPException(503, "HTML builder is not configured")
        if app.state.animation_active or app.state.html_active:
            raise HTTPException(429, "An execution task is already active")
        store = ArtifactStore(settings.artifact_dir)
        if payload.parent_artifact_id:
            try:
                if store.metadata(user_id, payload.parent_artifact_id).get("kind") != "html":
                    raise FileNotFoundError
            except (FileNotFoundError, ValueError):
                raise HTTPException(404, "Previous HTML artifact not found") from None
        if len(app.state.html_runs) >= 100:
            finished = [key for key, value in app.state.html_runs.items() if value["status"] != "RUNNING"]
            for key in finished[:50]:
                del app.state.html_runs[key]
        identifier = uuid4().hex
        state = {
            "id": identifier, "user_id": user_id, "status": "RUNNING",
            "phase": "DESIGNING", "attempts": 0, "artifact_generated": False,
            "parent_artifact_id": payload.parent_artifact_id,
        }
        enter_phase(state, "DESIGNING", detail="正在理解这次学习创作需求：" + payload.prompt.strip()[:110])
        app.state.html_runs[identifier] = state
        app.state.html_active = True

        async def work():
            usage = UsageMetadataCallbackHandler()
            config = {
                "callbacks": [usage], "recursion_limit": 80,
                "metadata": {"nar_run_id": identifier, "owner_user_id": user_id},
            }
            try:
                async with asyncio.timeout(settings.animation_timeout_seconds):
                    brief = ""
                    if settings.public_brief_enabled:
                        try:
                            brief = await asyncio.wait_for(stream_public_brief(settings, payload.prompt, state), timeout=16)
                        except Exception as exc:
                            state["public_brief_state"] = "UNAVAILABLE"
                            logger.info("Optional public learning brief unavailable: %s", type(exc).__name__)
                    effective_prompt = payload.prompt + (
                        "\n\n[已向用户呈现的初步教学需求理解，若不准确应以用户原话为准]\n" + brief
                        if brief else ""
                    )
                    graph = html_factory(settings, user_id, state, store, payload.parent_artifact_id)
                    result = await graph.ainvoke(
                        html_initial_state(effective_prompt, [m.model_dump() for m in payload.history]),
                        config=config,
                    )
                    state["model_trace"] = summarize_html_run(result.get("messages", []))
                    # If the model merely promised to generate an HTML file,
                    # resume the same conversation once with an explicit tool instruction.
                    # Never report browser validation failure when no build was submitted.
                    if not state.get("artifact_id") and state["attempts"] == 0:
                        state["recovery_attempts"] = 1
                        logger.warning(
                            "HTML builder ended without build id=%s model_messages=%s tool_calls=%s invalid_tool_calls=%s tool_names=%s finish_reason=%s; retrying once",
                            identifier,
                            state["model_trace"]["model_messages"],
                            state["model_trace"]["tool_calls"],
                            state["model_trace"]["invalid_tool_calls"],
                            state["model_trace"]["tool_names"],
                            state["model_trace"]["finish_reason"],
                        )
                        prior_messages = list(result.get("messages", []))
                        retry_state = {
                            **result,
                            "messages": [*prior_messages, HumanMessage(content=NO_BUILD_RECOVERY_INSTRUCTION)],
                        }
                        result = await graph.ainvoke(retry_state, config=config)
                        state["model_trace"] = summarize_html_run(result.get("messages", []))

                    messages = result.get("messages", [])
                    content = messages[-1].content if messages else ""
                    if isinstance(content, str):
                        state["output"] = content
                    elif isinstance(content, list):
                        state["output"] = "\n".join(
                            block.get("text", "") for block in content if isinstance(block, dict)
                        )
                    else:
                        state["output"] = ""
                    state["artifact_generated"] = bool(state.get("artifact_id"))
                    state["status"] = "SUCCEEDED" if state["artifact_generated"] else "FAILED"
                    if not state["artifact_generated"]:
                        if state["attempts"] == 0:
                            if state["model_trace"]["finish_reason"] == "length":
                                state["error_code"] = "MODEL_OUTPUT_TRUNCATED"
                                state["error"] = "模型输出达到长度上限，未形成可执行的 HTML。请检查分段生成及模型输出额度。"
                            elif state["model_trace"]["invalid_tool_calls"]:
                                state["error_code"] = "INVALID_TOOL_CALL"
                                state["error"] = "模型生成了无法解析的工具调用，未能提交 HTML。"
                            else:
                                state["error_code"] = "NO_BUILD_ATTEMPT"
                                state["error"] = "模型未提交 HTML 构建；系统已自动要求执行一次，仍未完成。"
                        elif state.get("execution_error"):
                            state["error_code"] = "EXECUTION_UNAVAILABLE"
                            state["error"] = "已尝试提交 HTML，但构建执行或作品保存失败，请检查执行服务。"
                        else:
                            state["error_code"] = "BUILD_VALIDATION_FAILED"
                            state["error"] = "HTML 已提交构建，但未通过浏览器检查，请查看检查报告后重试。"
            except ModelCallLimitExceededError:
                state.update(status="FAILED", error_code="MODEL_CALL_LIMIT",
                             error="已达到模型调用预算，尚未完成产物。")
            except TimeoutError:
                state.update(status="FAILED", error_code="TIMEOUT",
                             error="HTML 制作超时，请缩小交互范围后重试。")
            except asyncio.CancelledError:
                state.update(status="FAILED", error_code="CANCELLED",
                             error="服务停止，HTML 任务已中断。")
                raise
            except Exception as error:
                logger.warning(
                    "HTML builder failed id=%s phase=%s diagnostics=%s",
                    identifier, state["phase"], animation_failure_diagnostics(error),
                )
                state.update(status="FAILED", error_code="AGENT_ERROR",
                             error="HTML 制作失败，请检查执行服务或稍后重试。")
            finally:
                state.update(
                    usage=usage.usage_metadata,
                    usage_status="reported" if usage.usage_metadata else "unknown",
                )
                close_phase(state, failed=state.get("status") != "SUCCEEDED")
                app.state.html_active = False

        handle = asyncio.create_task(work())
        app.state.html_handles.add(handle)
        handle.add_done_callback(app.state.html_handles.discard)
        return {"id": identifier, "user_id": user_id, "status": "RUNNING"}

    @app.get("/v1/html/{identifier}")
    async def html_status(identifier: str, user_id: str = Depends(principal)):
        state = app.state.html_runs.get(identifier)
        if not state or state["user_id"] != user_id:
            raise HTTPException(404, "HTML task not found")
        return {**state, "elapsed_ms": public_elapsed_ms(state)}

    @app.get("/v1/html/{identifier}/events")
    async def html_events(identifier: str, user_id: str = Depends(principal)):
        state = app.state.html_runs.get(identifier)
        if not state or state["user_id"] != user_id:
            raise HTTPException(404, "HTML task not found")
        return StreamingResponse(stream_progress(state), media_type="text/event-stream", headers={
            "Cache-Control": "private, no-cache, no-transform", "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        })

    @app.get("/v1/artifacts/{identifier}/metadata")
    async def artifact_metadata(identifier: str, user_id: str = Depends(principal)):
        try:
            meta = ArtifactStore(settings.artifact_dir).metadata(user_id, identifier)
        except (FileNotFoundError, ValueError, KeyError):
            raise HTTPException(404, "Artifact not found") from None
        return {
            "kind": meta["kind"], "parent_artifact_id": meta.get("parent_id"),
            "created_at": meta["created_at"],
            "passed": bool((meta.get("report") or {}).get("passed")),
        }

    @app.get("/v1/artifacts/{identifier}/{filename}")
    async def artifact(identifier: str, filename: str, user_id: str = Depends(principal)):
        try:
            content = ArtifactStore(settings.artifact_dir).read(user_id, identifier, filename)
        except (FileNotFoundError, ValueError, KeyError):
            raise HTTPException(404, "Artifact not found") from None
        return Response(content, media_type="text/html" if filename == "index.html" else "image/png", headers={
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'",
        })

    @app.post("/v1/runs")
    async def run(payload: RunInput, user_id: str = Depends(principal)):
        if not settings.ready:
            raise HTTPException(503, "Model API key is not configured")
        if app.state.active_runs >= settings.max_concurrent_runs:
            raise HTTPException(429, "Run capacity reached", headers={"Retry-After": "5"})
        # No await between admission check and increment; one event loop per worker.
        app.state.active_runs += 1
        run_id = uuid4().hex
        started = monotonic()
        usage = UsageMetadataCallbackHandler()
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                agent = agent_factory(settings)
                result = await agent.ainvoke(
                    initial_state(payload.prompt, [m.model_dump() for m in payload.history]),
                    config={
                        "callbacks": [usage],
                        "recursion_limit": settings.recursion_limit,
                        "metadata": {"nar_run_id": run_id, "owner_user_id": user_id},
                    },
                )
            message = result["messages"][-1]
            content = message.content
            output = content if isinstance(content, str) else "\n".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
            return {
                "id": run_id, "user_id": user_id, "status": "SUCCEEDED",
                "output": output, "duration_ms": round((monotonic() - started) * 1000),
                "usage": usage.usage_metadata,
                "usage_status": "reported" if usage.usage_metadata else "unknown",
                "persisted": False, "artifact_generated": False,
            }
        except TimeoutError:
            raise HTTPException(504, detail={"id": run_id, "status": "FAILED", "code": "TIMEOUT"}) from None
        except Exception:
            # Do not expose prompts, upstream response bodies or credentials.
            logger.warning("Agent run failed id=%s", run_id)
            raise HTTPException(502, detail={"id": run_id, "status": "FAILED", "code": "AGENT_ERROR"}) from None
        finally:
            app.state.active_runs -= 1

    return app


app = create_app()
