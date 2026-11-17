"""Tests for HTML templates, authorized revisions, agent tools and async API.

The real Docker/Chromium test is opt-in via NAR_TEST_DOCKER and runs in CI.
"""
import asyncio
import base64
import json
import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agents.html_builder import build_html_agent, html_initial_state
from app.artifacts import ArtifactStore
from app.config import Settings
from app.main import create_app
from app.template_catalog import TemplateCatalog, TemplateError
from sandbox import broker

TOKEN = "html-test-" + "x" * 40
HEADERS = {"Authorization": "Bearer " + TOKEN, "X-User-ID": "teacher-a"}


def settings(**kwargs):
    return Settings(_env_file=None, service_token=TOKEN, api_key="test-key", execution_token=TOKEN,
                    html_builder_enabled=True, **kwargs)


def payload(source: bytes = b"<!doctype html><html><body><button>next</button></body></html>"):
    return {
        "report": {"passed": True, "kind": "html", "checks": {"controls": 1}},
        "index.html": base64.b64encode(source).decode(),
        "preview.png": base64.b64encode(b"png").decode(),
        "mobile.png": base64.b64encode(b"png").decode(),
    }


def test_catalog_renders_escaped_standalone_html():
    catalog = TemplateCatalog()
    found = catalog.search("背诵")
    assert any(t["id"] == "recitation-cards" for t in found)
    html = catalog.render("recitation-cards", {
        "title": "<危险&标题>",
        "cards": [{"question": "</script><script>alert(1)</script>", "answer": "正确答案"}],
    })
    assert "<title>&lt;危险&amp;标题&gt;</title>" in html
    assert "</script><script>alert(1)</script>" not in html
    assert "\\u003c/script\\u003e" in html
    assert "<button" in html and "application/json" in html
    for template_id in ("../etc/passwd", "missing-template"):
        with pytest.raises(TemplateError):
            catalog.render(template_id, {"title": "x", "cards": []})
    with pytest.raises(TemplateError):
        catalog.render("recitation-cards", {"title": "x", "cards": [{"question": "q"}]})


def test_artifact_revision_chain_enforces_owner(tmp_path):
    store = ArtifactStore(str(tmp_path))
    first = store.save("teacher-a", payload(), "html-v1", kind="html")
    second = store.save("teacher-a", payload(), "html-v2", kind="html", parent_id=first)
    assert store.metadata("teacher-a", second)["parent_id"] == first
    assert store.metadata("teacher-a", second)["kind"] == "html"
    assert store.read("teacher-a", first, "index.html") == store.read("teacher-a", second, "index.html")
    with pytest.raises(FileNotFoundError):
        store.metadata("teacher-b", first)
    with pytest.raises(FileNotFoundError):
        store.save("teacher-b", payload(), "x", kind="html", parent_id=first)


def test_agent_tool_executes_template_in_isolated_broker(monkeypatch, tmp_path):
    import agents.html_builder as module

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    config_json = json.dumps({"title": "复习", "cards": [{"question": "人为什么学习？", "answer": "理解世界"}]}, ensure_ascii=False)
    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[
            {"name": "search_html_templates", "args": {"query": "复习"}, "id": "search"}
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "render_html_template", "args": {"template_id": "recitation-cards", "config_json": config_json}, "id": "render"}
        ]),
        AIMessage(content="已生成可操作抽背练习。"),
    ]))
    original = httpx.AsyncClient
    observed = {}

    def handler(request):
        body = json.loads(request.content)
        observed.update(body)
        assert body["kind"] == "html"
        assert "<!doctype html>" in body["source"].lower()
        assert "人为什么学习？" in body["source"]
        return httpx.Response(200, json=payload(body["source"].encode()))

    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    progress = {}
    store = ArtifactStore(str(tmp_path))
    graph = build_html_agent(settings(), "teacher-a", progress, store, model=model)
    result = asyncio.run(graph.ainvoke(html_initial_state("制作背诵抽卡", []), config={"recursion_limit": 80}))
    assert result["messages"][-1].content == "已生成可操作抽背练习。"
    assert progress["attempts"] == 1 and progress["artifact_id"]
    assert store.metadata("teacher-a", progress["artifact_id"])["kind"] == "html"
    assert "人为什么学习？" in store.read("teacher-a", progress["artifact_id"], "index.html").decode()
    assert observed["kind"] == "html"


