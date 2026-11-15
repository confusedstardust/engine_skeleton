"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { BookOpen, PenLine, Pin, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { conversationApi, type ConversationSummary, type ConversationDetail } from "../../lib/conversation-api";
import {
  getConversationQuery, invalidateConversationQuery, peekConversationQuery,
  setConversationQuery, upsertConversationSummary,
} from "../../lib/conversation-query-cache";
import styles from "./practice-navigation.module.css";

type Props = {
  items: ConversationSummary[];
  activeConversationId: string | null;
  ownerId: string | null;
};

export default function PracticeHistoryList({ items, activeConversationId, ownerId }: Props) {
  const router = useRouter();
  const [menu, setMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (editingId) inputRef.current?.focus(); }, [editingId]);
  useEffect(() => {
    if (!menu) return;
    const dismiss = (event: Event) => {
      if (event.type === "keydown" && (event as KeyboardEvent).key !== "Escape") return;
      if (event.type === "pointerdown" && menuRef.current?.contains(event.target as Node)) return;
      setMenu(null);
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", dismiss);
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    menuRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", dismiss);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [menu]);

  function openMenu(id: string, x: number, y: number) {
    setMenu({
      id,
      x: Math.max(8, Math.min(x, window.innerWidth - 196)),
      y: Math.max(8, Math.min(y, window.innerHeight - 144)),
    });
  }

  async function refreshList() {
    if (!ownerId) return;
    invalidateConversationQuery(ownerId, "list");
    await getConversationQuery(ownerId, "list", 0, () => conversationApi.list(), { force: true });
  }

  async function update(id: string, changes: { title?: string; pinned?: boolean }) {
    if (!ownerId || mutatingId) return;
    setMutatingId(id); setError("");
    try {
      const updated = await conversationApi.update(id, changes);
      upsertConversationSummary(ownerId, updated);
      const key = "detail:" + id;
      const detail = peekConversationQuery<ConversationDetail>(ownerId, key);
      if (detail) setConversationQuery(ownerId, key, { ...detail, conversation: updated });
      await refreshList();
    } catch { setError("更新会话失败，请稍后重试。"); }
    finally { setMutatingId(null); }
  }

  function rename(id: string) {
    const title = editingTitle.trim();
    setEditingId(null);
    if (!title || title.length > 160) { setError("标题长度需为 1～160 个字符。"); return; }
    if (items.find(item => item.id === id)?.title !== title) void update(id, { title });
  }

  async function remove(id: string) {
    setMenu(null);
    if (!ownerId || mutatingId) return;
    if (!window.confirm("确定删除这段历史会话吗？此操作不可撤销，已单独保存的作品不会被删除。")) return;
    setMutatingId(id); setError("");
    try {
      await conversationApi.remove(id);
      const cached = peekConversationQuery<{ items: ConversationSummary[]; nextCursor: string | null }>(ownerId, "list");
      if (cached) setConversationQuery(ownerId, "list", { ...cached, items: cached.items.filter(item => item.id !== id) });
      if (activeConversationId === id) router.push("/practice");
      await refreshList();
    } catch { setError("删除会话失败。正在执行的任务结束后才可删除。"); }
    finally { setMutatingId(null); }
  }

  const selected = items.find(item => item.id === menu?.id);
  return <>
    {items.map(item => editingId === item.id ?
      <form key={item.id} className={styles.navRecentItem}
        onSubmit={event => { event.preventDefault(); rename(item.id); }}>
        <input ref={inputRef} aria-label="编辑会话标题" maxLength={160}
          className={styles.renameInput} value={editingTitle}
          onChange={event => setEditingTitle(event.target.value)}
          onBlur={() => setEditingId(null)}
          onKeyDown={event => {
            if (event.key === "Escape") { event.preventDefault(); setEditingId(null); }
          }} />
      </form> :
      <Link key={item.id} href={"/practice/chat/" + item.id} title={item.title}
        className={styles.navRecentItem}
        aria-current={activeConversationId === item.id ? "page" : undefined}
        onContextMenu={event => { event.preventDefault(); openMenu(item.id, event.clientX, event.clientY); }}
        onKeyDown={event => {
          if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
            event.preventDefault();
            const rect = event.currentTarget.getBoundingClientRect();
            openMenu(item.id, rect.right, rect.top);
          }
        }}>
        <BookOpen size={17} strokeWidth={1.65} aria-hidden="true" />
        <span>{item.title}</span>
        {item.pinned && <Pin className={styles.pinnedIcon} size={13} aria-label="已置顶" />}
      </Link>,
    )}
    {error && <p className={styles.navEmpty} role="alert">{error}</p>}
    {menu && selected && typeof document !== "undefined" && createPortal(
      <div ref={menuRef} role="menu" aria-label="会话操作" className={styles.historyMenu}
        style={{ left: menu.x, top: menu.y }}>
        <button type="button" role="menuitem" disabled={Boolean(mutatingId)}
          onClick={() => { setEditingId(selected.id); setEditingTitle(selected.title); setMenu(null); }}>
          <PenLine size={15} aria-hidden="true" />编辑标题
        </button>
        <button type="button" role="menuitem" disabled={Boolean(mutatingId)}
          onClick={() => { setMenu(null); void update(selected.id, { pinned: !selected.pinned }); }}>
          <Pin size={15} aria-hidden="true" />{selected.pinned ? "取消置顶" : "置顶会话"}
        </button>
        <button type="button" role="menuitem" disabled={Boolean(mutatingId)}
          className={styles.historyMenuDanger} onClick={() => { void remove(selected.id); }}>
          <Trash2 size={15} aria-hidden="true" />删除会话
        </button>
      </div>, document.body,
    )}
  </>;
}
