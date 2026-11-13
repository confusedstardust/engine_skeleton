export type RefreshResult = { key: string; active?: boolean; closed?: boolean; poll?: boolean; commit: () => void };
export type RefreshState = { syncing: boolean; error: string; lastSyncedAt: number | null; delayMs: number; paused: boolean; authRequired: boolean };
type Options = {
  task: (signal: AbortSignal) => Promise<RefreshResult>;
  onState: (state: RefreshState) => void;
  now?: () => number; random?: () => number;
  setTimer?: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>;
  clearTimer?: (timer: ReturnType<typeof setTimeout>) => void;
};

/** Await every sibling, including on failure, before another batch can start. */
export async function refreshBatch<T extends readonly unknown[]>(requests: { [K in keyof T]: Promise<T[K]> }): Promise<T> {
  const results = await Promise.allSettled(requests);
  for (const result of results) if (result.status === 'rejected') throw result.reason;
  return results.map(result => (result as PromiseFulfilledResult<unknown>).value) as unknown as T;
}

/** One full refresh at a time. Mutations require a snapshot started after the write. */
export function createRefreshPolling(options: Options) {
  const now = options.now ?? Date.now;
  const random = options.random ?? Math.random;
  const setTimer = options.setTimer ?? setTimeout;
  const clearTimer = options.clearTimer ?? clearTimeout;
  let state: RefreshState = { syncing: false, error: '', lastSyncedAt: null, delayMs: 5000, paused: true, authRequired: false };
  let active = false, disposed = false, running = false, epoch = 0, failures = 0, quiet = 0;
  let previousKey: string | undefined;
  let repeat = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let controller: AbortController | undefined;
  let waiters: { epoch: number; resolve: (ok: boolean) => void }[] = [];
  const emit = (patch: Partial<RefreshState>) => { state = { ...state, ...patch }; if (!disposed) options.onState(state); };
  const cancelTimer = () => { if (timer !== undefined) clearTimer(timer); timer = undefined; };
  const settle = (ok: boolean) => { const pending = waiters; waiters = []; pending.forEach(w => w.resolve(ok)); };

  async function run() {
    if (disposed || running) return;
    cancelTimer();
    running = true;
    const startedEpoch = epoch;
    const current = new AbortController();
    controller = current;
    emit({ syncing: true });
    try {
      const result = await options.task(current.signal);
      if (disposed || current.signal.aborted) return;
      // A write completed during this read. Do not publish its older snapshot.
      if (startedEpoch !== epoch) return;
      result.commit();
      const changed = previousKey !== undefined && result.key !== previousKey;
      quiet = previousKey === result.key ? quiet + 1 : 0;
      previousKey = result.key;
      failures = 0;
      repeat = result.poll !== false;
      const delayMs = result.active || changed ? 3000 : result.closed ? 60000 : quiet >= 6 ? 20000 : quiet >= 3 ? 10000 : 5000;
      emit({ error: '', lastSyncedAt: now(), delayMs, authRequired: false });
      settle(true);
    } catch (error) {
      if (disposed || current.signal.aborted || startedEpoch !== epoch) return;
      failures++;
      const status = (error as { status?: number })?.status;
      const authRequired = status === 401 || status === 403;
      const retry = Math.min(60000, 5000 * 2 ** Math.min(failures - 1, 4));
      emit({ error: error instanceof Error ? error.message : '同步失败，请重试', authRequired, delayMs: Math.min(60000, Math.round(retry * (0.9 + random() * 0.2))) });
      settle(false);
    } finally {
      running = false;
      if (!disposed) {
        emit({ syncing: false });
        if (startedEpoch !== epoch) void run();
        else if (active && repeat && !state.authRequired) timer = setTimer(() => { void run(); }, state.delayMs);
      }
    }
  }

  return {
    refresh({ mutation = false }: { mutation?: boolean } = {}) {
      if (disposed) return Promise.resolve(false);
      cancelTimer();
      if (mutation) epoch++;
      emit({ authRequired: false });
      const promise = new Promise<boolean>(resolve => { waiters.push({ epoch, resolve }); });
      void run();
      return promise;
    },
    setActive(value: boolean, { immediate = true }: { immediate?: boolean } = {}) {
      if (disposed || value === active) return;
      active = value;
      cancelTimer();
      emit({ paused: !value });
      if (active && !state.authRequired) {
        if (immediate) void run();
        else if (repeat) timer = setTimer(() => { void run(); }, state.delayMs);
      }
    },
    dispose() {
      disposed = true; active = false; cancelTimer(); controller?.abort(); settle(false);
    },
  };
}
