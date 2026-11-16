"""Billing V2 reconciliation quote -- READ-ONLY, never moves wallet balances.

A 'READY' quote is a prerequisite, *not permission to charge*: authorization,
actual reservation capacity, and a DB-idempotent settlement are separate gates.
Every event must be bound to a server-trusted owner and task/session.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Any, Mapping, Literal

from .nar_metering_v2 import NormalizedUsage, UserPriceSnapshot, raw_credit_amount

Status = Literal["READY", "FREE", "RECONCILING", "OVER_BUDGET"]
_COMPANY_ONLY = frozenset({"intent_shadow"})
_MAX_EVENTS = 2048


@dataclass(frozen=True)
class BillingQuote:
    status: Status
    owner: str
    billing_session_id: str
    credits: int | None
    raw_credits: Decimal | None
    price_version: str
    eligible_calls: int
    observed_calls: int
    reason: str

    @property
    def can_capture(self) -> bool:
        return self.status == "READY" and self.credits is not None


def _counter(record: Mapping[str, Any], name: str) -> int | None:
    raw = record.get(name)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 10**13:
        raise ValueError(f"Invalid {name} counter")
    return raw


def _usage(record: Mapping[str, Any]) -> NormalizedUsage:
    return NormalizedUsage(
        input_uncached=_counter(record, "input_uncached"),
        cache_read_input=_counter(record, "cache_read_input"),
        cache_write_input=_counter(record, "cache_write_input"),
        output_total=_counter(record, "output_total"),
        reasoning_output=_counter(record, "reasoning_output"),
        image_count=_counter(record, "image_count") or 0,
        tts_characters=_counter(record, "tts_characters") or 0,
        tool_calls=_counter(record, "tool_calls") or 0,
        status=str(record.get("usage_status", "UNKNOWN")),
    )


def reconcile_task_quote(
    *,
    owner: str,
    billing_session_id: str,
    events: list[Mapping[str, Any]],
    pricing_snapshot: Mapping[str, Any],
    reserved_credits: int,
    authorized_credits: int,
    delivered: bool,
    billing_session_final: bool,
    expected_billable_calls: int,
) -> BillingQuote:
    """Produce a deterministic task-level quote; fails closed on usage gaps.

    - No user charge without a delivered work and closed billing session.
    - Cost of shadow experiments never enters user credits.
    - Captures at most once *after* caller verifies both approved and reserved.
    - Rounds only the sum of eligible call charges, NOT each call.
    """
    if not owner or not billing_session_id:
        raise ValueError("Missing trusted owner or billing session")
    if not (0 <= len(events) <= _MAX_EVENTS):
        raise ValueError("Unreasonable usage event count")
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 0
           for n in (reserved_credits, authorized_credits, expected_billable_calls)):
        raise ValueError("Invalid budget or call count")
    snapshot = UserPriceSnapshot.from_mapping(pricing_snapshot)
    def reply(status: Status, credits: int | None, amount: Decimal | None,
              eligible: int, reason: str) -> BillingQuote:
        return BillingQuote(status, owner, billing_session_id, credits, amount,
                            snapshot.version, eligible, len(events), reason)
    if not delivered:
        # No viable artifact: company bears the model costs under current
        # recommended product policy, including incomplete provider usage.
        return reply("FREE", 0, Decimal(0), 0, "No deliverable; user not charged")
    if not billing_session_final:
        return reply("RECONCILING", None, None, 0, "Task or clarification session still open")

    seen: set[tuple[str, str]] = set()
    total = Decimal(0)
    eligible = 0
    for record in events:
        if str(record.get("owner_user_id", "")) != owner:
            raise ValueError("Cross-owner usage event")
        if str(record.get("billing_session_id", "")) != billing_session_id:
            raise ValueError("Cross-session usage event")
        key = (str(record.get("call_id") or ""), str(record.get("attempt_id") or ""))
        if not key[0] or key in seen:
            return reply("RECONCILING", None, None, eligible, "Missing or repeated provider call ID")
        seen.add(key)
        stage = str(record.get("stage") or "")
        billable = record.get("billable_to_user") is True
        if stage in _COMPANY_ONLY:
            if billable:
                return reply("RECONCILING", None, None, eligible, "Shadow call marked billable")
            continue
        if not billable:
            continue
        eligible += 1
        try:
            usage = _usage(record)
            total += raw_credit_amount(usage, snapshot)
        except (ValueError, TypeError):
            return reply("RECONCILING", None, None, eligible, "Incomplete or invalid provider usage")

    if eligible != expected_billable_calls:
        return reply("RECONCILING", None, None, eligible, "Missing billable call events")
    if expected_billable_calls == 0:
        return reply("RECONCILING", None, None, eligible, "No confirmed billable calls for delivered work")
    amount = int(total.to_integral_value(rounding=ROUND_CEILING))
    if amount > authorized_credits or amount > reserved_credits:
        return reply("OVER_BUDGET", amount, total, eligible, "Requires approved hold before settlement")
    return reply("READY", amount, total, eligible, "Provider usage complete")
