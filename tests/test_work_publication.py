import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend.teacher_ecosystem import TeacherEcosystemError
from webgal_backend.work_store import WorkStore, WorkConflictError
from webgal_backend.work_publication import create_router, create_public_router

ACTION = {"X-NarAgent-Action": "chat"}
A = "a" * 32
B = "b" * 32

def assets(value=b"first"):
    return {
        "index.html": b"<!doctype html><html><body>" + value + b"</body></html>",
        "preview.png": b"png",
        "mobile.png": b"mobile",
    }

def make_client(store, publisher, unpublisher=lambda owner, work: {"published": False}):
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda request: {"id": "teacher-a", "auth_type": "sso", "nickname": "张老师"},
        store=store, publisher=publisher, unpublisher=unpublisher,
        frontend_url="https://example.com/narrativeos",
    ))
    app.include_router(create_public_router(store=store))
    return TestClient(app)


def test_public_html_only_after_remote_publish_and_revocation(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "函数学习", "私有草稿", assets())
    expected = []
    def publisher(body):
        expected.append(body)
        return {"published": True}
    calls = []
    def unpublisher(owner, work_id):
        calls.append((owner, work_id))
        return {"published": False}
    with make_client(store, publisher, unpublisher) as client:
        url = f"/public/works/{work['id']}"
        assert client.get(url).status_code == 404
        assert client.get(url + "/index.html").status_code == 404
        response = client.post(f"/works/{work['id']}/publication", json={
            "title": "幂函数互动实验", "summary": "观察指数变化", "subject": "数学",
            "grade": "高中", "tags": ["函数"],
        }, headers=ACTION)
        assert response.status_code == 200, response.text
        assert response.json()["published"] is True
        assert expected[0]["resourceType"] == "INTERACTIVE_HTML"
        assert expected[0]["jobId"] == work["id"]
        assert expected[0]["playUrl"].startswith("https://example.com/narrativeos/practice/works/")
        assert client.get(url).json()["title"] == "幂函数互动实验"
        content = client.get(url + "/index.html")
        assert content.status_code == 200 and b"first" in content.content
        assert "sandbox allow-scripts" in content.headers["content-security-policy"]
        assert "no-store" in content.headers["cache-control"]
        assert client.get(url + "/cover.png").status_code == 200
        # Repeated publication of the same version and metadata is idempotent.
        response = client.post(f"/works/{work['id']}/publication", headers=ACTION, json={
            "title": "幂函数互动实验", "summary": "观察指数变化", "subject": "数学",
            "grade": "高中", "tags": ["函数"],
        })
        assert response.status_code == 200 and len(expected) == 1
        # A private edit does not change the published content.
        store.add_version("teacher-a", work["id"], B, assets(b"new-private"), A)
        assert b"first" in client.get(url + "/index.html").content
        response = client.delete(f"/works/{work['id']}/publication", headers=ACTION)
        assert response.status_code == 200
        assert calls == [("teacher-a", work["id"])]
        assert client.get(url + "/index.html").status_code == 404
        assert store.get("teacher-a", work["id"])["versions"][-1]["artifact_id"] == B


def test_ecosystem_failure_keeps_private_work_and_does_not_expose_it(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "私有作品", "", assets())
    def failing(_):
        raise TeacherEcosystemError("temporary 500")
    with make_client(store, failing) as client:
        response = client.post(f"/works/{work['id']}/publication",
                               json={"title": "私有作品"}, headers=ACTION)
        assert response.status_code == 503
        assert store.get("teacher-a", work["id"])["publication_status"] == "failed"
        assert client.get(f"/public/works/{work['id']}").status_code == 404
        assert store.get("teacher-a", work["id"])["id"] == work["id"]


def test_unpublish_blocks_public_even_if_remote_service_is_offline(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "公开教学", "", assets())
    offline = []
    def unpublish(owner, identifier):
        offline.append(identifier)
        if len(offline) == 1:
            raise TeacherEcosystemError("offline")
        return {"published": False}
    with make_client(store, lambda body: {"published": True}, unpublish) as client:
        url = f"/public/works/{work['id']}"
        assert client.post(f"/works/{work['id']}/publication",
                           json={"title": "公开教学"}, headers=ACTION).status_code == 200
        assert client.get(url).status_code == 200
        assert client.delete(f"/works/{work['id']}/publication", headers=ACTION).status_code == 503
        assert client.get(url).status_code == 404
        assert client.delete(f"/works/{work['id']}/publication", headers=ACTION).status_code == 200
        assert store.get("teacher-a", work["id"])["publication_status"] == "unpublished"


def test_publication_metadata_sync_and_race_guards(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "旧名字", "旧摘要", assets())
    pending = store.start_publication("teacher-a", work["id"])
    with pytest.raises(WorkConflictError):
        store.start_unpublish("teacher-a", work["id"])
    current = store.finish_publication(
        "teacher-a", work["id"], pending["pending_version_id"],
        "https://example.com/work", {
            "title": "新名字", "summary": "新摘要", "subject": "数学",
            "grade": "高中", "tags": ["函数"],
        },
    )
    assert current["title"] == "新名字"
    assert current["summary"] == "新摘要"
    assert current["subject"] == "数学"
    assert current["grade"] == "高中"
    assert current["tags"] == ["函数"]
    store.start_unpublish("teacher-a", work["id"])
    with pytest.raises(WorkConflictError):
        store.start_publication("teacher-a", work["id"])
    with pytest.raises(FileNotFoundError):
        store.public(work["id"])
    store.finish_unpublish("teacher-a", work["id"])
    with pytest.raises(WorkConflictError):
        store.finish_unpublish("teacher-a", work["id"])



def test_cover_choice_is_pinned_to_published_version(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "可交互函数", "简介", assets())
    assert store.private_cover("teacher-a", work["id"]) == b"png"
    store.update("teacher-a", work["id"], cover_variant="mobile")
    assert store.private_cover("teacher-a", work["id"]) == b"mobile"
    with pytest.raises(FileNotFoundError):
        store.private_cover("teacher-b", work["id"])
    pending = store.start_publication("teacher-a", work["id"])
    store.finish_publication(
        "teacher-a", work["id"], pending["pending_version_id"],
        "https://example.com/work",
        {"title": "可交互函数", "summary": "简介", "subject": "数学", "grade": "高中", "tags": []},
    )
    assert store.public_cover(work["id"]) == b"mobile"
    store.update("teacher-a", work["id"], cover_variant="preview")
    assert store.private_cover("teacher-a", work["id"]) == b"png"
    assert store.public_cover(work["id"]) == b"mobile"  # No silent change to public cover.
    store.start_unpublish("teacher-a", work["id"])
    with pytest.raises(FileNotFoundError):
        store.public_cover(work["id"])

