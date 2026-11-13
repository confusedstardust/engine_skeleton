"use client";

import { useEffect, useState } from "react";
import { forgeApi } from "../lib/api-client";
import { ModalBody, ModalFrame } from "./ui/modal";

type PracticeTool = {
  job_id: string;
  title: string;
  summary: string | null;
  cover_url: string | null;
  play_url: string;
  quiz_url: string | null;
};

export default function PracticeToolsDialog({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<PracticeTool[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    forgeApi<{ items: PracticeTool[] }>("/practice-tools", { signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setItems(data.items);
      })
      .catch(error => {
        if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "讲练工具加载失败");
      });
    return () => controller.abort();
  }, [attempt]);

  return (
    <ModalFrame title="讲练工具" onClose={onClose}>
      <div className="scene-dialog-layer">
        <ModalBody>
          <section className="scene-dialog">
            <div className="scene-dialog-head">
              <h2>讲练工具</h2>
              <button className="dialog-close" type="button" onClick={onClose} aria-label="关闭">×</button>
            </div>
            {error ? (
              <div>
                <p role="alert">{error}</p>
                <button className="btn outline" type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }}>重试</button>
              </div>
            ) : !items ? <p role="status">正在加载讲练工具…</p> : !items.length ? <p>暂无讲练工具。</p> : (
              <div className="scene-grid">
                {items.map(item => (
                  <article className="asset-library-card" key={item.job_id}>
                    {item.cover_url && <div className="asset-library-preview"><img src={item.cover_url} alt="" loading="lazy" decoding="async" /></div>}
                    <div className="asset-library-card-body">
                      <h3>{item.title}</h3>
                      {item.summary && <p>{item.summary}</p>}
                      <div className="admin-actions">
                        <a href={item.play_url}>打开作品</a>
                        {item.quiz_url && <a href={item.quiz_url}>打开习题</a>}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </ModalBody>
      </div>
    </ModalFrame>
  );
}
