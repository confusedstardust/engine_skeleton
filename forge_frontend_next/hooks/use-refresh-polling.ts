'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { createRefreshPolling, type RefreshResult, type RefreshState } from '../lib/refresh-polling';

/** Share manual, post-operation and adaptive periodic refreshes for one resource. */
export function useRefreshPolling(task: (signal: AbortSignal) => Promise<RefreshResult>, { resetKey, enabled = true, suspended = false }: { resetKey: string; enabled?: boolean; suspended?: boolean }) {
  const latest = useRef(task);
  latest.current = task;
  const active = useRef(enabled);
  active.current = enabled && !suspended;
  const wasSuspended = useRef(suspended);
  const current = useRef<ReturnType<typeof createRefreshPolling> | null>(null);
  const [state, setState] = useState<RefreshState>({ syncing: false, error: '', lastSyncedAt: null, delayMs: 5000, paused: true, authRequired: false });

  useEffect(() => {
    const polling = createRefreshPolling({ task: signal => latest.current(signal), onState: setState });
    current.current = polling;
    setState({ syncing: false, error: '', lastSyncedAt: null, delayMs: 5000, paused: true, authRequired: false });
    const visibility = () => polling.setActive(active.current && document.visibilityState !== 'hidden');
    const authenticated = () => { if (active.current && document.visibilityState !== 'hidden') void polling.refresh(); };
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('forge-auth-changed', authenticated);
    visibility();
    return () => { polling.dispose(); if (current.current === polling) current.current = null; document.removeEventListener('visibilitychange', visibility); window.removeEventListener('forge-auth-changed', authenticated); };
  }, [resetKey]);

  useEffect(() => {
    current.current?.setActive(enabled && !suspended && document.visibilityState !== 'hidden', { immediate: !wasSuspended.current });
    wasSuspended.current = suspended;
  }, [enabled, suspended]);
  const refresh = useCallback((options?: { mutation?: boolean }) => current.current?.refresh(options) ?? Promise.resolve(false), []);
  return { ...state, refresh };
}
