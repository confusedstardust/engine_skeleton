"use client";

import Link from "next/link";
import { BookOpen, Grid2X2, PenLine, Plus, Sparkles, Star } from "lucide-react";
import BrandLogo from "../../components/brand-logo";
import { useEffect, useState } from "react";
import { AccountMenu } from "../../components/account-menu";
import { Button } from "../../components/ui/button";
import { LoadingState } from "../../components/ui/state";
import { WorkspaceSidebar } from "../../components/ui/workspace-sidebar";
import { conversationApi, type ConversationSummary, type ConversationArtifact } from "../../lib/conversation-api";
import { workApi, type SavedWork } from "../../lib/work-api";
import styles from "./practice.module.css";
import navStyles from "./practice-navigation.module.css";

type View = "conversations" | "artifacts";

/** Portal-style shell; history queries return only summaries, never HTML/body. */
export default function PracticeNavigation({
  loggedIn, busy, refreshKey, serverRevision, serverEnabled, serverChecked,
  activeWorkId, activeConversationId, collapsed, onToggle, onNewConversation,
}: {
  loggedIn: boolean;
  busy: boolean;
  refreshKey: number;
  serverRevision: number;
  serverEnabled: boolean;
  serverChecked: boolean;
  activeWorkId: string | null;
  activeConversationId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
}) {
  const [recent, setRecent] = useState<SavedWork[]>([]);
  const [view, setView] = useState<View>("conversations");
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [artifacts, setArtifacts] = useState<ConversationArtifact[]>([]);
  const [nextConversations, setNextConversations] = useState<string | null>(null);
  const [nextArtifacts, setNextArtifacts] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loggedIn || !serverChecked) {
      setRecent([]); setConversations([]); setArtifacts([]);
      return;
    }
    let active = true;
    if (serverEnabled) {
      setLoading(true);
      void conversationApi.list().then(data => {
        if (!active) return;
        setConversations(data.items);
        setNextConversations(data.nextCursor);
      }).catch(() => { if (active) setError("会话列表暂时不可用"); })
        .finally(() => { if (active) setLoading(false); });
    } else {
      void workApi.list().then(({ works }) => {
        if (active) setRecent(works.slice(0, 5));
      }).catch(() => { /* Works are accessible through the history route. */ });
    }
    return () => { active = false; };
  }, [loggedIn, serverChecked, serverEnabled, refreshKey, serverRevision]);

  useEffect(() => {
    if (!loggedIn || !serverEnabled || view !== "artifacts") return;
    let active = true;
    setLoading(true);
    void conversationApi.artifacts().then(data => {
      if (!active) return;
      setArtifacts(data.items); setNextArtifacts(data.nextCursor);
    }).catch(() => { if (active) setError("产物列表暂时不可用"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loggedIn, serverEnabled, view, serverRevision]);

  async function more() {
    if (loading) return;
    const cursor = view === "conversations" ? nextConversations : nextArtifacts;
    if (!cursor) return;
    setLoading(true);
    try {
      if (view === "conversations") {
        const result = await conversationApi.list(cursor);
        setConversations(prev => [...prev, ...result.items.filter(item => !prev.some(p => p.id === item.id))]);
        setNextConversations(result.nextCursor);
      } else {
        const result = await conversationApi.artifacts(cursor);
        setArtifacts(prev => [...prev, ...result.items.filter(item =>
          !prev.some(p => p.artifactId === item.artifactId && p.conversationId === item.conversationId))]);
        setNextArtifacts(result.nextCursor);
      }
    } catch { setError("加载更多历史记录失败"); }
    finally { setLoading(false); }
  }

  return <WorkspaceSidebar
    className={styles.sidebar} ariaLabel="创作工作台导航"
    expanded={!collapsed} onToggle={onToggle}
    links={[
      { label: "发现灵感", href: "https://www.narrativeos.cn/teacher-ecosystem/", icon: <Grid2X2 aria-hidden="true" />, external: true },
      { label: "互动学习创作", href: "/practice", icon: <Sparkles aria-hidden="true" />, current: true },
      { label: "讲练工具", href: "/practice/resources", icon: <BookOpen aria-hidden="true" /> },
      { label: "我的作品", href: "/history", icon: <PenLine aria-hidden="true" /> },
      { label: "我的收藏", href: "https://www.narrativeos.cn/teacher-ecosystem/?view=favorites", icon: <Star aria-hidden="true" />, external: true },
    ]}
    action={{ label: "新建对话", icon: <Plus aria-hidden="true" />, disabled: busy, onClick: onNewConversation }}
    promo={<a className={navStyles.promo} href="https://www.narrativeos.cn/teacher-ecosystem/">
      <strong>好灵感，一起分享</strong>
      <span>去资源广场发现更多有趣的学习作品</span>
      <BrandLogo size={64} rounded={false} />
    </a>}
    footer={<AccountMenu />}>
    <section className={navStyles.navRecents} aria-label={serverEnabled ? "历史记录" : "最近作品"}>
      {serverEnabled ? <>
        <div className={navStyles.historyTabs} role="tablist" aria-label="历史分类">
          <Button variant="unstyled" role="tab" aria-selected={view === "conversations"}
            onClick={() => setView("conversations")}>对话</Button>
          <Button variant="unstyled" role="tab" aria-selected={view === "artifacts"}
            onClick={() => setView("artifacts")}>产物</Button>
        </div>
        {view === "conversations" ? conversations.map(item =>
          <Link key={item.id} href={"/practice/chat/" + item.id} title={item.title}
            className={navStyles.navRecentItem}
            aria-current={activeConversationId === item.id ? "page" : undefined}>
            <BookOpen size={17} strokeWidth={1.65} aria-hidden="true" />
            <span>{item.title}</span>
          </Link>
        ) : artifacts.map(item =>
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
      </> : <>
        <p className={navStyles.navSectionLabel}>最近作品</p>
        {recent.length ? recent.map(work =>
          <Link key={work.id} href={"/practice/?work=" + encodeURIComponent(work.id)}
            className={navStyles.navRecentItem}
            aria-current={activeWorkId === work.id ? "page" : undefined} title={work.title}>
            <BookOpen size={17} strokeWidth={1.65} aria-hidden="true" />
            <span>{work.title}</span>
          </Link>,
        ) : <p className={navStyles.navEmpty}>保存作品后，会在这里快速找到它们。</p>}
      </>}
    </section>
  </WorkspaceSidebar>;
}
