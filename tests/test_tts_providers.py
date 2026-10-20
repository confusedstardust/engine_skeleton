from __future__ import annotations

import base64
import copy
import json
import wave
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from webgal_backend import tts, tts_doubao
from webgal_backend.storage import JobStore, read_json, write_json
from webgal_backend.tts_config import default_tts_profile, job_tts_profile, load_tts_profiles, validate_profile
from webgal_backend.tts_pipeline import (
    available_tts_voices, build_tts_manifest, build_tts_voice_review,
    generate_tts_audio, generate_tts_voice_previews, select_tts_review_voice,
    selected_character_voices,
)


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    document = json.loads((Path(__file__).parents[1] / "webgal_backend/tts_profiles.json").read_text(encoding="utf-8"))
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setenv("WEBGAL_TTS_PROFILES", str(path))
    monkeypatch.setenv("DOUBAO_TTS_API_KEY", "secret-do-not-log")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-qwen-key")
    return path, document


def set_catalog(catalog, **changes):
    path, document = catalog
    document.update(changes)
    path.write_text(json.dumps(document), encoding="utf-8")


def stream_response(messages, status=200):
    return httpx.Response(status, headers={"X-Tt-Logid": "test-log"}, content="\n".join(json.dumps(m) for m in messages))


def mock_doubao(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(tts_doubao.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def good_response():
    return stream_response([
        {"code": 0, "data": base64.b64encode(b"\x01\x00\x02\x00").decode()},
        {"code": 0, "sentence": {"text": "hello"}},
        {"code": 0, "data": base64.b64encode(b"\x03\x00\x04\x00").decode()},
        {"code": 20000000, "data": None, "usage": {"text_words": 5}},
    ])


def test_doubao_stream_wav_metadata_and_cache(catalog, tmp_path, monkeypatch):
    captured = []
    def respond(request):
        captured.append(request)
        return good_response()
    mock_doubao(monkeypatch, respond)
    profile = default_tts_profile("doubao-tts2")
    options = replace(tts.options_from_profile(profile, instructions="自然清晰"), speech_rate=1.2, volume=60, pitch_rate=1.1)
    output = tmp_path / "voice.wav"
    tts.synthesize_text_to_file("hello", output, options=options)
    with wave.open(str(output)) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) == (24000, 1, 2)
        assert audio.readframes(10) == b"\x01\x00\x02\x00\x03\x00\x04\x00"
    request = captured[0]
    assert request.headers["X-Api-Key"] == "secret-do-not-log"
    assert request.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert request.headers["X-Api-Request-Id"]
    params = json.loads(request.content)["req_params"]
    assert "model" not in params
    assert params["speaker"] == profile["default_voice"]
    assert params["audio_params"] == {"format": "pcm", "sample_rate": 24000, "speech_rate": 20, "loudness_rate": 20}
    additions = json.loads(params["additions"])
    assert additions["context_texts"] == ["自然清晰"]
    assert "pitch" in additions["post_process"]
    metadata_text = output.with_suffix(".wav.tts.json").read_text()
    assert "secret-do-not-log" not in metadata_text
    assert json.loads(metadata_text)["usage"] == {"text_words": 5}
    assert tts.cached_synthesis(output, "hello", options)
    assert not tts.cached_synthesis(output, "changed", options)
    assert not tts.cached_synthesis(output, "hello", replace(options, pitch_rate=1.0))
    assert not tts.cached_synthesis(output, "hello", replace(options, provider="qwen"))
    output.write_bytes(b"corrupted")
    assert not tts.cached_synthesis(output, "hello", options)


@pytest.mark.parametrize("response", [
    lambda: stream_response([], 429),
    lambda: stream_response([{"code": 45000000, "message": "speaker permission denied"}]),
    lambda: stream_response([{"code": 0, "data": "!!!!"}, {"code": 20000000}]),
    lambda: stream_response([{"code": 0, "data": "AAAA"}]),
    lambda: stream_response([{"code": 20000000}]),
    lambda: stream_response([{"code": 0, "data": "AA=="}, {"code": 20000000}]),
    lambda: httpx.Response(200, content='{"code":0,'),
])
def test_incomplete_or_failed_audio_never_replaces_existing_file(catalog, tmp_path, monkeypatch, response):
    mock_doubao(monkeypatch, lambda _: response())
    output = tmp_path / "existing.wav"
    output.write_bytes(b"previous audio")
    with pytest.raises(tts.TTSSynthesisError):
        tts.synthesize_text_to_file("hello", output, options=tts.options_from_profile(default_tts_profile("doubao-tts2")))
    assert output.read_bytes() == b"previous audio"
    assert not output.with_suffix(".wav.tts.json").exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_transport_failure_and_missing_key_are_explicit(catalog, tmp_path, monkeypatch):
    def offline(request):
        raise httpx.ReadTimeout("network unavailable", request=request)
    mock_doubao(monkeypatch, offline)
    options = tts.options_from_profile(default_tts_profile("doubao-tts2"))
    with pytest.raises(tts.TTSSynthesisError, match="ReadTimeout"):
        tts.synthesize_text_to_file("hello", tmp_path / "out.wav", options=options)
    monkeypatch.delenv("DOUBAO_TTS_API_KEY")
    with pytest.raises(tts.TTSConfigError, match="DOUBAO_TTS_API_KEY"):
        tts.synthesize_text_to_file("hello", tmp_path / "out.wav", options=options)


def test_qwen_sdk_contract_is_preserved(catalog, tmp_path, monkeypatch):
    seen = {}
    class FakeQwen:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.callback = kwargs["callback"]
        def connect(self): pass
        def update_session(self, **kwargs): seen["session"] = kwargs
        def append_text(self, text): seen["text"] = text
        def commit(self):
            self.callback.on_event({"type": "response.audio.delta", "delta": "AAAAAA=="})
            self.callback.on_event({"type": "response.done"})
        def finish(self): seen["finished"] = True
    monkeypatch.setattr(tts, "_IMPORT_ERROR", None)
    monkeypatch.setattr(tts, "dashscope", SimpleNamespace())
    monkeypatch.setattr(tts, "QwenTtsRealtime", FakeQwen)
    monkeypatch.setattr(tts, "AudioFormat", SimpleNamespace(PCM_24000HZ_MONO_16BIT="pcm"))
    options = tts.options_from_profile(default_tts_profile("qwen-realtime"), instructions="warm")
    output = tmp_path / "qwen.wav"
    tts.synthesize_text_to_file("hello", output, options=options)
    assert seen["model"] == "qwen3-tts-flash-realtime"
    assert seen["session"]["voice"] == "Cherry"
    assert seen["session"]["instructions"] == "warm"
    assert seen["session"]["response_format"] == "pcm"
    assert seen["finished"] and output.exists()


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(provider="unknown"),
    lambda p: p.update(default_voice="not-a-voice"),
    lambda p: p["voices"].append(copy.deepcopy(p["voices"][0])),
    lambda p: p.update(auth={"api_key": "secret"}),
    lambda p: p.update(api_key="secret"),
    lambda p: p["options"].update(max_workers=0),
    lambda p: p["options"].update(speech_rate=float("nan")),
    lambda p: p.update(endpoint="https://user:secret@example.com/tts"),
    lambda p: p["options"].update(resource_id="seed-icl-2.0"),
])
def test_bad_profiles_fail_before_any_requests(catalog, mutate):
    profile = default_tts_profile("doubao-tts2")
    mutate(profile)
    with pytest.raises(tts.TTSConfigError):
        validate_profile(profile)


