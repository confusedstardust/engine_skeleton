/** Public task receipt data; model token counts remain internal to accounting. */
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

/** Never present a reserved or guessed charge as settled credits. */
export function getTaskUsageTitle(receipt: TaskUsageReceipt): string {
  if (receipt.billingStatus === "captured")
    return receipt.chargedCredits != null
      ? `本次消耗 ${receipt.chargedCredits} 积分`
      : "本次积分消耗待确认";
  if (receipt.billingStatus === "unmetered_released")
    return "模型未返回用量 · 未扣积分";
  if (receipt.billingStatus === "released")
    return "任务失败 · 已退还冻结积分";
  return "历史记录未结算";
}
