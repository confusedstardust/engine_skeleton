"""Conversation gateway contract: no DB needed; backend SQL migration is manual."""
import json
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend.nar_conversation_routes import create_router
from webgal_backend.nar_conversation_store import ConversationMissing


TODAY = datetime(2026, 11, 14, tzinfo=timezone.utc)
ID_A, ID_B, CID, TID = "a" * 32, "b" * 32, "c" * 32, "d" * 32


class MemoryLedger:
    def __init__(self):
        self.requests = {}
        self.messages = {}
        self.owners = {}
        self.ready_calls = 0

    def ready(self):
        self.ready_calls += 1
        return True

    def start_turn(self, owner, cid, req, prompt, mode, parent=None, create=False):
        if cid in self.owners and self.owners[cid] != owner:
            raise ConversationMissing("Wrong owner")
        if cid not in self.owners and not create:
            raise ConversationMissing("Missing")
        self.owners[cid] = owner
        key = cid, req
        if key in self.requests:
            return self.requests[key], False
        turn = {"id": TID, "conversationId": cid, "status": "QUEUED",
                "mode": mode, "runId": None, "errorCode": None,
                "createdAt": TODAY.isoformat()}
        self.requests[key] = turn
        self.messages.setdefault(cid, []).append({"role": "user", "content": prompt,
            "id": ID_A, "createdAt": TODAY.isoformat(), "seq": 1, "metadata": None})
        return turn, True

    def model_history(self, owner, cid, tid):
        assert self.owners[cid] == owner
        return []

    def mark_running(self, owner, cid, tid, run_id):
        assert self.owners[cid] == owner
        turn = next(t for (key_cid, _), t in self.requests.items() if key_cid == cid)
        turn.update(status="RUNNING", runId=run_id)
        return turn

    def finish_turn(self, owner, cid, tid, *, output, **kwargs):
        assert self.owners[cid] == owner
        turn = next(t for (key_cid, _), t in self.requests.items() if key_cid == cid)
        if turn["status"] != "SUCCEEDED":
            self.messages[cid].append({"role": "assistant", "content": output,
                "id": ID_B, "createdAt": TODAY.isoformat(), "seq": 2, "metadata": None})
        turn.update(status="SUCCEEDED")
        return turn

    def fail_turn(self, owner, cid, tid, code, uncertain=False, public_error=None, phase=None, public_metadata=None):
        turn = next(t for (key_cid, _), t in self.requests.items() if key_cid == cid)
        if turn["status"] not in ("FAILED", "SUCCEEDED") and public_error:
            self.messages[cid].append({"id": ID_B, "seq": len(self.messages[cid]) + 1,
                "role": "assistant", "content": public_error,
                "createdAt": TODAY.isoformat(),
                "metadata": {"errorCode": code, "phase": phase}})
        turn.update(status="UNKNOWN" if uncertain else "FAILED", errorCode=code)
        return turn

    def get_turn(self, owner, cid, tid):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        return next(t for (key_cid, _), t in self.requests.items() if key_cid == cid)

    def get_detail(self, owner, cid):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        turn = self.get_turn(owner, cid, TID)
        return {"conversation": {"id": cid, "title": "测试会话", "activeAt": TODAY.isoformat()},
                "messages": self.messages[cid], "nextBefore": None,
                "activeTurn": turn if turn["status"] in ("QUEUED", "RUNNING", "UNKNOWN") else None,
                "artifacts": []}

    def list_conversations(self, owner, limit, cursor):
        return {"items": [{"id": c, "title": "测试会话", "activeAt": TODAY.isoformat()}
                          for c, user in self.owners.items() if user == owner], "nextCursor": None}

    def get_messages(self, owner, cid, before, limit):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        return {"items": self.messages.get(cid, []), "nextBefore": None}

    def artifact_history(self, owner, limit, cursor):
        return {"items": [], "nextCursor": None}

    def link_work(self, owner, cid, aid, wid):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")

    def find_request(self, owner, cid, req):
        if self.owners.get(cid) != owner:
            return None
        turn = self.requests.get((cid, req))
        return {**turn, "prompt": self.messages[cid][0]["content"]} if turn else None

    def update_metadata(self, owner, cid, *, title=None, pinned=None):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        return {"id": cid, "title": title or "测试会话",
                "pinned": bool(pinned), "createdAt": TODAY.isoformat(),
                "activeAt": TODAY.isoformat()}

    def delete_conversation(self, owner, cid):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        del self.owners[cid]
        return {"deleted": True}


