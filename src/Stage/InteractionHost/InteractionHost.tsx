import React, { useEffect, useState } from 'react';
import { interactionManager } from '@/Core/Modules/interaction/InteractionManager';
import type { InteractionViewModel } from '@/Core/Modules/interaction/types';
import styles from './interactionHost.module.scss';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';

export const InteractionHost = () => {
  const [model, setModel] = useState<InteractionViewModel>(interactionManager.getViewModel());
  const menuOpen = useSelector((state: RootState) => state.GUI.showMenuPanel);
  useEffect(() => interactionManager.subscribe(setModel), []);
  useEffect(() => {
    if (model.lifecycle !== 'running' || model.config?.type !== 'qte') return;
    const timer = window.setInterval(() => setModel(interactionManager.getViewModel()), 50);
    return () => window.clearInterval(timer);
  }, [model.lifecycle, model.config?.type]);
  useEffect(() => {
    const onVisibility = () => document.hidden ? interactionManager.pause('hidden') : interactionManager.resume('hidden');
    const onBlur = () => interactionManager.pause('blur');
    const onFocus = () => interactionManager.resume('blur');
    const onKey = (event: KeyboardEvent) => {
      const current = interactionManager.getViewModel();
      if (current.lifecycle !== 'running') return;
      if (current.config?.type === 'qte') {
        if (event.repeat) return;
        const action = Object.entries(current.config.payload.bindings).find(([, codes]) => codes.includes(event.code))?.[0];
        if (action) { event.preventDefault(); interactionManager.dispatch({ type: 'qteAction', action }); }
      }
      if (current.config?.type === 'movement') {
        const axes: Record<string, [number, number]> = { ArrowUp: [0, -1], KeyW: [0, -1], ArrowLeft: [-1, 0], KeyA: [-1, 0], ArrowRight: [1, 0], KeyD: [1, 0], ArrowDown: [0, 1], KeyS: [0, 1] };
        const axis = axes[event.code];
        if (axis) { event.preventDefault(); interactionManager.dispatch({ type: 'moveAxes', x: axis[0], y: axis[1] }); }
        if (!event.repeat && (event.code === 'Space' || event.code === 'Enter')) { event.preventDefault(); interactionManager.dispatch({ type: 'confirmFinish' }); }
      }
    };
    document.addEventListener('visibilitychange', onVisibility); window.addEventListener('blur', onBlur); window.addEventListener('focus', onFocus); document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('visibilitychange', onVisibility); window.removeEventListener('blur', onBlur); window.removeEventListener('focus', onFocus); document.removeEventListener('keydown', onKey); };
  }, []);
  useEffect(() => { menuOpen ? interactionManager.pause('menu') : interactionManager.resume('menu'); }, [menuOpen]);
  if (model.lifecycle === 'idle' || model.lifecycle === 'cancelled') return null;
  if (model.lifecycle === 'loading') return <div className={styles.host}><section className={styles.panel}>正在加载互动内容…</section></div>;
  if (model.lifecycle === 'error') return <div className={styles.host}><section className={styles.panel}><p>{model.error || '互动内容加载失败。'}</p></section></div>;
  if (model.lifecycle === 'completed') return <div className={styles.host}><section className={styles.panel}><h2>互动完成</h2><button onClick={() => interactionManager.continueStory()}>继续剧情</button></section></div>;
  const config = model.config!; const snapshot = model.snapshot!;
  return <div className={styles.host} role="dialog" aria-modal="true"><section className={styles.panel}>
    <h2>{config.title}</h2>
    {model.lifecycle === 'paused' && <><p>互动已暂停。请确认后继续。</p><button onClick={() => interactionManager.continueAfterPause()}>继续挑战</button></>}
    {model.lifecycle === 'ready' && <button onClick={() => interactionManager.dispatch({ type: 'start' })}>开始</button>}
    {model.lifecycle === 'running' && config.type === 'investigation' && <Investigation model={model} />}
    {model.lifecycle === 'running' && config.type === 'qte' && <Qte model={model} />}
    {model.lifecycle === 'running' && config.type === 'movement' && <Movement model={model} />}
    {model.lifecycle === 'running' && config.payload.allowSkip && <button className={styles.skip} onClick={() => interactionManager.dispatch({ type: 'skip' })}>跳过</button>}
  </section></div>;
};

function Investigation({ model }: { model: InteractionViewModel }) {
  const config = model.config!; if (config.type !== 'investigation') return null; const snap = model.snapshot as Extract<typeof model.snapshot, { type: 'investigation' }>;
  const active = config.payload.hotspots.find((h) => h.id === snap.activeCardId);
  return <><div className={styles.evidence} style={{ backgroundImage: `url(./game/${config.payload.image})` }}>{config.payload.hotspots.map((hotspot) => <button key={hotspot.id} aria-label={hotspot.title} className={styles.hotspot} style={{ left: `${hotspot.rect.x * 100}%`, top: `${hotspot.rect.y * 100}%`, width: `${hotspot.rect.width * 100}%`, height: `${hotspot.rect.height * 100}%` }} onClick={() => interactionManager.dispatch({ type: 'pointerInspect', hotspotId: hotspot.id })} />)}</div>
    {active && <div className={styles.card}><strong>{active.title}</strong><p>{active.description}</p><button onClick={() => interactionManager.dispatch({ type: 'confirmClue' })}>收集线索</button></div>}
    <p>已收集 {snap.foundIds.length}/{config.payload.completion.requiredIds.length}</p><button disabled={!config.payload.completion.requiredIds.every((id) => snap.foundIds.includes(id))} onClick={() => interactionManager.dispatch({ type: 'confirmFinish' })}>结束搜证</button></>;
}
function Qte({ model }: { model: InteractionViewModel }) {
  const config = model.config!; if (config.type !== 'qte') return null; const snap = model.snapshot as Extract<typeof model.snapshot, { type: 'qte' }>;
  const step = config.payload.steps[snap.stepIndex];
  const keys = (config.payload.bindings[step.action] || []).map((code) => ({ ArrowLeft: '←', ArrowRight: '→', ArrowUp: '↑', ArrowDown: '↓', Space: '空格', KeyA: 'A', KeyD: 'D', KeyW: 'W', KeyS: 'S' }[code] || code));
  const duration = step.windowMs * config.payload.timeScale;
  const remainingPercent = Math.max(0, Math.min(100, snap.remainingMs / duration * 100));
  return <section className={styles.qte}><p>第 {snap.stepIndex + 1}/{config.payload.steps.length} 步 · 限时操作</p><div className={styles.keyPrompt}>{keys.join(' / ')}</div><p>请按键盘上的指定按键</p><div className={styles.timerTrack} aria-label="剩余时间"><div className={styles.timerFill} style={{ width: `${remainingPercent}%` }} /></div><p className={styles.timerText}>{(snap.remainingMs / 1000).toFixed(1)} 秒</p></section>;
}
function Movement({ model }: { model: InteractionViewModel }) {
  const config = model.config!; if (config.type !== 'movement') return null; const snap = model.snapshot as Extract<typeof model.snapshot, { type: 'movement' }>;
  return <><p>使用方向键或 WASD 控制宝玉移动。到黛玉身边后，按空格或回车确认。</p><p>当前位置：{Math.round(snap.currentAnchor.x)}, {Math.round(snap.currentAnchor.y)} {snap.reachedGoalId ? '（已到达目标）' : ''}</p><button disabled={!snap.reachedGoalId} onClick={() => interactionManager.dispatch({ type: 'confirmFinish' })}>确认到达</button></>;
}
