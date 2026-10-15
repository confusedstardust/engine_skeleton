import pytest
from fastapi.testclient import TestClient
import webgal_backend.app as backend

@pytest.mark.parametrize("offset,size,total,expected_more", [(0, 8, 25, True), (8, 12, 25, True), (20, 12, 25, False), (25, 12, 25, False)])
def test_feed_batches_keep_absolute_offsets_and_filters(monkeypatch, offset, size, total, expected_more):
    calls = []
    class Library:
        def list_assets(self, user_id, **options):
            calls.append((user_id, options))
            options["pagination"]["total"] = total
            return [{"id": str(i)} for i in range(options["offset"], min(total, options["offset"] + options["limit"]))]
    monkeypatch.setattr(backend, "user_from_request", lambda *args: {"id": "owner", "auth_type": "sso"})
    monkeypatch.setattr(backend, "get_asset_library", lambda: Library())
    response = TestClient(backend.app).get(f"/assets?offset={offset}&page_size={size}&collection=favorites&kind=figure&search=cat&category=people")
    assert response.status_code == 200
    data = response.json()
    assert len(data["assets"]) == min(size, total - offset)
    assert data["next_offset"] == offset + len(data["assets"])
    assert data["has_more"] is expected_more
    user, options = calls[0]
    assert user == "owner"
    assert options["offset"] == offset
    assert options["limit"] == size + 1
    assert options["original_only"] and options["include_favorite"]
    assert (options["collection"], options["kind"], options["search"], options["category"]) == ("favorites", "FIGURE", "cat", "people")

@pytest.mark.parametrize("query", ["offset=-1", "offset=0&page_size=0", "offset=0&page_size=49"])
def test_invalid_feed_pagination_never_queries_library(monkeypatch, query):
    monkeypatch.setattr(backend, "user_from_request", lambda *args: {"id": "owner", "auth_type": "sso"})
    monkeypatch.setattr(backend, "get_asset_library", lambda: pytest.fail("invalid request queried assets"))
    assert TestClient(backend.app).get("/assets?" + query).status_code == 422
