"""NarAgent call-level usage telemetry. No wallet logic and no prompt capture.

This is an internal opt-in supplement to the existing aggregate usage callback.
It does not authorize costs; Forge owns user billing and immutable persistence.
"""
from __future__ import annotations

from contextvars import ContextVar
from collections.abc import Mapping
from uuid import uuid4
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

active_intent_meter: ContextVar["ModelCallRecorder | None"] = ContextVar(
    "nar_active_intent_meter", default=None
)
_LIMIT = 10**13


def _clean_counter(x: Any) -> int | None:
    return x if isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= _LIMIT else None


def sanitized_usage(payload: Any) -> dict | None:
    """Allowlist only numeric usage. Never store model outputs, tool arguments or prompts."""
    if not isinstance(payload, Mapping):
        return None
    numeric_keys = (
        "input_tokens", "output_tokens", "prompt_tokens", "completion_tokens",
        "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens",
    )
    result = {k: n for k in numeric_keys
              if (n := _clean_counter(payload.get(k))) is not None}
    for key in ("input_token_details", "prompt_tokens_details",
                "output_token_details", "completion_tokens_details"):
        nested = payload.get(key)
        if isinstance(nested, Mapping):
            counters = {k: n for k in (
                "cache_read", "cached_tokens", "cache_write",
                "cached_input_tokens", "reasoning_tokens"
            ) if (n := _clean_counter(nested.get(k))) is not None}
            if counters:
                result[key] = counters
    return result or None


def _extract_usage(message: Any, llm_output: Any = None) -> dict | None:
    direct = sanitized_usage(getattr(message, "usage_metadata", None))
    if direct:
        return direct
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, Mapping):
        for key in ("token_usage", "usage"):
            result = sanitized_usage(metadata.get(key))
            if result:
                return result
    if isinstance(llm_output, Mapping):
        for key in ("token_usage", "usage"):
            result = sanitized_usage(llm_output.get(key))
            if result:
                return result
    return None


def provider_from_url(base_url: str) -> str:
    url = base_url.lower()
    if "deepseek" in url:
        return "deepseek"
    if "anthropic" in url:
        return "anthropic"
    return "openai"  # Compatible format; exact provider catalog remains Forge-owned.


class ModelCallRecorder(AsyncCallbackHandler):
    """Each LangChain LLM callback run ID appears at most once per task.

    The event IDs are not user-visible and are scoped to the owner/task on the
    trusted Forge side. Failure without usage is UNKNOWN rather than free.
    """
    def __init__(self, *, stage: str, provider: str, requested_model: str):
        self.stage = stage
        self.provider = provider
        self.requested_model = requested_model
        self._events: dict[str, dict] = {}

    @property
    def events(self) -> list[dict]:
        return list(self._events.values())

    def record_usage(self, usage: Any, *, call_id: str | None = None,
                     stage: str | None = None, actual_model: str | None = None):
        call_id = call_id or uuid4().hex
        if call_id in self._events:
            return
        safe = sanitized_usage(usage)
        complete = safe and (
            isinstance(safe.get("input_tokens", safe.get("prompt_tokens")), int)
            and isinstance(safe.get("output_tokens", safe.get("completion_tokens")), int)
        )
        self._events[call_id] = {
            "call_id": call_id, "stage": stage or self.stage,
            "provider": self.provider, "requested_model": self.requested_model,
            "actual_model": actual_model or self.requested_model,
            "usage_status": "REPORTED" if complete else "PARTIAL" if safe else "UNKNOWN",
            "usage": safe,
        }

    def record_response(self, response: Any, *, call_id: str | None = None):
        usage = _extract_usage(response)
        metadata = getattr(response, "response_metadata", None)
        actual_model = metadata.get("model_name") if isinstance(metadata, Mapping) else None
        self.record_usage(usage, call_id=call_id, actual_model=actual_model)

    async def on_llm_end(self, response: Any, *, run_id: Any, **kwargs: Any):
        model_message = None
        for generations in getattr(response, "generations", []) or []:
            if generations:
                model_message = getattr(generations[0], "message", None)
                if model_message is not None:
                    break
        llm_output = getattr(response, "llm_output", None)
        usage = _extract_usage(model_message, llm_output)
        actual_model = llm_output.get("model_name") if isinstance(llm_output, Mapping) else None
        self.record_usage(usage, call_id=str(run_id), actual_model=actual_model)

    async def on_llm_error(self, error: BaseException, *, run_id: Any, **kwargs: Any):
        # Do not store exception strings; provider may include request content.
        self.record_usage(None, call_id=str(run_id))


def record_direct_intent_response(response: Any):
    meter = active_intent_meter.get()
    if meter is not None:
        meter.record_response(response)
