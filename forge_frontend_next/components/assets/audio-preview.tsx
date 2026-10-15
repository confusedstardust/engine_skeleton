"use client";

import { useRef, useState } from "react";

function clock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export function AudioPreview({ src, name, durationMs }: { src: string; name: string; durationMs?: number | null }) {
  const audio = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState((durationMs || 0) / 1000);
  const [error, setError] = useState("");
  async function toggle() {
    const element = audio.current;
    if (!element) return;
    if (!element.paused) { element.pause(); return; }
    // Keep previews from competing with one another.
    document.querySelectorAll("audio").forEach(other => { if (other !== element) other.pause(); });
    setError("");
    try { await element.play(); } catch { setError("播放失败，请重试"); }
  }
  return <div className={`asset-audio ${playing ? "is-playing" : ""}`}>
    <audio ref={audio} src={src} preload="none" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onTimeUpdate={event => setPosition(event.currentTarget.currentTime)} onLoadedMetadata={event => { const value = event.currentTarget.duration; if (Number.isFinite(value)) setDuration(value); }} onError={() => { setPlaying(false); setError("音频暂时无法播放"); }} />
    <div className="asset-vinyl" aria-hidden="true"><span>♪</span></div>
    <div className="asset-audio-controls">
      <button type="button" className="asset-audio-play" aria-label={`${playing ? "暂停" : "播放"}${name}`} onClick={() => void toggle()}>{playing ? <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14M16 5v14" fill="none" stroke="currentColor" strokeWidth="3" /></svg> : <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z" fill="currentColor" /></svg>}</button>
      <div className="asset-audio-timeline"><input aria-label={`${name}播放进度`} type="range" min="0" max={duration || 1} step="0.1" value={Math.min(position, duration || 1)} disabled={!duration} onChange={event => { const next = Number(event.target.value); if (audio.current) audio.current.currentTime = next; setPosition(next); }} /><div><span>{clock(position)}</span><span>{duration ? clock(duration) : "试听"}</span></div></div>
    </div>
    {error && <span className="asset-audio-error" role="alert">{error}</span>}
  </div>;
}