def test_html_api_is_owner_scoped_and_background_task_finishes(tmp_path):
    config = settings(artifact_dir=str(tmp_path))

    class Graph:
        def __init__(self, state, store, owner, parent):
            self.state, self.store, self.owner, self.parent = state, store, owner, parent

        async def ainvoke(self, *args, **kwargs):
            self.state["artifact_id"] = self.store.save(
                self.owner, payload(), "test html", kind="html", parent_id=self.parent)
            return {"messages": [AIMessage(content="作品已经生成")]}

    app = create_app(
        config,
        html_factory=lambda cfg, owner, state, store, parent: Graph(state, store, owner, parent),
    )
    with TestClient(app) as client:
        response = client.post("/v1/html", headers=HEADERS, json={"prompt": "制作网页"})
        assert response.status_code == 202, response.text
        run = response.json()["id"]
        for _ in range(100):
            job = client.get("/v1/html/" + run, headers=HEADERS).json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.01)
        assert job["status"] == "SUCCEEDED" and job["artifact_generated"]
        first = job["artifact_id"]
        response = client.post("/v1/html", headers=HEADERS, json={
            "prompt": "修改", "parent_artifact_id": first,
        })
        assert response.status_code == 202
        for _ in range(100):
            job = client.get("/v1/html/" + response.json()["id"], headers=HEADERS).json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.01)
        assert job["status"] == "SUCCEEDED"
        assert ArtifactStore(str(tmp_path)).metadata("teacher-a", job["artifact_id"])["parent_id"] == first

        other = {**HEADERS, "X-User-ID": "teacher-b"}
        assert client.get("/v1/html/" + run, headers=other).status_code == 404
        assert client.post("/v1/html", headers=other, json={
            "prompt": "盗用", "parent_artifact_id": first,
        }).status_code == 404
        assert client.post("/v1/html", headers=HEADERS, json={
            "prompt": "bad", "parent_artifact_id": "../escape",
        }).status_code == 422
        assert client.get("/v1/artifacts/" + first + "/index.html", headers=other).status_code == 404



def test_failed_html_draft_can_be_patched_without_parent(monkeypatch, tmp_path):
    """A broken first draft remains editable, even for a brand-new artifact."""
    import agents.html_builder as module

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    initial = "<!doctype html><html><body><button>旧版</button></body></html>"
    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[
            {"name": "submit_custom_html", "args": {"html_source": initial}, "id": "build-broken"}
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "read_working_html", "args": {}, "id": "read-draft"}
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "replace_working_html", "args": {"old": "旧版", "new": "新版"}, "id": "repair"}
        ]),
        AIMessage(content="已经修复并验证。"),
    ]))
    original = httpx.AsyncClient
    attempts = []

    def handler(request):
        body = json.loads(request.content)
        attempts.append(body["source"])
        if len(attempts) == 1:
            return httpx.Response(200, json={"report": {
                "passed": False, "stage": "browser-check", "checks": {"errors": ["test failure"]},
            }})
        return httpx.Response(200, json=payload(body["source"].encode()))

    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    store = ArtifactStore(str(tmp_path))
    progress = {}
    graph = build_html_agent(settings(), "teacher-a", progress, store, model=model)
    result = asyncio.run(graph.ainvoke(html_initial_state("制作可交互网页", []), config={"recursion_limit": 80}))
    assert len(attempts) == 2 and "旧版" in attempts[0] and "新版" in attempts[1]
    assert progress["attempts"] == 2 and progress["strategy"] == "patch"
    assert "新版" in store.read("teacher-a", progress["artifact_id"], "index.html").decode()
    assert result["messages"][-1].content == "已经修复并验证。"

