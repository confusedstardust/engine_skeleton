'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

type Entry<T> = { data?: T; loaded: boolean; dirty: boolean; loading: boolean; error: string; version: number; controller?: AbortController; pending?: Promise<T | undefined>; fetch?: (signal: AbortSignal) => Promise<T> };

/** Cache per resource key; fetch only on demand or explicit invalidation. No timers. */
export function useLazyResource<T>(key: string, loader: (signal: AbortSignal) => Promise<T>, enabled: boolean) {
  const cache = useRef(new Map<string, Entry<T>>());
  const mounted = useRef(true);
  const [, render] = useState(0);
  const notify = useCallback(() => { if (mounted.current) render(n => n + 1); }, []);
  let entry = cache.current.get(key);
  if (!entry) { entry = { loaded: false, dirty: false, loading: false, error: '', version: 0 }; cache.current.set(key, entry); }
  const current = entry;
  current.fetch = loader;
  const load = useCallback((force = false): Promise<T | undefined> => {
    if (!force && current.pending) return current.pending;
    if (!force && current.loaded && !current.dirty) return Promise.resolve(current.data);
    current.controller?.abort();
    const controller = new AbortController(); current.controller = controller;
    const version = ++current.version;
    const fetch = current.fetch!;
    current.loading = true; current.error = ''; notify();
    const pending = (async () => {
      try {
        const value = await fetch(controller.signal);
        if (controller.signal.aborted || current.version !== version) return;
        current.data = value; current.loaded = true; current.dirty = false;
        return value;
      } catch (error) {
        if (!controller.signal.aborted && current.version === version) current.error = error instanceof Error ? error.message : '加载失败，请重试';
      } finally {
        if (current.version === version) { current.loading = false; current.pending = undefined; notify(); }
      }
    })();
    current.pending = pending;
    return pending;
  }, [current, notify]);
  const invalidate = useCallback(() => {
    current.controller?.abort(); current.version++; current.pending = undefined; current.loading = false;
    current.dirty = true; current.error = ''; notify();
  }, [current, notify]);
  const update = useCallback((fn: (data: T | undefined) => T) => { current.data = fn(current.data); current.loaded = true; notify(); }, [current, notify]);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; cache.current.forEach(item => item.controller?.abort()); }; }, []);
  useEffect(() => () => { current.controller?.abort(); }, [enabled, key]);
  useEffect(() => {
    if (enabled && (!current.loaded || current.dirty) && !current.loading && !current.error) void load();
  }, [enabled, key, current.dirty, current.loaded, current.loading, current.error, load]);
  return { data: current.data, loaded: current.loaded, dirty: current.dirty, loading: current.loading, error: current.error, load, invalidate, update };
}
