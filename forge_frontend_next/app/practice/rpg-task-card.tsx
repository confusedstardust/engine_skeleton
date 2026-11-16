"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, Gamepad2, LoaderCircle } from "lucide-react";
import { Button } from "../../components/ui/button";
import { withBasePath } from "../base-path";
import {
  conversationApi, type RpgCardStatus, type RpgJobStatus, type RpgMessageMetadata,
  type RpgQuote, type RpgSelections,
} from "../../lib/conversation-api";
import styles from "./rpg-task-card.module.css";

type Props = { conversationId: string; messageId: string; initial: RpgMessageMetadata };

// Matched to WebGALPipeline.RUN_ALL_PHASE_ORDER and actual store.transition phase strings.
const PHASES = [
  { title: "构思故事", codes: ["NARRATIVE_PLANNING"] },
  { title: "设计剧情与人物", codes: ["GAME_DESIGN", "GAME_DESIGN_COMPLETION"] },
  { title: "规划游戏素材", codes: ["ASSET_PLANNING"] },
  { title: "编排脚本与对话", codes: ["SCRIPT_REWRITE"] },
  { title: "处理音效与配音", codes: ["SOUND_EFFECT_PLANNING", "TTS_GENERATION", "TTS_PREVIEW_GENERATION"] },
  { title: "制作游戏素材", codes: ["ASSET_GENERATION"] },
  { title: "编写游戏场景", codes: ["SCENE_WRITING"] },
  { title: "校验内容与连接", codes: ["VALIDATING", "SCENE_CONNECTION_CHECK"] },
];

const inProgress = (state: string) =>
  ["CLAIMED", "JOB_CREATED", "STARTING", "STARTED"].includes(state);