def test_zero_build_result_is_retried_once_and_saved(tmp_path):
    """An AI saying 'I will build it' must not terminate an actual build task."""
    from app.html_diagnostics import NO_BUILD_RECOVERY_INSTRUCTION
    from langchain_core.messages import HumanMessage

    config = settings(artifact_dir=str(tmp_path))
    calls = []

    class Graph:
        async def ainvoke(self, input_state, **kwargs):
            calls.append(input_state)
            if len(calls) == 1:
                return {"messages": [AIMessage(content="模板库没有匹配，所以我将编写一个自定义 HTML 作品。")]}
            assert any(
                isinstance(message, HumanMessage) and message.content == NO_BUILD_RECOVERY_INSTRUCTION
                for message in input_state["messages"]
            )
            app_store = ArtifactStore(str(tmp_path))
            progress["state"]["artifact_id"] = app_store.save(
                "teacher-a", payload(), "<!doctype html><html></html>", kind="html"
            )
            progress["state"]["phase"] = "FINALIZING"
            return {"messages": [*input_state["messages"], AIMessage(content="已生成并保存互动 HTML。")]}

    progress = {}
    app = create_app(
        config, html_factory=lambda cfg, owner, state, store, parent: (
            progress.update({"state": state}) or Graph()
        ),
    )
    with TestClient(app) as client:
        run = client.post("/v1/html", headers=HEADERS, json={"prompt": "生成学习网页"}).json()["id"]
        for _ in range(100):
            job = client.get("/v1/html/" + run, headers=HEADERS).json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.01)
        assert job["status"] == "SUCCEEDED", job
        assert len(calls) == 2
        assert job["recovery_attempts"] == 1
        assert job["artifact_generated"]
        assert job["output"] == "已生成并保存互动 HTML。"


def test_zero_build_twice_is_reported_as_no_build_not_browser_failure(tmp_path):
    config = settings(artifact_dir=str(tmp_path))
    calls = []

    class Graph:
        async def ainvoke(self, input_state, **kwargs):
            calls.append(input_state)
            return {"messages": [
                *input_state.get("messages", []),
                AIMessage(content="模板库里没有合适模板，我会为你编写网页。"),
            ]}

    app = create_app(config, html_factory=lambda *args: Graph())
    with TestClient(app) as client:
        run = client.post("/v1/html", headers=HEADERS, json={"prompt": "生成互动网页"}).json()["id"]
        for _ in range(100):
            job = client.get("/v1/html/" + run, headers=HEADERS).json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.01)
        assert job["status"] == "FAILED", job
        assert job["phase"] == "DESIGNING"
        assert job["attempts"] == 0
        assert job["error_code"] == "NO_BUILD_ATTEMPT"
        assert job["recovery_attempts"] == 1
        assert "浏览器检查" not in job["error"]
        assert len(calls) == 2
        assert job["model_trace"]["tool_calls"] == 0


def test_html_trace_excludes_prompt_text_and_tool_arguments():
    from app.html_diagnostics import summarize_html_run
    secret = "not-for-logging-private-knowledge-5678"
    trace = summarize_html_run([
        AIMessage(content=secret, tool_calls=[
            {"name": "search_html_templates", "args": {"query": secret}, "id": "s"}
        ], response_metadata={"finish_reason": "tool_calls"}),
        AIMessage(content="准备制作网页"),
    ])
    assert trace["model_messages"] == 2
    assert trace["tool_calls"] == 1
    assert trace["tool_names"] == ["search_html_templates"]
    assert secret not in json.dumps(trace, ensure_ascii=False)


