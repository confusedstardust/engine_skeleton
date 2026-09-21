from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import pytest

from webgal_backend.config import Settings, settings
from webgal_backend.llm import LLMError, OpenAIFunctionClient
from webgal_backend.pipeline import WebGALPipeline


def test_kimi_settings_use_official_defaults(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-test-key")
    monkeypatch.delenv("KIMI_BASE_URL", raising=False)
    monkeypatch.delenv("KIMI_MODEL", raising=False)
    with patch("webgal_backend.config.load_dotenv"):
        configured = Settings.from_env()
    assert configured.kimi_api_key == "moonshot-test-key"
    assert configured.kimi_base_url == "https://api.moonshot.cn/v1"
    assert configured.kimi_model == "kimi-k2.7-code-highspeed"


def test_kimi_client_uses_chat_api_without_forbidden_sampling_or_thinking(monkeypatch, tmp_path: Path):
    with patch("webgal_backend.llm.settings", replace(settings, kimi_api_key="moonshot-test-key")):
        client = OpenAIFunctionClient(trace_dir=tmp_path, provider="kimi")
    captured = {}

    def request(path, payload, _trace_name):
        captured.update(path=path, payload=payload)
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}', "reasoning_content": "..."}}]}

    monkeypatch.setattr(client, "_request", request)
    assert client.call_text("test", "system", "user", thinking="disabled") == '{"ok": true}'
    assert captured["path"] == "/chat/completions"
    assert captured["payload"]["model"] == "kimi-k2.7-code-highspeed"
    assert "thinking" not in captured["payload"]
    assert "temperature" not in captured["payload"]
    assert "reasoning_effort" not in captured["payload"]


def test_kimi_structured_artifacts_use_validated_json_text_instead_of_tool_choice():
    class FakeKimi:
        provider = "kimi"

        def call_text(self, *_args, **_kwargs):
            return '{"artifact": {"value": 1}}'

        def parse_json_text(self, text, _trace_name):
            import json
            return json.loads(text)

        def call_function(self, *_args, **_kwargs):
            raise AssertionError("Kimi K2.7 Code must not use required/named tool choice")

    parsed, _raw = WebGALPipeline()._call_structured_llm(
        FakeKimi(), "emit_game_design", "artifact", "system", "prompt"
    )
    assert parsed == {"artifact": {"value": 1}}


def test_unknown_text_provider_is_rejected():
    with pytest.raises(LLMError, match="unsupported text model provider"):
        OpenAIFunctionClient(provider="typo")


def test_frontend_exposes_exact_kimi_model_and_provider_labels():
    home = (Path(__file__).resolve().parents[1] / "forge_frontend_next/app/page.tsx").read_text(encoding="utf-8")
    job = (Path(__file__).resolve().parents[1] / "forge_frontend_next/app/jobs/[jobId]/page.tsx").read_text(encoding="utf-8")
    assert 'type TextModel = "deepseek" | "mimo" | "kimi"' in home
    assert 'model: "kimi-k2.7-code-highspeed"' in home
    assert 'provider: "deepseek" | "mimo" | "kimi"' in job
