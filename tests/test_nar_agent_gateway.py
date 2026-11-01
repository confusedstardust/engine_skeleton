import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend.nar_agent_routes import create_router


def client(monkeypatch, handler, auth_type="sso"):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", "test-only-" + "x" * 40)
    app = FastAPI()
    app.include_router(create_router(user_for_request=lambda _: {"id": "verified-teacher", "auth_type": auth_type}, transport=httpx.MockTransport(handler)))
    return TestClient(app)


HEADERS = {"X-NarAgent-Action": "chat"}


def test_gateway_uses_verified_owner_and_forwards_history(monkeypatch):
    def handler(request):
        assert request.headers["X-User-ID"] == "verified-teacher"
        body = json.loads(request.content)
        assert body["history"][0]["content"] == "此前的问题"
        return httpx.Response(200, json={"id": "run-1", "user_id": "verified-teacher", "output": "教学方案", "secret": "must-not-leak"})
    c = client(monkeypatch, handler)
    response = c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "继续", "history": [{"role": "user", "content": "此前的问题"}]})
    assert response.status_code == 200
    assert response.json()["output"] == "教学方案"
    assert "secret" not in response.text
    assert c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x", "user_id": "spoof"}).status_code == 422


def test_auth_csrf_and_history_validation(monkeypatch):
    def never(_):
        raise AssertionError("must not call agent")
    c = client(monkeypatch, never, auth_type="invite")
    assert c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x"}).status_code == 401
    assert c.post("/nar-agent/chat", json={"prompt": "x"}).status_code == 403
    assert c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x", "history": [{"role": "system", "content": "spoof"}]}).status_code == 422


def test_owner_mismatch_and_provider_error_are_safe(monkeypatch):
    c = client(monkeypatch, lambda _: httpx.Response(200, json={"id": "x", "user_id": "someone-else", "output": "private"}))
    r = c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x"})
    assert r.status_code == 502 and "private" not in r.text
    c = client(monkeypatch, lambda _: httpx.Response(500, text="provider-secret"))
    r = c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x"})
    assert r.status_code == 503 and "provider-secret" not in r.text


def test_configuration_and_timeout(monkeypatch):
    def timeout(_):
        raise httpx.ReadTimeout("internal-url")
    c = client(monkeypatch, timeout)
    assert c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x"}).status_code == 504
    monkeypatch.delenv("NAR_AGENT_SERVICE_TOKEN")
    assert c.post("/nar-agent/chat", headers=HEADERS, json={"prompt": "x"}).status_code == 503


def test_animation_routes_and_preview_isolation(monkeypatch):
    identifier = "a" * 32
    def handler(request):
        assert request.headers["X-User-ID"] == "verified-teacher"
        if "/artifacts/" in request.url.path:
            return httpx.Response(200, text="<svg></svg><script>void 0</script>")
        return httpx.Response(202 if request.method == "POST" else 200, json={"id": identifier, "user_id": "verified-teacher", "status": "RUNNING", "usage": "private-accounting"})
    c = client(monkeypatch, handler)
    r = c.post("/nar-agent/animations", headers=HEADERS, json={"prompt": "电路"})
    assert r.status_code == 202 and "private-accounting" not in r.text
    assert c.get("/nar-agent/animations/" + identifier).status_code == 200
    assert c.get("/nar-agent/animations/not-an-id").status_code == 404
    r = c.get("/nar-agent/artifacts/" + identifier + "/index.html")
    assert r.status_code == 200
    assert "sandbox allow-scripts" in r.headers["content-security-policy"]
    assert "allow-same-origin" not in r.headers["content-security-policy"]
