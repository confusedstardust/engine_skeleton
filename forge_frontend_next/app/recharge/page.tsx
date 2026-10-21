"use client";
import { useErrorToast, useToast } from "../../components/ui/toast";
import { WorkbenchHeader } from "../../components/workbench-header";
import { usePaymentOrder } from "../../hooks/use-payment-order";
import { standardPaymentOrders, isOrderFulfilled as paid } from "../../lib/payment-orders";
import { PaymentCheckoutDialog } from "../../components/payment-checkout-dialog";
import { paymentsApi as api } from "../../lib/api-client";
import type { Product, Order } from "../../domain/payments";




import Link from "next/link";

import { useEffect, useState } from "react";
import { PriceFace, PricePeel } from "../../components/price-peel";


import { getCreditBalance, getCurrentUser } from "../invite-identity";
const money = (fen: number) => (fen / 100).toFixed(2);
const isCreditPack = (product: Product) => product.name.startsWith("加速体验包") || ["体验积分包", "标准积分包"].includes(product.name);
// Keep the approved copy visible while an older backend process is restarted.
const approvedFeatures: Record<string, string[]> = {
  Creator: ["每月 600 积分", "每月 3 次游戏下载额度", "1 GB 云存储", "2000+ 素材，最低 1 折积分抵扣", "新增功能优先免费体验推送"],
  Pro: ["每月 2500 积分", "每月 10 次游戏下载额度", "5 GB 云存储", "2000+ 素材，最低 1 折积分抵扣", "新增功能优先免费体验推送", "更强大的文件管理能力", "优先客户支持", "定时发布"],
  加速体验包: ["一次到账 100 积分", "用于文本、图片与语音生成"],
};

function PlanIcon({ file }: { file: "rocket-launch" | "palette" | "crown" | "student" }) {
  const source = `url("https://ecs-oss-ist.oss-cn-hangzhou.aliyuncs.com/site_asset/icons/plans/${file}.svg")`;
  return <span className="pricing-plan-emblem" aria-hidden="true"><span className="pricing-plan-symbol" style={{ maskImage: source, WebkitMaskImage: source }} /></span>;
}

