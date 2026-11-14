"use client";

import { useEffect, useState } from "react";
import styles from "./practice.module.css";
import type { LearningPlan } from "./live-progress";

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
  timeline, elapsedMs = 0, active = false, learningPlan, publicBrief, briefStreaming = false,
}: {
  timeline: TimelineEvent[];
  elapsedMs?: number;
  active?: boolean;
  learningPlan?: LearningPlan;
  publicBrief?: string;
  briefStreaming?: boolean;
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
    {visible && publicBrief && <div className={styles.publicBrief} aria-label="实时需求理解摘要">
      <strong>我对学习任务的理解 {briefStreaming ? "· 实时生成中" : ""}</strong>
      <p>{publicBrief}{briefStreaming && <span className={styles.publicBriefCaret} aria-hidden="true" />}</p>
    </div>}
    {visible && learningPlan && <div className={styles.learningPlan}>
      <strong>本次教学设计</strong>
      <p><b>学习目标</b>{learningPlan.learning_goal}</p>
      <p><b>互动方式</b>{learningPlan.interaction_method}</p>
      {learningPlan.key_concepts.length > 0 && <p><b>关键知识</b>{learningPlan.key_concepts.join(" · ")}</p>}
    </div>}
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
