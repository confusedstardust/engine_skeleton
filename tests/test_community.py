from contextlib import contextmanager

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from webgal_backend import community


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(community.router)
    return TestClient(app)


def test_guests_and_invite_users_cannot_post_or_read_private_questions(client, monkeypatch):
    def guest(*args):
        raise HTTPException(401, "Login required")

    monkeypatch.setattr(community, "user_from_request", guest)
    assert client.get("/community/mine").status_code == 401
    assert client.post("/community/questions", json={"question": "How do I create?"}, headers={"X-Forge-Community-Action": "1"}).status_code == 401
    monkeypatch.setattr(community, "user_from_request", lambda *args: {"id": "invite", "auth_type": "invite"})
    assert client.get("/community/mine").status_code == 401
    assert client.post("/community/questions", json={"question": "How do I create?"}, headers={"X-Forge-Community-Action": "1"}).status_code == 401


def test_writes_require_action_headers_and_admin_rights(client, monkeypatch):
    assert client.post("/community/questions", json={"question": "How do I create?"}).status_code == 403
    def forbidden(*args):
        raise HTTPException(403, "Admin required")
    monkeypatch.setattr(community, "require_admin", forbidden)
    assert client.get("/admin/community").status_code == 403
    assert client.put("/admin/community/questions/id", json={"answer": "Reply", "published": True}, headers={"X-Forge-Admin-Action": "1"}).status_code == 403


def test_blank_content_and_unanswered_publication_rejected(client, monkeypatch):
    assert client.post("/community/questions", json={"question": "       "}).status_code == 422
    monkeypatch.setattr(community, "require_admin", lambda *args: {})
    assert client.put("/admin/community/questions/id", json={"answer": "  ", "published": True}, headers={"X-Forge-Admin-Action": "1"}).status_code == 422
    assert client.post("/admin/community/announcements", json={"title": "  ", "content": "notice"}, headers={"X-Forge-Admin-Action": "1"}).status_code == 422


def test_public_listing_excludes_private_content_and_author_identifiers(client, monkeypatch):
    calls = []
    class Cursor:
        def execute(self, sql, params=()):
            calls.append((sql, params))
        def fetchall(self):
            return []
    @contextmanager
    def transaction(self):
        yield Cursor()
    monkeypatch.setattr(community.AssetLibrary, "_transaction", transaction)
    assert client.get("/community").status_code == 200
    assert all("WHERE published=1" in sql for sql, _ in calls)
    assert all("user_id" not in sql and "author_name" not in sql for sql, _ in calls)
    assert "kind='QUESTION'" in calls[1][0]
    calls.clear()
    monkeypatch.setattr(community, "user_from_request", lambda *args: {"id": "alice", "auth_type": "sso"})
    assert client.get("/community/mine").status_code == 200
    assert "WHERE user_id=%s" in calls[0][0]
    assert calls[0][1] == ("alice", "QUESTION", 0)
    calls.clear()
    assert client.get("/community/mine?kind=SUGGESTION").status_code == 200
    assert calls[0][1] == ("alice", "SUGGESTION", 0)
    assert client.get("/community/mine?kind=INVALID").status_code == 422


def test_duplicate_submission_returns_saved_record_without_insert(client, monkeypatch):
    calls = []
    class Cursor:
        def execute(self, sql, params=()): calls.append(sql)
        def fetchone(self): return {"id": "existing"}
    @contextmanager
    def transaction(self): yield Cursor()
    monkeypatch.setattr(community.AssetLibrary, "_transaction", transaction)
    monkeypatch.setattr(community, "user_from_request", lambda *args: {"id": "alice", "auth_type": "sso"})
    response = client.post("/community/questions", json={"question": "How to create?"}, headers={"X-Forge-Community-Action": "1"})
    assert response.status_code == 200
    assert response.json() == {"id": "existing", "duplicate": True}
    assert "question=%s" in calls[1]
    assert not any("INSERT" in sql for sql in calls)


def test_community_route_precedes_generic_admin_resource_route():
    from starlette.routing import Match
    from webgal_backend.app import app
    scope = {"type": "http", "path": "/admin/community", "method": "GET"}
    first_match = next(route for route in app.routes if route.matches(scope)[0] == Match.FULL)
    assert first_match.endpoint is community.admin_board


def test_suggestions_cannot_be_published(client, monkeypatch):
    class Cursor:
        def execute(self, sql, params=()):
            assert not sql.startswith("UPDATE")
        def fetchone(self):
            return {"id": "feedback", "kind": "SUGGESTION"}
    @contextmanager
    def transaction(self): yield Cursor()
    monkeypatch.setattr(community.AssetLibrary, "_transaction", transaction)
    monkeypatch.setattr(community, "require_admin", lambda *args: {})
    response = client.put("/admin/community/questions/feedback", json={"answer": "谢谢你的建议", "published": True}, headers={"X-Forge-Admin-Action": "1"})
    assert response.status_code == 422


@pytest.mark.parametrize("kind", ["QUESTION", "SUGGESTION"])
@pytest.mark.parametrize("content", ["a", "是", "aa是", "  aa是  "])
def test_short_messages_rejected_before_storage(client, monkeypatch, kind, content):
    monkeypatch.setattr(community.AssetLibrary, "_transaction", lambda *args: pytest.fail("short content reached storage"))
    response = client.post("/community/questions", json={"question": content, "kind": kind}, headers={"X-Forge-Community-Action": "1"})
    assert response.status_code == 422


@pytest.mark.parametrize("content", ["这是五个字", "  这是五个字  "])
def test_five_characters_pass_after_trimming(content):
    assert community.Question(question=content).question == "这是五个字"
