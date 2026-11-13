from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
import asyncio

import pytest
from PIL import Image
from starlette.datastructures import UploadFile

from webgal_backend.title_cover import fill_empty_title_image, local_title_cover, set_title_image, title_image
from webgal_backend.storage import JobStore


def game(tmp_path, value=""):
    root = tmp_path / "public/game"
    (root / "background").mkdir(parents=True)
    (root / "config.txt").write_text(f"Game_name:test;\nTitle_img:{value};\nTitle_bgm:theme.mp3;\n", encoding="utf-8")
    return root


def test_empty_title_is_filled_when_image_arrives_later(tmp_path):
    root = game(tmp_path)
    fill_empty_title_image(root)
    assert title_image(root) == ""
    (root / "background/first.webp").write_bytes(b"image")
    fill_empty_title_image(root)
    assert title_image(root) == "first.webp"
    assert "Title_bgm:theme.mp3;" in (root / "config.txt").read_text()


def test_existing_title_is_never_replaced_even_if_missing(tmp_path):
    root = game(tmp_path, "chosen.webp")
    (root / "background/first.webp").write_bytes(b"image")
    fill_empty_title_image(root)
    assert title_image(root) == "chosen.webp"
    assert local_title_cover(root) is None


def test_cover_follows_title_instead_of_filename_preference(tmp_path):
    root = game(tmp_path, "chosen.webp")
    (root / "background/title_old.webp").write_bytes(b"old")
    (root / "background/chosen.webp").write_bytes(b"chosen")
    assert local_title_cover(root).name == "chosen.webp"
    set_title_image(root, "title_old.webp")
    assert local_title_cover(root).name == "title_old.webp"


@pytest.mark.parametrize("name", ["../outside.webp", ""])
def test_cover_does_not_guess_another_image(tmp_path, name):
    root = game(tmp_path, name)
    (root / "background/title_old.webp").write_bytes(b"old")
    assert local_title_cover(root) is None


def test_upload_cover_replaces_title_without_publishing_other_drafts(tmp_path, monkeypatch):
    import webgal_backend.app as api
    store = JobStore(tmp_path / "jobs")
    job = store.create("test")
    job_dir = store.job_dir(job["id"])
    root = job_dir / "public/game"
    (root / "config.txt").write_text("Title_img:;\n", encoding="utf-8")
    job.update(status="DONE", has_published_build=True)
    store.mark_draft_changed(job, "scenes")
    revision = job["draft_revision"]
    monkeypatch.setattr(api, "store", store)
    monkeypatch.setattr(api, "_get_owned_job_or_404", lambda *args: store.get(job["id"]))
    content = BytesIO()
    Image.new("RGB", (32, 18), "blue").save(content, "PNG")
    content.seek(0)
    result = asyncio.run(api.upload_asset(
        job["id"], Mock(), UploadFile(filename="cover.png", file=content),
        "image", "background", False, None, revision, True,
    ))
    assert title_image(root) == result["asset"]["filename"]
    assert local_title_cover(root).exists()
    assert result["job"]["dirty_scopes"] == ["scenes"]
    assert result["job"]["draft_revision"] == revision
    assert result["job"]["cover_revision"] == 1


def test_library_cover_uses_accessible_background(tmp_path, monkeypatch):
    import webgal_backend.app as api
    store = JobStore(tmp_path / "jobs")
    job = store.create("test")
    job_dir = store.job_dir(job["id"])
    root = job_dir / "public/game"
    (root / "config.txt").write_text("Title_img:;\n", encoding="utf-8")
    job.update(status="DONE", has_published_build=True)
    store.save(job)
    monkeypatch.setattr(api, "store", store)
    monkeypatch.setattr(api, "_asset_user_and_job", lambda *args: ({"id": "user"}, store.get(job["id"])))
    monkeypatch.setattr(api, "_get_owned_job_or_404", lambda *args: store.get(job["id"]))
    content = BytesIO()
    Image.new("RGB", (32, 18), "red").save(content, "PNG")
    library = Mock()
    library.download_accessible_file.return_value = ({
        "kind": "BACKGROUND", "variant": "original", "object_key": "image.png",
        "name": "chosen", "asset_id": "asset", "id": "a" * 32, "bucket": "test",
    }, content.getvalue())
    monkeypatch.setattr(api, "get_asset_library", lambda: library)
    result = api.use_personal_asset(job["id"], api.UseLibraryAssetRequest(
        asset_file_id="a" * 32, target="background", title_cover=True,
    ), Mock())
    library.download_accessible_file.assert_called_once_with("user", "a" * 32)
    assert title_image(root) == result["asset"]["filename"]
    assert local_title_cover(root).exists()


@pytest.mark.parametrize("existing", ["", "chosen.webp"])
def test_apply_edits_fills_only_empty_title(tmp_path, monkeypatch, existing):
    from webgal_backend.pipeline import WebGALPipeline
    store = JobStore(tmp_path / "jobs")
    job = store.create("test")
    job_dir = store.job_dir(job["id"])
    root = job_dir / "public/game"
    (root / "config.txt").write_text(f"Title_img:{existing};\n", encoding="utf-8")
    draft = job_dir / "draft/game/background/first.webp"
    draft.parent.mkdir(parents=True)
    draft.write_bytes(b"image")
    job.update(status="DONE", has_published_build=True)
    store.mark_draft_changed(job, "assets")
    pipeline = WebGALPipeline(store)
    for method in ("_publish_uploaded_assets_to_oss", "_ensure_runtime_image_assets", "run_validation", "_rewrite_runtime_asset_urls", "_publish_asset_version"):
        monkeypatch.setattr(pipeline, method, Mock())
    pipeline.apply_draft_changes(job)
    assert title_image(root) == (existing or "first.webp")
