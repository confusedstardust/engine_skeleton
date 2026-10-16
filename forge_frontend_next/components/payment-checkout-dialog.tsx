'use client';

import * as Dialog from './ui/dialog';
import { useEffect, useState, type ReactNode } from 'react';
import type { Order } from '../domain/payments';
import { isOrderFulfilled } from '../lib/payment-orders';
import { withBasePath } from '../app/base-path';

export function PaymentCheckoutDialog({
  order,
  open,
  onOpenChange,
  busy,
  error,
  qrPath,
  title,
  description,
  success,
  onRefresh,
  qrAlt = '使用微信扫描此二维码付款',
}: {
  order: Order | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  error: string;
  qrPath: (id: string) => string;
  title: string;
  description: ReactNode;
  success: ReactNode;
  qrAlt?: string;
  onRefresh: (close?: boolean) => Promise<void>;
}) {
  const [qrError, setQrError] = useState(false);
  useEffect(() => {
    setQrError(false);
  }, [order?.id, open]);
  if (!order) return null;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Surface overlayClassName="recharge-payment-overlay" className="recharge-checkout recharge-payment-modal" aria-describedby={undefined}>
          <Dialog.Close className="recharge-payment-dismiss" aria-label="关闭支付窗口">
            ×
          </Dialog.Close>
          <div>
            <Dialog.Title asChild>
              <h2>{title}</h2>
            </Dialog.Title>
            <p>{description}</p>
          </div>
          {isOrderFulfilled(order) ? (
            <>
              {success}
              <Dialog.Close className="btn primary">完成</Dialog.Close>
            </>
          ) : order.status === 'PENDING' ? (
            <>
              {order.qr_ready && new Date(order.expires_at).getTime() > Date.now() && !qrError ? (
                <img
                  className="recharge-qr"
                  src={withBasePath(qrPath(order.id))}
                  alt={qrAlt}
                  onError={() => setQrError(true)}
                />
              ) : (
                <p role="status">
                  {qrError ? '二维码加载失败，请刷新页面重试。' : '支付状态确认中，请稍后刷新；请勿重复付款。'}
                </p>
              )}
              <p className="recharge-expiry">
                微信扫一扫付款 · 有效至{' '}
                {new Date(order.expires_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
              </p>
              <div className="recharge-buttons">
                <button className="btn primary" disabled={busy} onClick={() => void onRefresh()}>
                  刷新支付状态
                </button>
                <button className="btn outline" disabled={busy} onClick={() => void onRefresh(true)}>
                  关闭订单
                </button>
              </div>
            </>
          ) : (
            <p role="status">
              {order.status === 'PAID' ? '付款已确认，积分到账状态确认中，请刷新支付状态。' : '订单已关闭'}
            </p>
          )}
          {order.status === 'PAID' && !isOrderFulfilled(order) ? (
            <button className="btn primary" disabled={busy} onClick={() => void onRefresh()}>
              刷新支付状态
            </button>
          ) : null}
          {error ? (
            <p className="recharge-error" role="alert">
              {error}
            </p>
          ) : null}
        </Dialog.Surface>
    </Dialog.Root>
  );
}
