from __future__ import annotations

from pathlib import Path
import json

from fastapi.testclient import TestClient

import webgal_backend.app as backend_app
from credit_system.models import CreditBalance, CreditGrant, CreditReservation
from webgal_backend.pipeline import PipelineError
from webgal_backend.storage import JobStore


class FakeCredits:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def ensure_signup_credits(self, user_id: str) -> CreditGrant:
        self.calls.append(("signup", user_id))
        return CreditGrant("a" * 32, None, user_id, 200, True)

    def get_balance(self, user_id: str) -> CreditBalance:
        self.calls.append(("balance", user_id))
        return CreditBalance(200, 0, 0, 0)

    def ensure_billable_job(self, **kwargs) -> None:
        self.calls.append(("billable", kwargs))

    def reserve_for_game(self, **kwargs) -> CreditReservation:
        self.calls.append(("reserve", kwargs))
        return CreditReservation("b" * 32, kwargs["user_id"], kwargs["job_id"], kwargs["operation_key"], kwargs["units"], "RESERVED", True)

    def capture(self, reservation_id: str, *, units=None, settlement=None) -> CreditReservation:
        self.calls.append(("capture", reservation_id))
        return CreditReservation(reservation_id, "user-1", "a" * 32, "generation", 40, "CAPTURED", False)

    def release(self, reservation_id: str) -> None:
        self.calls.append(("release", reservation_id))


class FakePipeline:
    def __init__(self, store: JobStore, *, fail: bool = False) -> None:
        self.store = store
        self.fail = fail

    def run_all(self, job_id: str):
        if self.fail:
            raise PipelineError("generation failed")
        return self.store.get(job_id)

    def regenerate_asset_image(self, job, filename: str, prompt: str | None):
        if self.fail:
            raise PipelineError("image failed")
        output = self.store.job_dir(job["id"]) / "public" / "game" / "figure" / f"{filename}.webp"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"new image")
        return {"filename": filename, "subdir": "figure", "prompt": prompt or ""}

    def regenerate_tts_preview(self, job, speaker: str, voice: str):
        if self.fail:
            raise PipelineError("tts failed")
        job_dir = self.store.job_dir(job["id"])
        output = job_dir / "public" / "game" / "vocal_preview" / "speaker.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"audio")
        review = {"vocal_dir": "public/game/vocal_preview", "characters": [{"speaker": speaker, "voice": voice, "filename": "speaker.wav", "text": "测试台词", "status": "completed"}]}
        (job_dir / "state" / "tts_voice_review.json").write_text(json.dumps(review), encoding="utf-8")
        return review["characters"][0]


class FakeAssetLibrary:
    def __init__(self, record=None) -> None:
        self.record = record
        self.list_calls: list[dict[str, object]] = []

    def list_assets(self, user_id: str, **kwargs):
        self.list_calls.append({"user_id": user_id, **kwargs})
        return []

    def download_accessible_file(self, user_id: str, file_id: str):
        return self.record, b"not used"

    def download_accessible_variant(self, user_id: str, asset_id: str, variant: str):
        return None

    def record_draft_usage(self, **kwargs):
        return None

    def rename_asset(self, user_id: str, asset_id: str, name: str):
        return {"id": asset_id, "name": name.strip(), "kind": "FIGURE", "source_type": "UPLOADED"}

    def delete_asset(self, user_id: str, asset_id: str):
        return None


def _authenticated_user(_request, _workspace_root):
    return {
        "id": "user-1",
        "email": "user@example.com",
        "nickname": "user",
        "avatar_url": None,
        "providers": ["email"],
        "auth_type": "sso",
    }


def _invite_user(_request, _workspace_root):
    return {
        "id": "invite:0123456789abcdef",
        "email": None,
        "nickname": None,
        "avatar_url": None,
        "providers": [],
        "auth_type": "invite",
    }


def _invite_identity(_request, _workspace_root):
    return {"type": "invite", "invite_hash": "0" * 64}


def test_credit_balance_grants_signup_credits_once(monkeypatch):
    credits = FakeCredits()
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).get("/credits/balance")

    assert response.status_code == 200
    assert response.json() == {"available": 200, "reserved": 0, "consumed": 0, "revoked": 0}
    assert credits.calls == [("signup", "user-1"), ("balance", "user-1")]