def test_chunked_html_build_avoids_large_tool_arguments(monkeypatch, tmp_path):
    """A model can assemble small safe chunks before one browser build."""
    import agents.html_builder as module
    from langchain_core.messages import ToolMessage

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    first = "<!doctype html><html><body><h1>二次函数练习</h1>"
    middle = "<button id='next'>下一题</button><script>document.getElementById('next').onclick=()=>{};</script>"
    last = "</body></html>"
    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "search_html_templates", "args": {"query": "二次函数"}, "id": "search"}]),
        AIMessage(content="", tool_calls=[{"name": "write_html_chunk", "args": {"html_chunk": first, "mode": "start"}, "id": "start"}]),
        AIMessage(content="", tool_calls=[{"name": "write_html_chunk", "args": {"html_chunk": middle, "mode": "append"}, "id": "append"}]),
        AIMessage(content="", tool_calls=[{"name": "write_html_chunk", "args": {"html_chunk": last, "mode": "append"}, "id": "end"}]),
        AIMessage(content="", tool_calls=[{"name": "validate_working_html", "args": {}, "id": "validate"}]),
        AIMessage(content="已生成并通过 Chromium 检查。"),
    ]))
    requests = []
    original = httpx.AsyncClient

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["kind"] == "html"
        assert body["source"] == first + middle + last
        return httpx.Response(200, json=payload(body["source"].encode()))

    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    progress = {}
    graph = build_html_agent(settings(), "teacher-a", progress, ArtifactStore(str(tmp_path)), model=model)
    result = asyncio.run(graph.ainvoke(html_initial_state("做二次函数练习", []), config={"recursion_limit": 80}))
    assert len(requests) == 1
    assert progress["attempts"] == 1 and progress["strategy"] == "chunked"
    assert progress["draft_chunks"] == 3
    assert progress["draft_bytes"] == len((first + middle + last).encode("utf-8"))
    assert progress["artifact_id"]
    assert result["messages"][-1].content == "已生成并通过 Chromium 检查。"
    assert any(isinstance(m, ToolMessage) and 'draft_chunks' in str(m.content) for m in result["messages"])


def test_chunk_limits_and_lookup_budget(monkeypatch, tmp_path):
    """Oversize segments are refused before build and repeated searches are bounded."""
    from langchain_core.messages import ToolMessage

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "search_html_templates", "args": {}, "id": "s1"}]),
        AIMessage(content="", tool_calls=[{"name": "search_html_templates", "args": {}, "id": "s2"}]),
        AIMessage(content="", tool_calls=[{"name": "search_html_templates", "args": {}, "id": "s3"}]),
        AIMessage(content="", tool_calls=[{"name": "write_html_chunk", "args": {"html_chunk": "好" * 2500, "mode": "start"}, "id": "oversize"}]),
        AIMessage(content="未提交构建"),
    ]))
    progress = {}
    graph = build_html_agent(settings(), "teacher-a", progress, ArtifactStore(str(tmp_path)), model=model)
    result = asyncio.run(graph.ainvoke(html_initial_state("网页", []), config={"recursion_limit": 80}))
    assert "attempts" not in progress
    reports = [str(m.content) for m in result["messages"] if isinstance(m, ToolMessage)]
    assert any("Template lookup budget reached" in report for report in reports)
    assert any("6000 UTF-8 bytes" in report for report in reports)


def test_truncated_model_response_has_specific_error_code(tmp_path):
    """An actual length stop and invalid tool arguments are not called a browser failure."""
    config = settings(artifact_dir=str(tmp_path))

    class Graph:
        async def ainvoke(self, input_state, **kwargs):
            return {"messages": [
                *input_state.get("messages", []),
                AIMessage(content="", invalid_tool_calls=[{
                    "name": "submit_custom_html", "args": "{unfinished", "id": "bad",
                    "error": "invalid tool arguments",
                }], response_metadata={"finish_reason": "length"}),
            ]}

    app = create_app(config, html_factory=lambda *args: Graph())
    with TestClient(app) as client:
        run = client.post("/v1/html", headers=HEADERS, json={"prompt": "生成互动网页"}).json()["id"]
        for _ in range(100):
            job = client.get("/v1/html/" + run, headers=HEADERS).json()
            if job["status"] != "RUNNING":
                break
            time.sleep(0.01)
        assert job["status"] == "FAILED", job
        assert job["error_code"] == "MODEL_OUTPUT_TRUNCATED"
        assert job["model_trace"]["finish_reason"] == "length"
        assert job["model_trace"]["invalid_tool_calls"] >= 1
        assert job["attempts"] == 0


