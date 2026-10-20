import { paymentsApi } from './api-client';
import type { Order } from '../domain/payments';
import type { CreditBalance } from '../app/invite-identity';
import { getCreditBalance } from '../app/invite-identity';

export function isOrderFulfilled(order: Order | null) {
  return order?.status === 'PAID' && order.fulfillment_status === 'FULFILLED';
}

export function shouldPollOrder(order: Order) {
  return order.status === 'PENDING' || (order.status === 'PAID' && !isOrderFulfilled(order));
}

export type PaymentOrderAdapter = {
  list: (signal?: AbortSignal) => Promise<Order[]>;
  create: (payload: Record<string, unknown>, signal?: AbortSignal) => Promise<Order>;
  read: (id: string, signal?: AbortSignal) => Promise<Order>;
  close: (id: string, signal?: AbortSignal) => Promise<Order>;
  balance: (signal?: AbortSignal) => Promise<CreditBalance | null>;
  accepts: (order: Order) => boolean;
  conflictMessage: string;
  qrPath: (id: string) => string;
};

function adapter(prefix: string): PaymentOrderAdapter {
  const orderPath = (id: string) => `${prefix}/orders/${encodeURIComponent(id)}`;
  return {
    list: (signal) => paymentsApi<Order[]>(`${prefix}/orders`, { signal }),
    create: (payload, signal) =>
      paymentsApi<Order>(`${prefix}/orders`, { method: 'POST', body: JSON.stringify(payload), signal }),
    read: (id, signal) => paymentsApi<Order>(orderPath(id), { signal }),
    close: (id, signal) => paymentsApi<Order>(`${orderPath(id)}/close`, { method: 'POST', signal }),
    balance: () => getCreditBalance(),
    accepts: () => true,
    conflictMessage: '请先处理当前未完成的订单。',
    qrPath: (id) => `/api/forge/payments${orderPath(id)}/qr`,
  };
}

export const standardPaymentOrders = adapter('');
export const testPaymentOrders: PaymentOrderAdapter = {
  ...adapter('/test'),
  balance: (signal) => paymentsApi<CreditBalance>('/test/balance', { signal }),
  accepts: (order) => order.name === '私人支付测试',
  conflictMessage: '有未完成的正式订单，请先到充值页继续支付或关闭订单，再进行小额测试。',
};