def test_asset_library_list_forwards_generated_source_filter(monkeypatch):
    library = FakeAssetLibrary()
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)

    response = TestClient(backend_app.app).get("/assets?kind=figure&source_type=generated&limit=25")

    assert response.status_code == 200
    assert response.json() == {"assets": []}
    assert library.list_calls == [{"user_id": "user-1", "kind": "FIGURE", "source_type": "GENERATED", "limit": 25, "collection": None}]


def test_asset_library_rejects_unused_imported_source_type(monkeypatch):
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)

    response = TestClient(backend_app.app).get("/assets?source_type=IMPORTED")

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported asset source type"


def test_asset_library_owner_can_rename_and_delete_asset(monkeypatch):
    library = FakeAssetLibrary()
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)
    asset_id = "a" * 32

    rename_response = TestClient(backend_app.app).put(f"/assets/{asset_id}/name", json={"name": " 新名称 "})
    delete_response = TestClient(backend_app.app).delete(f"/assets/{asset_id}")

    assert rename_response.status_code == 200
    assert rename_response.json()["asset"]["name"] == "新名称"
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}


def test_from_library_accepts_owned_uploaded_asset(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"classroom_topic": "课堂"}, {"type": "sso", "user_id": "user-1"})
    library = FakeAssetLibrary({
        "id": "f" * 32,
        "asset_id": "a" * 32,
        "kind": "BGM",
        "source_type": "UPLOADED",
        "variant": "original",
        "bucket": "test-bucket",
        "object_key": "assets/uploaded.mp3",
        "mime_type": "audio/mpeg",
        "name": "上传素材",
    })
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)
    monkeypatch.setattr(backend_app, "_get_owned_job_or_404", lambda _job_id, _request: store.get(_job_id))

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/assets/from-library",
        json={"asset_file_id": "f" * 32, "target": "bgm", "base_revision": 0},
    )

    assert response.status_code == 200
    assert response.json()["asset"]["type"] == "bgm"


def test_successful_generation_captures_reserved_credits(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"classroom_topic": "课堂"}, {"type": "sso", "user_id": "user-1"})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(f"/jobs/{job['id']}/run", json={"background": False})

    assert response.status_code == 200
    assert ("capture", "b" * 32) in credits.calls
    assert not any(name == "release" for name, _ in credits.calls)


def test_failed_generation_releases_reserved_credits(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"classroom_topic": "课堂"}, {"type": "sso", "user_id": "user-1"})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store, fail=True))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(f"/jobs/{job['id']}/run", json={"background": False})

    assert response.status_code == 422
    assert ("release", "b" * 32) in credits.calls
    assert not any(name == "capture" for name, _ in credits.calls)


def test_invite_generation_runs_without_credit_calls(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"classroom_topic": "邀请码课堂"}, {"type": "invite", "invite_hash": "0" * 64})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _invite_user)
    monkeypatch.setattr(backend_app, "identity_from_request", _invite_identity)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(f"/jobs/{job['id']}/run", json={"background": False})

    assert response.status_code == 200
    assert credits.calls == []


def test_invite_image_regeneration_runs_without_credit_calls(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {}, {"type": "invite", "invite_hash": "0" * 64})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _invite_user)
    monkeypatch.setattr(backend_app, "identity_from_request", _invite_identity)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/assets/regenerate",
        json={"filename": "figure_role", "background": False},
    )

    assert response.status_code == 200
    assert credits.calls == []


def test_invite_tts_preview_runs_without_credit_calls(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"generate_tts": True}, {"type": "invite", "invite_hash": "0" * 64})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _invite_user)
    monkeypatch.setattr(backend_app, "identity_from_request", _invite_identity)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/voices/preview",
        json={"speaker": "角色A", "voice": "Cherry"},
    )

    assert response.status_code == 200
    assert credits.calls == []


