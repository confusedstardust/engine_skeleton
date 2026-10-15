"use client";

import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { withBasePath } from "../app/base-path";

export default function CommunityAuthDialog({ onClose, onAuthenticated, messageKind = "QUESTION" }: { messageKind?: "QUESTION" | "SUGGESTION"; onClose: () => void; onAuthenticated: () => Promise<void> }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [sendingCode, setSendingCode] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => { if (!cooldown) return; const timer = window.setTimeout(() => setCooldown(value => value - 1), 1000); return () => window.clearTimeout(timer); }, [cooldown]);
  async function auth(path: string, body: Record<string, string>) {
    const response = await fetch(withBasePath(`/api/account/${path}`), { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-Forge-Auth-Action": "1" }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "登录失败，请重试");
    return data;
  }
  async function sendCode() {
    setSendingCode(true); setError(""); setMessage("");
    try { const data = await auth("email/send-code", { email }); setCooldown(data.cooldown || 60); setMessage("验证码已发送，请查看邮箱。"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "验证码发送失败"); } finally { setSendingCode(false); }
  }
  return <Dialog.Root open onOpenChange={open => { if (!open && !busy) onClose(); }}><Dialog.Portal><Dialog.Overlay className="community-dialog-overlay" /><Dialog.Content className="community-auth-dialog" onEscapeKeyDown={event => { if (busy) event.preventDefault(); }}>
    <Dialog.Close className="community-dialog-close" aria-label="关闭登录注册" disabled={busy}>×</Dialog.Close><p className="router-kicker">NARRATIVEOS</p><Dialog.Title>登录 / 注册</Dialog.Title><Dialog.Description>登录后发送你的{messageKind === "SUGGESTION" ? "建议" : "问题"}，已填写的内容会保留。</Dialog.Description>
    <div className="community-auth-tabs">{(["login", "register"] as const).map(value => <button key={value} type="button" aria-pressed={mode === value} disabled={busy} onClick={() => { setMode(value); setError(""); setMessage(""); }}>{value === "login" ? "登录" : "注册"}</button>)}</div>
    <form onSubmit={async event => {
      event.preventDefault(); setError("");
      if (mode === "register" && password !== confirmPassword) { setError("两次输入的密码不一致"); return; }
      setBusy(true);
      try { await auth(mode, { email, password, ...(mode === "register" ? { code } : {}) }); window.dispatchEvent(new Event("forge-auth-changed")); await onAuthenticated(); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "登录失败，请重试"); } finally { setBusy(false); }
    }}><fieldset disabled={busy}><label>邮箱<input type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} maxLength={191} required /></label><label>密码<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 8 : 1} maxLength={512} value={password} onChange={event => setPassword(event.target.value)} required /></label>
      {mode === "register" && <><label>确认密码<input type="password" autoComplete="new-password" minLength={8} maxLength={512} value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} required /></label><label>邮箱验证码<div className="community-code-field"><input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={code} onChange={event => setCode(event.target.value)} required /><button type="button" disabled={sendingCode || cooldown > 0 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)} onClick={() => void sendCode()}>{cooldown ? `${cooldown}s 后重试` : sendingCode ? "发送中…" : "获取验证码"}</button></div></label></>}
      {error && <p role="alert" className="error">{error}</p>}{message && <p role="status">{message}</p>}<button className="community-auth-submit" type="submit">{busy ? "正在处理…" : mode === "login" ? "登录并发送" : "注册并发送"}</button>
    </fieldset></form>
  </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
