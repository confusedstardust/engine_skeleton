from __future__ import annotations

import json

from credit_system.billing import Pricing, credits_for_usage, estimate_hold, measure, snapshot


def test_hold_changes_with_selected_capabilities():
    pricing = Pricing(text_hold=20, image_hold=50, tts_hold=30)
    assert estimate_hold({}, pricing)[0] == 20
    assert estimate_hold({"generate_assets": True}, pricing)[0] == 70
    assert estimate_hold({"generate_assets": True, "generate_tts": True}, pricing)[0] == 100


def test_measure_and_price_provider_usage_and_created_assets(tmp_path):
    job_dir = tmp_path / "job"
    before = snapshot(job_dir)
    traces = job_dir / "state" / "llm_traces"
    traces.mkdir(parents=True)
    (traces / "0001_plan.json").write_text(json.dumps({"usage": {"prompt_tokens": 120_000, "completion_tokens": 20_000, "prompt_tokens_details": {"cached_tokens": 20_000}}}), encoding="utf-8")
    image = job_dir / "public" / "game" / "background" / "bg.webp"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    (job_dir / "assets_manifest.json").write_text(json.dumps({"images": [{"subdir": "background", "filename": "bg"}]}), encoding="utf-8")
    vocal = job_dir / "public" / "game" / "vocal" / "line.wav"
    vocal.parent.mkdir(parents=True)
    vocal.write_bytes(b"audio")
    manifest = job_dir / "state" / "tts_manifest.json"
    manifest.write_text(json.dumps({"items": [{"filename": "line.wav", "text": "一二三四五", "status": "completed"}]}), encoding="utf-8")

    usage = measure(job_dir, before)
    units, detail = credits_for_usage(usage, Pricing())

    assert usage.input_tokens == 120_000
    assert usage.cached_input_tokens == 20_000
    assert usage.images == 1
    assert usage.tts_characters == 5
    assert units == 47  # 20 input + 16 output + 10 image + 1 TTS
    assert detail["charge_parts"] == {"text": 36, "images": 10, "tts": 1}