def test_catalog_rejects_duplicate_ids_and_disabled_default(catalog):
    path, doc = catalog
    doc["profiles"].append(copy.deepcopy(doc["profiles"][0]))
    path.write_text(json.dumps(doc))
    with pytest.raises(tts.TTSConfigError, match="Duplicate"):
        load_tts_profiles()
    doc["profiles"].pop()
    next(p for p in doc["profiles"] if p["id"] == doc["default_profile"])["enabled"] = False
    path.write_text(json.dumps(doc))
    with pytest.raises(tts.TTSConfigError, match="enabled"):
        load_tts_profiles()


def test_new_tasks_snapshot_default_and_legacy_tasks_keep_qwen(catalog, tmp_path):
    set_catalog(catalog, default_profile="doubao-tts2")
    store = JobStore(tmp_path / "jobs")
    job = store.create("original source", {"voice_enabled": True})
    job_dir = store.job_dir(job["id"])
    assert job_tts_profile(job_dir)["provider"] == "doubao"
    assert job["options"] == {"voice_enabled": True}  # Billing identity is unchanged.
    set_catalog(catalog, default_profile="qwen-realtime")
    assert job_tts_profile(job_dir)["provider"] == "doubao"
    set_catalog(catalog, default_profile="doubao-tts2")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "job.json").write_text("{}")
    assert job_tts_profile(legacy)["provider"] == "qwen"


