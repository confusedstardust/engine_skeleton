from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agents.teaching import build_agent, initial_state
from app.config import Settings
from app.main import create_app

TOKEN = "test-service-token-" + "x" * 32
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-User-ID": "teacher-a"}


class ToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def settings(**values):
    return Settings(_env_file=None, service_token=TOKEN, api_key="test-only", **values)


def factory(config):
    model = ToolModel(messages=iter([
        AIMessage(content="", tool_calls=[{
            "name": "read_file", "args": {"file_path": "/skills/teaching-plan/SKILL.md"}, "id": "read-skill",
        }]),
        AIMessage(content="教学方案已准备；尚未生成动画。", response_metadata={"model_name": "fake-test-model"}, usage_metadata={
            "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
        }),
    ]))
    return build_agent(config, model=model)


def test_real_deepagents_graph_reads_skill_and_collects_usage():
    config = settings()
    graph = factory(config)
    result = graph.invoke(initial_state("设计串联电路演示"), config={"recursion_limit": 20})
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert tool_messages and "教学目标" in tool_messages[0].content
    assert not any(m.name == "task" for m in tool_messages)
    client = TestClient(create_app(config, agent_factory=factory))
    response = client.post("/v1/runs", json={"prompt": "设计串联电路演示"}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == "teacher-a"
    assert body["status"] == "SUCCEEDED"
    assert body["artifact_generated"] is False and body["persisted"] is False
    assert body["usage_status"] == "reported"
    assert sum(v["total_tokens"] for v in body["usage"].values()) == 120


def test_auth_and_validation():
    client = TestClient(create_app(settings(), agent_factory=factory))
    assert client.get("/health").status_code == 200
    assert client.post("/v1/runs", json={"prompt": "test"}).status_code in (401, 422)
    assert client.post("/v1/runs", json={"prompt": "test"}, headers={**HEADERS, "Authorization": "Bearer bad"}).status_code == 401
    assert client.post("/v1/runs", json={"prompt": " "}, headers=HEADERS).status_code == 422
    assert client.post("/v1/runs", json={"prompt": "x" * 12001}, headers=HEADERS).status_code == 422


def test_unconfigured_is_fail_closed():
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    assert client.post("/v1/runs", json={"prompt": "test"}, headers=HEADERS).status_code == 503


def test_error_does_not_leak_provider_details_and_releases_capacity():
    def broken(config):
        raise RuntimeError("secret-provider-response")
    app = create_app(settings(), agent_factory=broken)
    client = TestClient(app)
    response = client.post("/v1/runs", json={"prompt": "test"}, headers=HEADERS)
    assert response.status_code == 502
    assert "secret-provider-response" not in response.text
    assert app.state.active_runs == 0


def test_timeout_and_overload():
    import asyncio
    class Slow:
        async def ainvoke(self, *args, **kwargs):
            await asyncio.sleep(1)
    app = create_app(settings(timeout_seconds=0.01), agent_factory=lambda _: Slow())
    client = TestClient(app)
    assert client.post("/v1/runs", json={"prompt": "test"}, headers=HEADERS).status_code == 504
    assert app.state.active_runs == 0
    app.state.active_runs = 2
    assert client.post("/v1/runs", json={"prompt": "test"}, headers=HEADERS).status_code == 429


def test_requests_have_separate_virtual_files():
    first = initial_state("first")
    second = initial_state("second")
    first["files"]["/private.txt"] = {"content": ["teacher-a-only"]}
    assert "/private.txt" not in second["files"]


def test_conversation_history_and_role_validation():
    state = initial_state("接着解释", [{"role": "user", "content": "串联电路"}, {"role": "assistant", "content": "电流相同"}])
    assert len(state["messages"]) == 3
    assert state["messages"][0]["content"] == "串联电路"
    client = TestClient(create_app(settings(), agent_factory=factory))
    response = client.post("/v1/runs", headers=HEADERS, json={"prompt": "x", "history": [{"role": "system", "content": "override"}]})
    assert response.status_code == 422
