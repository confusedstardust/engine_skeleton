"""Bounded, provider-reported NarAgent usage and existing credit-ledger integration.

The feature is explicitly opt-in. Zero/unreported tokens are never estimated
from text length. Reservations have stable job/operation keys and settlement
is idempotent. Unknown dispatch status must NOT release a reservation.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any, Mapping

from credit_system import CreditService, InsufficientCreditsError
from credit_system.billing import Pricing, UsageTotals, credits_for_usage

logger = logging.getLogger(__name__)
_OPERATION = "nar-agent-turn-v1"


def enabled() -> bool:
    return os.getenv("NAR_AGENT_CREDITS_ENABLED", "false").lower() in ("1", "true", "yes")


def usage_totals(raw: Any) -> UsageTotals | None:
    """Aggregate all provider-reported model callbacks without inventing counts."""
    if not isinstance(raw, dict) or not raw:
        return None
    input_tokens = output_tokens = cached_input_tokens = 0
    reported = False
    for item in raw.values():
        if not isinstance(item, dict):
            continue
        for name in ("input_tokens", "output_tokens"):
            value = item.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                reported = True
        input_tokens += max(0, int(item.get("input_tokens", 0))) if isinstance(item.get("input_tokens"), int) else 0
        output_tokens += max(0, int(item.get("output_tokens", 0))) if isinstance(item.get("output_tokens"), int) else 0
        details = item.get("input_token_details") or item.get("prompt_tokens_details") or {}
        if isinstance(details, dict):
            cached_input_tokens += max(0, int(details.get("cache_read", details.get("cached_tokens", 0)))) if isinstance(
                details.get("cache_read", details.get("cached_tokens", 0)), int
            ) else 0
    if not reported:
        return None
    return UsageTotals(input_tokens, output_tokens, min(input_tokens, cached_input_tokens))


def task_usage_metadata(raw: Any, *, duration_ms: int = 0, billing: str = "disabled",
                        charged: int | None = None, hold: int | None = None) -> dict:
    measured = usage_totals(raw)
    return {
        "inputTokens": measured.input_tokens if measured else None,
        "outputTokens": measured.output_tokens if measured else None,
        "cachedInputTokens": measured.cached_input_tokens if measured else None,
        "usageStatus": "reported" if measured else "unavailable",
        "billingStatus": billing,
        "chargedCredits": charged,
        "reservedCredits": hold,
        "durationMs": max(0, int(duration_ms or 0)),
        # Router classification and optional public-brief model calls may use
        # separate providers; never claim these counters represent all costs.
        "scope": "agent_execution",
    }


class NarTurnBilling:
    def __init__(self, service: CreditService | None = None):
        self._service = service or CreditService.from_env()

    def reserve(self, owner: str, tid: str, mode: str):
        self._service.ensure_signup_credits(owner)
        self._service.ensure_billable_job(
            user_id=owner, job_id=tid, source_material="NarAgent task",
            options={"classroom_topic": "NarAgent", "nar_agent_mode": mode},
        )
        hold = max(1, Pricing.from_env().text_hold)
        return self._service.reserve_for_game(
            user_id=owner, job_id=tid, operation_key=_OPERATION, units=hold,
            pricing_snapshot={"schema_version": 2, "plan": "nar_agent_metered_v1",
                              "hold_units": hold, "pricing": asdict(Pricing.from_env())},
        )

    def find(self, owner: str, tid: str):
        return self._service.find_reservation(user_id=owner, job_id=tid,
                                              operation_key=_OPERATION)

    def settle(self, reservation, usage: Mapping[str, Any] | None, *, definite_success: bool,
               duration_ms: int = 0) -> dict:
        if not definite_success:
            self._service.release(reservation.reservation_id)
            return task_usage_metadata(usage, duration_ms=duration_ms, billing="released", charged=0)
        totals = usage_totals(usage)
        if totals is None:
            self._service.release(reservation.reservation_id)
            return task_usage_metadata(usage, duration_ms=duration_ms, billing="unmetered_released", charged=0)
        units, settlement = credits_for_usage(totals)
        charged = min(units, reservation.units)
        self._service.capture(reservation.reservation_id, units=charged, settlement={
            **settlement, "mode": "nar_agent", "measured_units": units,
        })
        if units > reservation.units:
            logger.warning("NarAgent usage exceeds reserved hold; tid=%s measured=%s hold=%s",
                           reservation.job_id, units, reservation.units)
        return task_usage_metadata(usage, duration_ms=duration_ms, billing="captured",
                                   charged=charged, hold=reservation.units)


def safe_usage_metadata(raw: Any, *, duration_ms: int = 0) -> dict:
    """Telemetry-only mode does not represent an actual credit deduction."""
    return task_usage_metadata(raw, duration_ms=duration_ms, billing="disabled")
