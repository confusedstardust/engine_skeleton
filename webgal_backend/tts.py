from __future__ import annotations

import argparse
import base64
import os
import threading
import wave
from dataclasses import dataclass
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
    voice: str = DEFAULT_QWEN_TTS_VOICE
    model: str = DEFAULT_QWEN_TTS_MODEL
    url: str = DEFAULT_QWEN_TTS_URL
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    sample_width: int = DEFAULT_SAMPLE_WIDTH
    volume: int = 50
    speed: int = 50
    pitch: int = 50


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


def synthesize_text_to_file(
    text: str,
    output_path: Path | str,
    *,
    options: TTSOptions | None = None,
    timeout: int = 60,
) -> Path:
    """Synthesize one text line with Qwen realtime TTS and save it as WAV."""
    if _IMPORT_ERROR is not None:
        raise TTSConfigError("dashscope is required for Qwen TTS. Install it with: pip install dashscope") from _IMPORT_ERROR

    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise TTSConfigError("DASHSCOPE_API_KEY is required for Qwen TTS")

    text = text.strip()
    if not text:
        raise TTSSynthesisError("TTS text must not be empty")

    options = options or TTSOptions()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    dashscope.api_key = api_key
    callback = _QwenSingleCallCallback()
    tts = QwenTtsRealtime(model=options.model, callback=callback, url=options.url)
    try:
        tts.connect()
        tts.update_session(
            voice=options.voice,
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode="commit",
        )
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

    tmp_output = output.with_suffix(output.suffix + ".tmp")
    _write_wav(tmp_output, pcm, options)
    tmp_output.replace(output)
    return output


def _write_wav(path: Path, pcm: bytes, options: TTSOptions) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(options.channels)
        handle.setsampwidth(options.sample_width)
        handle.setframerate(options.sample_rate)
        handle.writeframes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize one text line with Qwen realtime TTS.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--voice", default=DEFAULT_QWEN_TTS_VOICE)
    parser.add_argument("--model", default=DEFAULT_QWEN_TTS_MODEL)
    parser.add_argument("--url", default=DEFAULT_QWEN_TTS_URL)
    args = parser.parse_args()

    synthesize_text_to_file(
        args.text,
        Path(args.output),
        options=TTSOptions(voice=args.voice, model=args.model, url=args.url),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
