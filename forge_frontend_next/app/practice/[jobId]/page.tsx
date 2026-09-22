"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { withBasePath } from "../../base-path";
import { jsonAuthHeaders } from "../../invite-identity";

type QuizOption = {
  id: string;
  text: string;
};

type QuizQuestion = {
  id: string;
  type: "single_choice" | "judgement";
  prompt: string;
  options: QuizOption[];
  correct_option_ids: string[];
  explanation: string;
  knowledge_point: string;
  difficulty: "基础" | "进阶" | "挑战";
  teaching_tip: string;
};

type QuizPlan = {
  title: string;
  introduction: string;
  questions: QuizQuestion[];
};

type QuizResponse = {
  status: "NOT_GENERATED" | "QUEUED" | "RUNNING" | "READY" | "FAILED";
  error?: string | null;
  quiz?: QuizPlan | null;
  can_manage?: boolean;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    ...init,
    credentials: "include",
    headers: jsonAuthHeaders(init?.headers),
  });
  if (!response.ok) {
    const body = await response.text();
    let detail = body;
    try {
      const payload = JSON.parse(body) as { detail?: string | string[] };
      detail = Array.isArray(payload.detail) ? payload.detail.join("；") : payload.detail || body;
    } catch {
      // Keep the original response text when the backend did not return JSON.
    }
    throw new Error(detail || `请求失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export default function PracticePage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const [data, setData] = useState<QuizResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const value = await api<QuizResponse>(`/public/jobs/${jobId}/quiz`);
      setData(value);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "讲评练加载失败。");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (data?.status !== "QUEUED" && data?.status !== "RUNNING") return;
    const timer = window.setInterval(() => void refresh(), 2200);
    return () => window.clearInterval(timer);
  }, [data?.status, refresh]);

  const score = useMemo(() => {
    if (!data?.quiz) return 0;
    return data.quiz.questions.filter((question) =>
      revealed.has(question.id) && question.correct_option_ids.includes(answers[question.id] || ""),
    ).length;
  }, [answers, data?.quiz, revealed]);

  async function generate(regenerate: boolean) {
    if (regenerate && !window.confirm("重新生成会覆盖当前讲评练，确定继续吗？")) return;
    setActionBusy(true);
    setMessage("讲评练已进入生成队列，请稍候…");
    try {
      const value = await api<QuizResponse>(`/jobs/${jobId}/quiz`, {
        method: "POST",
        body: JSON.stringify({ regenerate }),
      });
      setData(value);
      if (regenerate) {
        setAnswers({});
        setRevealed(new Set());
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "讲评练生成失败。");
    } finally {
      setActionBusy(false);
    }
  }

  function reveal(question: QuizQuestion) {
    if (!answers[question.id]) {
      setMessage("请先选择一个答案。");
      return;
    }
    setMessage("");
    setRevealed((current) => new Set(current).add(question.id));
  }

  function resetPractice() {
    setAnswers({});
    setRevealed(new Set());
    setMessage("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const generating = data?.status === "QUEUED" || data?.status === "RUNNING";

  return (
    <>
      <header className="top-nav practice-nav">
        <div className="workspace-nav-leading">
          <Link className="brand brand-link" href="/">
            <div className="brand-seal" aria-hidden="true"><img src={withBasePath("/icon.png")} alt="" /></div>
            <div className="brand-copy"><span className="brand-name">临场 · 讲评练</span><span className="brand-subtitle">REVIEW & PRACTICE</span></div>
          </Link>
          <Link className="workspace-back" href={data?.can_manage ? `/jobs/${jobId}` : `/play/${jobId}/`}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
            <span>{data?.can_manage ? "返回作品" : "进入游戏"}</span>
          </Link>
        </div>
        <nav className="nav-links" aria-label="讲评练导航">
          {data?.quiz ? <button className="practice-nav-action" type="button" onClick={resetPractice}>重新作答</button> : null}
          <Link href="/history">我的作品</Link>
        </nav>
      </header>

      <main className="practice-page">
        {loading ? <section className="practice-state"><span className="practice-spinner" /><h1>正在读取讲评练</h1><p>正在准备作品的课后讲评内容。</p></section> : null}

        {!loading && (!data || data.status === "NOT_GENERATED") ? (
          <section className="practice-state">
            <span className="practice-state-mark">练</span>
            <p className="practice-kicker">TEACHER REVIEW KIT</p>
            <h1>为这份作品生成讲评练</h1>
            <p>系统会依据教学材料、学习目标和叙事大纲，生成单选与判断辨析卡片，并提供答案解析和教师追问建议。</p>
            {data?.can_manage ? (
              <button className="btn primary" type="button" disabled={actionBusy} onClick={() => void generate(false)}>{actionBusy ? "正在创建…" : "生成讲评练"}</button>
            ) : <small>这份作品暂未发布讲评练，请先体验游戏内容。</small>}
          </section>
        ) : null}

        {!loading && generating ? (
          <section className="practice-state">
            <span className="practice-spinner" />
            <p className="practice-kicker">GENERATING</p>
            <h1>正在生成讲评练</h1>
            <p>正在从作品中提取知识点、常见误区和可用于课堂讲评的追问。</p>
            {data?.quiz ? <small>上一版讲评练仍被保留，生成成功后会自动更新。</small> : null}
          </section>
        ) : null}

        {!loading && data?.status === "FAILED" ? (
          <section className="practice-state failed">
            <span className="practice-state-mark">!</span>
            <p className="practice-kicker">GENERATION FAILED</p>
            <h1>讲评练生成失败</h1>
            <p>{data.error || "模型暂时没有返回有效题目，请重新生成。"}</p>
            {data.can_manage ? <button className="btn primary" type="button" disabled={actionBusy} onClick={() => void generate(true)}>重新生成</button> : null}
          </section>
        ) : null}

        {!loading && data?.status === "READY" && data.quiz ? (
          <>
            <section className="practice-hero">
              <div>
                <p className="practice-kicker">REVIEW & PRACTICE · {data.quiz.questions.length} CARDS</p>
                <h1>{data.quiz.title}</h1>
                <span>{data.quiz.introduction}</span>
              </div>
              <aside>
                <small>当前进度</small>
                <strong>{revealed.size}<em> / {data.quiz.questions.length}</em></strong>
                <span>答对 {score} 题</span>
              </aside>
            </section>

            <section className="quiz-card-list">
              {data.quiz.questions.map((question, index) => {
                const isRevealed = revealed.has(question.id);
                const selected = answers[question.id];
                const correct = question.correct_option_ids[0];
                return (
                  <article className={`quiz-card ${question.type === "judgement" ? "judgement" : "choice"}`} key={question.id}>
                    <header>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <div><em>{question.type === "judgement" ? "判断辨析" : "单项选择"}</em><small>{question.difficulty} · {question.knowledge_point}</small></div>
                    </header>
                    <h2>{question.prompt}</h2>
                    <div className="quiz-options" role="radiogroup" aria-label={question.prompt}>
                      {question.options.map((option) => {
                        const optionCorrect = isRevealed && option.id === correct;
                        const optionWrong = isRevealed && option.id === selected && option.id !== correct;
                        return (
                          <button
                            className={`${selected === option.id ? "selected" : ""} ${optionCorrect ? "correct" : ""} ${optionWrong ? "wrong" : ""}`}
                            type="button"
                            role="radio"
                            aria-checked={selected === option.id}
                            disabled={isRevealed}
                            key={option.id}
                            onClick={() => setAnswers((current) => ({ ...current, [question.id]: option.id }))}
                          >
                            <span>{option.id}</span><strong>{option.text}</strong>
                          </button>
                        );
                      })}
                    </div>
                    {!isRevealed ? <button className="quiz-submit" type="button" onClick={() => reveal(question)}>确认答案</button> : (
                      <div className="quiz-explanation">
                        <strong>{selected === correct ? "回答正确" : `正确答案：${correct}`}</strong>
                        <p>{question.explanation}</p>
                        <div><span>教师讲评提示</span><p>{question.teaching_tip}</p></div>
                      </div>
                    )}
                  </article>
                );
              })}
            </section>

            <section className="practice-footer-actions">
              <button className="btn outline" type="button" onClick={resetPractice}>重新作答</button>
              {data.can_manage ? <button className="btn outline" type="button" disabled={actionBusy} onClick={() => void generate(true)}>{actionBusy ? "正在处理…" : "重新生成题目"}</button> : null}
              <Link className="btn primary" href={data.can_manage ? `/jobs/${jobId}` : `/play/${jobId}/`}>{data.can_manage ? "返回作品" : "进入游戏"}</Link>
            </section>
          </>
        ) : null}

        {message ? <div className="practice-toast" role="status">{message}</div> : null}
      </main>
    </>
  );
}