export default function RpgTaskCard({ conversationId, messageId, initial }: Props) {
  const [card, setCard] = useState<RpgCardStatus | null>(null);
  const [duration, setDuration] = useState(initial.spec.duration_minutes);
  const [images, setImages] = useState(initial.spec.generate_images);
  const [voice, setVoice] = useState(initial.spec.enable_voice);
  const [quote, setQuote] = useState<RpgQuote | null>(null);
  const [job, setJob] = useState<RpgJobStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitLock = useRef(false);

  const state = card?.state ?? initial.state;
  const version = card?.specVersion ?? initial.spec_version;
  const jobId = card?.jobId ?? initial.job_id;
  const topic = card?.spec.topic ?? initial.spec.topic;
  const confirmed = card?.confirmedOptions ?? initial.confirmed_options ?? null;
  const voiceEnabled = confirmed?.enableVoice ?? voice;
  const imagesEnabled = confirmed?.generateImages ?? images;
  const statusTerminal = job?.status === "DONE" || job?.status === "FAILED";

  useEffect(() => {
    let alive = true;
    void conversationApi.rpgStatus(conversationId, messageId)
      .then(result => { if (alive) setCard(result); })
      .catch(() => { /* History metadata remains a safe read-only fallback. */ });
    return () => { alive = false; };
  }, [conversationId, messageId]);

  useEffect(() => {
    if (state !== "PREPARED") { setQuote(null); return; }
    let alive = true;
    setQuote(null); setError("");
    const selections: RpgSelections = {
      specVersion: version, durationMinutes: duration,
      generateImages: images, enableVoice: voice,
    };
    void conversationApi.rpgQuote(conversationId, messageId, selections)
      .then(value => { if (alive) setQuote(value); })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : "暂时无法报价"); });
    return () => { alive = false; };
  }, [conversationId, messageId, state, version, duration, images, voice]);

  useEffect(() => {
    if (!inProgress(state) && !jobId) return;
    if (statusTerminal) return;
    // Rejected / unknown jobs must not trigger infinite background polling.
    if (state === "START_REJECTED" || state === "NEEDS_REVIEW") {
      if (jobId) {
        void conversationApi.rpgJob(jobId).then(setJob).catch(() => {});
      }
      return;
    }
    let alive = true;
    let count = 0;
    const refresh = async () => {
      try {
        const current = await conversationApi.rpgStatus(conversationId, messageId);
        if (!alive) return;
        setCard(current);
        if (current.jobId) {
          const result = await conversationApi.rpgJob(current.jobId);
          if (alive) setJob(result);
        }
        if (alive) setError("");
      } catch {
        if (alive) setError("任务状态暂时无法查询，可以刷新页面后继续查看。");
      }
    };
    void refresh();
    const timer = window.setInterval(() => {
      count += 1;
      if (document.visibilityState === "hidden" && count % 4 !== 0) return;
      void refresh();
    }, 3000);
    return () => { alive = false; window.clearInterval(timer); };
  // Do not depend on the whole job object: every GET produces a new object and
  // would otherwise cause an unbounded immediate-fetch loop.
  }, [conversationId, messageId, state, jobId, statusTerminal]);

  const selections = (): RpgSelections => ({
    specVersion: version, durationMinutes: duration,
    generateImages: images, enableVoice: voice,
  });

  const confirm = async () => {
    if (submitLock.current || !quote || !quote.sufficientBalance || state !== "PREPARED") return;
    submitLock.current = true;
    setBusy(true); setError("");
    try {
      const result = await conversationApi.rpgConfirm(
        conversationId, messageId, selections(), quote.holdCredits);
      setCard(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认失败，请重新报价");
      try { setCard(await conversationApi.rpgStatus(conversationId, messageId)); }
      catch { /* Keep the durable initial card; never auto-submit again. */ }
    } finally {
      submitLock.current = false;
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (submitLock.current || state !== "PREPARED") return;
    submitLock.current = true;
    setBusy(true); setError("");
    try { setCard(await conversationApi.rpgCancel(conversationId, messageId)); }
    catch (err) { setError(err instanceof Error ? err.message : "取消失败"); }
    finally { submitLock.current = false; setBusy(false); }
  };

  const playable = Boolean(job && job.status === "DONE"
    && job.build_state === "CURRENT" && job.has_published_build === true);
  const failed = job?.status === "FAILED";
  const activeIndex = PHASES.findIndex(item => item.codes.includes(job?.phase ?? ""));

  return <section className={styles.card} aria-label="WebGAL 互动剧情游戏制作任务">
    <div className={styles.header}>
      <Gamepad2 size={20} aria-hidden="true" />
      <div><strong>{topic || "互动叙事游戏"}</strong><small>WebGAL · 自动制作</small></div>
    </div>
    {confirmed && state !== "PREPARED" && <p className={styles.description}>
      已确认配置：{confirmed.durationMinutes} 分钟 ·
      配图{confirmed.generateImages ? "开启" : "关闭"} ·
      配音{confirmed.enableVoice ? "开启" : "关闭"}
    </p>}
    {state === "PREPARED" ? <>
      <p className={styles.description}>已整理好创作要求，确认配置后才会创建游戏任务并使用 RPG 积分。</p>
      <label className={styles.setting}>预计体验时长
        <span className={styles.number}><input type="number" min={5} max={60}
          value={duration} disabled={busy} onChange={event => setDuration(Number(event.target.value))} /> 分钟</span>
      </label>
      <label className={styles.setting}><span>生成场景和角色配图</span>
        <input type="checkbox" checked={images} disabled={busy} onChange={event => setImages(event.target.checked)} />
      </label>
      <label className={styles.setting}><span>生成角色配音</span>
        <input type="checkbox" checked={voice} disabled={busy} onChange={event => setVoice(event.target.checked)} />
      </label>
      <div className={styles.quote} aria-live="polite">
        {quote ? <>预计预冻结 <strong>{quote.holdCredits} 积分</strong>
          {!quote.sufficientBalance && <span> · 当前余额不足</span>}</>
          : "正在核算 RPG 预冻结积分…"}
        <small>最终金额按教师工作台原有游戏计费规则结算。</small>
      </div>
      <div className={styles.actions}>
        <Button variant="primary" disabled={busy || !quote || !quote.sufficientBalance ||
          !Number.isInteger(duration) || duration < 5 || duration > 60}
          busy={busy} onClick={() => { void confirm(); }}>确认并开始制作</Button>
        <Button variant="ghost" disabled={busy} onClick={() => { void cancel(); }}>取消</Button>
      </div>
    </> : state === "CANCELLED" ? <p className={styles.description}>已取消本次制作，未创建游戏任务。</p>
      : <>
        {playable ? <p className={styles.description}>游戏制作完成，可以打开体验或进入工作台编辑。</p>
          : failed ? <p className={styles.description}>游戏制作遇到问题，原任务已保留。可进入工作台检查。</p>
          : job?.status === "DONE" ? <p className={styles.description}>生成已完成，但尚未检测到可播放构建。请进入工作台检查并发布可用版本。</p>
          : state === "START_REJECTED" ? <p className={styles.description}>任务未能启动。已保留原游戏 Job，请在工作台处理。</p>
          : state === "NEEDS_REVIEW" ? <p className={styles.description}>启动结果暂时无法确认，为避免重复扣费不会自动重试。请检查工作台。</p>
          : <p className={styles.description}><LoaderCircle size={15} className={styles.spin} aria-hidden="true" /> {job?.status === "QUEUED" ? "任务已排队，等待开始" : "正在制作游戏…"}</p>}
        {!failed && !playable && inProgress(state) && <ol className={styles.phases}>
          {PHASES.map((item, index) => <li key={item.title}
            className={activeIndex === index ? styles.active : ""}>
            <span className={styles.dot} />{item.codes.includes("TTS_GENERATION") && !voiceEnabled
              ? "规划游戏音效" : item.codes.includes("ASSET_GENERATION") && !imagesEnabled
                ? "准备游戏资源" : item.title}
          </li>)}
        </ol>}
        {jobId && card && <div className={styles.actions}>
          {playable && <a className={styles.link} href={withBasePath("/play/" + jobId + "/")}
            target="_blank" rel="noopener noreferrer">打开游戏 <ExternalLink size={14} /></a>}
          <a className={styles.link} href={withBasePath("/jobs/" + jobId)}
            target="_blank" rel="noopener noreferrer">编辑 / 查看任务 <ExternalLink size={14} /></a>
        </div>}
      </>}
    {error && <p className={styles.error} role="alert">{error}</p>}
  </section>;
}
