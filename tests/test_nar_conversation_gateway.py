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
                "parentArtifactId": parent,
                "createdAt": TODAY.isoformat()}
        self.requests[key] = turn
        self.messages.setdefault(cid, []).append({"role": "user", "content": prompt,
            "id": ID_A, "createdAt": TODAY.isoformat(), "seq": 1, "metadata": None})
        return turn, True

    def latest_artifact(self, owner, cid, selected_id=None):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        items = getattr(self, "artifacts", {}).get(cid, [])
        if selected_id:
            return next((item for item in items if item["artifactId"] == selected_id), None)
        return items[0] if items else None

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


class FakeBilling:
    def reserve(self, owner, tid, mode):
        return object()

    def find(self, owner, tid):
        return object()

    def settle(self, reservation, usage, definite_success, duration_ms=0):
        return {"inputTokens": None, "outputTokens": None, "cachedInputTokens": None,
                "usageStatus": "unavailable", "billingStatus": "unmetered_released",
                "chargedCredits": 0, "reservedCredits": 20, "durationMs": duration_ms}


def make_client(monkeypatch, handler, store=None, user="teacher", billing_factory=FakeBilling,
                rpg_callbacks=None):
    monkeypatch.setenv("NAR_AGENT_SERVICE_TOKEN", "testing-" + "s" * 40)
    app = FastAPI()
    app.include_router(create_router(user_for_request=lambda _: {"id": user, "auth_type": "sso"},
                                   store=store or MemoryLedger(),
                                   transport=httpx.MockTransport(handler), billing_factory=billing_factory,
                                   **(rpg_callbacks or {})))
    return TestClient(app)


HEADERS = {"X-NarAgent-Action": "chat"}



def test_auto_always_uses_v2_even_when_live_percent_unset_and_idempotent(monkeypatch):
    monkeypatch.delenv("NAR_INTENT_V2_LIVE_PERCENT", raising=False)
    ledger = V2MemoryLedger()
    calls = []
    def agent(req):
        calls.append(req.url.path)
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={"schema_version": "2.0",
                 "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                     "html": ["create", "revise"], "animation": ["create", "revise"],
                     "hybrid": ["plan_only"]}})
        if req.url.path == "/v1/intent":
            data = json.loads(req.content)
            assert data["schema_version"] == "2.0"
            assert data["context_v2"]["current_message"] == "把赤壁赋做成互动网页"
            return httpx.Response(200, json=_v2_result("create", "new", "html", "execute"))
        assert req.url.path == "/v1/html"
        return httpx.Response(202, json={"id": TID, "user_id": "teacher", "status": "RUNNING"})
    client = make_client(monkeypatch, agent, ledger)
    body = {"conversation_id": CID, "client_request_id": ID_A,
            "mode": "auto", "prompt": "把赤壁赋做成互动网页"}
    first = client.post("/nar-agent/conversations", json=body, headers=HEADERS)
    assert first.status_code == 202, first.text
    assert first.json()["turn"]["mode"] == "html"
    second = client.post("/nar-agent/conversations", json=body, headers=HEADERS)
    assert second.status_code == 202 and second.json()["reused"] is True
    assert calls == ["/v1/capabilities", "/v1/intent", "/v1/html"]


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



def test_opted_in_billing_reserves_once_and_captures_reported_stream_tokens(monkeypatch):
    import webgal_backend.nar_conversation_routes as routes
    events = []

    class Metering:
        def reserve(self, owner, tid, mode):
            events.append(("reserve", owner, tid, mode))
            return object()

        def find(self, owner, tid):
            events.append(("find", owner, tid))
            return object()

        def settle(self, reservation, usage, definite_success, duration_ms=0):
            events.append(("settle", definite_success, usage, duration_ms))
            return {"inputTokens": 120, "outputTokens": 45, "cachedInputTokens": 0,
                    "usageStatus": "reported", "billingStatus": "captured",
                    "chargedCredits": 1, "reservedCredits": 20,
                    "durationMs": duration_ms}

    monkeypatch.setattr(routes, "NarTurnBilling", Metering)

    def provider(request):
        assert request.url.path == "/v1/runs/stream"
        data = ('event: delta\n'
                'data: {"text":"正在讲解"}\n\n'
                'event: done\n'
                'data: {"user_id":"teacher","output":"正在讲解","duration_ms":880,'
                '"usage":{"m":{"input_tokens":120,"output_tokens":45}}}\n\n')
        return httpx.Response(200, text=data, headers={"content-type":"text/event-stream"})

    ledger = MemoryLedger()
    client = make_client(monkeypatch, provider, ledger, billing_factory=Metering)
    payload = {"conversation_id": CID, "client_request_id": ID_A,
               "prompt": "解释串联电路", "mode": "chat"}
    result = client.post("/nar-agent/conversations/stream", headers=HEADERS, json=payload)
    assert result.status_code == 200
    assert 'event: result' in result.text
    assert [event[0] for event in events] == ["reserve", "find", "settle"]
    assert events[2] == ("settle", True, {"m": {"input_tokens": 120, "output_tokens": 45}}, 880)
    reused = client.post("/nar-agent/conversations/stream", headers=HEADERS, json=payload)
    assert reused.json()["reused"] is True
    assert len(events) == 3



