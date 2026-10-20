from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
import threading
import wave
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

try:
    import dashscope
    from dashscope.audio.qwen_tts_realtime import AudioFormat, QwenTtsRealtime, QwenTtsRealtimeCallback
except ImportError as exc:  # pragma: no cover - dependency hint for local CLI use
    dashscope = None
    AudioFormat = None
    QwenTtsRealtime = None
    QwenTtsRealtimeCallback = object
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


DEFAULT_QWEN_TTS_MODEL = "qwen3-tts-flash-realtime"
DEFAULT_QWEN_TTS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
DEFAULT_QWEN_TTS_VOICE = "Cherry"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2


class TTSConfigError(RuntimeError):
    pass


class TTSSynthesisError(RuntimeError):
    pass


@dataclass(frozen=True)
class TTSOptions:
    provider: str = "qwen"
    profile_id: str = "qwen-realtime"
    api_key_env: str = "DASHSCOPE_API_KEY"
    resource_id: str = ""
    voice: str = DEFAULT_QWEN_TTS_VOICE
    model: str = DEFAULT_QWEN_TTS_MODEL
    url: str = DEFAULT_QWEN_TTS_URL
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    sample_width: int = DEFAULT_SAMPLE_WIDTH
    volume: int = 50
    speech_rate: float = 1.0
    pitch_rate: float = 1.0
    instructions: str = ""
    optimize_instructions: bool = True


class _QwenSingleCallCallback(QwenTtsRealtimeCallback):
    def __init__(self) -> None:
        super().__init__()
        self.done = threading.Event()
        self.audio = bytearray()
        self.error: str | None = None

    def on_close(self, close_status_code: Any, close_msg: Any) -> None:
        if not self.done.is_set() and close_status_code not in (None, 1000):
            self.error = f"connection closed: code={close_status_code}, msg={close_msg}"
            self.done.set()

    def on_event(self, response: dict[str, Any]) -> None:
        event_type = response.get("type")
        if event_type == "response.audio.delta":
            delta = response.get("delta", "")
            if delta:
                self.audio.extend(base64.b64decode(delta))
            return
        if event_type in {"response.done", "session.finished"}:
            self.done.set()
            return
        if event_type and ("error" in event_type or event_type.endswith(".failed")):
            self.error = str(response)
            self.done.set()

    def wait_for_done(self, timeout: int) -> bytes:
        if not self.done.wait(timeout=timeout):
            raise TTSSynthesisError(f"TTS request timed out after {timeout}s")
        if self.error:
            raise TTSSynthesisError(self.error)
        if not self.audio:
            raise TTSSynthesisError("TTS response did not include audio data")
        return bytes(self.audio)


def options_from_profile(profile: dict[str, Any], *, voice: str | None = None, instructions: str = "") -> TTSOptions:
    config = profile.get("options", {})
    selected = voice or profile["default_voice"]
    if selected not in {item["id"] for item in profile["voices"]}:
        raise TTSConfigError(f"Unknown voice for TTS profile {profile['id']}: {selected}")
    return TTSOptions(
        provider=profile["provider"],
        profile_id=profile["id"],
        api_key_env=profile["auth"]["api_key_env"],
        voice=selected,
        model=config.get("model", ""),
        resource_id=config.get("resource_id", ""),
        url=profile["endpoint"],
        volume=config.get("volume", 50),
        speech_rate=config.get("speech_rate", 1.0),
        pitch_rate=config.get("pitch_rate", 1.0),
        instructions=instructions,
        optimize_instructions=config.get("optimize_instructions", True),
    )


