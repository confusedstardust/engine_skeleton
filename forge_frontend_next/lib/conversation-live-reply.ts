/** Per-account, per-conversation ephemeral streamed text. Never persisted to browser storage. */
type LiveReply = { text: string };
const live = new Map<string, LiveReply>();
const listeners = new Map<string, Set<() => void>>();
function key(owner: string, conversationId: string) { return owner + "::" + conversationId; }
export function getLiveReply(owner: string, conversationId: string): string {
  return live.get(key(owner, conversationId))?.text ?? "";
}
export function setLiveReply(owner: string, conversationId: string, text: string): void {
  const id = key(owner, conversationId);
  live.set(id, { text });
  listeners.get(id)?.forEach(listener => listener());
}
export function clearLiveReply(owner: string, conversationId: string): void {
  const id = key(owner, conversationId);
  if (!live.has(id)) return;
  live.delete(id);
  listeners.get(id)?.forEach(listener => listener());
}
export function subscribeLiveReply(owner: string, conversationId: string, listener: () => void): () => void {
  const id = key(owner, conversationId);
  let group = listeners.get(id);
  if (!group) { group = new Set(); listeners.set(id, group); }
  group.add(listener);
  return () => {
    group?.delete(listener);
    if (!group?.size) listeners.delete(id);
  };
}
