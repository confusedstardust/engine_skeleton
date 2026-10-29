"use client";
import { Button } from './ui/button';
import { InlineFeedback } from './ui/feedback';

import { Pagination } from "./ui/pagination";

import { useEffect, useState } from "react";
import { boardApi, type BoardQuestion } from "../lib/community";
import CommunityMessageForm from "./community-message-form";

export default function CommunityFeedback({ userId }: { userId: string | null }) {
  const authenticated = Boolean(userId);
  const [mine, setMine] = useState(true);
  const [items, setItems] = useState<BoardQuestion[]>([]);
  const [offset, setOffset] = useState(0);
  const [more, setMore] = useState(false);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!mine || !authenticated) { setItems([]); return; }
    let active = true;
    setLoading(true); setError(""); setItems([]);
    void boardApi<{ questions: BoardQuestion[]; has_more: boolean }>(`/community/mine?kind=SUGGESTION&offset=${offset}`).then(data => {
      if (active) { setItems(data.questions); setMore(data.has_more); }
    }).catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [mine, authenticated, userId, offset, revision]);
  return <section className="community-feedback" id="feedback" aria-labelledby="community-feedback-title">
    <div className="community-column-heading"><h2 id="community-feedback-title">建议与批评</h2>{authenticated && <div className="community-tabs"><Button variant="unstyled" type="button" aria-pressed={mine} onClick={() => { setMine(!mine); setOffset(0); }}>{mine ? "收起我的建议" : "我的建议"}</Button></div>}</div>
    <p className="community-feedback-invitation">我们认真对待使用产品的你，也愿意听见不满意的声音。</p>
    <CommunityMessageForm kind="SUGGESTION" onSent={() => { setMine(true); setOffset(0); setRevision(value => value + 1); }} />
    {authenticated && mine && <div className="community-feedback-history" aria-busy={loading}>
      {loading && <p role="status">正在加载建议…</p>}
      {error && <InlineFeedback >{error} <Button variant="unstyled" className="community-text-button" onClick={() => setRevision(value => value + 1)}>重试</Button></InlineFeedback>}
      {!loading && !error && !items.length && <p>还没有提交过建议。</p>}
      {items.map(item => <article key={item.id} className="community-feedback-item"><time>{item.created_at.slice(0, 10)}</time><p>{item.question}</p>{item.answer && <div><span>管理员回复</span><p>{item.answer}</p></div>}</article>)}
      {(offset > 0 || more) && <Pagination ariaLabel="我的建议分页" className="community-pagination" page={offset / 6 + 1} hasMore={more} disabled={loading} onPageChange={page => setOffset((page - 1) * 6)} />}
    </div>}
  </section>;
}
