"use client";

import Link from "next/link";
import { Plus, Sparkles, FolderOpen, BookOpen } from "lucide-react";
import { accountMessages } from "@narrativeos/ui/i18n";
import BrandLogo from "../../components/brand-logo";
import PracticeHistoryList from "./practice-history-list";
import { useEffect, useState } from "react";
import { CONVERSATION_STALE_MS, getConversationQuery, peekConversationQuery, setConversationQuery, subscribeConversationQuery } from "../../lib/conversation-query-cache";
import { AccountMenu } from "../../components/account-menu";
import { Button } from "../../components/ui/button";
import { LoadingState } from "../../components/ui/state";
import { useBrowserOrigin, WorkspaceSidebar } from "@narrativeos/ui/workspace-sidebar";
import { portalHref } from "@narrativeos/ui/app-links";
import { conversationApi, type ConversationSummary, type ConversationArtifact } from "../../lib/conversation-api";
import styles from "./practice.module.css";
import navStyles from "./practice-navigation.module.css";

type View = "conversations" | "artifacts";

/** Portal-style shell; history queries return only summaries, never HTML/body. */
export default function PracticeNavigation({
  loggedIn, busy, ownerId, serverReady, serverChecked,
  activeConversationId, collapsed, onToggle, onNewConversation,
}: {
  loggedIn: boolean;
  busy: boolean;
  ownerId: string | null;
  serverReady: boolean;
  serverChecked: boolean;
  activeConversationId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
}) {
  const origin = useBrowserOrigin();
  const plaza = portalHref("/teacher-ecosystem/", origin, process.env.NEXT_PUBLIC_SSO_ORIGIN);
  const [view, setView] = useState<View>("conversations");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [artifacts, setArtifacts] = useState<ConversationArtifact[]>([]);
  const [nextConversations, setNextConversations] = useState<string | null>(null);
  const [nextArtifacts, setNextArtifacts] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // The sidebar is a subscriber of summary cache, never a follower of every
  // chat-detail update or browser-focus event. Cache is scoped to SSO owner.
  useEffect(() => {
    if (!loggedIn || !serverReady || !serverChecked || !ownerId) {
      setConversations([]); setArtifacts([]); setLoading(false);
      return;
    }
    let active = true;
    const cached = peekConversationQuery<{ items: ConversationSummary[]; nextCursor: string | null }>(ownerId, "list");
    if (cached) { setConversations(cached.items); setNextConversations(cached.nextCursor); }
    else setLoading(true);
    const sync = () => {
      const value = peekConversationQuery<{ items: ConversationSummary[]; nextCursor: string | null }>(ownerId, "list");
      if (active && value) { setConversations(value.items); setNextConversations(value.nextCursor); }
    };
    const unsubscribe = subscribeConversationQuery(ownerId, "list", sync);
    void getConversationQuery(ownerId, "list", CONVERSATION_STALE_MS.list, () => conversationApi.list())
      .then(sync).catch(() => { if (active && !cached) setError("会话列表暂时不可用"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; unsubscribe(); };
  }, [loggedIn, serverChecked, serverReady, ownerId]);

  useEffect(() => {
    if (!loggedIn || !serverReady || !ownerId || view !== "artifacts") return;
    let active = true;
    const cached = peekConversationQuery<{ items: ConversationArtifact[]; nextCursor: string | null }>(ownerId, "artifacts");
    if (cached) { setArtifacts(cached.items); setNextArtifacts(cached.nextCursor); }
    else setLoading(true);
    const sync = () => {
      const value = peekConversationQuery<{ items: ConversationArtifact[]; nextCursor: string | null }>(ownerId, "artifacts");
      if (active && value) { setArtifacts(value.items); setNextArtifacts(value.nextCursor); }
    };
    const unsubscribe = subscribeConversationQuery(ownerId, "artifacts", sync);
    void getConversationQuery(ownerId, "artifacts", CONVERSATION_STALE_MS.artifacts,
      () => conversationApi.artifacts()).then(sync)
      .catch(() => { if (active && !cached) setError("产物列表暂时不可用"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; unsubscribe(); };
  }, [loggedIn, serverReady, ownerId, view]);

  async function more() {
    if (loading) return;
    const cursor = view === "conversations" ? nextConversations : nextArtifacts;
    if (!cursor) return;
    setLoading(true);
    try {
      if (view === "conversations") {
        const result = await conversationApi.list(cursor);
        const combined = [...conversations, ...result.items.filter(item => !conversations.some(p => p.id === item.id))];
        setConversations(combined);
        setNextConversations(result.nextCursor);
        if (ownerId) setConversationQuery(ownerId, "list", { items: combined, nextCursor: result.nextCursor });
      } else {
        const result = await conversationApi.artifacts(cursor);
        const combined = [...artifacts, ...result.items.filter(item =>
          !artifacts.some(p => p.artifactId === item.artifactId && p.conversationId === item.conversationId))];
        setArtifacts(combined);
        setNextArtifacts(result.nextCursor);
        if (ownerId) setConversationQuery(ownerId, "artifacts", { items: combined, nextCursor: result.nextCursor });
      }
    } catch { setError("加载更多历史记录失败"); }
    finally { setLoading(false); }
  }

  return <WorkspaceSidebar
    className={styles.sidebar} ariaLabel="创作工作台导航"
    expanded={!collapsed} onToggle={onToggle}
    toggleLabel={collapsed ? "展开侧栏" : "收起侧栏"}
    brandHref="/" tagline="创造新的知识互动体验" LinkComponent={Link}
    logo={size => <BrandLogo size={size} rounded={size === 64} />}
    links={{
      discover: { href: plaza, external: true },
      create: { href: "/practice", current: true },
      works: { href: "/history" },
      assets: { href: "/assets" },
    }}
    secondaryLinks={[
      { label: "讲练工具", href: "/practice/resources", icon: <BookOpen aria-hidden="true" /> },
      { label: accountMessages["zh-CN"].myAssets, href: "/my-assets", icon: <FolderOpen aria-hidden="true" /> },
    ]}
    action={{ label: "新建对话", icon: <Plus aria-hidden="true" />, disabled: busy, onClick: onNewConversation }}
    footer={<AccountMenu dock />}>
    <section className={navStyles.navRecents} aria-label="历史会话和产物">
      {loggedIn && serverReady ? <>
        <div className={navStyles.historyTabs} role="tablist" aria-label="历史分类">
          <Button variant="unstyled" role="tab" aria-selected={view === "conversations"}
            onClick={() => setView("conversations")}>对话</Button>
          <Button variant="unstyled" role="tab" aria-selected={view === "artifacts"}
            onClick={() => setView("artifacts")}>产物</Button>
        </div>
        <div className={navStyles.historyList}>
          {view === "conversations" && busy && !activeConversationId &&
            <div className={navStyles.navRecentItem} role="status" aria-live="polite">
              <span className={navStyles.navBookWorking}><BookOpen size={17} strokeWidth={1.65} aria-hidden="true" /></span>
              <span>正在理解需求…</span>
            </div>}
        {view === "conversations" ?
          <PracticeHistoryList items={conversations} ownerId={ownerId}
            activeConversationId={activeConversationId} activeBusy={busy} /> : artifacts.map(item =>
          <Link key={item.conversationId + ":" + item.artifactId}
            href={"/practice/chat/" + item.conversationId + "?artifact=" + item.artifactId}
            className={navStyles.navRecentItem} title={item.title}>
            <Sparkles size={17} strokeWidth={1.65} aria-hidden="true" />
            <span>{item.title}</span>
          </Link>
        )}
        {loading && <LoadingState inline className={navStyles.navLoading}>正在读取历史…</LoadingState>}
        {!loading && !(view === "conversations" ? conversations.length : artifacts.length) &&
          <p className={navStyles.navEmpty}>{view === "conversations" ? "还没有历史对话。" : "还没有关联的产物。"}</p>}
        {error && <p className={navStyles.navEmpty} role="alert">{error}</p>}
        {(view === "conversations" ? nextConversations : nextArtifacts) &&
          <Button variant="ghost" size="sm" disabled={loading} onClick={() => { void more(); }}>加载更多</Button>}
        </div>
      </> : <p className={navStyles.navEmpty}>
        {!loggedIn ? "请先登录以查看历史对话。" :
          !serverChecked ? "正在检查会话数据库…" :
          "会话数据库尚未完成迁移。已保存作品仍可从「我的作品」打开。"}
      </p>}
    </section>
  </WorkspaceSidebar>;
}
