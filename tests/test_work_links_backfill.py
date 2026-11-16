from webgal_backend.work_store import WorkStore
from webgal_backend.work_links_backfill import eligible_repairs, repair_one
from webgal_backend.work_urls import work_page_url
from webgal_backend.storage import read_json

A = "a" * 32
ASSETS = {"index.html": b"<html>ok</html>", "preview.png": b"one", "mobile.png": b"two"}


def test_legacy_public_link_republish_preserves_owner_version_and_author(tmp_path):
    store = WorkStore(tmp_path)
    saved = store.create("owner-a", A, "html", "阅读互动", "", ASSETS)
    opened = store.start_publication("owner-a", saved["id"])
    wrong = f"http://43.138.207.82/practice/works/{saved['id']}/"
    store.finish_publication("owner-a", saved["id"], opened["pending_version_id"], wrong, {
        "title": "阅读互动", "summary": "", "subject": "语文", "grade": None, "tags": [],
    })
    pending = eligible_repairs(store, "http://43.138.207.82")
    assert len(pending) == 1 and pending[0]["old_url"] == wrong
    calls = []
    fixed = repair_one(store, pending[0], "http://43.138.207.82",
        lookup=lambda _: {"published": True, "authorName": "原作者"},
        publish=lambda body: calls.append(body) or {"published": True})
    assert fixed == work_page_url("http://43.138.207.82", saved["id"])
    assert calls[0]["authorName"] == "原作者"
    assert calls[0]["playUrl"] == fixed
    assert calls[0]["ownerUserId"] == "owner-a"
    assert store.get("owner-a", saved["id"])["published_version_id"] == opened["pending_version_id"]
    assert eligible_repairs(store, "http://43.138.207.82") == []


def test_backfill_does_not_mutate_when_remote_author_is_unknown(tmp_path):
    from webgal_backend.work_store import WorkConflictError
    import pytest
    store = WorkStore(tmp_path)
    saved = store.create("owner-b", A, "html", "实验", "", ASSETS)
    opened = store.start_publication("owner-b", saved["id"])
    wrong = "https://example.com/practice/works/" + saved["id"] + "/"
    store.finish_publication("owner-b", saved["id"], opened["pending_version_id"], wrong, {
        "title": "实验", "summary": "", "subject": None, "grade": None, "tags": [],
    })
    plan = eligible_repairs(store, "https://example.com")[0]
    with pytest.raises(WorkConflictError, match="author attribution"):
        repair_one(store, plan, "https://example.com",
                   lookup=lambda _: {"published": True},
                   publish=lambda _: pytest.fail("must not publish"))
    assert read_json(store.path(saved["id"]) / "work.json")["public_url"] == wrong
