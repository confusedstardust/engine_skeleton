"use client";
import { randomUUID } from "../app/random-uuid";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { withBasePath } from "../app/base-path";
import { getCreditBalance, type CreditBalance } from "../app/invite-identity";
import { creditBalanceChangedEvent } from "./credit-balance";

type Order = { id: string; name: string; status: string; fulfillment_status: string; payable_fen: number; credits: number; qr_ready: boolean; expires_at: string };
type Evidence = { payment_status: string; fulfillment_status: string; verified_callback: boolean; granted_credits: number; grant_ledger_entries: number };
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge/payments${path}`), { ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "请求失败");
  return data;
}
export default function PaymentTestPanel({ embedded = false }: { embedded?: boolean }) {
  const [access, setAccess] = useState<"loading" | "allowed" | "denied">("loading");
  const [order, setOrder] = useState<Order | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [qrError, setQrError] = useState(false);
  const key = useRef<string | null>(null);
  useEffect(() => {
    let active = true;
    void api("/test/products").then(async () => {
      if (!active) return;
      setAccess("allowed");
      const [history, value] = await Promise.all([api<Order[]>("/orders"), getCreditBalance()]);
      if (!active) return;
      setBalance(value);
      const pending = history.find(row => row.status === "PENDING");
      if (pending) { setOrder(pending); if (pending.name === "私人支付测试") setOpen(true); }
    }).catch(e => { if (active) { setAccess("denied"); setError(e.message); } });
    return () => { active = false; };
  }, []);
  const check = useCallback(async (id: string) => {
    const value = await api<Order>(`/orders/${id}`);
    setOrder(value);
    const report = await api<Evidence>(`/test/orders/${id}/verification`);
    setEvidence(report);
    if (value.status === "PAID" && value.fulfillment_status === "FULFILLED") {
      setBalance(await getCreditBalance());
      window.dispatchEvent(new Event(creditBalanceChangedEvent));
    }
  }, []);
  useEffect(() => {
    if (!order || order.name !== "私人支付测试" || order.status !== "PENDING") return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try { await check(order.id); } catch(e) { if (active) setError(e instanceof Error ? e.message : "确认失败"); }
      if (active) timer = setTimeout(() => void poll(), 5000);
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [order?.id, order?.status, order?.name, check]);
  async function start() {
    if (order?.status === "PENDING") {
      if (order.name === "私人支付测试") setOpen(true);
      else setError("有未完成的正式订单，请先到充值页继续支付或关闭订单，再进行小额测试。");
      return;
    }
    setBusy(true); setError(""); setEvidence(null); setQrError(false);
    key.current ||= randomUUID();
    try { const value = await api<Order>("/test/orders", { method: "POST", body: JSON.stringify({ request_key: key.current }) }); setOrder(value); setOpen(true); key.current = null; }
    catch(e) { setError(e instanceof Error ? e.message : "下单失败"); }
    finally { setBusy(false); }
  }
  async function refresh(close = false) {
    if (!order) return; setBusy(true); setError("");
    try { if (close) setOrder(await api<Order>(`/orders/${order.id}/close`, { method: "POST" })); else await check(order.id); }
    catch(e) { setError(e instanceof Error ? e.message : "操作失败"); }
    finally { setBusy(false); }
  }
  if (access !== "allowed") return <section className="private-payment-test"><p role="status">{access === "loading" ? "正在验证访问权限…" : "仅限已登录的测试账号使用；请确认测试权限、测试商品和支付配置均已就绪。"}</p>{!embedded ? <Link href="/">返回首页</Link> : null}</section>;
  const completed = order?.status === "PAID" && order.fulfillment_status === "FULFILLED";
  return <section className="private-payment-test">{!embedded ? <Link href="/recharge">← 返回充值页</Link> : null}<p className="private-test-kicker">PRIVATE PAYMENT TEST</p><h1>真实支付验收</h1><p>仅当前授权账号可用 · 走正式微信支付与积分入账流程</p>
    <section className="private-test-card"><h2>¥0.10 <small>／1 积分</small></h2><p>点击后创建真实订单，由你使用微信扫码付款。可测试下单、二维码、付款确认及积分到账。</p><p className="admin-subscription-note">主动查询确认付款与微信自动回调分别验收；完整回调测试需要公网服务已部署。</p><button className="btn primary" disabled={busy} onClick={() => void start()}>{busy ? "正在处理…" : order?.status === "PENDING" ? "继续测试订单" : "创建 ¥0.10 测试订单"}</button><p>当前积分余额：{balance ? balance.available : "—"}</p></section>
    {error ? <p role="alert" className="recharge-error">{error}</p> : null}
    {evidence ? <section className="private-test-card"><h2>服务端验收结果</h2><dl><dt>微信支付状态</dt><dd>{evidence.payment_status}</dd><dt>积分发放状态</dt><dd>{evidence.fulfillment_status}</dd><dt>到账积分</dt><dd>{evidence.granted_credits}</dd><dt>入账流水数量</dt><dd>{evidence.grant_ledger_entries}（应为 1，重复查询不会重复入账）</dd><dt>验签通过的微信回调</dt><dd>{evidence.verified_callback ? "已收到并处理" : "尚未收到；若已支付，可能通过主动查询确认，不能视为回调验收通过"}</dd></dl><button className="btn outline" disabled={busy} onClick={() => void refresh()}>重新检查验收结果</button></section> : null}
    <Dialog.Root open={open} onOpenChange={setOpen}><Dialog.Portal><Dialog.Overlay className="recharge-payment-overlay"/><Dialog.Content className="recharge-checkout recharge-payment-modal" aria-describedby={undefined}><Dialog.Close className="recharge-payment-dismiss" aria-label="关闭测试支付窗口">×</Dialog.Close><Dialog.Title>{completed ? "测试支付成功" : "微信扫码支付"}</Dialog.Title><p>真实扣款 ¥{order ? (order.payable_fen / 100).toFixed(2) : "0.10"} · 到账 1 积分</p>
      {completed ? <p className="recharge-success" role="status">1 积分已到账，当前可用 {balance ? balance.available : "—"} 积分</p> : order?.status === "PENDING" ? <>{order.qr_ready && !qrError ? <img className="recharge-qr" src={withBasePath(`/api/forge/payments/orders/${order.id}/qr`)} alt="微信扫码支付一角钱" onError={() => setQrError(true)}/> : <p>二维码暂不可用，请检查订单状态；不要重复付款。</p>}<div className="recharge-buttons"><button className="btn primary" disabled={busy} onClick={() => void refresh()}>刷新支付状态</button><button className="btn outline" disabled={busy} onClick={() => void refresh(true)}>关闭订单</button></div></> : <p>订单已关闭</p>}
      {error ? <p role="alert" className="recharge-error">{error}</p> : null}
    </Dialog.Content></Dialog.Portal></Dialog.Root>
  </section>;
}
