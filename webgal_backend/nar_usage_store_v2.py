"""Opt-in, append-only NarAgent V2 model-call usage event persistence.

The billing V1 path never calls this module. Install migration 006 before
enabling V2 shadow writes. Never store prompts, model output or API keys.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from forge_database import Database, ConnectionFactory

from .nar_metering_v2 import NormalizedUsage

_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,191}$")
_CALL = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_HEX = re.compile(r"^[0-9a-f]{32}$")
_STAGES = frozenset({
    "intent_v1", "intent_v2", "intent_shadow", "public_brief",
    "builder", "repair", "chat", "animation", "image", "tts", "tool",
})


@dataclass(frozen=True)
class ModelUsageEvent:
    event_key: str
    owner_user_id: str
    call_id: str
    stage: str
    provider: str
    usage: NormalizedUsage
    billable_to_user: bool = False
    conversation_id: str | None = None
    turn_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    requested_model: str | None = None
    actual_model: str | None = None
    provider_request_id: str | None = None
    price_catalog_version: str | None = None
    provider_cost_micro_usd: Decimal | None = None

    def __post_init__(self):
        if not _KEY.fullmatch(self.event_key) or not _CALL.fullmatch(self.call_id):
            raise ValueError("Invalid event or call id")
        if not self.owner_user_id or len(self.owner_user_id) > 191:
            raise ValueError("Owner is required")
        if self.stage not in _STAGES:
            raise ValueError("Unknown stage")
        if self.stage == "intent_shadow" and self.billable_to_user:
            raise ValueError("Shadow experiments must never bill a user")
        if not self.provider or len(self.provider) > 64:
            raise ValueError("Invalid provider")
        for value in (self.conversation_id, self.turn_id, self.task_id):
            if value is not None and not _HEX.fullmatch(value):
                raise ValueError("Invalid owner-scoped ID")
        if self.provider_cost_micro_usd is not None and (
                not self.provider_cost_micro_usd.is_finite() or self.provider_cost_micro_usd < 0):
            raise ValueError("Invalid provider cost")


def safe_payload(event: ModelUsageEvent) -> dict[str, Any]:
    """All persisted fields must be known, counter-only or opaque IDs."""
    usage = event.usage
    return {
        "event_key": event.event_key,
        "owner_user_id": event.owner_user_id,
        "conversation_id": event.conversation_id,
        "turn_id": event.turn_id,
        "task_id": event.task_id,
        "call_id": event.call_id,
        "attempt_id": event.attempt_id,
        "stage": event.stage,
        "provider": event.provider,
        "requested_model": event.requested_model,
        "actual_model": event.actual_model,
        "usage_status": usage.status,
        "usage_source": "model_callback",
        "input_uncached": usage.input_uncached,
        "cache_read_input": usage.cache_read_input,
        "cache_write_input": usage.cache_write_input,
        "output_total": usage.output_total,
        "reasoning_output": usage.reasoning_output,
        "image_count": usage.image_count,
        "tts_characters": usage.tts_characters,
        "tool_calls": usage.tool_calls,
        "provider_request_id": event.provider_request_id,
        "provider_cost_micro_usd": str(event.provider_cost_micro_usd)
            if event.provider_cost_micro_usd is not None else None,
        "price_catalog_version": event.price_catalog_version,
        "billable_to_user": bool(event.billable_to_user),
    }


class NarUsageEventStore:
    def __init__(self, factory: ConnectionFactory):
        self._database = Database(factory)

    def record(self, event: ModelUsageEvent) -> bool:
        """Insert once, reject conflicting replays. Return True only on insert.

        No upsert: an UNKNOWN event cannot silently mutate into a settled
        REPORTED event. Reconciliation must create its own linked event.
        """
        payload = safe_payload(event)
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode("utf8")).hexdigest()
        event_id = hashlib.sha256(("nar-usage-v2:" + event.event_key).encode()).hexdigest()[:32]
        fields = list(payload)
        with self._database.transaction() as cursor:
            cursor.execute("SELECT payload_sha256 FROM nar_usage_events WHERE event_key=%s FOR UPDATE",
                           (event.event_key,))
            existing = cursor.fetchone()
            if existing:
                if existing["payload_sha256"] != fingerprint:
                    raise ValueError("Conflicting usage event replay")
                return False
            columns = ["id", "payload_sha256", *fields, "raw_usage_json"]
            values = [event_id, fingerprint, *(payload[f] for f in fields), None]
            names = ",".join("`" + col + "`" for col in columns)
            placeholders = ",".join(["%s"] * len(columns))
            cursor.execute(f"INSERT INTO nar_usage_events ({names}) VALUES ({placeholders})", values)
        return True
