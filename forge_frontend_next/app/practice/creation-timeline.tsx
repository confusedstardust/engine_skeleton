"use client";

import { useEffect, useState } from "react";
import styles from "./practice.module.css";

export type TimelineEvent = {
  id: string;
  phase: string;
  title: string;
  detail?: string;
  status: "running" | "completed" | "failed";
  started_at: string;
  completed_at?: string | null;
  duration_ms?: number | null;
};

function formatDuration(ms: number) {
  const sec = Math.max(0, Math.floor(ms / 1000));
  if (sec < 60) return `${sec}秒`;
  return `${Math.floor(sec / 60)}分${String(sec % 60).padStart(2, "0")}秒`;
}

/** Observable server stages, not a transcript of hidden model reasoning. */
export default function CreationTimeline({
  timeline, elapsedMs = 0, active = false,
}: {
  timeline: TimelineEvent[];
  elapsedMs?: number;
  active?: boolean;
}) {
  const [visible, setVisible] = useState(true);
  const [start, setStart] = useState(() => Date.now());
  useEffect(() => { setStart(Date.now()); }, [elapsedMs, active]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setTick(value => value + 1), 1000);
    return () => window.clearInterval(id);
  }, [active]);
  const displayedMs = elapsedMs + (active ? Math.max(0, Date.now() - start) : 0);
  const elapsed = formatDuration(displayedMs);
  const complete = timeline.length > 0 && timeline.every(event => event.status === "completed");

  // Suppress unused tick lint warnings while reading real time from Date.now().
  void tick;
  return <section className={styles.timeline} aria-label="创作过程">
    <button type="button" className={styles.timelineToggle} aria-expanded={visible} onClick={() => setVisible(!visible)}>
      <span className={styles.timelineHeading}>{active ? "✦ 正在创作" : complete ? "✓ 创作过程" : "创作过程"}</span>
      <span className={styles.timelineElapsed}>用时 {elapsed}</span>
      <span aria-hidden="true">{visible ? "⌃" : "⌄"}</span>
    </button>
    {visible && <ol className={styles.timelineList}>
      {timeline.map(event => <li key={event.id} className={styles.timelineItem}>
        <span aria-label={event.status === "completed" ? "已完成" : event.status === "failed" ? "已失败" : "进行中"} className={styles.timelineMarker}>
          {event.status === "completed" ? "✓" : event.status === "failed" ? "!" : "·"}
        </span>
        <div className={styles.timelineBody}>
          <div className={styles.timelineRow}>
            <strong>{event.title}</strong>
            <span>{event.duration_ms != null ? formatDuration(event.duration_ms) :
              event.status === "running" && active
                ? formatDuration(Math.max(0, Date.now() - new Date(event.started_at).getTime()))
                : event.status === "running" ? "进行中" : ""}</span>
          </div>
          {event.detail && <p>{event.detail}</p>}
        </div>
      </li>)}
    </ol>}
  </section>;
}
