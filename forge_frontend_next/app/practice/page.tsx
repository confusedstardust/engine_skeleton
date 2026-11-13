"use client";

import { useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import { forgeApi } from "../../lib/api-client";
import { WorkbenchHeader } from "../../components/workbench-header";
import styles from "./practice-resources.module.css";

type Resource = {
  job_id: string;
  title: string;
  summary: string | null;
  cover_url: string | null;
  play_url: string;
  quiz_url: string | null;
};

export default function PracticePage() {
  const [items, setItems] = useState<Resource[] | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    forgeApi<{ items: Resource[] }>("/practice-tools", { signal: controller.signal })
      .then(({ items }) => { if (!controller.signal.aborted) setItems(items); })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [attempt]);

  return (
    <main className={styles.page}>
      <WorkbenchHeader title="讲练工具" subtitle="CLASSROOM RESOURCES" />
      <section className={styles.content} aria-label="课堂资源">
        <h1>课堂资源</h1>
        {error ? <p role="alert">课堂资源加载失败。 <Button onClick={() => { setError(false); setAttempt(value => value + 1); }}>重试</Button></p>
          : !items ? <p role="status">正在加载课堂资源…</p>
          : !items.length ? <p>暂无课堂资源。</p>
          : <div className={styles.resourceGrid}>
            {items.map(item => (
              <article className={styles.resourceCard} key={item.job_id}>
                {item.cover_url && <img src={item.cover_url} alt="" loading="lazy" />}
                <h2>{item.title}</h2>
                {item.summary && <p>{item.summary}</p>}
                <div className={styles.actions}>
                  <a href={item.play_url} target="_blank" rel="noopener noreferrer">打开资源 ↗</a>
                  {item.quiz_url && <a href={item.quiz_url} target="_blank" rel="noopener noreferrer">打开习题 ↗</a>}
                </div>
              </article>
            ))}
          </div>}
      </section>
    </main>
  );
}