def test_followup_animation_edit_v2_uses_original_generator(monkeypatch):
    parent_id = "e" * 32
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    ledger.artifacts = {CID: [{"artifactId": parent_id, "kind": "animation", "title": "马达动画"}]}
    ledger.messages[CID] = [
        {"role": "user", "content": "给我制作一个马达的原理拆解动画", "id": ID_A, "seq": 1},
        {"role": "assistant", "content": "已完成动画。", "id": ID_B, "seq": 2},
    ]
    requests = []
    from webgal_backend.work_store import WorkStore
    monkeypatch.setattr(WorkStore, "find_by_artifact", lambda self, owner, aid: None)

    def agent(req):
        requests.append((req.url.path, json.loads(req.content) if req.content else {}))
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={"schema_version": "2.0",
                 "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                     "html": ["create", "revise"], "animation": ["create", "revise"],
                     "hybrid": ["plan_only"]}})
        if req.url.path == "/v1/intent":
            assert requests[-1][1]["schema_version"] == "2.0"
            return httpx.Response(200, json=_v2_result(
                "revise", "referenced", "animation", "execute", target=parent_id))
        assert req.url.path == "/v1/animations"
        assert json.loads(req.content)["parent_artifact_id"] == parent_id
        return httpx.Response(202, json={"user_id": "teacher", "id": TID, "status": "RUNNING"})

    c = make_client(monkeypatch, agent, ledger)
    response = c.post("/nar-agent/conversations/" + CID + "/turns",
                      headers=HEADERS, json={"client_request_id": "f" * 32,
                       "prompt": "补充要求：直接给我东西啊", "mode": "auto",
                       "parent_artifact_id": parent_id})
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["mode"] == "animation"
    assert response.json()["turn"]["parentArtifactId"] == parent_id
    assert [path for path, _ in requests] == ["/v1/capabilities", "/v1/intent", "/v1/animations"]



def test_auto_v2_new_animation_does_not_reuse_parent(monkeypatch):
    parent_id = "e" * 32
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    ledger.artifacts = {CID: [{"artifactId": parent_id, "kind": "animation", "title": "旧动画"}]}
    ledger.messages[CID] = [{"role": "user", "content": "马达", "id": ID_A, "seq": 1}]
    requests = []
    def agent(req):
        requests.append((req.url.path, json.loads(req.content) if req.content else {}))
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={"schema_version": "2.0",
                 "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                     "html": ["create", "revise"], "animation": ["create", "revise"],
                     "hybrid": ["plan_only"]}})
        if req.url.path == "/v1/intent":
            assert json.loads(req.content)["schema_version"] == "2.0"
            return httpx.Response(200, json=_v2_result("create", "new", "animation", "execute"))
        assert req.url.path == "/v1/animations"
        assert "parent_artifact_id" not in json.loads(req.content)
        return httpx.Response(202, json={"user_id": "teacher", "id": TID, "status": "RUNNING"})
    c = make_client(monkeypatch, agent, ledger)
    response = c.post("/nar-agent/conversations/" + CID + "/turns",
                      headers=HEADERS, json={"client_request_id": "b" * 32,
                       "prompt": "新做一个磁场的独立动画", "mode": "auto",
                       "parent_artifact_id": parent_id})
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["parentArtifactId"] is None
    assert [path for path, _ in requests] == ["/v1/capabilities", "/v1/intent", "/v1/animations"]