def test_progress_timeline_records_actual_phases_and_durations():
    from app.progress_events import enter_phase, close_phase, public_elapsed_ms

    state = {"status": "RUNNING"}
    enter_phase(state, "DESIGNING")
    enter_phase(state, "PLANNING", "拟采用两种函数对比图，理解函数的变化")
    enter_phase(state, "DRAFTING")
    enter_phase(state, "BUILDING")
    enter_phase(state, "CHECKING")
    enter_phase(state, "FINALIZING")
    state["status"] = "SUCCEEDED"
    close_phase(state)
    close_phase(state)
    assert [item["phase"] for item in state["timeline"]] == [
        "DESIGNING", "PLANNING", "DRAFTING", "BUILDING", "CHECKING", "FINALIZING",
    ]
    assert all(item["status"] == "completed" for item in state["timeline"])
    assert all(isinstance(item["duration_ms"], int) and item["duration_ms"] >= 0
               for item in state["timeline"])
    assert len(state["timeline"]) == 6
    assert state["timeline"][1]["detail"].startswith("拟采用")
    assert public_elapsed_ms(state) == state["elapsed_ms"]


def test_progress_failure_closes_last_actual_stage_only():
    from app.progress_events import enter_phase, close_phase
    state = {"status": "RUNNING"}
    enter_phase(state, "DESIGNING")
    enter_phase(state, "PLANNING")
    state["status"] = "FAILED"
    close_phase(state, failed=True)
    assert [event["status"] for event in state["timeline"]] == ["completed", "failed"]
    assert state["phase"] == "PLANNING"


def test_html_agent_learning_plan_is_explicit_not_hidden_reasoning(monkeypatch, tmp_path):
    import agents.html_builder as module

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    config = json.dumps({
        "title": "函数练习",
        "cards": [{"question": "x=1 时函数值是多少？", "answer": "1"}],
    }, ensure_ascii=False)
    model = Model(messages=iter([
        AIMessage(content="", tool_calls=[
            {"name": "search_html_templates", "args": {"query": "函数"}, "id": "search"}
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "record_learning_plan", "args": {
                "learning_goal": "理解函数的变化",
                "interaction_method": "参数滑块和曲线比较",
                "key_concepts": ["自变量", "幂函数", "指数函数"],
            }, "id": "plan"}
        ]),
        AIMessage(content="", tool_calls=[
            {"name": "render_html_template", "args": {
                "template_id": "recitation-cards", "config_json": config,
            }, "id": "build"}
        ]),
        AIMessage(content="已制作互动作品"),
    ]))
    original = httpx.AsyncClient
    def handler(request):
        source = json.loads(request.content)["source"]
        return httpx.Response(200, json=payload(source.encode()))
    monkeypatch.setattr(module.httpx, "AsyncClient",
                        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handler)))
    progress = {}
    graph = build_html_agent(settings(), "teacher-a", progress, ArtifactStore(str(tmp_path)), model=model)
    asyncio.run(graph.ainvoke(html_initial_state("做一个函数练习", []), config={"recursion_limit": 80}))
    assert progress["learning_plan"]["learning_goal"] == "理解函数的变化"
    assert [event["phase"] for event in progress["timeline"]] == [
        "PLANNING", "BUILDING", "CHECKING", "FINALIZING",
    ]
    assert "参数滑块和曲线比较" in progress["timeline"][0]["detail"]


@pytest.mark.skipif(os.getenv("NAR_TEST_DOCKER") != "1", reason="Requires real CI Docker + Chromium")
def test_real_docker_html_browser_smoke():
    source = TemplateCatalog().render("recitation-cards", {
        "title": "诗词抽背", "cards": [
            {"question": "明月几时有？", "answer": "把酒问青天"},
            {"question": "海内存知己", "answer": "天涯若比邻"},
        ],
    })
    output = broker.execute(source, "html")
    assert output["report"]["passed"], json.dumps(output["report"], ensure_ascii=False)
    assert output["report"]["kind"] == "html"
    assert output["report"]["checks"]["controls"] >= 3
    assert output["report"]["checks"]["template_interactions"]["passed"] is True
    assert b"<html" in base64.b64decode(output["index.html"])
