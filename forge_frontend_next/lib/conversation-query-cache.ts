/**
 * Short-lived, per-SSO-account in-memory query cache.
 * This stores server RESPONSES for UI performance, never browser-persistent chat.
 * Identical in-flight reads are coalesced; only changed keys notify subscribers.
 * Mirrors staleTime / invalidation semantics used by established query libraries.
 */
type CacheEntry<T> = { data?: T; at: number; pending?: Promise<T> };
const entries = new Map<string, CacheEntry<unknown>>();
const listeners = new Map<string, Set<() => void>>();
const MAX_ENTRIES = 80;

export const CONVERSATION_STALE_MS = {
  readiness: 5 * 60_000,
  list: 60_000,
  artifacts: 60_000,
  detail: 2 * 60_000,
} as const;

function makeKey(owner: string, key: string): string {
  return owner + "::" + key;
}

export function peekConversationQuery<T>(owner: string, key: string): T | undefined {
  return entries.get(makeKey(owner, key))?.data as T | undefined;
}

export function subscribeConversationQuery(owner: string, key: string, listener: () => void): () => void {
  const id = makeKey(owner, key);
  let group = listeners.get(id);
  if (!group) { group = new Set(); listeners.set(id, group); }
  group.add(listener);
  return () => {
    group?.delete(listener);
    if (!group?.size) listeners.delete(id);
  };
}

function notify(id: string) { listeners.get(id)?.forEach(listener => listener()); }

export function setConversationQuery<T>(owner: string, key: string, data: T): void {
  const id = makeKey(owner, key);
  const old = entries.get(id);
  entries.set(id, { data, at: Date.now(), pending: old?.pending as Promise<T> | undefined });
  notify(id);
}

export async function getConversationQuery<T>(
  owner: string, key: string, staleMs: number, fetcher: () => Promise<T>,
  options?: { force?: boolean },
): Promise<T> {
  const id = makeKey(owner, key);
  const entry = entries.get(id) as CacheEntry<T> | undefined;
  // Never re-request a recently fetched entry, even when a component remounts.
  if (!options?.force && entry?.data !== undefined && Date.now() - entry.at < staleMs) {
    return entry.data;
  }
  // Deduplicate concurrent navigation, sidebar, and mutation-driven fetches.
  if (entry?.pending) return entry.pending;
  let request: Promise<T>;
  request = fetcher().then((data): T => {
    const latest = entries.get(id) as CacheEntry<T> | undefined;
    // A mutation may have installed newer data while this read was in flight.
    if (latest?.pending !== request) return latest?.data ?? data;
    setConversationQuery(owner, key, data);
    const written = entries.get(id) as CacheEntry<T> | undefined;
    if (written?.pending === request) delete written.pending;
    // Bound memory without touching browser storage.
    if (entries.size > MAX_ENTRIES) {
      const victim = [...entries.entries()].find(([k, v]) =>
        k !== id && !v.pending && !listeners.has(k));
      if (victim) entries.delete(victim[0]);
    }
    return data;
  }).catch(error => {
    const latest = entries.get(id);
    if (latest?.pending === request) delete latest.pending;
    throw error;
  });
  entries.set(id, { data: entry?.data, at: entry?.at ?? 0, pending: request });
  return request;
}

export function invalidateConversationQuery(owner: string, key: string): void {
  const id = makeKey(owner, key);
  const entry = entries.get(id);
  if (entry) entry.at = 0;
  notify(id);
}

/** Update the visible sidebar immediately after a successful server mutation. */
export function upsertConversationSummary(
  owner: string, conversation: { id: string; title: string; createdAt?: string; activeAt?: string },
): void {
  type Summary = { id: string; title: string; createdAt: string; activeAt: string };
  const cache = peekConversationQuery<{ items: Summary[]; nextCursor: string | null }>(owner, "list");
  if (!cache) return;
  const now = new Date().toISOString();
  const original = cache.items.find(item => item.id === conversation.id);
  const item: Summary = {
    id: conversation.id,
    title: conversation.title || original?.title || "新的学习对话",
    createdAt: conversation.createdAt || original?.createdAt || now,
    activeAt: conversation.activeAt || now,
  };
  setConversationQuery(owner, "list", {
    ...cache, items: [item, ...cache.items.filter(row => row.id !== item.id)].slice(0, 30),
  });
}

export function clearConversationQueryOwner(owner: string) {
  const prefix = owner + "::";
  for (const key of entries.keys()) {
    if (key.startsWith(prefix)) { entries.delete(key); notify(key); }
  }
}
