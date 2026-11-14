"""Live progress SSE: real stage transitions, no internal reasoning or secret data."""
import asyncio
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.progress_events import close_phase, enter_phase
from app.progress_stream import progress_payload, stream_progress
from app.config import Settings

TOKEN = "sse-tests-" + "x" * 40
HEADERS = {"Authorization": "Bearer " + TOKEN, "X-User-ID": "teacher-a"}
RUN_ID = "a" * 32


def test_public_payload_never_exposes_model_trace_or_unverified_html():
    state = {
        "id": RUN_ID, "status": "RUNNING", "user_id": "teacher-a",
        "phase": "DESIGNING", "attempts": 0, "output": "internal scratchpad",
        "artifact_id": "f" * 32, "model_trace": {"raw": "secret"},
        "tool_arguments": {"private": "secret"},
    }
    payload = progress_payload(state)
    assert payload["status"] == "RUNNING" and payload["id"] == RUN_ID
    for key in ("user_id", "model_trace", "tool_arguments", "output", "artifact_id"):
        assert key not in payload


def test_sse_emits_content_plan_updates_and_terminates_with_result():
    state = {"id": RUN_ID, "status": "RUNNING", "user_id": "teacher-a"}
    enter_phase(state, "DESIGNING", "理解本次三角函数学习需求")

    async def collect():
        stream = stream_progress(state, interval=0.001, heartbeat_seconds=1.0)
        assert await anext(stream) == "retry: 1500\n\n"
        first = await anext(stream)
        assert "event: progress\n" in first and "理解本次三角函数学习需求" in first
        state["learning_plan"] = {
            "learning_goal": "观察正弦函数图像变化",
            "interaction_method": "拖动相位滑块",
            "key_concepts": ["周期", "振幅"],
        }
        enter_phase(state, "PLANNING", "用滑块对照曲线")
        second = await anext(stream)
        assert "event: progress\n" in second
        assert "观察正弦函数图像变化" in second
        assert "拖动相位滑块" in second
        enter_phase(state, "CHECKING")
        state["status"] = "SUCCEEDED"
        state["artifact_id"] = "b" * 32
        state["output"] = "已生成互动图像。"
        close_phase(state)
        final = await anext(stream)
        assert "event: complete\n" in final
        assert "已生成互动图像。" in final
        assert "\\" not in final.split("event: complete\n")[0]
        try:
            await anext(stream)
            assert False, "SSE should stop after the terminal event"
        except StopAsyncIteration:
            pass
        return first, second, final

    first, second, final = asyncio.run(collect())
    assert "chain_of_thought" not in first + second + final


def test_owner_checked_sse_route_returns_private_cache_control(tmp_path):
    settings = Settings(_env_file=None, service_token=TOKEN, api_key="test-key",
                        execution_token=TOKEN, html_builder_enabled=True,
                        artifact_dir=str(tmp_path))
    app = create_app(settings)
    state = {"id": RUN_ID, "status": "SUCCEEDED", "user_id": "teacher-a",
             "artifact_id": "b" * 32, "output": "互动课堂已完成", "timeline": []}
    app.state.html_runs[RUN_ID] = state
    app.state.animations[RUN_ID] = state
    with TestClient(app) as client:
        for kind in ("html", "animations"):
            route = f"/v1/{kind}/{RUN_ID}/events"
            response = client.get(route, headers=HEADERS)
            assert response.status_code == 200
            assert "event: complete\n" in response.text
            assert "text/event-stream" in response.headers["content-type"]
            assert response.headers["x-accel-buffering"] == "no"
            other = {**HEADERS, "X-User-ID": "teacher-b"}
            assert client.get(route, headers=other).status_code == 404
            assert client.get(route).status_code in (401, 422)