def synthesis_fingerprint(text: str, options: TTSOptions) -> str:
    value = {"text": text.strip(), "options": asdict(options), "schema_version": 1}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cached_synthesis(output: Path, text: str, options: TTSOptions) -> bool:
    try:
        metadata = json.loads(output.with_suffix(output.suffix + ".tts.json").read_text(encoding="utf-8"))
        return (
            metadata["fingerprint"] == synthesis_fingerprint(text, options)
            and metadata["audio_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def synthesize_text_to_file(text: str, output_path: Path | str, *, options: TTSOptions | None = None, timeout: int = 60) -> Path:
    """Provider-independent synthesis; commit only complete, validated WAV audio."""
    if options is None:
        from .tts_config import default_tts_profile
        options = options_from_profile(default_tts_profile())
    text = text.strip()
    if not text:
        raise TTSSynthesisError("TTS text must not be empty")
    if (options.sample_rate, options.channels, options.sample_width) != (24000, 1, 2):
        raise TTSConfigError("TTS output must be 24 kHz mono 16-bit WAV")
    api_key = os.getenv(options.api_key_env, "").strip()
    if not api_key:
        raise TTSConfigError(f"{options.api_key_env} is required for {options.provider} TTS")
    metadata: dict[str, Any] = {}
    if options.provider == "qwen":
        pcm = _synthesize_qwen_pcm(text, options, api_key, timeout)
    elif options.provider == "doubao":
        from .tts_doubao import synthesize_pcm
        pcm, metadata = synthesize_pcm(text, options, api_key, timeout)
    else:
        raise TTSConfigError(f"Unsupported TTS provider: {options.provider}")
    if not pcm or len(pcm) % (options.channels * options.sample_width):
        raise TTSSynthesisError("TTS returned empty or unaligned PCM audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, suffix=".wav.tmp", delete=False) as handle:
            temporary = Path(handle.name)
        _write_wav(temporary, pcm, options)
        temporary.replace(output)
        from .storage import write_json
        write_json(output.with_suffix(output.suffix + ".tts.json"), {
            **metadata, "provider": options.provider, "profile_id": options.profile_id,
            "fingerprint": synthesis_fingerprint(text, options), "audio_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        })
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


def _synthesize_qwen_pcm(text: str, options: TTSOptions, api_key: str, timeout: int) -> bytes:
    if _IMPORT_ERROR is not None:
        raise TTSConfigError("dashscope is required for Qwen TTS. Install it with: pip install dashscope") from _IMPORT_ERROR
    dashscope.api_key = api_key
    callback = _QwenSingleCallCallback()
    tts = QwenTtsRealtime(model=options.model, callback=callback, url=options.url)
    try:
        tts.connect()
        session_options = {
            "voice": options.voice,
            "response_format": AudioFormat.PCM_24000HZ_MONO_16BIT,
            "speech_rate": options.speech_rate,
            "volume": options.volume,
            "pitch_rate": options.pitch_rate,
            "mode": "commit",
        }
        if options.instructions.strip():
            session_options["instructions"] = options.instructions.strip()
            session_options["optimize_instructions"] = options.optimize_instructions
        tts.update_session(**session_options)
        tts.append_text(text)
        tts.commit()
        pcm = callback.wait_for_done(timeout=timeout)
        tts.finish()
    except Exception as exc:
        try:
            tts.finish()
        except Exception:
            pass
        if isinstance(exc, (TTSConfigError, TTSSynthesisError)):
            raise
        raise TTSSynthesisError(str(exc)) from exc

    return pcm


def _write_wav(path: Path, pcm: bytes, options: TTSOptions) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(options.channels)
        handle.setsampwidth(options.sample_width)
        handle.setframerate(options.sample_rate)
        handle.writeframes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize one line using a configured TTS profile.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", help="Profile ID in tts_profiles.json (otherwise uses default_profile)")
    parser.add_argument("--voice")
    parser.add_argument("--model")
    parser.add_argument("--url")
    parser.add_argument("--instructions", default="")
    parser.add_argument("--no-optimize-instructions", action="store_true")
    args = parser.parse_args()

    from .tts_config import default_tts_profile
    options = options_from_profile(default_tts_profile(args.profile), voice=args.voice, instructions=args.instructions)
    if args.model:
        if options.provider != "qwen":
            parser.error("--model is only supported by Qwen; Doubao uses resource_id in its profile")
        options = replace(options, model=args.model)
    if args.url:
        options = replace(options, url=args.url)
    if args.no_optimize_instructions:
        options = replace(options, optimize_instructions=False)
    synthesize_text_to_file(args.text, Path(args.output), options=options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
