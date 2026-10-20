'use client';

import { useAudioPreview } from '../../hooks/use-audio-preview';

function clock(seconds: number) {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
}

export function AudioPreview({ src, name, durationMs }: { src: string; name: string; durationMs?: number | null }) {
  const preview = useAudioPreview(src, durationMs);
  const { playing, position, duration, error, toggle } = preview;
  return (
    <div className={`asset-audio ${playing ? 'is-playing' : ''}`}>
      <audio {...preview.audioProps} />
      <div className="asset-vinyl" aria-hidden="true">
        <span>♪</span>
      </div>
      <div className="asset-audio-controls">
        <button
          type="button"
          className="asset-audio-play"
          aria-label={`${playing ? '暂停' : '播放'}${name}`}
          onClick={() => void toggle()}
        >
          {playing ? (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M8 5v14M16 5v14" fill="none" stroke="currentColor" strokeWidth="3" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m8 5 11 7-11 7Z" fill="currentColor" />
            </svg>
          )}
        </button>
        <div className="asset-audio-timeline">
          <input
            aria-label={`${name}播放进度`}
            type="range"
            min="0"
            max={duration || 1}
            step="0.1"
            value={Math.min(position, duration || 1)}
            disabled={!duration}
            onChange={(event) => {
              const next = Number(event.target.value);
              preview.seek(next);
            }}
          />
          <div>
            <span>{clock(position)}</span>
            <span>{duration ? clock(duration) : '试听'}</span>
          </div>
        </div>
      </div>
      {error && (
        <span className="asset-audio-error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
