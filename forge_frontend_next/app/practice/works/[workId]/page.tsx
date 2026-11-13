"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { forgeApi } from "../../../../lib/api-client";
import { withBasePath } from "../../../base-path";
import styles from "./public-work.module.css";

type PublicWork = {
  id: string;
  title: string;
  summary?: string;
  kind: string;
  subject?: string | null;
  grade?: string | null;
  tags?: string[];
  version: number;
  published_at?: string;
};

/** A public read-only player; no owner cookie or private artifact URL is used. */
export default function PublicWorkPage() {
  const { workId } = useParams<{ workId: string }>();
  const [work, setWork] = useState<PublicWork | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!/^[0-9a-f]{32}$/.test(workId || "")) { setError("作品链接无效"); setLoading(false); return; }
    let active = true;
    forgeApi<PublicWork>(`/public/works/${workId}`).then(result => {
      if (active) setWork(result);
    }).catch(() => { if (active) setError("作品未发布、已撤回，或暂时不可访问"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workId]);
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/practice">NarrativeOS <span>／ 互动学习作品</span></Link></header>
    {loading && <p className={styles.message}>正在读取互动学习作品…</p>}
    {error && !loading && <p role="alert" className={styles.message}>{error}</p>}
    {work && !loading && <section className={styles.content}>
      <div className={styles.title}><h1>{work.title}</h1>
        <p>{[work.subject, work.grade, `V${work.version}`].filter(Boolean).join(" · ")}</p>
        {work.summary && <p>{work.summary}</p>}</div>
      <div className={styles.viewer}>
        <iframe title={work.title} sandbox="allow-scripts" allow="fullscreen" allowFullScreen
          referrerPolicy="no-referrer" src={withBasePath(`/api/forge/public/works/${work.id}/index.html`)} />
      </div>
      <p className={styles.note}>这是创作者发布的互动学习资源。请自行核对知识准确性。</p>
    </section>}
  </main>;
}
