"use client";
import { WorkbenchHeader } from "../../../components/workbench-header";
import { usePolling } from "../../../hooks/use-polling";
import { forgeApi as api } from "../../../lib/api-client";
import type { QuizResponse } from "../../../domain/quiz";






import { ConfirmDialog } from "../../../components/ui/modal";
import { use, useMemo, useState } from "react";

export default function PracticePage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  return <PracticeWorkspace key={jobId} jobId={jobId} />;
}

function PracticeWorkspace({ jobId }: { jobId: string }) {
  const [data, setData] = useState<QuizResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmRegenerate, setConfirmRegenerate] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  usePolling(async signal => {
    const value = await api<QuizResponse>(`/public/jobs/${jobId}/quiz`, { signal });
    if (!signal.aborted) { setData(value); setMessage(""); setLoading(false); }
    return value.status === "QUEUED" || value.status === "RUNNING";
  }, {
    intervalMs: 2200, resetKey: jobId,
    enabled: !data || data.status === "QUEUED" || data.status === "RUNNING",
    onError: error => { setMessage(error instanceof Error ? error.message : "习题加载失败。"); setLoading(false); },
  });

  const score = useMemo(() => {
    if (!data?.quiz) return 0;
    return data.quiz.questions.filter((question) =>
      revealed.has(question.id) && question.correct_option_ids.includes(answers[question.id] || ""),
    ).length;
  }, [answers, data?.quiz, revealed]);

  async function generate(regenerate: boolean) {
    setConfirmRegenerate(false);
    setActionBusy(true);
    setMessage("习题已进入生成队列，请稍候…");
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
      setMessage(error instanceof Error ? error.message : "习题生成失败。");
    } finally {
      setActionBusy(false);
    }
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
      <WorkbenchHeader title="临场 · 习题" subtitle="PRACTICE" className="top-nav practice-nav" label="习题导航" fallback={data?.can_manage ? `/jobs/${jobId}` : `/play/${jobId}/`}>
{data?.quiz ? <button className="top-nav-action" type="button" onClick={resetPractice}>重新作答</button> : null}
{data?.quiz && data.can_manage ? <button className="top-nav-action" type="button" disabled={actionBusy || generating} onClick={() => setConfirmRegenerate(true)}>{actionBusy || generating ? "正在生成…" : "重新生成题目"}</button> : null}
</WorkbenchHeader>

      <ConfirmDialog open={confirmRegenerate} title="重新生成题目？" description="重新生成会覆盖当前习题。" onCancel={() => setConfirmRegenerate(false)} onConfirm={() => void generate(true)} />
      <main className="practice-page">
        {loading ? <section className="practice-state"><span className="practice-spinner" /><h1>正在读取习题</h1><p>正在准备作品的课后习题内容。</p></section> : null}

        {!loading && (!data || data.status === "NOT_GENERATED") ? (
          <section className="practice-state">
            <span className="practice-state-mark">练</span>
            <p className="practice-kicker">TEACHER REVIEW KIT</p>
            <h1>为这份作品生成习题</h1>
            <p>系统会依据教学材料、学习目标和叙事大纲，生成单选与判断习题，并提供答案解析。</p>
            {data?.can_manage ? (
              <button className="btn primary" type="button" disabled={actionBusy} onClick={() => void generate(false)}>{actionBusy ? "正在创建…" : "生成习题"}</button>
            ) : <small>这份作品暂未发布习题，请先体验游戏内容。</small>}
          </section>
        ) : null}

        {!loading && generating ? (
          <section className="practice-state">
            <span className="practice-spinner" />
            <p className="practice-kicker">GENERATING</p>
            <h1>正在生成习题</h1>
            <p>正在依据作品内容生成题目与答案解析。</p>
            {data?.quiz ? <small>上一版习题仍被保留，生成成功后会自动更新。</small> : null}
          </section>
        ) : null}

        {!loading && data?.status === "FAILED" ? (
          <section className="practice-state failed">
            <span className="practice-state-mark">!</span>
            <p className="practice-kicker">GENERATION FAILED</p>
            <h1>习题生成失败</h1>
            <p>{data.error || "模型暂时没有返回有效题目，请重新生成。"}</p>
            {data.can_manage ? <button className="btn primary" type="button" disabled={actionBusy} onClick={() => setConfirmRegenerate(true)}>重新生成</button> : null}
          </section>
        ) : null}

        {!loading && data?.status === "READY" && data.quiz ? (
          <>
            <section className="practice-hero">
              <div>
                <p className="practice-kicker">REVIEW & PRACTICE · {data.quiz.questions.length} CARDS</p>
                <h1>{data.quiz.title.replace(/课后讲评练|讲评练/g, "课后习题")}</h1>
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
                      <div><em>{question.type === "judgement" ? "判断辨析" : "单项选择"}</em></div>
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
                            onClick={() => {
                              setAnswers((current) => ({ ...current, [question.id]: option.id }));
                              setRevealed((current) => new Set(current).add(question.id));
                            }}
                          >
                            <span>{option.id}</span><strong>{option.text}</strong>
                          </button>
                        );
                      })}
                    </div>
                    {isRevealed ? (
                      <div className="quiz-explanation" role="status">
                        <strong>{selected === correct ? "回答正确" : `回答错误，正确答案：${correct}`}</strong>
                        <p>{question.explanation}</p>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </section>

          </>
        ) : null}

        {message ? <div className="practice-toast" role="status">{message}</div> : null}
      </main>
    </>
  );
}