def test_cross_conversation_artifact_cannot_be_used_as_edit_parent(monkeypatch):
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    ledger.artifacts = {CID: [{"artifactId": "e" * 32, "kind": "animation"}]}
    ledger.messages[CID] = []
    c = make_client(monkeypatch, lambda _: httpx.Response(200), ledger)
    res = c.post("/nar-agent/conversations/" + CID + "/turns",
                 headers=HEADERS, json={"client_request_id": "b" * 32,
                        "prompt": "调成居中", "mode": "auto",
                        "selected_artifact_id": "d" * 32})
    assert res.status_code == 404



class V2MemoryLedger(MemoryLedger):
    """Stub only for the V2 live-gate contract. Production uses SQL CAS."""
    pending = None

    def artifact_candidates(self, owner, cid, selected_id=None, limit=5):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        items = getattr(self, "artifacts", {}).get(cid, [])
        if selected_id and not any(item["artifactId"] == selected_id for item in items):
            raise ConversationMissing("Selected artifact is not owner-scoped")
        return items[:limit]

    def get_pending_clarification(self, owner, cid, clarification_id=None):
        if self.owners.get(cid) != owner:
            raise ConversationMissing("Not found")
        if self.pending and (not clarification_id
                or self.pending["metadata"]["clarification_v2"]["clarification_id"] == clarification_id):
            return self.pending
        return None

    def claim_clarification_answer(self, owner, cid, request_id, raw_answer):
        from webgal_backend.nar_pending_schema_v2 import ClarificationAnswer
        from webgal_backend.nar_pending_v2 import (
            validate_clarification_answer, mark_clarification_answered)
        item = self.get_pending_clarification(owner, cid, raw_answer["clarification_id"])
        validated = validate_clarification_answer(
            item["metadata"], ClarificationAnswer.model_validate(raw_answer))
        item["metadata"] = mark_clarification_answered(item["metadata"], validated, request_id)
        return {"metadata": item["metadata"], "reused": False}

    def recent_rpg_games(self, owner, cid, limit=5):
        assert owner == "teacher" and cid == CID
        return []

    def get_turn_original_prompt(self, owner, cid, source_turn_id):
        assert owner == "teacher" and cid == CID and source_turn_id == TID
        return "我想做个春江花月夜的互动游戏"

    def supersede_pending_clarification(self, owner, cid):
        item = self.get_pending_clarification(owner, cid)
        if not item:
            return False
        for name in ("choices", "clarification_v2", "pending_task_v2"):
            item["metadata"][name]["status"] = "superseded"
        return True

    def finish_turn(self, owner, cid, tid, *, output, **kwargs):
        self.final_metadata = kwargs.get("public_metadata")
        return super().finish_turn(owner, cid, tid, output=output, **kwargs)


def _v2_result(action, relation, output, next_step, target=None, question=None):
    return {"user_id": "teacher", "schema_version": "2.0", "decision": {
        "schema_version": "2.0",
        "tasks": [{"action": action, "target_relation": relation,
                   "candidate_artifact_id": target, "desired_output": output,
                   "goal": "把马达动画的画面居中" if action == "revise" else "新制作一次函数练习网页",
                   "requirements": []}],
        "next_step": next_step,
        "uncertainty": "target" if question else "none",
        "clarification": question}}


def test_v2_live_independent_html_does_not_inherit_even_explicit_legacy_parent(monkeypatch):
    monkeypatch.setenv("NAR_INTENT_V2_LIVE_PERCENT", "100")
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    artifact = "e" * 32
    ledger.artifacts = {CID: [{"artifactId": artifact, "kind": "animation", "title": "马达动画"}]}
    ledger.messages[CID] = [{"role": "assistant", "content": "旧动画已经做好", "id": ID_B, "seq": 1}]
    calls = []

    def agent(req):
        if req.url.path == "/v1/capabilities":
            calls.append((req.url.path, {}))
            return httpx.Response(200, json={"schema_version": "2.0",
                "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                    "html": ["create", "revise"], "animation": ["create", "revise"],
                    "hybrid": ["plan_only"]}})
        data = json.loads(req.content)
        calls.append((req.url.path, data))
        if req.url.path == "/v1/intent":
            assert data["schema_version"] == "2.0"
            assert data["context_v2"]["workspace"]["selected_artifact_id"] == artifact
            return httpx.Response(200, json=_v2_result(
                "create", "new", "html", "execute"))
        assert req.url.path == "/v1/html"
        assert "parent_artifact_id" not in data
        return httpx.Response(202, json={"user_id": "teacher", "id": TID, "status": "RUNNING"})

    c = make_client(monkeypatch, agent, ledger)
    body = {"client_request_id": "f" * 32, "prompt": "这个完成了，现在做一个新的函数网页",
            "mode": "auto", "parent_artifact_id": artifact,
            "selected_artifact_id": artifact}
    first = c.post("/nar-agent/conversations/" + CID + "/turns", headers=HEADERS, json=body)
    assert first.status_code == 202, first.text
    assert first.json()["turn"]["mode"] == "html"
    assert first.json()["turn"]["parentArtifactId"] is None
    second = c.post("/nar-agent/conversations/" + CID + "/turns", headers=HEADERS, json=body)
    assert second.json()["reused"] is True
    assert [x[0] for x in calls] == ["/v1/capabilities", "/v1/intent", "/v1/html"]


