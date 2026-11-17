"""Owner-authenticated SSE snapshots of actual NarAgent progress.

Only public-facing milestones are emitted, never model message streams,
tool arguments, chain-of-thought, credentials or intermediate HTML source.
The stream observes task state; disconnecting it never cancels generation.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from .progress_events import public_elapsed_ms

PUBLIC_FIELDS = (
    "id", "status", "phase", "attempts", "timeline", "learning_plan",
    "artifact_id", "artifact_generated", "parent_artifact_id",
    "error", "error_code", "output", "public_brief", "public_brief_state",
)


def progress_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded allowlisted snapshot so internal model traces never leak."""
    data = {key: state[key] for key in PUBLIC_FIELDS if key in state}
    if state.get("status") == "RUNNING":
        # Never publish incomplete generated prose or an unverified artifact ID.
        data.pop("output", None)
        data.pop("artifact_id", None)
    data["elapsed_ms"] = public_elapsed_ms(state)
    return data


async def stream_progress(
    state: dict[str, Any], *, interval: float = 0.3,
    heartbeat_seconds: float = 12.0,
) -> AsyncIterator[str]:
    """Emit updated snapshots at subsecond latency and terminate on final state.

    Each new connection starts with the latest snapshot, making reconnection
    idempotent; the frontend replaces state rather than appending duplicate steps.
    Heartbeats prevent idle proxies from killing a quiet model call.
    """
    previous = None
    quiet = 0.0
    sequence = 0
    yield "retry: 1500\n\n"
    while True:
        snapshot = progress_payload(state)
        # elapsed_ms naturally advances. Exclude it from the change signature,
        # letting the browser render a running second-by-second clock locally.
        signature = json.dumps({k: v for k, v in snapshot.items() if k != "elapsed_ms"},
                               ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if signature != previous:
            previous = signature
            sequence += 1
            event = "complete" if snapshot.get("status") != "RUNNING" else "progress"
            payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            yield f"id: {sequence}\nevent: {event}\ndata: {payload}\n\n"
            quiet = 0.0
        if snapshot.get("status") != "RUNNING":
            return
        await asyncio.sleep(interval)
        quiet += interval
        if quiet >= heartbeat_seconds:
            yield ": heartbeat\n\n"
            quiet = 0.0