def make_client(monkeypatch, handler, store=None, user="teacher"):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", "testing-" + "s" * 40)
    app = FastAPI()
    app.include_router(create_router(user_for_request=lambda _: {"id": user, "auth_type": "sso"},
                                   store=store or MemoryLedger(),
                                   transport=httpx.MockTransport(handler)))
    return TestClient(app)


HEADERS = {"X-NarAgent-Action": "chat"}


def test_auto_route_runs_classifier_once_and_preserves_idempotent_mode(monkeypatch):
    ledger = MemoryLedger()
    calls = []
    def agent(req):
        calls.append(req.url.path)
        if req.url.path == "/v1/intent":
            assert json.loads(req.content)["has_editable_html"] is False
            return httpx.Response(200, json={"user_id": "teacher", "mode": "html"})
        assert req.url.path == "/v1/html"
        return httpx.Response(202, json={"id": TID, "user_id": "teacher", "status": "RUNNING"})
    client = make_client(monkeypatch, agent, ledger)
    body = {"conversation_id": CID, "client_request_id": ID_A,
            "mode": "auto", "prompt": "把赤壁赋做成互动网页"}
    first = client.post("/nar-agent/conversations", json=body, headers=HEADERS)
    assert first.status_code == 202
    assert first.json()["turn"]["mode"] == "html"
    second = client.post("/nar-agent/conversations", json=body, headers=HEADERS)
    assert second.status_code == 202 and second.json()["reused"] is True
    assert calls == ["/v1/intent", "/v1/html"]


def test_history_mutations_require_auth_and_owner(monkeypatch):
    ledger = MemoryLedger()
    ledger.owners[CID] = "teacher"
    ledger.messages[CID] = []
    allowed = make_client(monkeypatch, lambda req: httpx.Response(200), ledger)
    denied = make_client(monkeypatch, lambda req: httpx.Response(200), ledger, user="other")
    assert allowed.patch("/nar-agent/conversations/" + CID,
                         json={"title": "新标题", "pinned": True}, headers=HEADERS).status_code == 200
    assert denied.patch("/nar-agent/conversations/" + CID,
                        json={"title": "越权"}, headers=HEADERS).status_code == 404
    assert denied.delete("/nar-agent/conversations/" + CID, headers=HEADERS).status_code == 404
    assert allowed.delete("/nar-agent/conversations/" + CID, headers=HEADERS).json() == {"deleted": True}


def test_chat_creates_durable_message_and_duplicate_request_is_not_redispatched(monkeypatch):
    store = MemoryLedger()
    calls = []

    def agent(req):
        calls.append(req)
        assert req.headers["X-User-ID"] == "teacher"
        assert json.loads(req.content)["history"] == []
        return httpx.Response(200, json={
            "id": "run-1", "user_id": "teacher", "output": "电路学习方案",
        })

    client = make_client(monkeypatch, agent, store)
    request = {"conversation_id": CID, "client_request_id": ID_A,
               "mode": "chat", "prompt": "解释串联电路"}
    result = client.post("/nar-agent/conversations", json=request, headers=HEADERS)
    assert result.status_code == 202
    assert result.json()["turn"]["status"] == "SUCCEEDED"
    repeat = client.post("/nar-agent/conversations", json=request, headers=HEADERS)
    assert repeat.status_code == 202 and repeat.json()["reused"] is True
    assert len(calls) == 1
    detail = client.get("/nar-agent/conversations/" + CID)
    assert detail.status_code == 200
    assert [m["content"] for m in detail.json()["messages"]] == ["解释串联电路", "电路学习方案"]
    assert "user_id" not in str(detail.json())


def test_html_is_reconciled_asynchronously_without_dispatching_again(monkeypatch):
    store = MemoryLedger()
    calls = []
    def agent(req):
        calls.append(req.method)
        if req.method == "POST":
            return httpx.Response(202, json={"id": TID, "user_id": "teacher", "status": "RUNNING"})
        return httpx.Response(200, json={"id": TID, "user_id": "teacher",
                                          "status": "SUCCEEDED", "output": "作品完成",
                                          "artifact_id": ID_A})
    c = make_client(monkeypatch, agent, store)
    created = c.post("/nar-agent/conversations", headers=HEADERS, json={
        "conversation_id": CID, "client_request_id": ID_B,
        "prompt": "创建HTML", "mode": "html"
    })
    assert created.status_code == 202 and created.json()["turn"]["status"] == "RUNNING"
    polled = c.get(f"/nar-agent/conversations/{CID}/turns/{TID}")
    assert polled.status_code == 200 and polled.json()["turn"]["status"] == "SUCCEEDED"
    again = c.get(f"/nar-agent/conversations/{CID}/turns/{TID}")
    assert again.json()["turn"]["status"] == "SUCCEEDED"
    assert calls == ["POST", "GET"]