def test_v2_live_animation_revision_keeps_parent_and_original_generator(monkeypatch):
    monkeypatch.setenv("NAR_INTENT_V2_LIVE_PERCENT", "100")
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    parent = "e" * 32
    ledger.artifacts = {CID: [{"artifactId": parent, "kind": "animation", "title": "马达动画"}]}
    ledger.messages[CID] = [{"role": "assistant", "content": "马达动画已完成", "id": ID_B, "seq": 1}]
    calls = []
    from webgal_backend.work_store import WorkStore
    monkeypatch.setattr(WorkStore, "find_by_artifact", lambda self, owner, artifact_id: None)

    def agent(req):
        if req.url.path == "/v1/capabilities":
            calls.append(req.url.path)
            return httpx.Response(200, json={"schema_version": "2.0",
                "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                    "html": ["create", "revise"], "animation": ["create", "revise"],
                    "hybrid": ["plan_only"]}})
        data = json.loads(req.content)
        calls.append(req.url.path)
        if req.url.path == "/v1/intent":
            return httpx.Response(200, json=_v2_result(
                "revise", "referenced", "animation", "execute", target=parent))
        assert req.url.path == "/v1/animations"
        assert data["parent_artifact_id"] == parent
        return httpx.Response(202, json={"user_id": "teacher", "id": TID, "status": "RUNNING"})

    c = make_client(monkeypatch, agent, ledger)
    response = c.post("/nar-agent/conversations/" + CID + "/turns",
        headers=HEADERS, json={"client_request_id": "f"*32,
        "prompt": "把刚才马达动画的画面居中", "mode": "auto"})
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["mode"] == "animation"
    assert response.json()["turn"]["parentArtifactId"] == parent
    assert calls == ["/v1/capabilities", "/v1/intent", "/v1/animations"]


def test_v2_live_ambiguous_target_generates_persistent_card_without_dispatch(monkeypatch):
    monkeypatch.setenv("NAR_INTENT_V2_LIVE_PERCENT", "100")
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    ledger.messages[CID] = [{"role": "assistant", "content": "两个作品已完成", "id": ID_B, "seq": 1}]
    ledger.artifacts = {CID: [
        {"artifactId": "e"*32, "kind": "animation", "title": "马达动画"},
        {"artifactId": "f"*32, "kind": "html", "title": "函数网页"}]}
    calls = []

    def agent(req):
        calls.append(req.url.path)
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={"schema_version": "2.0",
                "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                    "html": ["create", "revise"], "animation": ["create", "revise"],
                    "hybrid": ["plan_only"]}})
        assert req.url.path == "/v1/intent"
        return httpx.Response(200, json=_v2_result(
            "revise", "ambiguous", "unspecified", "clarify", question={
            "question": "你想修改哪一件作品？",
            "options": ["马达动画", "函数网页"], "allow_custom": True}))

    c = make_client(monkeypatch, agent, ledger)
    response = c.post("/nar-agent/conversations/" + CID + "/turns",
        headers=HEADERS, json={"client_request_id": "f"*32,
                                 "prompt": "把那个居中", "mode": "auto"})
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["status"] == "SUCCEEDED"
    assert calls == ["/v1/capabilities", "/v1/intent"]
    assert ledger.final_metadata["choices"]["schemaVersion"] == "2.0"
    assert ledger.final_metadata["clarification_v2"]["status"] == "pending"
    assert ledger.final_metadata["pending_task_v2"]["proposal"]["tasks"][0]["action"] == "revise"


