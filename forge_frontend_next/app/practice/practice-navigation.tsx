"use client";

import Link from "next/link";
import { BookOpen, Grid2X2, PenLine, Plus, Sparkles, Star } from "lucide-react";
import BrandLogo from "../../components/brand-logo";
import { useEffect, useState } from "react";
import { AccountMenu } from "../../components/account-menu";
import { WorkspaceSidebar } from "../../components/ui/workspace-sidebar";
import { workApi, type SavedWork } from "../../lib/work-api";
import styles from "./practice.module.css";
import navStyles from "./practice-navigation.module.css";

/** Practice-specific routes and recent-work data; the navigation UI is shared. */
export default function PracticeNavigation({
  loggedIn, busy, refreshKey, activeWorkId, collapsed, onToggle, onNewConversation,
}: {
  loggedIn: boolean;
  busy: boolean;
  refreshKey: number;
  activeWorkId: string | null;
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
    <section className={navStyles.navRecents} aria-label="最近作品">
      <p className={navStyles.navSectionLabel}>最近作品</p>
      {recent.length ? recent.map(work =>
        <Link key={work.id} href={"/practice/?work=" + encodeURIComponent(work.id)}
          className={navStyles.navRecentItem} aria-current={activeWorkId === work.id ? "page" : undefined} title={work.title}>
          <BookOpen size={17} strokeWidth={1.65} aria-hidden="true" />
          <span>{work.title}</span>
        </Link>,
      ) : <p className={navStyles.navEmpty}>保存作品后，会在这里快速找到它们。</p>}
    </section>
  </WorkspaceSidebar>;
}
