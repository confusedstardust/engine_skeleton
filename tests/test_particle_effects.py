from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from webgal_backend.particle_effects import ParticleEffectError, save_scene_assignment, validate_sprite_sheet
from webgal_backend.pipeline import WebGALPipeline
from webgal_backend.storage import JobStore, read_json


def test_bundled_effect_strips_match_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[1] / "public" / "game" / "tex" / "effects"
    for name in ("meteor.png", "wind.png", "lightning.png"):
        assert validate_sprite_sheet(root / name) == (128, 10)


def test_effect_sheet_rejects_opaque_or_wrong_sized_png(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.png"
    Image.new("RGB", (1280, 128), "black").save(invalid)
    with pytest.raises(ParticleEffectError, match="transparency"):
        validate_sprite_sheet(invalid)


def test_save_scene_assignment_clamps_unsafe_values(tmp_path: Path) -> None:
    saved = save_scene_assignment(tmp_path, "start.txt", {
        "effect_id": "meteor",
        "count": 9999,
        "speed": -20,
        "scale": 8,
        "opacity": 4,
        "layer": "invalid",
    })
    assert saved["count"] == 300
    assert saved["speed"] == 0.2
    assert saved["scale"] == 2.0
    assert saved["opacity"] == 1.0
    assert saved["layer"] == "foreground"


def test_pipeline_updates_only_managed_particle_command(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs")
    job = store.create("effect test")
    job_dir = store.job_dir(job["id"])
    scene_dir = job_dir / "public" / "game" / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene = scene_dir / "start.txt"
    scene.write_text("pixiPerform:particle -id=wind;\nbgm:test.mp3;\n角色:台词;\n", encoding="utf-8")
    save_scene_assignment(job_dir, "start.txt", {"effect_id": "meteor", "count": 12, "speed": 7})

    WebGALPipeline(store)._apply_particle_effect_changes(job_dir, {"start.txt"})

    text = scene.read_text(encoding="utf-8")
    assert text.count("pixiPerform:particle ") == 1
    assert "-id=meteor" in text
    assert "-count=12" in text
    assert "bgm:test.mp3;\n角色:台词;" in text
    config = read_json(job_dir / "public" / "game" / "effects.json")
    assert set(config["effects"]) >= {"meteor", "wind", "lightning", "rain", "snow", "cherry_blossoms"}
    assert config["effects"]["rain"]["sheet"] == {"frame_width": 128, "frame_height": 640, "frame_count": 5, "columns": 5}
    assert config["effects"]["snow"]["sheet"] == {"frame_width": 128, "frame_height": 128, "frame_count": 10, "columns": 10}
    assert config["effects"]["cherry_blossoms"]["sheet"] == {"frame_width": 529, "frame_height": 678, "frame_count": 1, "columns": 1}
    assert (job_dir / "public" / "game" / "tex" / "effects" / "rain.png").exists()
    assert (job_dir / "public" / "game" / "tex" / "effects" / "snow.png").exists()
    assert (job_dir / "public" / "game" / "tex" / "effects" / "cherryBlossoms.webp").exists()
