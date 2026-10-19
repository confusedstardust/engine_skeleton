"""Doubao HTTP chunked TTS adapter. Streaming stays behind the shared WAV API."""
from __future__ import annotations

import base64
import binascii
import json
import math
import time
import uuid
from typing import Any, Iterable, Iterator

import httpx

from .tts import TTSOptions, TTSSynthesisError


def _messages(lines: Iterable[str]) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    pending = ""
    for line in lines:
        line = line.strip()
        if not line or line.startswith(("event:", "id:", ":")):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            break
        pending += line
        while pending:
            try:
                value, end = decoder.raw_decode(pending)
            except ValueError:
                break
            yield value
            pending = pending[end:].lstrip()
    if pending:
        raise TTSSynthesisError("Doubao TTS returned malformed or truncated JSON")


def synthesize_pcm(
    text: str, options: TTSOptions, api_key: str, timeout: int,
) -> tuple[bytes, dict[str, Any]]:
    request_id = str(uuid.uuid4())
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": options.resource_id,
        "X-Api-Request-Id": request_id,
        "X-Control-Require-Usage-Tokens-Return": "*",
    }
    params: dict[str, Any] = {
        "text": text,
        "speaker": options.voice,
        "audio_params": {
            "format": "pcm",
            "sample_rate": options.sample_rate,
            "speech_rate": round((options.speech_rate - 1) * 100),
            "loudness_rate": max(-50, min(100, round((options.volume / 50 - 1) * 100))),
        },
    }
    additions: dict[str, Any] = {}
    if options.instructions.strip():
        additions["context_texts"] = [options.instructions.strip()]
    if options.pitch_rate != 1:
        additions["post_process"] = {"pitch": max(-12, min(12, round(12 * math.log2(options.pitch_rate))))}
    if additions:
        params["additions"] = json.dumps(additions, ensure_ascii=False)
    deadline = time.monotonic() + timeout
    audio = bytearray()
    metadata: dict[str, Any] = {"request_id": request_id, "usage": {}}
    finished = False
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=min(timeout, 10))) as client:
            with client.stream("POST", options.url, headers=headers, json={"req_params": params}) as response:
                metadata["log_id"] = response.headers.get("X-Tt-Logid", "")
                if response.status_code != 200:
                    category = "rate limit" if response.status_code == 429 else "request failed"
                    raise TTSSynthesisError(f"Doubao TTS {category}: HTTP {response.status_code}; request_id={request_id}")
                for message in _messages(response.iter_lines()):
                    if time.monotonic() > deadline:
                        raise TTSSynthesisError("Doubao TTS request timed out")
                    if not isinstance(message, dict) or message.get("code") not in (0, 20000000):
                        detail = str(message).replace(api_key, "[redacted]")
                        raise TTSSynthesisError(f"Doubao TTS synthesis failed: {detail}; request_id={request_id}")
                    if message.get("data"):
                        audio.extend(base64.b64decode(message["data"], validate=True))
                    if message.get("code") == 20000000:
                        metadata["usage"] = message.get("usage") or {}
                        finished = True
                        break
    except (httpx.HTTPError, ValueError, TypeError, binascii.Error) as exc:
        raise TTSSynthesisError(f"Doubao TTS transport/stream error ({type(exc).__name__}); request_id={request_id}") from exc
    if not finished or not audio:
        raise TTSSynthesisError(f"Doubao TTS stream ended without complete audio; request_id={request_id}")
    return bytes(audio), metadata