def test_same_pipeline_drives_preview_selection_and_full_doubao_audio(catalog, tmp_path, monkeypatch):
    set_catalog(catalog, default_profile="doubao-tts2")
    calls = []
    def respond(request):
        calls.append(json.loads(request.content)["req_params"])
        return good_response()
    mock_doubao(monkeypatch, respond)
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"voice_enabled": True})
    job_dir = store.job_dir(job["id"])
    write_json(job_dir / "state/narrative_plan.json", {"characters": [{"id": "hero", "name": "Hero", "gender": "female"}]})
    (job_dir / "state/game_design_webgal.txt").write_text("Scene:start.txt\nHero: hello;\n", encoding="utf-8")
    review = build_tts_voice_review(job_dir, {})
    assert {v["name"] for v in review["available_voices"]} == {v["id"] for v in default_tts_profile()["voices"]}
    generate_tts_voice_previews(job_dir, review)
    assert review["characters"][0]["status"] == "completed"
    generate_tts_voice_previews(job_dir, review)
    assert review["characters"][0]["status"] == "skipped_existing" and len(calls) == 1
    female = [v for v in available_tts_voices(review["tts_profile"]) if v["gender"] == "female"]
    select_tts_review_voice(review, "Hero", female[1]["name"])
    generate_tts_voice_previews(job_dir, review)
    assert calls[-1]["speaker"] == female[1]["name"]
    male = next(v for v in review["available_voices"] if v["gender"] == "male")
    with pytest.raises(ValueError, match="gender"):
        select_tts_review_voice(review, "Hero", male["name"])
    # Changing the system default must not change a task's provider or voice list.
    set_catalog(catalog, default_profile="qwen-realtime")
    manifest = build_tts_manifest(job_dir, selected_character_voices(review))
    generate_tts_audio(job_dir, manifest, enabled=True)
    assert manifest["tts_profile"]["provider"] == "doubao"
    assert all(i["status"] == "completed" for i in manifest["items"])
    assert calls[-1]["speaker"] == female[1]["name"]
    audio = job_dir / manifest["vocal_dir"] / manifest["items"][0]["filename"]
    assert audio.exists() and read_json(audio.with_suffix(".wav.tts.json"))["provider"] == "doubao"


def test_http_voice_preview_contract_exposes_catalog_and_playable_wav(catalog, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from webgal_backend import app as backend
    from webgal_backend.pipeline import WebGALPipeline

    set_catalog(catalog, default_profile="doubao-tts2")
    mock_doubao(monkeypatch, lambda _: good_response())
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"voice_enabled": True})
    job_dir = store.job_dir(job["id"])
    write_json(job_dir / "state/narrative_plan.json", {"characters": [{"id": "hero", "name": "Hero", "gender": "female"}]})
    (job_dir / "state/game_design_webgal.txt").write_text("Scene:start.txt\nHero: hello;\n", encoding="utf-8")
    review = build_tts_voice_review(job_dir, {})
    write_json(job_dir / "state/tts_voice_review.json", review)
    monkeypatch.setattr(backend, "store", store)
    monkeypatch.setattr(backend, "pipeline", WebGALPipeline(store=store))
    monkeypatch.setattr(backend, "_credit_user_and_job", lambda *_: ({"id": "test-user"}, store.get(job["id"])))
    monkeypatch.setattr(backend, "_get_owned_job_or_404", lambda *_: store.get(job["id"]))
    monkeypatch.setattr(backend, "_reserve_resource_credits", lambda *_, **__: None)
    client = TestClient(backend.app)
    voice = review["characters"][0]["voice"]
    result = client.post(f"/jobs/{job['id']}/voices/preview", json={"speaker": "Hero", "voice": voice})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["voice"]["status"] == "completed"
    assert data["voices"][0]["preview_exists"]
    assert "/game/vocal_preview/" in data["voices"][0]["preview_url"]
    assert {v["name"] for v in data["available_voices"]} == {v["id"] for v in review["tts_profile"]["voices"]}
    assert "tts_profile" not in data  # Credentials/configuration do not travel to the UI.
    assert "DOUBAO_TTS_API_KEY" not in result.text


def test_stream_decoder_handles_network_fragmentation_and_sse_frames(catalog, tmp_path, monkeypatch):
    payload = ('event: 352\ndata: {"code":0,"data":"AAAAAA=="}\n\n'
               'event: 152\ndata: {"code":20000000,"usage":{"text_words":5}}\n\n').encode()
    class Fragmented(httpx.SyncByteStream):
        def __iter__(self):
            for offset in range(0, len(payload), 3):
                yield payload[offset:offset + 3]
    mock_doubao(monkeypatch, lambda _: httpx.Response(200, stream=Fragmented()))
    output = tmp_path / "stream.wav"
    tts.synthesize_text_to_file("hello", output, options=tts.options_from_profile(default_tts_profile("doubao-tts2")))
    assert output.exists()