def test_v2_live_formal_choice_resumes_original_task(monkeypatch):
    monkeypatch.setenv("NAR_INTENT_V2_LIVE_PERCENT", "0")
    from webgal_backend.nar_pending_v2 import make_clarification_metadata
    from webgal_backend.work_store import WorkStore
    monkeypatch.setattr(WorkStore, "find_by_artifact", lambda self, owner, artifact_id: None)
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    artifact = "e" * 32
    question = _v2_result("revise", "selected", "animation", "clarify", artifact, {
        "question": "你想怎么调整？", "options": ["画面居中", "只移动按钮"],
        "allow_custom": True})["decision"]
    metadata = make_clarification_metadata(question, origin_turn_id=TID,
        verified_target_artifact_id=artifact, clarification_id="9"*32)
    ledger.pending = {"message_id": ID_B, "metadata": metadata}
    ledger.messages[CID] = [{"role": "assistant", "content": "你想怎么调整？", "id": ID_B, "seq": 1}]
    ledger.artifacts = {CID: [{"artifactId": artifact, "kind": "animation", "title": "马达动画"}]}
    calls = []

    def agent(req):
        if req.url.path == "/v1/capabilities":
            calls.append(req.url.path)
            return httpx.Response(200, json={"schema_version": "2.0",
                "capabilities": {"chat": ["answer", "discuss", "evaluate"],
                    "html": ["create", "revise"], "animation": ["create", "revise"],
                    "hybrid": ["plan_only"]}})
        data = json.loads(req.content)
        calls.append(req.url.path)
        if req.url.path == "/v1/intent":
            assert data["context_v2"]["conversation"]["pending_clarification"]["current_answer"]["selected_labels"] == ["画面居中"]
            return httpx.Response(200, json=_v2_result(
                "revise", "selected", "animation", "execute", target=artifact))
        assert req.url.path == "/v1/animations"
        assert "把马达动画的画面居中" in data["prompt"]
        assert data["parent_artifact_id"] == artifact
        return httpx.Response(202, json={"user_id": "teacher", "id": TID, "status": "RUNNING"})

    c = make_client(monkeypatch, agent, ledger)
    response = c.post("/nar-agent/conversations/" + CID + "/turns",
        headers=HEADERS, json={
            "client_request_id": "f"*32, "mode": "auto", "prompt": "我选择：画面居中",
            "selected_artifact_id": artifact,
            "clarification_answer": {
                "clarification_id": "9"*32, "selected_option_ids": ["o1"],
                "custom_text": ""}})
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["mode"] == "animation"
    assert calls == ["/v1/capabilities", "/v1/intent", "/v1/animations"]
    assert ledger.pending["metadata"]["choices"]["status"] == "answered"


def test_v2_unavailable_fails_closed_without_legacy_intent_or_html(monkeypatch):
    monkeypatch.setenv("NAR_INTENT_V2_LIVE_PERCENT", "0")
    ledger = V2MemoryLedger()
    requests = []
    def unavailable(req):
        requests.append(req.url.path)
        assert req.url.path == "/v1/capabilities"
        return httpx.Response(503)
    client = make_client(monkeypatch, unavailable, ledger)
    resp = client.post("/nar-agent/conversations", headers=HEADERS, json={
        "conversation_id": CID, "client_request_id": ID_A,
        "mode": "auto", "prompt": "我想做个春江花月夜的互动游戏"})
    assert resp.status_code == 503
    assert requests == ["/v1/capabilities"]
    assert not ledger.requests

