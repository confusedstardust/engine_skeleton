"use client";

import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { withBasePath } from "../app/base-path";
import { jsonAuthHeaders } from "../app/invite-identity";

type Detail = { user: { id: string; email?: string; nickname?: string; created_at: string; blocked: boolean }; subscription: { name: string; expires_at: string; billing_period: string } | null; revision: number };
async function request(path: string, init?: RequestInit): Promise<Detail> {
  const response = await fetch(withBasePath(`/api/forge/admin/users/${path}`), { ...init, credentials: "include", cache: "no-store", headers: { ...jsonAuthHeaders(), "Content-Type": "application/json", "X-Forge-Admin-Action": "1" } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "用户信息加载失败");
  return data;
}
function localDate(iso: string) {
  const value = new Date(iso);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export default function AdminUserDetail({ userId, onClose }: { userId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [plan, setPlan] = useState("Free");
  const [expiry, setExpiry] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  function apply(value: Detail) {
    setDetail(value); setPlan(value.subscription?.name || "Free");
    setExpiry(value.subscription?.expires_at ? localDate(value.subscription.expires_at) : "");
  }
  useEffect(() => {
    let active = true;
    request(`${encodeURIComponent(userId)}/detail`).then(value => { if (active) apply(value); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [userId]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!detail) return;
    setBusy(true); setError(""); setSaved(false);
    try {
      const value = await request(`${encodeURIComponent(userId)}/subscription`, { method: "PATCH", body: JSON.stringify({ plan, expires_at: plan === "Free" ? null : new Date(expiry).toISOString(), reason, expected_revision: detail.revision }) });
      apply(value); setReason(""); setSaved(true);
    } catch (e) { setError(e instanceof Error ? e.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return <Dialog.Root open onOpenChange={open => { if (!open && !busy) onClose(); }}><Dialog.Portal>
    <Dialog.Overlay className="recharge-payment-overlay" />
    <Dialog.Content className="admin-user-dialog" aria-describedby={undefined} onEscapeKeyDown={e => { if (busy) e.preventDefault(); }} onPointerDownOutside={e => { if (busy) e.preventDefault(); }}>
      <Dialog.Title>用户详情与订阅</Dialog.Title><Dialog.Close className="recharge-payment-dismiss" disabled={busy} aria-label="关闭用户详情">×</Dialog.Close>
      {error ? <p role="alert" className="recharge-error">{error}</p> : null}
      {!detail ? <p role="status">正在加载用户信息…</p> : <>
        <dl className="admin-user-info"><div><dt>用户</dt><dd>{detail.user.nickname || "未设置昵称"}</dd></div><div><dt>邮箱</dt><dd>{detail.user.email || "—"}</dd></div><div><dt>账号 ID</dt><dd>{detail.user.id}</dd></div><div><dt>注册时间</dt><dd>{new Date(detail.user.created_at).toLocaleString()}</dd></div><div><dt>账号状态</dt><dd>{detail.user.blocked ? "已禁用" : "正常"}</dd></div><div><dt>当前订阅</dt><dd>{detail.subscription?.name || "Free"}{detail.subscription ? ` · 至 ${new Date(detail.subscription.expires_at).toLocaleString()}` : ""}</dd></div></dl>
        <form onSubmit={save} className="admin-subscription-form">
          <h3>修改订阅</h3>
          <label>套餐<select aria-label="套餐" value={plan} disabled={busy} onChange={e => { setPlan(e.target.value); setSaved(false); }}>{["Free", "Creator", "Pro", "School"].map(name => <option key={name}>{name}</option>)}</select></label>
          {plan !== "Free" ? <label>到期时间<input type="datetime-local" value={expiry} required disabled={busy} onChange={e => { setExpiry(e.target.value); setSaved(false); }} /></label> : null}
          <label>修改原因<textarea value={reason} required maxLength={500} disabled={busy} placeholder="例如：试用授权、订阅调整" onChange={e => { setReason(e.target.value); setSaved(false); }} /></label>
          <p className="admin-subscription-note">这里只调整订阅身份与有效期，不扣款、不发放或回收积分，也不改变已付款订单的按月积分发放计划。</p>
          {saved ? <p role="status" className="recharge-success">订阅已保存</p> : null}
          <button className="btn primary" disabled={busy || !reason.trim()}>{busy ? "正在保存…" : "保存订阅"}</button>
        </form>
      </>}
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}
