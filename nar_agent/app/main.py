import asyncio
import logging
import secrets
from time import monotonic
from uuid import uuid4
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from langchain_core.callbacks import UsageMetadataCallbackHandler
from pydantic import BaseModel, Field, model_validator

from agents.teaching import build_agent, initial_state
from app.config import Settings
from app.artifacts import ArtifactStore
from agents.animation import animation_state, build_animation_agent

logger = logging.getLogger(__name__)


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


def create_app(settings: Settings | None = None, *, agent_factory=build_agent, animation_factory=build_animation_agent) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="NarAgent", version="0.1.0")
    app.state.active_runs = 0
    app.state.animations = {}
    app.state.animation_handles = set()
    app.state.animation_active = False

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
        if settings.animation_enabled and len(settings.execution_token.get_secret_value()) < 32:
            raise HTTPException(503, "Configure execution token")
        return {"status": "configured", "provider_connectivity": "not_checked"}

    @app.post("/v1/animations", status_code=202)
    async def create_animation(payload: RunInput, user_id: str = Depends(principal)):
        if not settings.ready or not settings.animation_enabled or len(settings.execution_token.get_secret_value()) < 32:
            raise HTTPException(503, "Animation execution is not configured")
        if app.state.animation_active:
            raise HTTPException(429, "One animation can run at a time")
        if len(app.state.animations) >= 100:
            finished = [key for key, item in app.state.animations.items() if item["status"] != "RUNNING"]
            for key in finished[:50]:
                del app.state.animations[key]
        identifier = uuid4().hex
        state = {"id": identifier, "user_id": user_id, "status": "RUNNING", "phase": "DESIGNING", "attempts": 0, "artifact_generated": False}
        app.state.animations[identifier] = state
        app.state.animation_active = True

        async def work():
            usage = UsageMetadataCallbackHandler()
            try:
                async with asyncio.timeout(settings.animation_timeout_seconds):
                    store = ArtifactStore(settings.artifact_dir)
                    graph = animation_factory(settings, user_id, state, store)
                    result = await graph.ainvoke(animation_state(payload.prompt, [m.model_dump() for m in payload.history]), config={"callbacks": [usage], "recursion_limit": 80, "metadata": {"nar_run_id": identifier, "owner_user_id": user_id}})
                    content = result["messages"][-1].content
                    state["output"] = content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
                    state["artifact_generated"] = bool(state.get("artifact_id"))
                    state["status"] = "SUCCEEDED" if state["artifact_generated"] else "FAILED"
                    if not state["artifact_generated"]:
                        state["error"] = "未获得通过检查的动画，请调整提示词后重试。"
            except TimeoutError:
                state.update(status="FAILED", error="动画制作超时，请缩小演示范围后重试。")
            except asyncio.CancelledError:
                state.update(status="FAILED", error="服务停止，动画任务已中断。")
                raise
            except Exception:
                logger.warning("Animation failed id=%s", identifier)
                state.update(status="FAILED", error="动画制作失败，请检查执行服务或稍后重试。")
            finally:
                state.update(usage=usage.usage_metadata, usage_status="reported" if usage.usage_metadata else "unknown")
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
        return state

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