def test_selected_interactive_story_resumes_original_game_without_feature_flags(monkeypatch):
    """Regression: choosing the RPG option must yield PREPARED, not capability_review."""
    from webgal_backend.nar_pending_v2 import make_clarification_metadata

    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"
    original = {"schema_version": "2.0", "tasks": [{
        "action": "create", "target_relation": "new", "candidate_artifact_id": None,
        "candidate_game_job_id": None, "desired_output": "unspecified",
        "goal": "制作《春江花月夜》互动游戏", "requirements": []
    }], "next_step": "clarify", "uncertainty": "output", "clarification": {
        "question": "你想要的《春江花月夜》互动游戏更接近哪一种形式？",
        "options": [
            "互动剧情游戏：通过角色选择和对话分支推动剧情，可有多个结局",
            "网页练习小游戏：通过答题、拖拽、排序等方式完成闯关",
            "其他形式"
        ],
        "allow_custom": True,
    }}
    metadata = make_clarification_metadata(original, origin_turn_id=TID,
        verified_target_artifact_id=None, clarification_id="9" * 32)
    ledger.pending = {"message_id": ID_B, "metadata": metadata}
    ledger.messages[CID] = [{
        "id": ID_B, "seq": 1, "role": "assistant", "content": original["clarification"]["question"]
    }]
    paths = []
    def agent(req):
        paths.append(req.url.path)
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={
                "schema_version": "2.0", "capabilities": {
                    "chat": ["answer", "discuss", "evaluate"],
                    "html": ["create", "revise"],
                    "animation": ["create", "revise"], "hybrid": ["plan_only"]
                }})
        if req.url.path == "/v1/intent":
            packet = json.loads(req.content)["context_v2"]
            assert packet["capabilities"]["game"] == ["create", "edit_link"]
            assert packet["conversation"]["pending_clarification"]["current_answer"]["selected_labels"] == [
                original["clarification"]["options"][0]]
            # The model can incorrectly interpret a confirmed format choice
            # as continuation. Forge must resume create/new when executable.
            return httpx.Response(200, json=_v2_result(
                "continue", "none", "game", "execute"))
        raise AssertionError("A game must not dispatch or reserve before its confirmation card")

    def not_yet_called(*args, **kwargs):
        raise AssertionError("RPG job/quote must wait for explicit confirmation")
    c = make_client(monkeypatch, agent, ledger, rpg_callbacks={
        "rpg_create": not_yet_called, "rpg_get": not_yet_called,
        "rpg_run": not_yet_called, "rpg_quote": not_yet_called,
        "rpg_balance": not_yet_called,
    })
    response = c.post("/nar-agent/conversations/" + CID + "/turns", json={
        "client_request_id": "f" * 32, "mode": "auto",
        "prompt": "我选择：互动剧情游戏：通过角色选择和对话分支推动剧情，可有多个结局",
        "clarification_answer": {
            "clarification_id": "9" * 32, "selected_option_ids": ["o1"],
            "custom_text": "",
        },
    }, headers=HEADERS)
    assert response.status_code == 202, response.text
    assert response.json()["turn"]["status"] == "SUCCEEDED"
    assert ledger.final_metadata["card_type"] == "rpg"
    assert ledger.final_metadata["rpg"]["state"] == "PREPARED"
    assert ledger.final_metadata["rpg"]["source_turn_id"] == TID
    assert "春江花月夜" in ledger.final_metadata["rpg"]["continued_requirements"]
    assert ledger.pending["metadata"]["choices"]["status"] == "answered"
    assert paths == ["/v1/capabilities", "/v1/intent"]

def test_composer_role_play_uses_rpg_when_intent_returns_html(monkeypatch):
    ledger = V2MemoryLedger()
    ledger.owners[CID] = "teacher"

    def agent(req):
        if req.url.path == "/v1/capabilities":
            return httpx.Response(200, json={"schema_version": "2.0", "capabilities": {
                "chat": ["answer", "discuss", "evaluate"], "html": ["create", "revise"],
                "animation": ["create", "revise"], "hybrid": ["plan_only"],
            }})
        assert req.url.path == "/v1/intent"
        return httpx.Response(200, json=_v2_result("create", "new", "html", "execute"))

    def wait_for_confirmation(*args, **kwargs):
        raise AssertionError("RPG jobs and quotes must wait for confirmation")

    client = make_client(monkeypatch, agent, ledger, rpg_callbacks={
        name: wait_for_confirmation for name in
        ("rpg_create", "rpg_get", "rpg_run", "rpg_quote", "rpg_balance")
    })
    response = client.post("/nar-agent/conversations/" + CID + "/turns", json={
        "client_request_id": ID_A, "mode": "auto",
        "prompt": "创作形式：互动角色扮演\n扮演水滴，探索水循环",
    }, headers=HEADERS)
    assert response.status_code == 202, response.text
    assert ledger.final_metadata["card_type"] == "rpg"
    assert ledger.final_metadata["rpg"]["state"] == "PREPARED"
    assert ledger.final_metadata["rpg"]["spec"]["topic"] == "扮演水滴，探索水循环"
