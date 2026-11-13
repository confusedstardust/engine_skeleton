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
