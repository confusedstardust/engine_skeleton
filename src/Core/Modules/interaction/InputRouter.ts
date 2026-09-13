import type { PauseReason } from './types';

/** The single authority for story-input ownership while an interaction is active. */
export class InputRouter {
  private mode: 'story' | 'interaction' | 'continuation-wait' = 'story';
  private pauses = new Set<PauseReason>();
  public canAdvanceStory() { return this.mode === 'story' && this.pauses.size === 0; }
  public setInteractionActive(active: boolean) { this.mode = active ? 'interaction' : 'story'; }
  public setContinuationWait() { this.mode = 'continuation-wait'; }
  public releaseContinuation() { if (this.pauses.size === 0) this.mode = 'story'; }
  public addPause(reason: PauseReason) { this.pauses.add(reason); }
  public removePause(reason: PauseReason) { this.pauses.delete(reason); }
  public getPauseReasons(): PauseReason[] { return Array.from(this.pauses); }
  public get activeMode() { return this.mode; }
  public reset() { this.mode = 'story'; this.pauses.clear(); }
}
export const inputRouter = new InputRouter();
