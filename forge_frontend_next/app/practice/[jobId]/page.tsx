"use client";
import { Spinner } from '../../../components/ui/state';
import { InlineFeedback } from '../../../components/ui/feedback';

import { Button } from '../../../components/ui/button';
import { useToast } from "../../../components/ui/toast";
import { WorkbenchHeader } from "../../../components/workbench-header";
import { usePolling } from "../../../hooks/use-polling";
import { forgeApi as api } from "../../../lib/api-client";
import type { QuizPlan, QuizResponse } from "../../../domain/quiz";
import { QuestionCard, QuestionOptions, QuestionExplanation } from '../../../components/quiz-question';
import { QuizCountRange } from '../../../components/quiz-count-range';
import { ClassroomQuizManager } from "../../../components/classroom-quiz-manager";
import { ClassroomQuizContent } from "../../../components/classroom-quiz-content";






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
  const [editingQuiz, setEditingQuiz] = useState(false);
  const [minQuestions, setMinQuestions] = useState(4);
  const [maxQuestions, setMaxQuestions] = useState(6);
  const [teacherView, setTeacherView] = useState<'quiz' | 'submissions' | 'analysis'>('quiz');
  const notify = useToast();
  const [loadError, setLoadError] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Set<string>>(new Set());

  usePolling(async signal => {
    const value = await api<QuizResponse>(`/public/jobs/${jobId}/quiz`, { signal });
    if (!signal.aborted) { setData(value); setLoadError(""); setLoading(false); }
    return value.status === "QUEUED" || value.status === "RUNNING";
  }, {
    intervalMs: 2200, resetKey: jobId,
    enabled: !data || data.status === "QUEUED" || data.status === "RUNNING",
    onError: error => { setLoadError(error instanceof Error ? error.message : "习题加载失败。"); setLoading(false); },
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
    try {
      const value = await api<QuizResponse>(`/jobs/${jobId}/quiz`, {
        method: "POST",
        body: JSON.stringify({ regenerate, min_questions: minQuestions, max_questions: maxQuestions }),
      });
      setData({ ...value, can_manage: true });
      notify(value.status === "READY" ? "习题已生成" : "习题已进入生成队列，请稍候…", "success");
      if (regenerate) {
        setAnswers({});
        setRevealed(new Set());
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "习题生成失败。", "error");
    } finally {
      setActionBusy(false);
    }
  }

  function resetPractice() {
    setAnswers({});
    setRevealed(new Set());
    setLoadError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const generating = data?.status === "QUEUED" || data?.status === "RUNNING";
  const quantityControls = <QuizCountRange min={minQuestions} max={maxQuestions} disabled={actionBusy || generating} onChange={(min, max) => { setMinQuestions(min); setMaxQuestions(max); }} />;
  async function saveQuiz(quiz: QuizPlan) {
    const value = await api<QuizResponse>(`/jobs/${jobId}/quiz`, { method: 'PUT', body: JSON.stringify({ quiz_plan: quiz }) });
    setData({ ...value, can_manage: true });
    notify('习题已保存', 'success');
  }

  return (
    <>
      <WorkbenchHeader title="临场 · 习题" subtitle="PRACTICE" className="top-nav practice-nav" label="习题导航" fallback={data?.can_manage ? `/jobs/${jobId}` : `/play/${jobId}/`}>
{data?.quiz && !data.can_manage ? <Button variant="unstyled" className="top-nav-action" type="button" onClick={resetPractice}>重新作答</Button> : null}
</WorkbenchHeader>

      <ConfirmDialog open={confirmRegenerate} title="重新生成题目？" description={`将生成 ${minQuestions}–${maxQuestions} 道题并覆盖当前习题，已发放的班级练习和历史答卷保留原题。`} onCancel={() => setConfirmRegenerate(false)} onConfirm={() => void generate(true)} />
      <main className={`practice-page ${data?.can_manage ? 'practice-teacher-workspace' : ''}`}>
        {data?.can_manage && data.quiz ? <>
          <nav className="classroom-tabs" aria-label="习题管理视图">
            <Button variant="unstyled" type="button" aria-pressed={teacherView === 'quiz'} onClick={() => setTeacherView('quiz')}>习题内容</Button>
            <Button variant="unstyled" type="button" disabled={editingQuiz} aria-pressed={teacherView === 'submissions'} onClick={() => setTeacherView('submissions')}>班级答卷</Button>
            <Button variant="unstyled" type="button" disabled={editingQuiz} aria-pressed={teacherView === 'analysis'} onClick={() => setTeacherView('analysis')}>学情分析</Button>
          </nav>
          <div hidden={teacherView === 'quiz'}><ClassroomQuizManager jobId={jobId} quizTitle={data.quiz.title} active={teacherView !== 'quiz'} view={teacherView === 'analysis' ? 'analysis' : 'submissions'} /></div>
        </> : null}
        {loadError && <InlineFeedback  >{loadError}</InlineFeedback>}
        {loading ? <section className="practice-state"><Spinner size="lg" tone="gold" className="practice-loading-spinner" /><h1>正在读取习题</h1><p>正在准备作品的课后习题内容。</p></section> : null}

        {!loading && !loadError && (!data || data.status === "NOT_GENERATED") ? (
          <section className="practice-state">
            <span className="practice-state-mark">练</span>
            <p className="practice-kicker">TEACHER REVIEW KIT</p>
            <h1>为这份作品生成习题</h1>
            <p>系统会依据教学材料、学习目标和叙事大纲，生成单选与判断习题，并提供答案解析。</p>
            {data?.can_manage ? (
              <>{quantityControls}<Button variant="primary" type="button" busy={Boolean(actionBusy)} onClick={() => void generate(false)}>{actionBusy ? "正在创建…" : "生成习题"}</Button></>
            ) : <small>这份作品暂未发布习题，请先体验游戏内容。</small>}
          </section>
        ) : null}

        {!loading && generating ? (
          <section className="practice-state">
            <Spinner size="lg" tone="gold" className="practice-loading-spinner" />
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
            {data.can_manage ? <>{quantityControls}<Button variant="primary" type="button" busy={Boolean(actionBusy)} onClick={() => setConfirmRegenerate(true)}>重新生成</Button></> : null}
          </section>
        ) : null}

        {!loading && data?.status === "READY" && data.quiz && data.can_manage && teacherView === 'quiz' ? (
          <ClassroomQuizContent quiz={data.quiz} busy={actionBusy || generating} onRegenerate={() => setConfirmRegenerate(true)} onSave={saveQuiz} onEditingChange={setEditingQuiz} generationControls={quantityControls} />
        ) : null}

        {!loading && data?.status === "READY" && data.quiz && !data.can_manage ? (
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
                return <QuestionCard question={question} index={index} key={question.id} typeLabel={question.type === 'judgement' ? '判断辨析' : '单项选择'}>
                  <QuestionOptions question={question} selected={selected} revealed={isRevealed} disabled={isRevealed} onSelect={id => {
                    setAnswers(current => ({ ...current, [question.id]: id }));
                    setRevealed(current => new Set(current).add(question.id));
                  }} />
                  {isRevealed && <QuestionExplanation question={question} selected={selected} announce />}
                </QuestionCard>;
              })}
            </section>

          </>
        ) : null}


      </main>
    </>
  );
}