def test_retry_preview_keeps_old_wav_when_new_request_fails(catalog, tmp_path, monkeypatch):
    from webgal_backend.pipeline import WebGALPipeline, PipelineError
    set_catalog(catalog, default_profile="doubao-tts2")
    mock_doubao(monkeypatch, lambda _: good_response())
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"voice_enabled": True})
    job_dir = store.job_dir(job["id"])
    write_json(job_dir / "state/narrative_plan.json", {"characters": [{"id": "hero", "name": "Hero", "gender": "female"}]})
    (job_dir / "state/game_design_webgal.txt").write_text("Scene:start.txt\nHero: hello;\n", encoding="utf-8")
    review = generate_tts_voice_previews(job_dir, build_tts_voice_review(job_dir, {}))
    write_json(job_dir / "state/tts_voice_review.json", review)
    item = review["characters"][0]
    output = job_dir / review["vocal_dir"] / item["filename"]
    original = output.read_bytes()
    # Reuse the installed transport with a business failure instead of patching Client twice.
    monkeypatch.setattr(tts_doubao, "synthesize_pcm", lambda *_: (_ for _ in ()).throw(tts.TTSSynthesisError("permission denied")))
    with pytest.raises(PipelineError, match="permission denied"):
        WebGALPipeline(store=store).regenerate_tts_preview(job, "Hero", item["voice"])
    assert output.read_bytes() == original


def test_imported_voice_descriptions_reach_llm_and_review(catalog, tmp_path):
    from webgal_backend.pipeline import WebGALPipeline
    from webgal_backend.tts_config import tts_settings

    set_catalog(catalog, default_profile="doubao-tts2")
    store = JobStore(tmp_path / "jobs")
    job = store.create("lesson", {"voice_enabled": True, "text_model": "deepseek"})
    job_dir = store.job_dir(job["id"])
    profile = job_tts_profile(job_dir)
    selected = "zh_male_qingshuangnanda_uranus_bigtts"
    assert selected in {voice["id"] for voice in profile["voices"]}
    plan = {"characters": [{"id": "hero", "name": "Hero", "gender": "male", "personality": "阳光开朗的大学生"}]}
    write_json(job_dir / "state/narrative_plan.json", plan)
    script = "Scene:start.txt\nHero: 这是一句用于验证角色试听选声线的普通对白;\n"
    captured = []

    class AssignmentLLM:
        def call_text(self, stage, system, prompt, **kwargs):
            captured.append((stage, prompt))
            return json.dumps({"Hero": [selected, "清爽自然、年轻阳光"]})

        def parse_json_text(self, text, stage):
            return json.loads(text)

    def factory(**kwargs):
        assert kwargs["provider"] == "deepseek"
        return AssignmentLLM()

    assigned = WebGALPipeline(store=store, llm_factory=factory)._assign_tts_voices(
        job, job_dir, plan, tts_settings(profile),
    )
    assert captured[0][0] == "tts_voice_assignment"
    for voice in profile["voices"]:
        assert voice["id"] in captured[0][1]
        assert voice["description"] in captured[0][1]
    review = build_tts_voice_review(job_dir, assigned, script_text=script)
    assert review["characters"][0]["voice"] == selected
    assert review["characters"][0]["tone"] == "清爽自然、年轻阳光"
    # A manual choice is retained if the review is rebuilt with another LLM suggestion.
    select_tts_review_voice(review, "Hero", "zh_male_taocheng_uranus_bigtts")
    refreshed = build_tts_voice_review(job_dir, assigned, existing_review=review, script_text=script)
    assert refreshed["characters"][0]["voice"] == "zh_male_taocheng_uranus_bigtts"


def test_catalog_expansion_does_not_rewrite_existing_task_snapshot(catalog, tmp_path):
    set_catalog(catalog, default_profile="doubao-tts2")
    store = JobStore(tmp_path / "jobs")
    existing = store.create("old lesson", {"voice_enabled": True})
    existing_dir = store.job_dir(existing["id"])
    original = job_tts_profile(existing_dir)
    new_voice = {
        "id": "new-authorized-voice", "label": "New voice", "gender": "female",
        "description": "A new catalog entry for a future task",
    }
    document = catalog[1]
    next(p for p in document["profiles"] if p["id"] == "doubao-tts2")["voices"].append(new_voice)
    set_catalog(catalog)
    assert job_tts_profile(existing_dir) == original
    created = store.create("new lesson", {"voice_enabled": True})
    assert new_voice in job_tts_profile(store.job_dir(created["id"]))["voices"]
