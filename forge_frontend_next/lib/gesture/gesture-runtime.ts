import { CameraManager } from "./camera-manager";
import { HandTrackingAdapter } from "./hand-tracking-adapter";
import { interpretHand } from "./gesture-interpreter";
import { GestureStateMachine } from "./gesture-state-machine";
import { GestureBindingDispatcher } from "./gesture-dispatcher";
import type { GestureBindings, GestureEvent, GestureManifest, GestureAction, NarActionEvent } from "./gesture-types";

export class GestureRuntime {
  private camera = new CameraManager();
  private tracker = new HandTrackingAdapter();
  private machine = new GestureStateMachine();
  private listeners = new Set<(event: GestureEvent) => void>();
  private dispatcher: GestureBindingDispatcher;
  private running = false;
  private disposed = false;
  private generation = 0;
  private raf = 0;
  private lastInference = 0;
  private lastStamp = 0;
  constructor(bindings: GestureBindings, manifest: GestureManifest, send:(action:GestureAction,event:NarActionEvent)=>void) {
    this.dispatcher = new GestureBindingDispatcher(bindings,manifest,send);
  }
  setHoverTarget(target: boolean) { this.machine.setHoverTarget(target); }
  onEvent(listener: (event: GestureEvent) => void) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  async start() {
    if (this.disposed) throw new Error("Runtime 已释放");
    if (this.running) return;
    this.running = true;
    const generation = ++this.generation;
    try {
      // Permission request comes directly from the user's click (iOS Safari).
      const video = await this.camera.start();
      if (!this.running || this.generation !== generation) { this.camera.stop(); return; }
      await this.tracker.initialize();
      if (!this.running || this.generation !== generation) { this.tracker.dispose(); this.camera.stop(); return; }
      this.lastInference = 0; this.lastStamp = 0;
      const loop = (time:number) => {
        if (!this.running || this.generation !== generation || document.hidden) return;
        if (time - this.lastInference >= 1000 / 15 && video.readyState >= 2) {
          this.lastInference = time;
          // detectForVideo is synchronous; one rAF = one inference maximum.
          try {
            const result = this.tracker.detect(video,Math.max(time,this.lastStamp + 0.001));
            this.lastStamp = Math.max(time,this.lastStamp + 0.001);
            if (result !== undefined) {
              const events = this.machine.update(interpretHand(result ?? undefined),time);
              this.dispatcher.dispatch(events);
              for (const event of events) for (const listener of this.listeners) listener(event);
            }
          } catch {
            // Preserve regular mouse/touch interaction if MediaPipe stops working.
            this.stop(); return;
          }
        }
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
    } catch (error) {
      this.stop();
      throw error instanceof Error ? error : new Error("手势识别无法启动");
    }
  }
  stop() {
    this.running = false; this.generation += 1;
    cancelAnimationFrame(this.raf); this.raf = 0;
    this.camera.stop(); this.tracker.dispose(); this.machine.reset();
  }
  dispose() { if (this.disposed) return; this.disposed = true; this.stop(); this.listeners.clear(); }
}
