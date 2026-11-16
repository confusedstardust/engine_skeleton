"""Call-level metering invariants: no prompt capture or duplicate model events."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.metering import (
    ModelCallRecorder, active_intent_meter, record_direct_intent_response,
    sanitized_usage, provider_from_url,
)
from app.public_brief import stream_public_brief


def make_recorder(stage="builder"):
    return ModelCallRecorder(stage=stage, provider="deepseek", requested_model="deepseek-chat")


def test_sanitized_usage_never_includes_model_content():
    data = sanitized_usage({
        "input_tokens": 120,
        "output_tokens": 22,
        "input_token_details": {"cache_read": 45, "user_prompt": "private"},
        "prompt": "private", "api_key": "secret", "reasoning_text": "secret",
    })
    assert data == {
        "input_tokens": 120, "output_tokens": 22,
        "input_token_details": {"cache_read": 45},
    }


def test_callback_event_is_deduplicated_by_model_run_id():
    meter = make_recorder()
    message = SimpleNamespace(usage_metadata={
        "input_tokens": 500, "output_tokens": 100, "input_token_details": {"cache_read": 400},
    })
    response = SimpleNamespace(
        generations=[[SimpleNamespace(message=message)]],
        llm_output={"model_name": "deepseek-chat"},
    )
    run_id = uuid4()
    asyncio.run(meter.on_llm_end(response, run_id=run_id))
    asyncio.run(meter.on_llm_end(response, run_id=run_id))
    asyncio.run(meter.on_llm_error(Exception("sensitive prompt"), run_id=run_id))
    assert len(meter.events) == 1
    event = meter.events[0]
    assert event["call_id"] == str(run_id)
    assert event["usage"]["input_token_details"]["cache_read"] == 400
    assert event["usage_status"] == "REPORTED"
    assert "prompt" not in str(event)
    assert "sensitive" not in str(event)


def test_unknown_callback_is_marked_unknown_not_free():
    meter = make_recorder()
    asyncio.run(meter.on_llm_error(RuntimeError("sensitive"), run_id=uuid4()))
    assert meter.events[0]["usage_status"] == "UNKNOWN"
    assert meter.events[0]["usage"] is None


def test_direct_intent_records_real_model_usage_without_changing_response():
    meter = make_recorder("intent_v2")
    token = active_intent_meter.set(meter)
    try:
        response = SimpleNamespace(content='{"mode":"html"}', usage_metadata={
            "input_tokens": 900, "output_tokens": 20,
        })
        record_direct_intent_response(response)
    finally:
        active_intent_meter.reset(token)
    assert response.content == '{"mode":"html"}'
    assert meter.events[0]["stage"] == "intent_v2"
    assert meter.events[0]["usage"]["input_tokens"] == 900


def test_public_brief_consumes_final_usage_chunk_after_display_limit():
    meter = make_recorder()
    state = {}
    class FakeModel:
        async def astream(self, _messages):
            yield SimpleNamespace(content="学习" * 700)
            yield SimpleNamespace(content="", usage_metadata={
                "input_tokens": 300, "output_tokens": 30,
            })
    result = asyncio.run(stream_public_brief(None, "学习", state, model=FakeModel(), recorder=meter))
    assert len(result) == 700
    assert len(meter.events) == 1
    assert meter.events[0]["stage"] == "public_brief"
    assert meter.events[0]["usage"]["output_tokens"] == 30


def test_provider_selector_does_not_expose_urls():
    assert provider_from_url("https://api.deepseek.com") == "deepseek"
    assert provider_from_url("https://api.other.com") == "openai"
