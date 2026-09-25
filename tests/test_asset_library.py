from pathlib import Path

from types import SimpleNamespace

from webgal_backend import asset_library as module
from webgal_backend import oss_storage
from webgal_backend.asset_library import AssetFileRecord, publish_public_oss_references, sync_generated_job_assets
from webgal_backend.oss_storage import asset_access_url, asset_object_key


def test_asset_object_key_separates_source_and_revision(monkeypatch):
    monkeypatch.setattr(oss_storage, "settings", SimpleNamespace(oss_prefix="private-assets"))
    key = asset_object_key(
        user_id="user01", source_type="GENERATED", asset_id="asset01",
        revision=3, file_id="file01", extension="WEBP",
    )
    assert key == "private-assets/users/user01/assets/generated/asset01/r3/file01.webp"


def test_generated_sync_prefers_draft_and_keeps_source_type(tmp_path: Path, monkeypatch):
    public = tmp_path / "public" / "game" / "background" / "room.webp"
    draft = tmp_path / "draft" / "game" / "background" / "room.webp"
    public.parent.mkdir(parents=True)
    draft.parent.mkdir(parents=True)
    public.write_bytes(b"published")
    draft.write_bytes(b"draft")
    job = {"id": "job01", "identity": {"type": "sso", "user_id": "user01"}}
    monkeypatch.setattr(module.asset_library, "enabled_for", lambda _job: True)
    captured = []

    def register_file(**kwargs):
        captured.append(kwargs)
        return AssetFileRecord("asset01", "file01", 1, "key", "url", "sha")

    monkeypatch.setattr(module.asset_library, "register_file", register_file)
    result = sync_generated_job_assets(job, tmp_path)
    assert len(result) == 1
    assert captured[0]["path"] == draft
    assert captured[0]["source_type"] == "GENERATED"
    assert captured[0]["source_key"] == "background/room.webp"


def test_public_access_url_is_stable_and_unsigned(monkeypatch):
    monkeypatch.setattr(oss_storage, "settings", SimpleNamespace(
        oss_access_mode="public", oss_bucket="assets", oss_endpoint="https://oss-cn-hangzhou.aliyuncs.com",
    ))
    assert asset_access_url("games/bg.webp") == "https://assets.oss-cn-hangzhou.aliyuncs.com/games/bg.webp"


def test_publish_rewrites_webgal_asset_references_to_public_oss(tmp_path: Path, monkeypatch):
    scene = tmp_path / "public" / "game" / "scene" / "start.txt"
    scene.parent.mkdir(parents=True)
    scene.write_text(
        "changeBg:room.webp -next;\n"
        "changeFigure:teacher.webp -left -next;\n"
        "老师:你好。 -vocal=hello.wav;\n"
        "bgm:opening.mp3;\n"
        "playEffect:./game/vocal/bell.mp3 -next;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "settings", SimpleNamespace(oss_access_mode="public"))
    monkeypatch.setattr(module.asset_library, "enabled_for", lambda _job: True)
    records = []
    for index, logical in enumerate((
        "background/room.webp", "figure/teacher.webp", "vocal/hello.wav", "bgm/opening.mp3", "vocal/bell.mp3",
    )):
        records.append({
            "logical_path": logical, "asset_id": f"a{index}", "file_id": f"f{index}", "revision": 1,
            "object_key": f"objects/{logical}", "url": f"https://assets.example/{logical}",
        })
    monkeypatch.setattr(module, "sync_generated_job_assets", lambda _job, _dir: records)
    manifest = publish_public_oss_references({"id": "job01"}, tmp_path)
    text = scene.read_text(encoding="utf-8")
    assert "changeBg:https://assets.example/background/room.webp" in text
    assert "changeFigure:https://assets.example/figure/teacher.webp" in text
    assert "-vocal=https://assets.example/vocal/hello.wav" in text
    assert "bgm:https://assets.example/bgm/opening.mp3" in text
    assert "playEffect:https://assets.example/vocal/bell.mp3" in text
    assert manifest and manifest["rewritten_scenes"] == ["start.txt"]
