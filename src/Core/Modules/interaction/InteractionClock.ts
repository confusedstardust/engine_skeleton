export class InteractionClock {
  private active = false;
  private last = 0;
  private elapsed = 0;
  public start() { this.active = true; this.last = performance.now(); }
  public pause() { this.tick(); this.active = false; }
  public reset() { this.active = false; this.elapsed = 0; this.last = 0; }
  public tick() { if (!this.active) return 0; const now = performance.now(); const delta = now - this.last; this.last = now; this.elapsed += delta; return delta; }
  public getElapsed() { this.tick(); return this.elapsed; }
}
