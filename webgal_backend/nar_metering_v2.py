"""Pure, provider-normalized NarAgent V2 metering and user pricing.

This module does not modify balances. Gateway persistence and wallet settlement
live in separate services; unknown usage is never interpreted as zero cost.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping

MILLION = Decimal("1000000")
THOUSAND = Decimal("1000")
MAX_COUNTER = 10**13


def _nonnegative(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_COUNTER else None


def _first(source: Mapping[str, Any], *names: str) -> int | None:
    for name in names:
        if name in source:
            return _nonnegative(source[name])
    return None


@dataclass(frozen=True)
class NormalizedUsage:
    input_uncached: int | None
    cache_read_input: int | None
    cache_write_input: int | None
    output_total: int | None
    reasoning_output: int | None = None
    image_count: int = 0
    tts_characters: int = 0
    tool_calls: int = 0
    status: str = "REPORTED"

    def __post_init__(self):
        if self.status not in {"REPORTED", "PARTIAL", "UNKNOWN", "FAILED_PRE_SEND"}:
            raise ValueError("Invalid usage status")
        for field in ("input_uncached", "cache_read_input", "cache_write_input", "output_total",
                      "reasoning_output", "image_count", "tts_characters", "tool_calls"):
            value = getattr(self, field)
            if value is not None and _nonnegative(value) is None:
                raise ValueError("Invalid nonnegative usage counter")
        if (self.reasoning_output is not None and self.output_total is not None
                and self.reasoning_output > self.output_total):
            raise ValueError("Reasoning token count cannot exceed output tokens")

    @property
    def complete(self) -> bool:
        return self.status == "REPORTED" and self.input_uncached is not None and self.output_total is not None


def normalize_provider_usage(raw: Mapping[str, Any] | None, provider: str = "openai") -> NormalizedUsage:
    """Make disjoint buckets; OpenAI/DeepSeek cached is INCLUDED in prompt,
    Anthropic cache read/write is EXCLUDED from its input_tokens.
    Never infer usage from text length or a guessed tokenizer.
    """
    if raw is None or not isinstance(raw, Mapping):
        return NormalizedUsage(None, None, None, None, status="UNKNOWN")
    provider = provider.strip().lower()
    details = raw.get("prompt_tokens_details") or raw.get("input_token_details") or {}
    if not isinstance(details, Mapping):
        details = {}
    output_details = raw.get("completion_tokens_details") or raw.get("output_token_details") or {}
    if not isinstance(output_details, Mapping):
        output_details = {}
    output = _first(raw, "output_tokens", "completion_tokens")
    reasoning = _first(output_details, "reasoning_tokens", "reasoning")
    if provider == "anthropic":
        uncached = _first(raw, "input_tokens")
        read = _first(raw, "cache_read_input_tokens")
        write = _first(raw, "cache_creation_input_tokens")
        if read is None:
            read = 0
        if write is None:
            write = 0
    else:
        total = _first(raw, "input_tokens", "prompt_tokens")
        read = _first(details, "cache_read", "cached_tokens", "cached_input_tokens")
        if read is None:
            read = _first(raw, "prompt_cache_hit_tokens", "cached_tokens")
        write = _first(details, "cache_write", "cache_creation_input_tokens")
        read = 0 if read is None else read
        write = 0 if write is None else write
        uncached = None if total is None or read + write > total else total - read - write
    status = "REPORTED" if uncached is not None and output is not None else "PARTIAL"
    return NormalizedUsage(uncached, read, write, output, reasoning, status=status)


@dataclass(frozen=True)
class UserPriceSnapshot:
    version: str = "nar-user-v2-compat-1"
    uncached_input_per_million: int = 200
    cache_read_per_million: int = 0
    cache_write_per_million: int = 200
    output_per_million: int = 800
    image_each: int = 10
    tts_per_thousand_characters: int = 5
    tool_each: int = 0

    @classmethod
    def from_mapping(cls, source: Mapping[str, Any]) -> "UserPriceSnapshot":
        keys = cls.__dataclass_fields__
        subset = {k: source[k] for k in keys if k in source}
        result = cls(**subset)
        if any(not isinstance(getattr(result, k), int) or isinstance(getattr(result, k), bool)
               or getattr(result, k) < 0 for k in keys if k != "version"):
            raise ValueError("Invalid price snapshot")
        if not result.version or len(result.version) > 64:
            raise ValueError("Invalid price version")
        return result


def raw_credit_amount(usage: NormalizedUsage, pricing: UserPriceSnapshot) -> Decimal:
    """Unrounded charge for exactly one call, excluding company-only calls."""
    if not usage.complete or usage.cache_read_input is None or usage.cache_write_input is None:
        raise ValueError("Only complete provider-reported usage may be billed")
    return (
        Decimal(usage.input_uncached) * pricing.uncached_input_per_million / MILLION
        + Decimal(usage.cache_read_input) * pricing.cache_read_per_million / MILLION
        + Decimal(usage.cache_write_input) * pricing.cache_write_per_million / MILLION
        + Decimal(usage.output_total) * pricing.output_per_million / MILLION
        + Decimal(usage.image_count) * pricing.image_each
        + Decimal(usage.tts_characters) * pricing.tts_per_thousand_characters / THOUSAND
        + Decimal(usage.tool_calls) * pricing.tool_each
    )


def task_credit_charge(calls: list[tuple[NormalizedUsage, bool]], pricing: UserPriceSnapshot,
                       *, allow_unknown: bool = False) -> int:
    """Task-level single ceil. Shadow/free calls never contribute.

    UNKNOWN billable events block settlement; they are not free zero-cost events.
    """
    total = Decimal(0)
    for usage, billable in calls:
        if not billable:
            continue
        if not usage.complete:
            if allow_unknown:
                continue
            raise ValueError("Incomplete usage requires reconciliation")
        total += raw_credit_amount(usage, pricing)
    return int(total.to_integral_value(rounding=ROUND_CEILING))


def provider_cost_micro_usd(usage: NormalizedUsage, *,
                            uncached_per_million_usd: Decimal,
                            cache_read_per_million_usd: Decimal,
                            cache_write_per_million_usd: Decimal,
                            output_per_million_usd: Decimal) -> Decimal:
    """Actual provider cost uses its own price catalog, not user credit policy."""
    if not usage.complete:
        raise ValueError("Cannot determine exact provider cost without usage")
    amounts = (
        Decimal(usage.input_uncached) * uncached_per_million_usd
        + Decimal(usage.cache_read_input) * cache_read_per_million_usd
        + Decimal(usage.cache_write_input) * cache_write_per_million_usd
        + Decimal(usage.output_total) * output_per_million_usd
    )
    return amounts  # USD/million-token * token -> micro-USD
