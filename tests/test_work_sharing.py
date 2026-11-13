from fastapi import FastAPI
from fastapi.testclient import TestClient

from webgal_backend.work_store import WorkStore
from webgal_backend.work_sharing import create_router

A = "a" * 32
ASSETS = {
    "index.html": b"<!doctype html><html><body>work</body></html>",
    "preview.png": b"png",
    "mobile.png": b"mobile",
}

def client_for(store, owner="teacher-a"):
    app = FastAPI()
    app.include_router(create_router(
        user_for_request=lambda request: {"id": owner, "auth_type": "sso"},
        store=store, frontend_url="https://example.com/narrativeos",
    ))
    return TestClient(app)


def test_share_is_published_only_and_owner_scoped(tmp_path):
    store = WorkStore(tmp_path)
    work = store.create("teacher-a", A, "html", "诗词互动学习", "课堂练习", ASSETS)
    work_id = work["id"]
    with client_for(store) as client:
        assert client.get(f"/works/{work_id}/share").status_code == 409
        assert client.get(f"/works/{work_id}/share/qr.png").status_code == 409
        pending = store.start_publication("teacher-a", work_id)
        store.finish_publication(
            "teacher-a", work_id, pending["pending_version_id"],
            f"https://example.com/narrativeos/practice/works/{work_id}",
            {"title": "诗词互动学习", "summary": "课堂练习", "subject": "语文",
             "grade": "初中", "tags": ["诗词"]},
        )
        result = client.get(f"/works/{work_id}/share")
        assert result.status_code == 200
        assert result.json()["public_url"].endswith("/practice/works/" + work_id)
        assert result.json()["title"] == "诗词互动学习"
        assert "owner_user_id" not in result.text
        qr = client.get(f"/works/{work_id}/share/qr.png")
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/png")
        assert qr.content[:8] == b"\x89PNG\r\n\x1a\n"
    with client_for(store, owner="teacher-b") as other:
        assert other.get(f"/works/{work_id}/share").status_code == 404
        assert other.get(f"/works/{work_id}/share/qr.png").status_code == 404
    store.start_unpublish("teacher-a", work_id)
    with client_for(store) as client:
        assert client.get(f"/works/{work_id}/share").status_code == 409
        assert client.get(f"/works/{work_id}/share/qr.png").status_code == 409
