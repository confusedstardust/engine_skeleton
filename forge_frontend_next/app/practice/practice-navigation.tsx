"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { workApi, type SavedWork } from "../../lib/work-api";
import { withBasePath } from "../base-path";
import styles from "./practice.module.css";

function NavGlyph({ kind }: { kind: "spark" | "grid" | "archive" | "plus" | "book" }) {
  const path = {
    spark: <><path d="m12 2 2.4 7.6L22 12l-7.6 2.4L12 22l-2.4-7.6L2 12l7.6-2.4Z"/></>,
    grid: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    archive: <><rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v11h14V9m-10 5h6"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    book: <><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1m0-15c3-2 6-2 9-1v15c-3-1-6-1-9 1M12 5v15"/></>,
  }[kind];
  return <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
    strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{path}</svg>;
}

export default function PracticeNavigation({
  loggedIn, busy, refreshKey, onNewConversation,
}: {
  loggedIn: boolean;
  busy: boolean;
  refreshKey: number;
  onNewConversation: () => void;
}) {
  const [recent, setRecent] = useState<SavedWork[]>([]);
  useEffect(() => {
    if (!loggedIn) { setRecent([]); return; }
    let active = true;
    workApi.list().then(({ works }) => {
      if (active) setRecent(works.slice(0, 5));
    }).catch(() => { /* The navigation works even if the saved-work API is down. */ });
    return () => { active = false; };
  }, [loggedIn, refreshKey]);

  return <aside className={styles.sidebar} aria-label="创作工作台导航">
    <Link href="/" className={styles.navBrand}>
      <span className={styles.navBrandIcon} aria-hidden="true">N</span>
      <span><strong>NarrativeOS</strong><small>让知识成为探索</small></span>
    </Link>
    <p className={styles.navSectionLabel}>工作台</p>
    <nav className={styles.navItems} aria-label="工作台">
      <a className={styles.navItem} href="https://www.narrativeos.cn/teacher-ecosystem/" rel="noopener noreferrer">
        <NavGlyph kind="grid" />发现灵感
      </a>
      <span className={`${styles.navItem} ${styles.navItemActive}`} aria-current="page">
        <NavGlyph kind="spark" />互动学习创作
      </span>
      <Link className={styles.navItem} href="/history">
        <NavGlyph kind="archive" />我的作品
      </Link>
    </nav>
    <div className={styles.navDivider} />
    <button type="button" className={styles.navNewButton} disabled={busy} onClick={onNewConversation}>
      <NavGlyph kind="plus" />新建对话
    </button>
    <div className={styles.navRecents}>
      <p className={styles.navSectionLabel}>最近作品</p>
      {recent.length ? recent.map(work =>
        <a key={work.id} className={styles.navRecentItem} title={work.title}
          href={withBasePath(`/practice/?work=${work.id}`)}>
          <NavGlyph kind="book" />
          <span>{work.title}</span>
        </a>,
      ) : <p className={styles.navEmpty}>保存作品后，会在这里快速找到它们。</p>}
    </div>
    <div className={styles.navBottom}>
      <span className={styles.navBottomStar} aria-hidden="true">✦</span>
      <strong>灵感，从一个问题开始</strong>
      <span>把教材与想法变成可探索的学习体验。</span>
    </div>
  </aside>;
}
