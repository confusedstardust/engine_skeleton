'use client';
import { Button } from './ui/button';
import { useToast } from './ui/toast';
import { adminApi } from '../lib/api-client';

import { useEffect, useRef, useState } from 'react';
import { FormSelect } from './ui/form-controls';
import * as Dialog from './ui/dialog';

type Detail = {
  user: { id: string; email?: string; nickname?: string; created_at: string; blocked: boolean };
  subscription: { name: string; expires_at: string; billing_period: string } | null;
  revision: number;
};
function request(path: string, init?: RequestInit): Promise<Detail> {
  return adminApi<Detail>(`/users/${path}`, init);
}
function localDate(iso: string) {
  const value = new Date(iso);
  return new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export default function AdminUserDetail({ userId, onClose }: { userId: string; onClose: () => void }) {
  const notify = useToast();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [plan, setPlan] = useState('Free');
  const [expiry, setExpiry] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [giftUnits, setGiftUnits] = useState('');
  const [giftReason, setGiftReason] = useState('');
  const giftRequest = useRef<{ signature: string; id: string } | null>(null);

  async function giftCredits(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    const units = Number(giftUnits);
    if (!Number.isSafeInteger(units) || units < 1 || units > 1000000 || !giftReason.trim()) return;
    const signature = JSON.stringify([userId, units, giftReason.trim()]);
    if (giftRequest.current?.signature !== signature) {
      giftRequest.current = { signature, id: crypto.randomUUID().replaceAll('-', '') };
    }
    setBusy(true); setError('');
    try {
      const result = await adminApi<{ units: number; created: boolean }>(`/users/${encodeURIComponent(userId)}/credits`, {
        method: 'POST',
        body: JSON.stringify({ units, reason: giftReason.trim(), request_id: giftRequest.current.id }),
      });
      notify(`已赠送 ${result.units} 积分`, "success");
      setGiftUnits(''); setGiftReason(''); giftRequest.current = null;
    } catch (e) {
      setError(e instanceof Error ? e.message : '赠送失败');
    } finally { setBusy(false); }
  }
  function apply(value: Detail) {
    setDetail(value);
    setPlan(value.subscription?.name || 'Free');
    setExpiry(value.subscription?.expires_at ? localDate(value.subscription.expires_at) : '');
  }
  useEffect(() => {
    let active = true;
    request(`${encodeURIComponent(userId)}/detail`)
      .then((value) => {
        if (active) apply(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [userId]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!detail) return;
    setBusy(true);
    setError('');
    try {
      const value = await request(`${encodeURIComponent(userId)}/subscription`, {
        method: 'PATCH',
        body: JSON.stringify({
          plan,
          expires_at: plan === 'Free' ? null : new Date(expiry).toISOString(),
          reason,
          expected_revision: detail.revision,
        }),
      });
      apply(value);
      setReason('');
      notify("订阅已保存", "success");
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog.Root
      busy={busy}
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Dialog.Surface
        overlayClassName="recharge-payment-overlay"
        className="admin-user-dialog"
        aria-describedby={undefined}
        onEscapeKeyDown={(e) => {
          if (busy) e.preventDefault();
        }}
        onPointerDownOutside={(e) => {
          if (busy) e.preventDefault();
        }}
      >
        <Dialog.Title>用户详情与账户管理</Dialog.Title>
        <Dialog.Close className="recharge-payment-dismiss" disabled={busy} aria-label="关闭用户详情">
          ×
        </Dialog.Close>
        {error ? (
          <p role="alert" className="recharge-error">
            {error}
          </p>
        ) : null}
        {!detail ? (
          <p role="status">正在加载用户信息…</p>
        ) : (
          <>
            <dl className="admin-user-info">
              <div>
                <dt>用户</dt>
                <dd>{detail.user.nickname || '未设置昵称'}</dd>
              </div>
              <div>
                <dt>邮箱</dt>
                <dd>{detail.user.email || '—'}</dd>
              </div>
              <div>
                <dt>账号 ID</dt>
                <dd>{detail.user.id}</dd>
              </div>
              <div>
                <dt>注册时间</dt>
                <dd>{new Date(detail.user.created_at).toLocaleString()}</dd>
              </div>
              <div>
                <dt>账号状态</dt>
                <dd>{detail.user.blocked ? '已禁用' : '正常'}</dd>
              </div>
              <div>
                <dt>当前订阅</dt>
                <dd>
                  {detail.subscription?.name || 'Free'}
                  {detail.subscription ? ` · 至 ${new Date(detail.subscription.expires_at).toLocaleString()}` : ''}
                </dd>
              </div>
            </dl>
            <form onSubmit={giftCredits} className="admin-subscription-form">
              <h3>赠送积分</h3>
              <label>赠送数量
                <input type="number" min={1} max={1000000} step={1} required value={giftUnits}
                  disabled={busy} onChange={(e) => { setGiftUnits(e.target.value); }} />
              </label>
              <label>赠送原因
                <textarea required maxLength={500} value={giftReason} disabled={busy}
                  placeholder="例如：活动奖励、服务补偿"
                  onChange={(e) => { setGiftReason(e.target.value); }} />
              </label>
              <p className="admin-subscription-note">积分立即到账，长期有效，赠送操作会记录管理员和原因。</p>
              <Button variant="primary" type="submit" busy={Boolean(busy)} disabled={busy || !giftUnits || !giftReason.trim()}>
                {busy ? '正在处理…' : '赠送积分'}
              </Button>
            </form>
            <form onSubmit={save} className="admin-subscription-form">
              <h3>修改订阅</h3>
              <label>
                套餐
                <FormSelect
                  ariaLabel="套餐"
                  value={plan}
                  disabled={busy}
                  onValueChange={(value) => {
                    setPlan(value);
                  }}
                  options={['Free', 'Creator', 'Pro', 'School'].map((name) => ({ value: name, label: name }))}
                />
              </label>
              {plan !== 'Free' ? (
                <label>
                  到期时间
                  <input
                    type="datetime-local"
                    value={expiry}
                    required
                    disabled={busy}
                    onChange={(e) => {
                      setExpiry(e.target.value);
                    }}
                  />
                </label>
              ) : null}
              <label>
                修改原因
                <textarea
                  value={reason}
                  required
                  maxLength={500}
                  disabled={busy}
                  placeholder="例如：试用授权、订阅调整"
                  onChange={(e) => {
                    setReason(e.target.value);
                  }}
                />
              </label>
              <p className="admin-subscription-note">
                这里只调整订阅身份与有效期，不扣款、不发放或回收积分，也不改变已付款订单的按月积分发放计划。
              </p>
              <Button variant="primary" type="submit" busy={Boolean(busy)} disabled={busy || !reason.trim()}>
                {busy ? '正在保存…' : '保存订阅'}
              </Button>
            </form>
          </>
        )}
      </Dialog.Surface>
    </Dialog.Root>
  );
}
