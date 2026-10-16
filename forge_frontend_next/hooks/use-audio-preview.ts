'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { claimAudioPreview } from '../lib/audio-preview';

export function useAudioPreview(source?: string | null, durationMs?: number | null) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const session = useRef(0);
  const cleanup = useRef<(() => void) | null>(null);
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState((durationMs || 0) / 1000);
  const [error, setError] = useState('');
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const stop = useCallback(() => {
    session.current++;
    cleanup.current?.();
    cleanup.current = null;
    setPlaying(false);
    setActiveKey(null);
  }, []);
  useEffect(() => {
    stop();
    setPosition(0);
    setDuration((durationMs || 0) / 1000);
    setError('');
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    return stop;
  }, [source, durationMs, stop]);
  async function play(key: string, load?: () => Promise<Blob>) {
    stop();
    setError('');
    const id = session.current;
    const release = claimAudioPreview(stop);
    let audio: HTMLAudioElement | null = null;
    let url: string | null = null;
    const dispose = () => {
      release();
      if (audio) {
        audio.removeEventListener('pause', paused);
        audio.removeEventListener('ended', ended);
        audio.removeEventListener('error', failed);
        audio.pause();
      }
      if (url) {
        URL.revokeObjectURL(url);
        url = null;
      }
    };
    const paused = () => {
      if (session.current === id) setPlaying(false);
    };
    const ended = () => {
      if (session.current === id) {
        stop();
        setPosition(0);
        if (audio) audio.currentTime = 0;
      }
    };
    const failed = () => {
      if (session.current === id) {
        stop();
        setError('音频暂时无法播放');
      }
    };
    cleanup.current = dispose;
    setActiveKey(key);
    try {
      if (load) {
        const blob = await load();
        if (session.current !== id) return;
        url = URL.createObjectURL(blob);
        audio = new Audio(url);
        audio.preload = 'none';
      } else audio = audioRef.current;
      if (!audio) {
        stop();
        return;
      }
      audio.addEventListener('pause', paused);
      audio.addEventListener('ended', ended);
      audio.addEventListener('error', failed);
      await audio.play();
      if (session.current === id) setPlaying(true);
    } catch (reason) {
      if (session.current === id) {
        stop();
        setError(reason instanceof Error ? reason.message : '播放失败，请重试');
      }
    }
  }
  function toggle() {
    if (playing) stop();
    else void play(source || 'preview');
  }
  function seek(value: number) {
    if (audioRef.current) audioRef.current.currentTime = value;
    setPosition(value);
  }
  return {
    audioRef,
    playing,
    position,
    duration,
    error,
    activeKey,
    play,
    stop,
    toggle,
    seek,
    audioProps: {
      ref: audioRef,
      src: source || undefined,
      preload: 'none' as const,
      onTimeUpdate: (event: React.SyntheticEvent<HTMLAudioElement>) => setPosition(event.currentTarget.currentTime),
      onLoadedMetadata: (event: React.SyntheticEvent<HTMLAudioElement>) => {
        if (Number.isFinite(event.currentTarget.duration)) setDuration(event.currentTarget.duration);
      },
      onError: () => {
        stop();
        setError('音频暂时无法播放');
      },
    },
  };
}
