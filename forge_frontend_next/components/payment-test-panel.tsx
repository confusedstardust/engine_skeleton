"use client";
import { useErrorToast } from "./ui/toast";
import { usePaymentOrder } from "../hooks/use-payment-order";
import { testPaymentOrders, isOrderFulfilled } from "../lib/payment-orders";
import { PaymentCheckoutDialog } from "./payment-checkout-dialog";
import { paymentsApi as api, ApiError } from "../lib/api-client";
import type { Order } from "../domain/payments";

import { ReturnLink } from "./navigation-return";

import Link from "next/link";
import { useEffect, useState } from "react";

import { type CreditBalance } from "../app/invite-identity";

type Evidence = { payment_status: string; fulfillment_status: string; verified_callback: boolean; granted_credits: number; grant_ledger_entries: number };

export default function PaymentTestPanel({ embedded = false }: { embedded?: boolean }) {
  const [loadError, setLoadError] = useState("");
  const [access, setAccess] = useState<"loading" | "allowed" | "denied">("loading");
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const checkout = usePaymentOrder(testPaymentOrders, {
    onRead: async (value, signal) => {
      const report = await api<Evidence>(`/test/orders/${encodeURIComponent(value.id)}/verification`, { signal });
      if (!signal.aborted) setEvidence(report);
    },
  });
  const { order, open, setOpen, busy, error, balance, setBalance, restore, start: startOrder, refresh } = checkout;
  useErrorToast(checkout.operationError, open || access !== "allowed");
  useEffect(() => {
    let active = true;
    void api("/test/products").then(async () => {
      if (!active) return;
      setAccess("allowed");
      let history: Order[];
      let value: CreditBalance | null;
      try {
        [history, value] = await Promise.all([api<Order[]>("/test/orders"), api<CreditBalance>("/test/balance")]);
      } catch (failure) {
        if (active) setLoadError(failure instanceof Error ? failure.message : "订单记录加载失败");
        return;
      }
      if (!active) return;
      setBalance(value);
      restore(history);
    }).catch(e => { if (active) { setAccess("denied"); setLoadError(e instanceof ApiError && e.status === 404 ? "页面不存在" : e.message); } });
    return () => { active = false; };
  }, [restore, setBalance]);
  async function start() {
    if (order?.status !== "PENDING") setEvidence(null);
    await startOrder();
  }
  if (access !== "allowed") return <section className="private-payment-test"><p role="status">{access === "loading" ? "正在验证访问权限…" : "测试支付暂不可用"}</p>{access === "denied" ? <p role="alert" className="recharge-error">{loadError === "页面不存在" ? "请登录已标记为测试账号的 NarrativeOS 用户或管理员账号。" : loadError || "测试配置检查失败，请稍后重试。"}</p> : null}{!embedded ? <ReturnLink /> : null}</section>;
  const completed = isOrderFulfilled(order);
  return <section className="private-payment-test">{!embedded ? <Link href="/recharge">← 返回充值页</Link> : null}<p className="private-test-kicker">PRIVATE PAYMENT TEST</p><h1>真实支付验收</h1><p>仅当前授权账号可用 · 走正式微信支付与积分入账流程</p>
    <section className="private-test-card"><h2>¥0.10 <small>／1 积分</small></h2><p>点击后创建真实订单，由你使用微信扫码付款。可测试下单、二维码、付款确认及积分到账。</p><p className="admin-subscription-note">主动查询确认付款与微信自动回调分别验收；完整回调测试需要公网服务已部署。</p><button className="btn primary" disabled={busy} onClick={() => void start()}>{busy ? "正在处理…" : order?.status === "PENDING" ? "继续测试订单" : "创建 ¥0.10 测试订单"}</button><p>当前积分余额：{balance ? balance.available : "—"}</p></section>
    {loadError ? <p role="alert" className="recharge-error">{loadError}</p> : null}
    {evidence ? <section className="private-test-card"><h2>服务端验收结果</h2><dl><dt>微信支付状态</dt><dd>{evidence.payment_status}</dd><dt>积分发放状态</dt><dd>{evidence.fulfillment_status}</dd><dt>到账积分</dt><dd>{evidence.granted_credits}</dd><dt>入账流水数量</dt><dd>{evidence.grant_ledger_entries}（应为 1，重复查询不会重复入账）</dd><dt>验签通过的微信回调</dt><dd>{evidence.verified_callback ? "已收到并处理" : "尚未收到；若已支付，可能通过主动查询确认，不能视为回调验收通过"}</dd></dl><button className="btn outline" disabled={busy} onClick={() => void refresh()}>重新检查验收结果</button></section> : null}
    {!evidence && order?.status === "PAID" && testPaymentOrders.accepts(order) ? <button className="btn outline" disabled={busy} onClick={() => void refresh()}>重新检查验收结果</button> : null}
    <PaymentCheckoutDialog order={order} open={open} onOpenChange={setOpen} busy={busy} error={error} qrPath={testPaymentOrders.qrPath} onRefresh={refresh}
      title={completed ? "测试支付成功" : "微信扫码支付"}
      description={<>真实扣款 ¥{order ? (order.payable_fen / 100).toFixed(2) : "0.10"} · 到账 1 积分</>}
      success={<p className="recharge-success" role="status">1 积分已到账，当前可用 {balance ? balance.available : "—"} 积分</p>}
      qrAlt="微信扫码支付一角钱" />
  </section>;
}
