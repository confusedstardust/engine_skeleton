"use client";

import { useEffect, useState } from "react";
import { getCurrentUser } from "../app/invite-identity";
import { boardApi } from "../lib/community";
import CommunityAuthDialog from "./community-auth-dialog";

export type MessageKind = "QUESTION" | "SUGGESTION";

export default function CommunityMessageForm({ kind, onSent }: { kind: MessageKind; onSent: () => void }) {
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [message, setMessage] = useState("");
  const key = kind === "QUESTION" ? "community-question-draft" : "community-suggestion-draft";
  const feedback = kind === "SUGGESTION";
  useEffect(() => { try { setDraft(sessionStorage.getItem(key) || ""); } catch { /* Storage may be unavailable. */ } }, [key]);

  async function send() {
    setSending(true); setMessage("");
    try {
      await boardApi("/community/questions", { method: "POST", body: JSON.stringify({ question: draft.trim(), kind }) });
      setDraft("");
      try { sessionStorage.removeItem(key); } catch { /* Storage may be unavailable. */ }
      setMessage("已发送");
      onSent();
    } catch (reason) {
      if (reason instanceof Error && "status" in reason && reason.status === 401) setAuthOpen(true);
      else setMessage(reason instanceof Error ? reason.message : "发送失败，请重试");
    } finally { setSending(false); }
  }
  return <div className={`community-compose ${feedback ? "community-feedback-compose" : ""}`}>
    <form onSubmit={async event => {
      event.preventDefault(); setSending(true); setMessage("");
      const user = await getCurrentUser();
      if (user?.auth_type !== "sso") { setSending(false); setAuthOpen(true); return; }
      await send();
    }}><label className="sr-only" htmlFor={`community-${kind.toLowerCase()}`}>{feedback ? "你的建议与批评" : "你的问题"}</label><textarea id={`community-${kind.toLowerCase()}`} placeholder={feedback ? "如果有哪里让你觉得“还可以更好”，欢迎告诉我们。我们熟悉自己做的产品，但只有你，知道它用起来是什么感受。" : "把让你困惑的地方写下来吧。你当时想做什么，在哪一步遇到了问题？"} minLength={5} maxLength={2000} required value={draft} onChange={event => { setDraft(event.target.value); try { sessionStorage.setItem(key, event.target.value); } catch { /* Storage may be unavailable. */ } }} disabled={sending} /><div className="community-compose-footer">{draft.length > 0 && draft.trim().length < 5 && <small className="community-length-hint" role="status">至少填写 5 个字符（不计首尾空白），还差 {5 - draft.trim().length} 个</small>}<button type="submit" disabled={sending || draft.trim().length < 5}>{sending ? "发送中…" : "发送"}</button></div></form>
    {message && <p className="community-submit-status" role="status">{message}</p>}
    {authOpen && <CommunityAuthDialog messageKind={kind} onClose={() => setAuthOpen(false)} onAuthenticated={async () => {
      const user = await getCurrentUser();
      if (user?.auth_type !== "sso") throw new Error("登录状态尚未同步，请稍后重试");
      setAuthOpen(false); await send();
    }} />}
  </div>;
}
