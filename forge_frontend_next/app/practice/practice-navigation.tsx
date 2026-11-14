"use client";

import Link from "next/link";
import { BookOpen, Grid2X2, PenLine, Plus, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { AccountMenu } from "../../components/account-menu";
import BrandLogo from "../../components/brand-logo";
import { WorkspaceSidebar } from "../../components/ui/workspace-sidebar";
import { workApi, type SavedWork } from "../../lib/work-api";
import styles from "./practice.module.css";

/** Practice-specific routes and recent-work data; the navigation UI is shared. */
export default function PracticeNavigation({
  loggedIn, busy, refreshKey, collapsed, onToggle, onNewConversation,
}: {
  loggedIn: boolean;
  busy: boolean;
  refreshKey: number;
  collapsed: boolean;
  onToggle: () => void;
  onNewConversation: () => void;
}) {
  const [recent, setRecent] = useState<SavedWork[]>([]);
  useEffect(() => {
    if (!loggedIn) { setRecent([]); return; }
    let active = true;
    workApi.list().then(({ works }) => {
      if (active) setRecent(works.slice(0, 5));
    }).catch(() => { /* Keep navigation usable when recent works are unavailable. */ });
    return () => { active = false; };
  }, [loggedIn, refreshKey]);

  return <WorkspaceSidebar
    className={styles.sidebar} ariaLabel="创作工作台导航"
    expanded={!collapsed} onToggle={onToggle}
    links={[
      { label: "发现灵感", href: "https://www.narrativeos.cn/teacher-ecosystem/", icon: <Grid2X2 aria-hidden="true" />, external: true },
      { label: "互动学习创作", href: "/practice", icon: <Sparkles aria-hidden="true" />, current: true },
      { label: "我的作品", href: "/history", icon: <PenLine aria-hidden="true" /> },
    ]}
    action={{ label: "新建对话", icon: <Plus aria-hidden="true" />, disabled: busy, onClick: onNewConversation }}
    footer={<AccountMenu dock={{
      loginLabel: "登录 NarrativeOS",
      loginContent: <><span className="account-trigger-avatar" aria-hidden="true"><BrandLogo size={25} rounded /></span><span>登录 NarrativeOS</span></>,
    }} />}>
    <section className={styles.navRecents} aria-label="最近作品">
      <p className={styles.navSectionLabel}>最近作品</p>
      {recent.length ? recent.map(work =>
        <Link key={work.id} href={"/practice/?work=" + encodeURIComponent(work.id)}
          className={styles.navRecentItem} title={work.title}>
          <BookOpen size={17} strokeWidth={1.65} aria-hidden="true" />
          <span>{work.title}</span>
        </Link>,
      ) : <p className={styles.navEmpty}>保存作品后，会在这里快速找到它们。</p>}
    </section>
  </WorkspaceSidebar>;
}
