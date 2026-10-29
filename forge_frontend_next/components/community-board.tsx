"use client";
import { Button } from './ui/button';
import { InlineFeedback } from './ui/feedback';
import { EmptyState } from './ui/state';

import { Pagination } from "./ui/pagination";

import { useEffect, useState } from "react";
import CommunityMessageForm from "./community-message-form";
import { getCurrentUser, type AuthUser } from "../app/invite-identity";

import { boardApi, type BoardData, type BoardQuestion } from "../lib/community";
export { boardApi, type BoardData, type BoardNotice, type BoardQuestion } from "../lib/community";

const commonQuestions = [
  { question: "第一次使用，从哪里开始？", answer: "点击首页的「开始创作」，选择创作场景，再填写主题与材料。已有的创作可以在账号菜单的「我的作品」中继续编辑。" },
  { question: "素材库和我的资产有什么区别？", answer: "素材库用于浏览平台共享素材；我的资产用于管理自己的上传与收藏，方便在创作时再次选用。" },
];

export default function CommunityBoard() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [questions, setQuestions] = useState<BoardQuestion[]>([]);
  const [mine, setMine] = useState(true);
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [ownQuestions, setOwnQuestions] = useState<BoardQuestion[]>([]);
  const [ownOffset, setOwnOffset] = useState(0);
  const [ownMore, setOwnMore] = useState(false);
  const [ownLoading, setOwnLoading] = useState(false);
  const [ownError, setOwnError] = useState("");


  useEffect(() => {
    let active = true;
    const refresh = () => { void getCurrentUser().then(value => { if (active) setUser(value); }); };
    refresh(); window.addEventListener("forge-auth-changed", refresh);
    return () => { active = false; window.removeEventListener("forge-auth-changed", refresh); };
  }, []);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setQuestions([]);
    void boardApi<BoardData>(`/community?offset=${offset}`).then(value => {
      if (!active) return;
      setQuestions(value.questions); setMore(value.has_more);
    }).catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offset, revision]);

  useEffect(() => {
    if (user?.auth_type !== "sso" || !mine) { setOwnQuestions([]); return; }
    let active = true;
    setOwnLoading(true); setOwnError(""); setOwnQuestions([]);
    void boardApi<{ questions: BoardQuestion[]; has_more: boolean }>(`/community/mine?kind=QUESTION&offset=${ownOffset}`).then(value => {
      if (active) { setOwnQuestions(value.questions); setOwnMore(value.has_more); }
    }).catch(reason => { if (active) setOwnError(reason.message); }).finally(() => { if (active) setOwnLoading(false); });
    return () => { active = false; };
  }, [user?.id, user?.auth_type, mine, ownOffset, revision]);

  return <section className="community-section" id="community" aria-label="提问与答疑">
    <div className="community-layout">
      <section className="community-qa" aria-labelledby="community-qa-title"><div className="community-column-heading"><h2 id="community-qa-title">提问与答疑 <span>Q&A</span></h2><div className="community-tabs">{user?.auth_type === "sso" && <Button variant="unstyled" type="button" aria-pressed={mine} onClick={() => { setMine(!mine); setOwnOffset(0); }}>{mine ? "收起我的提问" : "我的提问"}</Button>}</div></div>
        <p className="community-invitation">你遇到的问题，也许正是另一个人还没问出口的疑惑。留在这里，让我们的回答，也能帮到后来的人。</p>
        <div className="community-question-list" aria-busy={loading}>
          {commonQuestions.map((item, index) => <details className="community-question" key={item.question} open={index === 0}><summary><span className="qa-letter">Q</span><h4>{item.question}</h4><span className="qa-expand" aria-hidden="true">+</span></summary><div className="community-answer"><span className="qa-letter">A</span><p>{item.answer}</p></div></details>)}
          {questions.map(item => <details className="community-question" key={item.id} open><summary><span className="qa-letter">Q</span><h4>{item.question}</h4><span className="qa-expand" aria-hidden="true">+</span></summary><div className="community-answer"><span className="qa-letter">A</span><p>{item.answer || "已收到你的问题，等待答复。"}</p></div></details>)}
          {loading && <p role="status">正在加载留言…</p>}
          {error && <InlineFeedback >{error} <Button variant="unstyled" className="community-text-button" type="button" onClick={() => setRevision(value => value + 1)}>重新加载</Button></InlineFeedback>}
        </div>
        {(offset > 0 || more) && <Pagination ariaLabel="公开问答分页" className="community-pagination" page={offset / 6 + 1} hasMore={more} disabled={loading} onPageChange={page => setOffset((page - 1) * 6)} />}
        {user?.auth_type === "sso" && mine && <div className="community-own-questions" aria-busy={ownLoading}>
          <h3>我的提问</h3>
          {ownLoading && <p role="status">正在加载我的提问…</p>}
          {ownError && <InlineFeedback >{ownError} <Button variant="unstyled" className="community-text-button" onClick={() => setRevision(value => value + 1)}>重试</Button></InlineFeedback>}
          {!ownLoading && !ownError && !ownQuestions.length && <EmptyState as="p" className="community-empty">还没有提交过提问。</EmptyState>}
          {ownQuestions.map(item => <details className="community-question" key={item.id} open><summary><span className="qa-letter">Q</span><h4>{item.question}</h4>{item.answer ? <span className="qa-expand" aria-hidden="true">+</span> : <span className="community-pending">待答复</span>}</summary>{item.answer && <div className="community-answer"><span className="qa-letter">A</span><p>{item.answer}</p></div>}</details>)}
          {(ownOffset > 0 || ownMore) && <Pagination ariaLabel="我的提问分页" className="community-pagination" page={ownOffset / 6 + 1} hasMore={ownMore} disabled={ownLoading} onPageChange={page => setOwnOffset((page - 1) * 6)} />}
        </div>}
        <CommunityMessageForm kind="QUESTION" onSent={() => { setMine(true); setOwnOffset(0); setRevision(value => value + 1); }} />
      </section>
    </div>
  </section>;
}
