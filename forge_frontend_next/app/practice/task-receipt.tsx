"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronUp, Clock3, Coins, Gauge } from "lucide-react";
import styles from "./task-receipt.module.css";

export type TaskUsageReceipt = {
  inputTokens: number | null;
  outputTokens: number | null;
  cachedInputTokens: number | null;
  usageStatus: "reported" | "unavailable";
  billingStatus: "captured" | "unmetered_released" | "released" | "disabled";
  chargedCredits: number | null;
  reservedCredits: number | null;
  durationMs: number;
  scope?: string;
};

function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes ? minutes + "分" + String(seconds % 60).padStart(2, "0") + "秒" : seconds + "秒";
}

export default function TaskReceipt({ value, compact = false }: { value: TaskUsageReceipt; compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const settled = value.billingStatus === "captured";
  const title = settled ? "本次消耗 " + (value.chargedCredits ?? 0) + " 积分" :
    value.billingStatus === "unmetered_released" ? "模型未返回用量 · 未扣积分" :
    value.billingStatus === "released" ? "任务失败 · 已退还冻结积分" : "历史记录未结算";
  return <Collapsible.Root open={open} onOpenChange={setOpen} className={compact ? `${styles.root} ${styles.compact}` : styles.root}>
    <Collapsible.Trigger type="button" className={styles.trigger} aria-label="查看本次任务的用量详情">
      {!compact && <span className={styles.time}><CheckCircle2 size={15} aria-hidden="true" />
        <Clock3 size={14} aria-hidden="true" /> 用时 {duration(value.durationMs)}</span>}
      <span className={styles.cost}><Coins size={15} aria-hidden="true" />{title}
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</span>
    </Collapsible.Trigger>
    <Collapsible.Content className={styles.details}>
      {compact && <span><Clock3 size={14} aria-hidden="true" /> 用时 {duration(value.durationMs)}</span>}
      <span><Gauge size={14} aria-hidden="true" /> 输入 Token：{value.inputTokens?.toLocaleString("zh-CN") ?? "暂无数据"}</span>
      <span>输出 Token：{value.outputTokens?.toLocaleString("zh-CN") ?? "暂无数据"}</span>
      <span>缓存输入：{value.cachedInputTokens?.toLocaleString("zh-CN") ?? "暂无数据"}</span>
      <small>统计仅包含 Agent 执行链中模型提供的用量，不包含单独的意图路由及可选摘要调用；未返回用量时不推算扣费。</small>
    </Collapsible.Content>
  </Collapsible.Root>;
}
