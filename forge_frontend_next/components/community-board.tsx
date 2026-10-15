"use client";

import { useEffect, useState } from "react";
import CommunityMessageForm from "./community-message-form";
import CommunityFeedback from "./community-feedback";
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

  return <section className="community-section" id="community" aria-label="提问与建议">
    <div className="community-layout">
      <section className="community-qa" aria-labelledby="community-qa-title"><div className="community-column-heading"><h2 id="community-qa-title">提问与答疑 <span>Q&A</span></h2><div className="community-tabs">{user?.auth_type === "sso" && <button type="button" aria-pressed={mine} onClick={() => { setMine(!mine); setOwnOffset(0); }}>{mine ? "收起我的提问" : "我的提问"}</button>}</div></div>
        <p className="community-invitation">你遇到的问题，也许正是另一个人还没问出口的疑惑。留在这里，让我们的回答，也能帮到后来的人。</p>
        <div className="community-question-list" aria-busy={loading}>
          {commonQuestions.map((item, index) => <details className="community-question" key={item.question} open={index === 0}><summary><span className="qa-letter">Q</span><h4>{item.question}</h4><span className="qa-expand" aria-hidden="true">+</span></summary><div className="community-answer"><span className="qa-letter">A</span><p>{item.answer}</p></div></details>)}
          {questions.map(item => <details className="community-question" key={item.id} open><summary><span className="qa-letter">Q</span><h4>{item.question}</h4><span className="qa-expand" aria-hidden="true">+</span></summary><div className="community-answer"><span className="qa-letter">A</span><p>{item.answer || "已收到你的问题，等待答复。"}</p></div></details>)}
          {loading && <p role="status">正在加载留言…</p>}
          {error && <p role="alert">{error} <button className="community-text-button" type="button" onClick={() => setRevision(value => value + 1)}>重新加载</button></p>}
        </div>
        {(offset > 0 || more) && <div className="community-pagination"><button type="button" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 6))}>上一页</button><span>第 {offset / 6 + 1} 页</span><button type="button" disabled={loading || !more} onClick={() => setOffset(value => value + 6)}>下一页</button></div>}
        {user?.auth_type === "sso" && mine && <div className="community-own-questions" aria-busy={ownLoading}>
          <h3>我的提问</h3>
          {ownLoading && <p role="status">正在加载我的提问…</p>}
          {ownError && <p role="alert">{ownError} <button className="community-text-button" onClick={() => setRevision(value => value + 1)}>重试</button></p>}
          {!ownLoading && !ownError && !ownQuestions.length && <p className="community-empty">还没有提交过提问。</p>}
          {ownQuestions.map(item => <details className="community-question" key={item.id} open><summary><span className="qa-letter">Q</span><h4>{item.question}</h4>{item.answer ? <span className="qa-expand" aria-hidden="true">+</span> : <span className="community-pending">待答复</span>}</summary>{item.answer && <div className="community-answer"><span className="qa-letter">A</span><p>{item.answer}</p></div>}</details>)}
          {(ownOffset > 0 || ownMore) && <div className="community-pagination"><button type="button" disabled={ownLoading || ownOffset === 0} onClick={() => setOwnOffset(value => Math.max(0, value - 6))}>上一页</button><span>第 {ownOffset / 6 + 1} 页</span><button type="button" disabled={ownLoading || !ownMore} onClick={() => setOwnOffset(value => value + 6)}>下一页</button></div>}
        </div>}
        <CommunityMessageForm kind="QUESTION" onSent={() => { setMine(true); setOwnOffset(0); setRevision(value => value + 1); }} />
      </section>
      <CommunityFeedback userId={user?.auth_type === "sso" ? user.id : null} />
    </div>
  </section>;
}
