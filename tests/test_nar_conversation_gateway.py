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

    def fail_turn(self, owner, cid, tid, code, uncertain=False):
        turn = next(t for (key_cid, _), t in self.requests.items() if key_cid == cid)
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


def make_client(monkeypatch, handler, store=None, user="teacher"):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", "testing-" + "s" * 40)
    app = FastAPI()
    app.include_router(create_router(user_for_request=lambda _: {"id": user, "auth_type": "sso"},
                                   store=store or MemoryLedger(),
                                   transport=httpx.MockTransport(handler)))
    return TestClient(app)


HEADERS = {"X-NarAgent-Action": "chat"}


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
