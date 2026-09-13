import { stageStateManager } from '@/Core/Modules/stage/stageStateManager';
import { WebGAL } from '@/Core/WebGAL';
import { nextSentence } from '@/Core/controller/gamePlay/nextSentence';
import { inputRouter } from './InputRouter';
import { InteractionClock } from './InteractionClock';
import { loadInteractionConfig } from './configLoader';
import type { InteractionAction, InteractionConfig, InteractionLifecycle, InteractionResult, InteractionSaveState, InteractionViewModel, ModuleSnapshot, PauseReason } from './types';

type Listener = (model: InteractionViewModel) => void;
const emptySave = (): InteractionSaveState => ({ schemaVersion: 1, contentVersion: 'interaction-v1', active: null, receipts: {}, pendingContinuation: null });

/** Owns exactly one blocking interaction; views only dispatch typed actions to it. */
export class InteractionManager {
  private lifecycle: InteractionLifecycle = 'idle'; private config: InteractionConfig | null = null; private snapshot: ModuleSnapshot | null = null;
  private instanceId = ''; private nodeId = ''; private configPath = ''; private epoch = 0; private abort: AbortController | null = null;
  private listeners = new Set<Listener>(); private clock = new InteractionClock(); private pauses = new Set<PauseReason>(); private settled = false; private qteTimer: ReturnType<typeof setTimeout> | null = null; private qteDeadlineAt = 0;
  public subscribe(listener: Listener) { this.listeners.add(listener); listener(this.model()); return () => { this.listeners.delete(listener); }; }
  public get isActive() { return this.lifecycle !== 'idle' && this.lifecycle !== 'cancelled'; }
  public canAdvanceStory() { return inputRouter.canAdvanceStory(); }
  public getViewModel() { return this.model(); }
  public async activate(nodeId: string, configPath: string, sceneUrl: string, enteredSentenceId: number) {
    this.cancel(); this.epoch++; const epoch = this.epoch; this.instanceId = `${nodeId}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`; this.nodeId = nodeId; this.configPath = configPath; this.lifecycle = 'loading'; this.settled = false; inputRouter.setInteractionActive(true); this.emit();
    this.abort = new AbortController();
    try { const config = await loadInteractionConfig(configPath, this.abort.signal); if (epoch !== this.epoch) return; if (config.id !== nodeId || config.sceneFile !== sceneUrl.split('/').pop()) throw new Error('交互节点 ID 或场景文件不匹配。'); this.config = config; this.snapshot = this.initialSnapshot(config); this.lifecycle = 'ready'; this.persistActive(sceneUrl, enteredSentenceId); this.emit(); }
    catch (error) { if (epoch !== this.epoch || (error as Error).name === 'AbortError') return; this.lifecycle = 'error'; this.emit((error as Error).message); }
  }
  public start() { if (this.lifecycle !== 'ready' || this.pauses.size) return; this.lifecycle = 'running'; this.clock.start(); this.armQteDeadline(); this.persistActive(); this.emit(); }
  public dispatch(action: InteractionAction) {
    if (!this.config) return; if (action.type === 'start') return this.start(); if (action.type === 'skip' && this.config.payload.allowSkip) return this.complete({ outcome: 'skipped', values: this.defaultValues() });
    if (this.lifecycle !== 'running') return;
    if (this.config.type === 'investigation') this.investigation(action);
    if (this.config.type === 'qte') this.qte(action);
    if (this.config.type === 'movement') this.movement(action);
  }
  public pause(reason: PauseReason) { if (!this.isActive) return; this.pauses.add(reason); if (this.lifecycle === 'running') { this.clock.pause(); this.clearTimer(); this.lifecycle = 'paused'; } this.emit(); }
  public resume(reason: PauseReason) { this.pauses.delete(reason); if (this.lifecycle === 'paused' && this.pauses.size === 0) { this.lifecycle = 'ready'; } this.emit(); }
  public continueAfterPause() { this.pauses.delete('manual'); if (this.lifecycle === 'paused') this.lifecycle = 'ready'; this.emit(); }
  public complete(result: InteractionResult) {
    if (this.lifecycle !== 'running' || this.settled) return; this.settled = true; this.lifecycle = 'settling'; this.clock.pause(); this.clearTimer();
    const save = this.save(); save.receipts[this.instanceId] = result; save.pendingContinuation = { receiptId: this.instanceId, sceneUrl: '', continueSentenceId: 0 }; save.active = null;
    Object.entries(this.config!.resultBindings).forEach(([source, target]) => { const value = source === 'outcome' ? result.outcome : result.values[source]; if (value !== undefined) stageStateManager.setStageVar({ key: target, value }); });
    stageStateManager.setStage('interactionState', save); stageStateManager.commit(); this.lifecycle = 'completed'; inputRouter.setContinuationWait(); this.emit();
  }
  /** Explicit UI action: never allow the completing click/key to fall through into story input. */
  public continueStory() { if (this.lifecycle !== 'completed' || this.pauses.size) return; const state = this.save(); state.pendingContinuation = null; stageStateManager.setStage('interactionState', state); stageStateManager.commit(); inputRouter.releaseContinuation(); WebGAL.gameplay.performController.unmountPerformByPrefix('interaction#', true); this.dispose(); nextSentence(); }
  public flushToStageState() { if (this.lifecycle === 'loading' || this.lifecycle === 'error' || this.lifecycle === 'settling') return false; this.persistActive(); return true; }
  public cancel() { this.epoch++; this.abort?.abort(); this.abort = null; this.clearTimer(); this.clock.reset(); this.config = null; this.snapshot = null; this.lifecycle = 'idle'; this.pauses.clear(); inputRouter.reset(); this.emit(); }
  public dispose() { this.clearTimer(); this.config = null; this.snapshot = null; this.lifecycle = 'idle'; this.pauses.clear(); inputRouter.reset(); this.emit(); }
  private investigation(action: InteractionAction) { const config = this.config; if (!config || config.type !== 'investigation') return; const snap = this.snapshot as Extract<ModuleSnapshot, { type: 'investigation' }>; if (action.type === 'pointerInspect') { if (config.payload.hotspots.some((h) => h.id === action.hotspotId)) snap.activeCardId = action.hotspotId; } if (action.type === 'confirmClue' && snap.activeCardId) { if (!snap.foundIds.includes(snap.activeCardId)) snap.foundIds.push(snap.activeCardId); snap.activeCardId = null; } if (action.type === 'confirmFinish' && config.payload.completion.requiredIds.every((id) => snap.foundIds.includes(id))) this.complete({ outcome: 'success', values: this.defaultValues() }); this.emit(); }
  private qte(action: InteractionAction) { const config = this.config; if (!config || config.type !== 'qte' || action.type !== 'qteAction') return; const snap = this.snapshot as Extract<ModuleSnapshot, { type: 'qte' }>; const expected = config.payload.steps[snap.stepIndex]; if (!expected) return; if (action.action !== expected.action) return this.complete({ outcome: 'failed', values: { completedSteps: snap.completedSteps } }); snap.stepIndex++; snap.completedSteps++; if (snap.stepIndex === config.payload.steps.length) return this.complete({ outcome: 'success', values: { completedSteps: snap.completedSteps } }); this.armQteDeadline(); this.emit(); }
  private movement(action: InteractionAction) { const config = this.config; if (!config || config.type !== 'movement' || (action.type !== 'moveAxes' && action.type !== 'confirmFinish')) return; const snap = this.snapshot as Extract<ModuleSnapshot, { type: 'movement' }>; const p = config.payload; if (action.type === 'moveAxes') {
    const step = Math.max(8, Math.round(p.speed / 16));
    snap.currentAnchor.x = Math.max(p.bounds.x, Math.min(p.bounds.x + p.bounds.width, snap.currentAnchor.x + action.x * step));
    snap.currentAnchor.y = Math.max(p.bounds.y, Math.min(p.bounds.y + p.bounds.height, snap.currentAnchor.y + action.y * step));
    // Persist the visual offset through StageState, then let the normal Pixi sync own
    // the render. Directly assigning Pixi x/y would be overwritten by the next sync.
    stageStateManager.updateEffectAndCommit({ target: p.target, transform: { position: {
      x: snap.currentAnchor.x - p.initialAnchor.x,
      y: snap.currentAnchor.y - p.initialAnchor.y,
    } } });
    const r = p.goal.rect; snap.reachedGoalId = snap.currentAnchor.x >= r.x && snap.currentAnchor.x <= r.x + r.width && snap.currentAnchor.y >= r.y && snap.currentAnchor.y <= r.y + r.height ? p.goal.id : null;
  } else if (snap.reachedGoalId) this.complete({ outcome: 'success', values: { reached: true } }); this.persistActive(); this.emit(); }
  private armQteDeadline() { this.clearTimer(); if (this.lifecycle !== 'running' || this.config?.type !== 'qte') return; const snap = this.snapshot as Extract<ModuleSnapshot, { type: 'qte' }>; const step = this.config.payload.steps[snap.stepIndex]; const ms = step.windowMs * this.config.payload.timeScale; snap.remainingMs = ms; this.qteDeadlineAt = performance.now() + ms; this.qteTimer = setTimeout(() => this.complete({ outcome: 'failed', values: { completedSteps: snap.completedSteps } }), ms); }
  private clearTimer() { if (this.qteTimer) clearTimeout(this.qteTimer); this.qteTimer = null; this.qteDeadlineAt = 0; }
  private initialSnapshot(config: InteractionConfig): ModuleSnapshot { if (config.type === 'investigation') return { type: 'investigation', foundIds: [], activeCardId: null, activeElapsedMs: 0 }; if (config.type === 'qte') return { type: 'qte', stepIndex: 0, remainingMs: 0, completedSteps: 0, effectiveTimeScale: config.payload.timeScale }; return { type: 'movement', originalTransform: null, currentAnchor: { ...config.payload.initialAnchor }, reachedGoalId: null }; }
  private defaultValues(): Record<string, string | number | boolean> { if (!this.config) return {}; if (this.config.type === 'investigation') { const found = (this.snapshot as Extract<ModuleSnapshot, { type: 'investigation' }>).foundIds; return Object.fromEntries(this.config.payload.hotspots.map((h) => [`clue_${h.id}`, found.includes(h.id)])); } return {}; }
  private save(): InteractionSaveState { return stageStateManager.getCalculationStageState().interactionState || emptySave(); }
  private persistActive(sceneUrl = '', enteredSentenceId = 0) { if (!this.config || !this.snapshot) return; const save = this.save(); save.active = { instanceId: this.instanceId, nodeId: this.nodeId, kind: this.config.type, configPath: this.configPath, sceneUrl, enteredSentenceId, continueSentenceId: enteredSentenceId + 1, lifecycle: this.lifecycle === 'running' ? 'running' : this.lifecycle === 'paused' ? 'paused' : 'ready', resumePolicy: this.config.resumePolicy, module: this.snapshot }; stageStateManager.setStage('interactionState', save); }
  private model(error?: string): InteractionViewModel {
    if (this.lifecycle === 'running' && this.config?.type === 'qte' && this.snapshot?.type === 'qte' && this.qteDeadlineAt) {
      this.snapshot.remainingMs = Math.max(0, this.qteDeadlineAt - performance.now());
    }
    return { lifecycle: this.lifecycle, config: this.config, snapshot: this.snapshot, pauseReasons: Array.from(this.pauses), error };
  }
  private emit(error?: string) { const model = this.model(error); this.listeners.forEach((listener) => listener(model)); }
}
export const interactionManager = new InteractionManager();
