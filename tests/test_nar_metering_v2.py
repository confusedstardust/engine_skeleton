import pytest
from decimal import Decimal
from webgal_backend.nar_metering_v2 import (
    UserPriceSnapshot, NormalizedUsage, normalize_provider_usage,
    raw_credit_amount, task_credit_charge, provider_cost_micro_usd,
)


def test_screenshot_regression_once_per_task():
    usage = normalize_provider_usage({
        "input_tokens": 145896, "output_tokens": 13834,
        "input_token_details": {"cache_read": 141696},
    })
    assert usage.input_uncached == 4200
    assert usage.cache_read_input == 141696
    assert task_credit_charge([(usage, True)], UserPriceSnapshot()) == 12


def test_intent_and_builder_are_not_rounded_individually():
    small = NormalizedUsage(1000, 0, 0, 100)
    builder = NormalizedUsage(1000, 0, 0, 100)
    assert raw_credit_amount(small, UserPriceSnapshot()) == Decimal("0.28")
    assert task_credit_charge([(small, True), (builder, True)], UserPriceSnapshot()) == 1
    assert task_credit_charge([(small, False), (builder, True)], UserPriceSnapshot()) == 1


def test_shadow_never_adds_user_charge_even_if_large():
    shadow = NormalizedUsage(0, 0, 0, 100000)
    real = NormalizedUsage(5000, 0, 0, 1250)
    assert task_credit_charge([(shadow, False), (real, True)], UserPriceSnapshot()) == 2


def test_openai_cache_is_input_subset_and_reasoning_is_output_subset():
    data = normalize_provider_usage({
        "prompt_tokens": 100, "completion_tokens": 50,
        "prompt_tokens_details": {"cached_tokens": 80},
        "completion_tokens_details": {"reasoning_tokens": 30},
    })
    assert (data.input_uncached, data.cache_read_input, data.output_total,
            data.reasoning_output) == (20, 80, 50, 30)
    assert task_credit_charge([(data, True)], UserPriceSnapshot()) == 1


def test_deepseek_cache_fields_are_not_double_counted():
    data = normalize_provider_usage({
        "prompt_tokens": 1000, "completion_tokens": 200,
        "prompt_cache_hit_tokens": 800, "prompt_cache_miss_tokens": 200,
    }, provider="deepseek")
    assert data.input_uncached == 200


def test_anthropic_exclusive_cache_and_write():
    data = normalize_provider_usage({
        "input_tokens": 100, "cache_read_input_tokens": 700,
        "cache_creation_input_tokens": 200, "output_tokens": 50,
    }, provider="anthropic")
    assert (data.input_uncached, data.cache_read_input, data.cache_write_input) == (100, 700, 200)


def test_missing_or_invalid_usage_never_becomes_free_usage():
    for raw in (None, {}, {"input_tokens": 5}, {"input_tokens": -1, "output_tokens": 3}):
        data = normalize_provider_usage(raw)
        assert not data.complete
        with pytest.raises(ValueError, match="Incomplete"):
            task_credit_charge([(data, True)], UserPriceSnapshot())
    with pytest.raises(ValueError, match="Reasoning token count"):
        NormalizedUsage(0, 0, 0, 1, reasoning_output=2)


def test_provider_actual_cost_is_separate_from_free_user_cache():
    data = NormalizedUsage(100, 900, 0, 200)
    cost = provider_cost_micro_usd(
        data, uncached_per_million_usd=Decimal("1"),
        cache_read_per_million_usd=Decimal("0.1"),
        cache_write_per_million_usd=Decimal("1.25"),
        output_per_million_usd=Decimal("2"),
    )
    assert cost == Decimal("590.0")
    assert task_credit_charge([(data, True)], UserPriceSnapshot()) == 1


def test_pricing_snapshot_is_immutable_and_validated():
    snap = UserPriceSnapshot.from_mapping({"version": "fixed", "output_per_million": 1200})
    assert task_credit_charge([(NormalizedUsage(0, 0, 0, 1000), True)], snap) == 2
    with pytest.raises(ValueError):
        UserPriceSnapshot.from_mapping({"output_per_million": -1})


def test_35_credits_are_not_hard_capped_in_pure_quote():
    sample = NormalizedUsage(0, 0, 0, 43750)
    assert task_credit_charge([(sample, True)], UserPriceSnapshot()) == 35