def test_single_image_regeneration_has_its_own_metered_reservation(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {}, {"type": "sso", "user_id": "user-1"})
    job_dir = store.job_dir(job["id"])
    (job_dir / "assets_manifest.json").write_text(json.dumps({"images": [{"filename": "figure_role", "subdir": "figure"}]}), encoding="utf-8")
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)
    monkeypatch.setattr(backend_app, "_get_owned_job_or_404", lambda job_id, _request: store.get(job_id))

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/assets/regenerate",
        json={"filename": "figure_role", "prompt": "new", "background": False},
    )

    assert response.status_code == 200
    reservation = next(call[1] for call in credits.calls if call[0] == "reserve")
    assert reservation["pricing_snapshot"]["plan"] == "image-regenerate-v1"
    assert reservation["units"] == 10
    assert ("capture", "b" * 32) in credits.calls


def test_failed_single_image_regeneration_releases_credits(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {}, {"type": "sso", "user_id": "user-1"})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store, fail=True))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/assets/regenerate",
        json={"filename": "figure_role", "background": False},
    )

    assert response.status_code == 422
    assert ("release", "b" * 32) in credits.calls


def test_tts_preview_regeneration_has_its_own_metered_reservation(monkeypatch, tmp_path: Path):
    credits = FakeCredits()
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"generate_tts": True}, {"type": "sso", "user_id": "user-1"})
    monkeypatch.setattr(backend_app, "store", store)
    monkeypatch.setattr(backend_app, "pipeline", FakePipeline(store))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_credit_service", lambda: credits)
    monkeypatch.setattr(backend_app, "_get_owned_job_or_404", lambda job_id, _request: store.get(job_id))

    response = TestClient(backend_app.app).post(
        f"/jobs/{job['id']}/voices/preview",
        json={"speaker": "角色A", "voice": "Cherry"},
    )

    assert response.status_code == 200
    reservation = next(call[1] for call in credits.calls if call[0] == "reserve")
    assert reservation["pricing_snapshot"]["plan"] == "tts-preview-v1"
    assert reservation["units"] == 30
    assert ("capture", "b" * 32) in credits.calls


def test_asset_favorite_routes_use_authenticated_user(monkeypatch):
    calls = []
    library = FakeAssetLibrary()
    library.set_favorite = lambda user, asset, favorite: calls.append((user, asset, favorite))
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)
    client = TestClient(backend_app.app)
    asset = "a" * 32
    assert client.put(f"/assets/{asset}/favorite").json() == {"favorite": True}
    assert client.delete(f"/assets/{asset}/favorite").json() == {"favorite": False}
    assert calls == [("user-1", asset, True), ("user-1", asset, False)]
    assert client.put("/assets/invalid/favorite").status_code == 422
    monkeypatch.setattr(backend_app, "user_from_request", _invite_user)
    assert client.put(f"/assets/{asset}/favorite").status_code == 403


def test_asset_collection_filter(monkeypatch):
    library = FakeAssetLibrary()
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)
    client = TestClient(backend_app.app)
    assert client.get("/assets?collection=favorites").status_code == 200
    assert library.list_calls[-1]["collection"] == "favorites"
    assert client.get("/assets?collection=invalid").status_code == 422


def test_asset_search_pagination_uses_lookahead(monkeypatch):
    library = FakeAssetLibrary()
    rows = [{"id": str(i)} for i in range(13)]
    def list_page(user_id, **options):
        library.list_calls.append(options)
        return rows
    library.list_assets = list_page
    monkeypatch.setattr(backend_app, "user_from_request", _authenticated_user)
    monkeypatch.setattr(backend_app, "get_asset_library", lambda: library)
    client = TestClient(backend_app.app)
    response = client.get("/assets?page=2&page_size=12&search=courtyard&source_type=GENERATED")
    assert response.status_code == 200
    assert response.json() == {"assets": rows[:12], "page": 2, "has_more": True}
    assert library.list_calls[-1]["offset"] == 12
    assert library.list_calls[-1]["search"] == "courtyard"
    assert library.list_calls[-1]["limit"] == 13
    assert library.list_calls[-1]["original_only"] is True
    rows.clear()
    assert client.get("/assets?page=1").json()["has_more"] is False
    assert client.get("/assets?page=0").status_code == 422
    assert client.get("/assets?page=1&page_size=100").status_code == 422
