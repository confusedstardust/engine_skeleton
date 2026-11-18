import type { GestureId, GestureEvent, HandFeatures, Direction } from "./gesture-types";

const ACTIVATION_MS = 100;
const LOST_MS = 180;
const PALM_HOLD_MS = 900;
const PALM_COOLDOWN_MS = 1200;
const DWELL_MS = 700;
const DWELL_RADIUS = 0.025;
const SWIPE_MIN = 0.15;
const delta = (a: {x:number;y:number}, b: {x:number;y:number}) => Math.hypot(a.x-b.x,a.y-b.y);
type Point = {x:number;y:number};
type Continuous = Exclude<GestureId, "open_palm_hold">;

/** Single-hand deterministic arbitration; no model-authored thresholds. */
export class GestureStateMachine {
  private active: Continuous | null = null;
  private candidate: GestureId | null = null;
  private candidateAt = 0;
  private lastVisible = 0;
  private lastPoint: Point | null = null;
  private pointerFrom: Point | null = null;
  private pointerSince = 0;
  private dwellFrom: Point | null = null;
  private dwellAt = 0;
  private dwellFired = false;
  private swipeFired = false;
  private palmTriggered = false;
  private palmReleaseAt = 0;
  private hoverTarget = false;
  private lastTimestamp = 0;

  setHoverTarget(hasTarget: boolean) {
    this.hoverTarget = hasTarget;
    if (!hasTarget) { this.dwellAt = 0; this.dwellFrom = null; this.dwellFired = false; }
  }

  reset() {
    this.active = null; this.candidate = null; this.lastPoint = null;
    this.pointerFrom = null; this.dwellFrom = null; this.dwellAt = 0;
    this.dwellFired = false; this.swipeFired = false; this.palmTriggered = false;
    this.hoverTarget = false; this.lastTimestamp = 0;
  }

  update(f: HandFeatures | null, timestamp: number): GestureEvent[] {
    if (!Number.isFinite(timestamp) || timestamp < this.lastTimestamp) return [];
    this.lastTimestamp = timestamp;
    const events: GestureEvent[] = [];
    const emit = (id: GestureId, phase: GestureEvent["phase"], data: GestureEvent["data"] = {}) =>
      events.push({gestureId:id, phase, data, timestamp});
    if (f) this.lastVisible = timestamp;
    if (!f) {
      if (this.active && timestamp - this.lastVisible >= LOST_MS) {
        emit(this.active,"end");
        this.reset();
      }
      return events;
    }
    // Fist takes precedence over incidental thumb/index proximity.
    const pose: GestureId | null = f.fist ? "fist_rotate" :
      f.pinchRatio <= (this.active === "pinch" ? 0.50 : 0.35) ? "pinch" :
      f.pointer ? "index_pointer" : f.palm ? "open_palm_hold" : null;

    if (pose !== this.candidate) {
      this.candidate = pose;
      this.candidateAt = timestamp;
      if (pose !== "open_palm_hold") this.palmTriggered = false;
    }
    if (this.active && pose !== this.active) {
      emit(this.active, "end");
      this.active = null; this.lastPoint = null;
      this.pointerFrom = null; this.dwellAt = 0; this.dwellFired = false;
      this.swipeFired = false; this.hoverTarget = false;
    }
    if (pose === "open_palm_hold") {
      if (!this.palmTriggered && timestamp - this.candidateAt >= PALM_HOLD_MS &&
          (this.palmReleaseAt === 0 || timestamp - this.palmReleaseAt >= PALM_COOLDOWN_MS)) {
        emit("open_palm_hold","trigger");
        this.palmTriggered = true;
        this.palmReleaseAt = timestamp;
      }
      return events;
    }
    if (!pose) return events;
    if (!this.active) {
      if (timestamp - this.candidateAt < ACTIVATION_MS) return events;
      this.active = pose;
      this.lastPoint = {x:pose === "fist_rotate" ? f.cx : f.x,y:pose === "fist_rotate" ? f.cy : f.y};
      if (pose === "index_pointer") {
        this.pointerFrom = {x:f.x,y:f.y}; this.pointerSince = timestamp;
        this.dwellFrom = {x:f.x,y:f.y}; this.dwellAt = timestamp;
      }
      emit(pose,"start",pose === "fist_rotate" ? {} : {x:f.x,y:f.y});
      return events;
    }
    const now = {x:pose === "fist_rotate" ? f.cx : f.x,y:pose === "fist_rotate" ? f.cy : f.y};
    const previous = this.lastPoint ?? now;
    // Clamp relative deltas so tracking jumps never rotate/drag an entire scene.
    const dx = Math.max(-0.15,Math.min(0.15,now.x-previous.x));
    const dy = Math.max(-0.15,Math.min(0.15,now.y-previous.y));
    this.lastPoint = now;
    const data = pose === "fist_rotate" ? {dx,dy} : {x:f.x,y:f.y,dx,dy};
    emit(pose,"move",data);
    if (pose !== "index_pointer") return events;
    const from = this.pointerFrom ?? now;
    const movement = delta(from,now), duration = timestamp - this.pointerSince;
    if (!this.swipeFired && movement >= SWIPE_MIN && duration >= 150 && duration <= 500) {
      const horizontal = Math.abs(now.x-from.x) >= Math.abs(now.y-from.y);
      const direction: Direction = horizontal ? (now.x > from.x ? "right" : "left") : (now.y > from.y ? "down" : "up");
      emit(pose,"swipe",{direction,x:f.x,y:f.y});
      this.swipeFired = true;
      this.dwellFired = true;
    }
    if (duration > 500 && movement < SWIPE_MIN) {
      this.pointerFrom = now; this.pointerSince = timestamp;
    }
    if (!this.hoverTarget || this.swipeFired) return events;
    if (!this.dwellFrom || delta(this.dwellFrom,now) > DWELL_RADIUS) {
      this.dwellFrom = now; this.dwellAt = timestamp; this.dwellFired = false;
    } else if (!this.dwellFired && timestamp - this.dwellAt >= DWELL_MS) {
      emit(pose,"click",{x:f.x,y:f.y});
      this.dwellFired = true;
    }
    return events;
  }
}
