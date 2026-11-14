"""Durable saved-works contract without MySQL or a real model provider."""
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend.work_store import WorkConflictError, WorkStore
from webgal_backend.works_routes import create_router

TOKEN = "works-token-" + "x" * 40
ARTIFACT_A = "a" * 32
ARTIFACT_B = "b" * 32
ASSETS = {
    "index.html": b"<!doctype html><html><body><button>next</button></body></html>",
    "preview.png": b"preview-image-bytes",
    "mobile.png": b"mobile-image-bytes",
}
ACTION = {"X-NarAgent-Action": "chat"}


def test_saved_works_owner_scope_dedup_versions(tmp_path):
    store = WorkStore(tmp_path)
    first = store.create("teacher-a", ARTIFACT_A, "html", "函数练习", "摘要", ASSETS)
    assert store.create("teacher-a", ARTIFACT_A, "html", "重复", "", ASSETS)["id"] == first["id"]
    assert len(store.list_for("teacher-a")) == 1
    assert store.list_for("teacher-b") == []
    with pytest.raises(FileNotFoundError):
        store.get("teacher-b", first["id"])
    with pytest.raises(FileNotFoundError):
        store.asset("teacher-b", first["id"], first["current_version_id"], "index.html")
    assert store.asset("teacher-a", first["id"], first["current_version_id"], "index.html") == ASSETS["index.html"]
    updated = store.add_version("teacher-a", first["id"], ARTIFACT_B, ASSETS, ARTIFACT_A)
    assert len(updated["versions"]) == 2
    assert updated["current_version_id"] != first["current_version_id"]
    assert store.asset("teacher-a", first["id"], first["current_version_id"], "index.html") == ASSETS["index.html"]
    with pytest.raises(WorkConflictError):
        store.add_version("teacher-a", first["id"], "c" * 32, ASSETS, ARTIFACT_A)
    with pytest.raises(FileNotFoundError):
        store.get("teacher-a", "../outside")
    assert store.update("teacher-a", first["id"], title="新标题")["title"] == "新标题"


def test_works_api_imports_verified_owner_artifact_and_keeps_it_private(tmp_path, monkeypatch):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("NAR_AGENT_URL", "http://nar-agent:8020")
    calls = []
    def upstream(request: httpx.Request):
        calls.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        assert request.headers["X-User-ID"] == "teacher-a"
        if request.url.path.endswith("/metadata"):
            return httpx.Response(200, json={
                "kind": "html", "passed": True, "parent_artifact_id": None,
            })
        for name, content in ASSETS.items():
            if request.url.path.endswith("/" + name):
                return httpx.Response(200, content=content)
        return httpx.Response(404)
    store = WorkStore(tmp_path)
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda request: {"id": "teacher-a", "auth_type": "sso"},
        store=store, transport=httpx.MockTransport(upstream),
    ))
    with TestClient(app) as client:
        assert client.post("/works", json={
            "artifact_id": ARTIFACT_A, "kind": "html", "title": "函数练习",
        }).status_code == 403
        created = client.post("/works", json={
            "artifact_id": ARTIFACT_A, "kind": "html", "title": "函数练习",
        }, headers=ACTION)
        assert created.status_code == 201, created.text
        work = created.json()["work"]
        imported_call_count = len(calls)
        repeated = client.post("/works", json={
            "artifact_id": ARTIFACT_A, "kind": "html", "title": "函数练习",
        }, headers=ACTION)
        assert repeated.json()["work"]["id"] == work["id"]
        assert len(calls) == imported_call_count  # dedup uses durable owned work, not remote cache
        work_id, version_id = work["id"], work["current_version_id"]
        assert len(client.get("/works").json()["works"]) == 1
        response = client.get(f"/works/{work_id}/assets/{version_id}/index.html")
        assert response.status_code == 200 and response.content == ASSETS["index.html"]
        assert "sandbox" in response.headers["content-security-policy"]
        response = client.patch(f"/works/{work_id}", headers=ACTION, json={
            "title": "幂函数与指数函数",
            "tags": ["数学", "图像"],
        })
        assert response.status_code == 200
        assert response.json()["work"]["tags"] == ["数学", "图像"]
        assert client.get("/works/" + work_id).json()["work"]["title"] == "幂函数与指数函数"
        assert client.get("/works/" + work_id + "/assets/" + "f" * 32 + "/preview.png").status_code == 404

    other = FastAPI()
    other.include_router(create_router(
        user_for_request=lambda request: {"id": "teacher-b", "auth_type": "sso"},
        store=store, transport=httpx.MockTransport(upstream),
    ))
    with TestClient(other) as c:
        assert c.get("/works").json()["works"] == []
        assert c.get("/works/" + work_id).status_code == 404
        assert c.get(f"/works/{work_id}/assets/{version_id}/preview.png").status_code == 404


def test_api_rejects_unverified_html_and_owner_mismatch(tmp_path, monkeypatch):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", TOKEN)
    def handler(request):
        return httpx.Response(200, json={"kind": "animation", "passed": True, "parent_artifact_id": None})
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda request: {"id": "teacher-a", "auth_type": "sso"},
        store=WorkStore(tmp_path), transport=httpx.MockTransport(handler),
    ))
    with TestClient(app) as c:
        result = c.post("/works", headers=ACTION, json={"artifact_id": ARTIFACT_A, "kind": "html", "title": "测试"})
        assert result.status_code == 422
