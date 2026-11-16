import pytest
from decimal import Decimal

from webgal_backend.nar_metering_v2 import NormalizedUsage
from webgal_backend.nar_usage_store_v2 import ModelUsageEvent, safe_payload


def test_immutable_event_payload_excludes_sensitive_model_content():
    event = ModelUsageEvent(
        event_key="nar.turn1.intent.0", owner_user_id="owner-1",
        call_id="call-001", stage="intent_v2", provider="deepseek",
        turn_id="a" * 32, usage=NormalizedUsage(100, 20, 0, 5),
        billable_to_user=True, provider_cost_micro_usd=Decimal("0.023"),
    )
    data = safe_payload(event)
    assert data["input_uncached"] == 100
    assert data["provider_cost_micro_usd"] == "0.023"
    assert not any(k in data for k in ("prompt", "output_text", "api_key", "messages"))


def test_shadow_is_never_user_billable():
    with pytest.raises(ValueError, match="Shadow"):
        ModelUsageEvent("event.1", "owner", "call.1", "intent_shadow", "deepseek",
                        NormalizedUsage(0, 0, 0, 100), billable_to_user=True)


def test_invalid_ids_and_unknown_stage_fail_closed():
    with pytest.raises(ValueError):
        ModelUsageEvent("bad key with spaces", "owner", "call", "builder", "deepseek",
                        NormalizedUsage(100, 0, 0, 10))
    with pytest.raises(ValueError):
        ModelUsageEvent("event1", "owner", "call", "not-an-operation", "deepseek",
                        NormalizedUsage(100, 0, 0, 10))
