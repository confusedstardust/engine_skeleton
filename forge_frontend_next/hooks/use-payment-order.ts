'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Order } from '../domain/payments';
import type { CreditBalance } from '../app/invite-identity';
import { creditBalanceChangedEvent } from '../components/credit-balance';
import { randomUUID } from '../app/random-uuid';
import { isOrderFulfilled, shouldPollOrder, type PaymentOrderAdapter } from '../lib/payment-orders';
import { usePolling } from './use-polling';

type Callbacks = {
  onRead?: (order: Order, signal: AbortSignal) => Promise<void>;
  onPaid?: (order: Order, signal: AbortSignal) => Promise<void>;
};

export function usePaymentOrder(adapter: PaymentOrderAdapter, callbacks: Callbacks = {}) {
  const [order, setOrder] = useState<Order | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [pollingError, setPollingError] = useState('');
  const [balance, setBalance] = useState<CreditBalance | null>(null);
  const [creditedBalance, setCreditedBalance] = useState<CreditBalance | null>(null);
  const [balanceRefreshing, setBalanceRefreshing] = useState(false);
  const currentCallbacks = useRef(callbacks);
  const lifecycle = useRef(new AbortController());
  const revision = useRef(0);
  const operation = useRef(false);
  const requestKey = useRef<{ payload: string; key: string } | null>(null);
  const notified = useRef(new Set<string>());
  useEffect(() => {
    currentCallbacks.current = callbacks;
  });
  useEffect(() => {
    lifecycle.current = new AbortController();
    return () => {
      lifecycle.current.abort();
      revision.current += 1;
    };
  }, []);

  const restore = useCallback(
    (history: Order[]) => {
      revision.current += 1;
      setOrders(history);
      const pending = history.find(shouldPollOrder) || null;
      setOrder(pending);
      if (pending && adapter.accepts(pending)) setOpen(true);
    },
    [adapter],
  );

  async function apply(next: Order, signal: AbortSignal, expected: number) {
    const active = () => !signal.aborted && !lifecycle.current.signal.aborted && revision.current === expected;
    if (!active()) return;
    setOrders((rows) => [next, ...rows.filter((row) => row.id !== next.id)].slice(0, 20));
    try {
      if (isOrderFulfilled(next)) {
        if (!notified.current.has(next.id)) {
          notified.current.add(next.id);
          window.dispatchEvent(new Event(creditBalanceChangedEvent));
          await currentCallbacks.current.onPaid?.(next, signal);
        }
        if (!active()) return;
        setBalanceRefreshing(true);
        try {
          const value = await adapter.balance(signal);
          if (active() && value) {
            setBalance(value);
            setCreditedBalance(value);
          }
        } finally {
          if (active()) setBalanceRefreshing(false);
        }
      }
    } finally {
      if (active()) setOrder(next);
    }
  }

  async function read(id: string, signal: AbortSignal, expected: number, quiet = false) {
    const next = await adapter.read(id, signal);
    if (signal.aborted || lifecycle.current.signal.aborted || expected !== revision.current) return false;
    try {
      await currentCallbacks.current.onRead?.(next, signal);
      if (!signal.aborted && expected === revision.current) {
        setPollingError('');
        if (!quiet) setError('');
      }
    } finally {
      await apply(next, signal, expected);
    }
    return shouldPollOrder(next);
  }

  usePolling(
    async (signal) => {
      if (operation.current) return true;
      return order ? read(order.id, signal, revision.current, true) : false;
    },
    {
      enabled: !!order && shouldPollOrder(order) && adapter.accepts(order),
      resetKey: order?.id,
      intervalMs: 5000,
      onError: (failure) => setPollingError(failure instanceof Error ? failure.message : '暂时无法确认支付状态'),
    },
  );

  async function start(payload: Record<string, unknown> = {}) {
    if (operation.current) return;
    const pending = orders.find(shouldPollOrder) || (order && shouldPollOrder(order) ? order : null);
    if (pending) {
      if (!adapter.accepts(pending)) {
        setError(adapter.conflictMessage);
        return;
      }
      setOrder(pending);
      setOpen(true);
      return;
    }
    const signature = JSON.stringify(payload);
    if (requestKey.current && requestKey.current.payload !== signature) {
      setError('上次订单状态尚未确认，请先重试原订单。');
      return;
    }
    requestKey.current ??= { payload: signature, key: randomUUID() };
    const signal = lifecycle.current.signal;
    const expected = ++revision.current;
    operation.current = true;
    setBusy(true);
    setError('');
    setPollingError('');
    setCreditedBalance(null);
    try {
      let next: Order;
      try {
        next = await adapter.create({ ...payload, request_key: requestKey.current.key }, signal);
      } catch (failure) {
        if (signal.aborted) return;
        setError(failure instanceof Error ? failure.message : '下单失败，请重试');
        // Keep the same idempotency key if both the creation response and history read fail.
        try {
          const history = await adapter.list(signal);
          if (signal.aborted) return;
          setOrders(history);
          const pending = history.find(shouldPollOrder);
          if (pending) {
            setOrder(pending);
            if (adapter.accepts(pending)) {
              requestKey.current = null;
              setOpen(true);
            } else setError(adapter.conflictMessage);
          }
        } catch {
          /* Retain the original failure and key for a safe retry. */
        }
        return;
      }
      if (signal.aborted) return;
      requestKey.current = null;
      setOpen(true);
      try {
        await currentCallbacks.current.onRead?.(next, signal);
      } finally {
        await apply(next, signal, expected);
      }
    } catch (failure) {
      if (!signal.aborted) setError(failure instanceof Error ? failure.message : '订单状态更新失败，请重试');
    } finally {
      operation.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }

  async function refresh(close = false) {
    if (!order || operation.current || !adapter.accepts(order)) return;
    const signal = lifecycle.current.signal;
    const expected = ++revision.current;
    operation.current = true;
    setBusy(true);
    setError('');
    setPollingError('');
    try {
      if (close) {
        await apply(await adapter.close(order.id, signal), signal, expected);
        requestKey.current = null;
      } else await read(order.id, signal, expected);
    } catch (failure) {
      if (!signal.aborted) setError(failure instanceof Error ? failure.message : '操作失败，请重试');
    } finally {
      operation.current = false;
      if (!signal.aborted) setBusy(false);
    }
  }
  return {
    order,
    orders,
    open,
    setOpen,
    busy,
    error: error || pollingError,
    operationError: error,
    setError,
    balance,
    setBalance,
    creditedBalance,
    balanceRefreshing,
    restore,
    start,
    refresh,
  };
}