export default function RechargePage() {
  const notify = useToast();
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(true);
  const [signedIn, setSignedIn] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [subscription, setSubscription] = useState<{ name: string } | null>(null);
  const [historyReady, setHistoryReady] = useState(false);

  const checkout = usePaymentOrder(standardPaymentOrders, {
    onPaid: async (_order, signal) => {
      const data = await api<{ subscription: { name: string } | null }>("/subscription", { signal }).catch(() => null);
      if (!signal.aborted && data) setSubscription(data.subscription);
    },
  });
  const { order: selected, orders, balance, setBalance, error, busy, open: checkoutOpen, setOpen: setCheckoutOpen, creditedBalance, balanceRefreshing, restore, start: startOrder, refresh: refreshOrClose } = checkout;

  useErrorToast(checkout.operationError, checkoutOpen);

  useEffect(() => {
    let active = true;
    setLoadError("");
    // All reads authenticate independently on the server; avoid a client waterfall.
    // Capture failures immediately so a slow auth response cannot leave a rejected promise unhandled.
    const catalogRequest = api<{ enabled: boolean; products: Product[] }>("/products")
      .then((value) => ({ value, error: null })).catch((error: unknown) => ({ value: null, error }));
    const balanceRequest = getCreditBalance();
    const historyRequest = Promise.all([api<Order[]>("/orders"), api<{ subscription: { name: string } | null }>("/subscription")])
      .then((value) => ({ value, error: null })).catch((error: unknown) => ({ value: null, error }));
    void (async () => {
      try {
        const user = await getCurrentUser();
        if (!active) return;
        if (user?.auth_type !== "sso") return;
        setSignedIn(true);
        // Balance and order history must not block rendering the catalog.
        void balanceRequest.then((value) => { if (active) setBalance(value); });
        void historyRequest.then((result) => {
          if (!active) return;
          if (!result.value) throw result.error;
          const [history, currentSubscription] = result.value;
          setSubscription(currentSubscription.subscription);
          restore(history);
          setHistoryReady(true);
        }).catch((failure) => {
          if (active) setLoadError(failure instanceof Error ? failure.message : "订单记录加载失败，请刷新后重试");
        });
        const result = await catalogRequest;
        if (!active) return;
        if (!result.value) throw result.error;
        const catalog = result.value;
        setEnabled(catalog.enabled);
        setProducts(catalog.products);
      } catch (failure) {
        if (active) setLoadError(failure instanceof Error ? failure.message : "加载失败，请重试");
      } finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [restore, setBalance]);

  async function create(product: Product) {
    if (!isCreditPack(product) && subscription) { notify("当前订阅仍在有效期内，可购买资源包补充积分。", "info"); return; }
    await startOrder({ product_id: product.id });
  }

  const [catalogTab, setCatalogTab] = useState<"subscription" | "resources">("subscription");
  const [annualBilling, setAnnualBilling] = useState(false);
  const [priceMotionKey, setPriceMotionKey] = useState(0);
  function changeBilling(annual: boolean) {
    if (annual === annualBilling) return;
    setAnnualBilling(annual); setPriceMotionKey((key) => key + 1);
  }
  const boostProducts = products.filter(isCreditPack).sort((a, b) => a.price_fen - b.price_fen);
  const [highlightedPlan, setHighlightedPlan] = useState<string | null>(null);
  const sortedProducts = products.filter((product) => !isCreditPack(product) && product.billing_period !== "year").sort((a, b) => { const rank = (name: string) => name === "Creator" ? 0 : name === "Pro" ? 1 : 2; return rank(a.name) - rank(b.name); });
  const pending = orders.some((row) => row.status === "PENDING");
  return <>
    <WorkbenchHeader title="临场 · 创作套餐" subtitle="CREATIVE CREDITS" className="top-nav recharge-nav" wrapBrand={false} />
    <main className="recharge-page recharge-twilight">
      <div className="recharge-heading recharge-hero"><p className="recharge-hero-eyebrow">让每一份灵感，都有展开的空间</p><h1 aria-label="创建互动体验，按创作节奏付费">{["创建互动体验，", "按创作节奏付费"].map((line, lineIndex) => <span key={line} className={lineIndex ? "recharge-hero-accent" : undefined} aria-hidden="true">{Array.from(line).map((char, index) => <span key={index} className="recharge-title-char" style={{ animationDelay: `${0.12 + (lineIndex * 7 + index) * 0.045}s` }}>{char}</span>)}</span>)}</h1><p className="recharge-hero-description">从一次灵感到持续创作，选择适合你的方案。<br className="recharge-hero-break" />用积分开启互动叙事，让文本、知识与想象成为可参与的故事。</p></div>
      {loading ? <p role="status">正在加载账户…</p> : !signedIn ? <div className="recharge-empty"><p>请使用 NarrativeOS 账号登录后充值。</p><Link className="btn primary" href="/login">前往登录</Link></div> : <>
        <section className="recharge-balance" aria-label="当前积分"><div><span>{balance && balance.available < 0 ? "当前欠费积分" : "当前可用积分"}</span><strong>{balance ? balance.available.toLocaleString("zh-CN") : "—"}</strong></div>{balance && balance.reserved > 0 ? <p>{balance.reserved} 分正在任务中使用。</p> : null}</section>
        {!enabled || products.length === 0 ? <div className="recharge-empty"><p>充值暂未开放</p><span>充值档位准备好后会在这里显示。</span></div> : <>
          <div className="pricing-catalog-tabs" role="tablist" aria-label="套餐类型">
            {([ ["subscription", "订阅方案"], ["resources", "资源包"] ] as const).map(([value, label]) => <button key={value} id={`catalog-tab-${value}`} role="tab" aria-selected={catalogTab === value} aria-controls="catalog-panel" tabIndex={catalogTab === value ? 0 : -1} className={catalogTab === value ? "active" : ""} onClick={() => setCatalogTab(value)} onKeyDown={(event) => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); const next = event.key === "Home" ? "subscription" : event.key === "End" ? "resources" : value === "subscription" ? "resources" : "subscription"; setCatalogTab(next); document.getElementById(`catalog-tab-${next}`)?.focus(); } }}>{label}</button>)}
          </div>
          {catalogTab === "subscription" ? <div className="billing-cycle" aria-label="付款周期">
            <button className={`billing-cycle-label${!annualBilling ? " active" : ""}`} onClick={() => changeBilling(false)}>按月</button>
            <button type="button" role="switch" aria-label="按年付费" aria-checked={annualBilling} className={`billing-toggle${annualBilling ? " annual" : ""}`} onClick={() => changeBilling(!annualBilling)}><span className="billing-toggle-thumb"><svg className="billing-toggle-arrow" viewBox="0 0 18 18" fill="none" aria-hidden="true"><path d="M15 9H3m5-5-5 5 5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg></span></button>
            <button className={`billing-cycle-label${annualBilling ? " active" : ""}`} onClick={() => changeBilling(true)}>按年</button><span className="billing-saving">立省15%起</span>
          </div> : null}
          <section id="catalog-panel" role="tabpanel" aria-labelledby={`catalog-tab-${catalogTab}`} className={`pricing-grid pricing-grid-${catalogTab}`}>
            {catalogTab === "subscription" ? <>
            <article className="pricing-card pricing-card-free" aria-label="Free 套餐">
              <div className="pricing-card-top"><h2 className="pricing-card-category pricing-card-name">Free</h2></div>
              <div className="pricing-plan-heading"><h3>从一次灵感开始</h3><p>体验互动叙事创作，让教学灵感迈出第一步。</p></div>
              <Link className="pricing-cta pricing-cta-free" href="/?workspace=1">免费使用</Link>
              <div className="pricing-price-stage"><div className="pricing-price"><span>¥</span><strong>0</strong><small>/ 月</small></div></div>
              <div className="pricing-payment-caption" />
              <div className="pricing-card-details"><h4 className="pricing-feature-heading">免费创作权益</h4><ul><li>注册即获100积分</li><li>每周赠送20积分</li><li>使用AI生成各类高质量互动叙事体验</li><li>免费使用海量讲评工具、实用功能</li><li>免费获取海量音乐、插图、背景素材</li><li>每月200MB云存储</li><li>邀请家人、朋友和同事一起创作</li></ul></div>
            </article>
            {sortedProducts.map((product) => {
              const pro = product.name.toLowerCase() === "pro";
              const annualProduct = products.find((candidate) => candidate.name === product.name && candidate.billing_period === "year");
              const purchaseProduct = annualBilling ? annualProduct : product;
              const displayPrice = annualBilling ? annualProduct ? annualProduct.price_fen / 100 : pro ? 2700 : product.name === "Creator" ? 869 : product.price_fen * 12 / 100 : product.price_fen / 100;
              return <article key={product.id} className={`pricing-card${pro ? " pricing-card-featured" : ""}${highlightedPlan === product.id ? " pricing-card-selected" : ""}`} onMouseEnter={() => setHighlightedPlan(product.id)} onMouseLeave={() => setHighlightedPlan(null)} onFocus={() => setHighlightedPlan(product.id)} onBlur={() => setHighlightedPlan(null)} aria-label={`${product.name} 套餐`}>
                <span className="pricing-ribbon">{pro ? "高阶创作者" : "最受欢迎"}</span>
                <div className="pricing-card-top"><PlanIcon file={pro ? "crown" : "palette"} /><h2 className="pricing-card-category pricing-card-name">{product.name}</h2>{pro ? <span className="pricing-badge">{annualBilling ? "年付省 ¥528" : "更多创作额度"}</span> : null}</div>
                <div className="pricing-plan-heading"><h3>{pro ? "让创作持续发生" : "把任何文本、知识与教学灵感变成互动体验。"}</h3><p>{pro ? "提供更高的每月 credits 配额与官方优先支持。适合需要更多积分、创作能力、下载额度和深度定制作品IP的创作者，扩大品牌影响力。" : "面向教师、文旅场景、IP叙事等泛人文互动体验场景。解锁更多功能、强大AI工具以及海量素材。"}</p></div>
                <button className="pricing-cta" disabled={busy || !historyReady || !purchaseProduct || !!subscription} onClick={() => { if (purchaseProduct) void create(purchaseProduct); }}>{!historyReady ? "正在核查订单…" : busy ? "正在处理…" : pending ? "继续支付" : subscription ? subscription.name === product.name ? "当前订阅" : "已有有效订阅" : !purchaseProduct ? "年付方案待确认" : pro ? "升级Pro" : "开始使用Creator"}</button>
                <div className={`pricing-price-stage pricing-price-stage-pro${annualBilling ? " is-annual" : ""}`} aria-live="polite">
                  <PriceFace value={displayPrice} annual={annualBilling} />
                  {annualBilling && priceMotionKey > 0 ? <PricePeel key={priceMotionKey} value={product.price_fen / 100} /> : null}
                </div>
                <div className="pricing-payment-caption">{annualBilling ? annualProduct ? `每月到账 ${annualProduct.credits} 积分` : "年付价格预览，暂未开放购买" : ""}</div>
                <div className="pricing-card-details"><h4 className="pricing-feature-heading">{pro ? "Creator 的所有功能，外加：" : "免费版的所有功能，外加："}</h4><ul>{(product.features?.length ? product.features : approvedFeatures[product.name] || [`${product.credits.toLocaleString("zh-CN")} 创作积分`]).map((feature) => <li key={feature}>{feature}</li>)}<li>加入个人品牌/IP署名标识</li></ul></div>
              </article>;
            })}
            <article className="pricing-card pricing-card-school" aria-label="School 套餐">
              <div className="pricing-card-top"><PlanIcon file="student" /><h2 className="pricing-card-category pricing-card-name">School</h2></div>
              <div className="pricing-plan-heading"><h3>为学校、企业、文旅场景而设</h3><p>提供一站式互动叙事体验解决方案，集中管理团队与作品，优化协作流程，让创作开展与内容生产更高效。</p></div>
              <a className="pricing-cta" href="mailto:stardust1192@gmail.com">获取专属解决方案</a>
              <div className="pricing-card-details"><h4 className="pricing-feature-heading">面向教育、企业和文旅的专属服务</h4><ul><li>5 人起订，面向教育、企业和文旅场景</li><li>共享额度、共享工作空间与工作台</li><li>集中管理团队和作品</li><li>设置团队设计审批流程</li><li>设置知识产权赔偿内容控制权限*</li><li>优先客户支持</li><li>专属设计支持服务</li><li>专属客户经理服务</li><li>更大记忆容量和 5 GB 存储空间</li><li>定制工作台和线下培训支持</li><li>更优质的协作体验</li></ul><p className="school-service-note">* 具体服务范围、支持标准及知识产权相关约定，以双方确认的定制方案为准。</p></div>
            </article>
            </> : <div className="pricing-boost-stack" aria-label="资源包">
              {boostProducts.map((product) => <article key={product.id} className="pricing-card pricing-boost-card" aria-label={`${product.name} ${product.credits} 积分`}>
                <div className="pricing-card-top"><PlanIcon file="rocket-launch" /><h2 className="pricing-card-category pricing-card-name">{product.name}</h2><span className="pricing-boost-tag">一次性补充</span></div>
                <p className="pricing-boost-quota"><strong>{product.credits.toLocaleString("zh-CN")}</strong><span>创作积分</span></p><p className="pricing-boost-note">{product.credits > 100 ? "充足补给，让创作持续发生" : "轻量尝鲜，即刻开启创作"}</p>
                <div className="pricing-price"><span>¥</span><strong>{Number(money(product.price_fen))}</strong><small>/ 次</small></div>
                <button className="pricing-cta" disabled={busy || !historyReady} onClick={() => void create(product)}>{!historyReady ? "正在核查订单…" : busy ? "正在处理…" : pending ? "继续支付" : `购买 ${product.credits.toLocaleString("zh-CN")} 积分`}</button>
              </article>)}
            </div>}
          </section>
        </>}
        {selected ? <PaymentCheckoutDialog order={selected} open={checkoutOpen} onOpenChange={setCheckoutOpen} busy={busy} error={error} qrPath={standardPaymentOrders.qrPath} onRefresh={refreshOrClose}
          title={paid(selected) ? "充值成功" : selected.status === "CLOSED" ? "订单已关闭" : "微信扫码支付"}
          description={<>{selected.credit_delivery === "monthly" ? `每月 ${selected.credits} 积分 · 共 12 个月` : `${selected.credits} 积分`} · ¥ {money(selected.payable_fen)}</>}
          success={<div className="recharge-success-panel" role="status"><span className="recharge-success-mark" aria-hidden="true">✓</span><p className="recharge-success">{selected.credit_delivery === "monthly" ? "首月积分已到账，后续积分每月发放。" : "积分已到账，可继续创作。"}</p><strong className="recharge-credited-amount">本次到账 {selected.credits.toLocaleString("zh-CN")} 积分</strong><p>{balanceRefreshing ? "正在更新积分余额…" : creditedBalance ? `当前可用 ${creditedBalance.available.toLocaleString("zh-CN")} 积分` : "余额暂未刷新，可在右上角账户中查看。"}</p></div>}
        /> : null}

      </>}
      {loadError ? <p className="recharge-error" role="alert">{loadError}</p> : null}
    </main>
  </>;
}