def test_cross_user_reads_are_denied_and_status_requires_auth(monkeypatch):
    store = MemoryLedger()
    store.owners[CID] = "teacher"
    store.messages[CID] = []
    first = make_client(monkeypatch, lambda req: httpx.Response(200), store, user="teacher")
    other = make_client(monkeypatch, lambda req: httpx.Response(200), store, user="attacker")
    assert first.get("/nar-agent/conversations").status_code == 200
    assert other.get("/nar-agent/conversations/" + CID).status_code == 404


def test_authenticated_status_reports_database_readiness_not_environment_flag(monkeypatch):
    store = MemoryLedger()
    c = make_client(monkeypatch, lambda req: httpx.Response(200), store)
    assert c.get("/nar-agent/conversations/status").json() == {"ready": True}
    assert c.get("/nar-agent/conversations").status_code == 200
    assert store.ready_calls == 1


def test_missing_migration_is_explicit_http_503_not_a_browser_fallback(monkeypatch):
    store = MemoryLedger()
    store.ready = lambda: False
    c = make_client(monkeypatch, lambda req: httpx.Response(200), store)
    result = c.get("/nar-agent/conversations/status")
    assert result.status_code == 503
    assert "002_nar_conversation_history.sql" in result.json()["detail"]


def test_anonymous_or_invite_login_cannot_read_chat_history(monkeypatch):
    app = FastAPI()
    app.include_router(create_router(user_for_request=lambda _: {"id": "invite", "auth_type": "invite"},
                                    store=MemoryLedger()))
    client = TestClient(app)
    assert client.get("/nar-agent/conversations/status").status_code == 401
    assert client.get("/nar-agent/conversations").status_code == 401
    assert client.get("/nar-agent/conversations/" + CID).status_code == 401


def test_failed_html_returns_specific_public_message_and_persists_it(monkeypatch):
    store = MemoryLedger()
    def agent(req):
        if req.method == "POST":
            return httpx.Response(202, json={"id": TID, "user_id": "teacher", "status": "RUNNING"})
        return httpx.Response(200, json={
            "id": TID, "user_id": "teacher", "status": "FAILED",
            "phase": "DESIGNING", "error_code": "MODEL_AUTH_FAILED",
            "error": "模型服务认证或权限验证失败，请检查模型服务凭据与权限。",
        })
    c = make_client(monkeypatch, agent, store)
    started = c.post("/nar-agent/conversations", headers=HEADERS, json={
        "conversation_id": CID, "client_request_id": ID_A,
        "prompt": "串并联电路", "mode": "html",
    })
    assert started.status_code == 202
    ended = c.get(f"/nar-agent/conversations/{CID}/turns/{TID}")
    assert ended.status_code == 200
    assert ended.json()["turn"]["errorCode"] == "MODEL_AUTH_FAILED"
    assert ended.json()["task"]["phase"] == "DESIGNING"
    again = c.get(f"/nar-agent/conversations/{CID}/turns/{TID}")
    assert again.json()["turn"]["status"] == "FAILED"
    detail = c.get("/nar-agent/conversations/" + CID).json()
    assert "模型服务认证" in detail["messages"][-1]["content"]
    assert detail["messages"][-1]["metadata"]["phase"] == "DESIGNING"



def test_real_chat_sse_chunks_are_persisted_and_not_redispatched(monkeypatch):
    ledger = MemoryLedger()
    calls = []
    def streaming_agent(request):
        calls.append(request.url.path)
        assert request.url.path == "/v1/runs/stream"
        content = (
            'event: delta\ndata: {"text":"这"}\n\n'
            'event: delta\ndata: {"text":"是答案"}\n\n'
            'event: done\ndata: {"id":"model-run","user_id":"teacher","output":"这是答案"}\n\n'
        )
        return httpx.Response(200, content=content,
                              headers={"content-type": "text/event-stream"})
    client = make_client(monkeypatch, streaming_agent, ledger)
    body = {"conversation_id": CID, "client_request_id": ID_A,
            "mode": "chat", "prompt": "解释串联电路"}
    response = client.post("/nar-agent/conversations/stream", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert "event: accepted" in response.text
    assert '"text": "这"' in response.text
    assert '"text": "是答案"' in response.text
    assert "event: result" in response.text
    detail = client.get("/nar-agent/conversations/" + CID).json()
    assert [m["content"] for m in detail["messages"]] == ["解释串联电路", "这是答案"]
    again = client.post("/nar-agent/conversations/stream", headers=HEADERS, json=body)
    assert again.status_code == 200
    assert again.json()["reused"] is True
    assert calls == ["/v1/runs/stream"]

