"use client";

import { useCallback, useEffect, useState } from "react";
import { getCreditBalance, type CreditBalance as Balance } from "../app/invite-identity";

export const creditBalanceChangedEvent = "narrativeos:credits-changed";

export function CreditBalance() {
  const [balance, setBalance] = useState<Balance | null>(null);

  const refresh = useCallback(async () => {
    setBalance(await getCreditBalance());
  }, []);

  useEffect(() => {
    void refresh();
    window.addEventListener(creditBalanceChangedEvent, refresh);
    return () => window.removeEventListener(creditBalanceChangedEvent, refresh);
  }, [refresh]);

  if (!balance) return null;

  return (
    <span
      className="credit-balance"
      title={balance.reserved > 0 ? `另有 ${balance.reserved} 积分正在生成任务中` : "当前可用积分"}
    >
      积分 <strong>{balance.available}</strong>
      {balance.reserved > 0 ? <small>（冻结 {balance.reserved}）</small> : null}
    </span>
  );
}
