import { OneEuroFilter } from './oneEuro';
import { computeFeatures, smooth } from './features';
import { DEFAULT_MOTION, MOTIONS, type MotionConfig, type MotionDetector, type Sample } from './motions';
import { POSES, scorePose } from './poses';
import type { GestureEvent, GestureFrame, HandInput, HandResult, PoseDef, TwoHandState, Vec3 } from './types';

export interface PoseConfig {
  /** A pose becomes active at this score… */
  enter: number;
  /** …and stays active until it drops below this. */
  exit: number;
  /** A different pose must beat the active one by this much to take over. */
  margin: number;
  /** Candidate must persist this long before the switch (ms). */
  debounceMs: number;
  /** Include experimental poses. */
  experimental: boolean;
}

export const DEFAULT_POSE: PoseConfig = { enter: 0.62, exit: 0.42, margin: 0.08, debounceMs: 70, experimental: true };

export interface EngineConfig { pose: PoseConfig; motion: MotionConfig; smoothing: { minCutoff: number; beta: number } }
/** Any subset of the config, e.g. `{ pose: { experimental: false } }` or JSON exported from the Gesture Lab. */
export interface EngineConfigInput { pose?: Partial<PoseConfig>; motion?: Partial<MotionConfig>; smoothing?: Partial<EngineConfig['smoothing']> }

export const DEFAULT_CONFIG: EngineConfig = {
  pose: DEFAULT_POSE,
  motion: DEFAULT_MOTION,
  smoothing: { minCutoff: 2.2, beta: 8 },
};

const HISTORY_MS = 1600;
/** A hand unseen this long is forgotten (its pose ends). */
const LOST_MS = 250;

interface Track {
  id: number;
  handedness: 'Left' | 'Right';
  lastSeen: number;
  filters: OneEuroFilter[];
  wfilters: OneEuroFilter[];
  pose: string | null;
  poseSince: number;
  cand: string | null;
  candSince: number;
  held: boolean;
  hist: Sample[];
  mem: Record<string, Record<string, number>>;
  cooldown: Record<string, number>;
  vel: { x: number; y: number };
  result: HandResult | null;
}

type Listener = (e: GestureEvent) => void;

/**
 * GESTURE ENGINE. Feed it hands every frame; get back stable poses, per-pose scores, continuous
 * values and discrete events (pose start/end, swipes, circles, taps, claps, …).
 *
 *   const engine = new GestureEngine();
 *   engine.on('swipe-left', (e) => …);
 *   engine.on('pose', (e) => …);           // every pose start/end
 *   const frame = engine.update(hands, performance.now());
 */
export class GestureEngine {
  config: EngineConfig;
  /** The latest frame (already updated when event listeners run). */
  frame: GestureFrame = { t: 0, hands: [], twoHand: { present: false, distance: 0, angle: 0, zoom: 1 }, events: [] };
  poses: PoseDef[];
  motions: MotionDetector[];
  private tracks: Track[] = [];
  private nextId = 0;
  private listeners = new Map<string, Set<Listener>>();
  private two = { prevD: -1, clapSpeed: 0, clapCool: 0, grip: '' as string, d0: 0, a0: 0, zoomFired: '', steerFired: '', lastT: 0, busyUntil: 0 };

  constructor(config: EngineConfigInput = {}) {
    this.config = {
      pose: { ...DEFAULT_POSE, ...config.pose },
      motion: { ...DEFAULT_MOTION, ...config.motion },
      smoothing: { ...DEFAULT_CONFIG.smoothing, ...config.smoothing },
    };
    this.poses = [...POSES];
    this.motions = [...MOTIONS];
  }

  /** Add or replace a pose. */
  registerPose(def: PoseDef) { this.poses = [...this.poses.filter((p) => p.id !== def.id), def]; }
  /** Add or replace a motion detector. */
  registerMotion(d: MotionDetector) { this.motions = [...this.motions.filter((m) => m.id !== d.id), d]; }

  /**
   * Listen to events. `name` is an event name ('fist', 'swipe-left', 'clap', …), a kind
   * ('pose' | 'motion' | 'two-hand') or '*' for everything. Returns an unsubscribe function.
   */
  on(name: string, fn: Listener): () => void {
    let set = this.listeners.get(name);
    if (!set) this.listeners.set(name, (set = new Set()));
    set.add(fn);
    return () => set!.delete(fn);
  }

  /** Every gesture name the engine can emit (poses + motions + two-hand), for UIs. */
  get catalog() {
    return {
      poses: this.activePoses().map((p) => ({ id: p.id, name: p.name, emoji: p.emoji, hint: p.hint, experimental: !!p.experimental })),
      motions: this.motions.flatMap((m) => m.names),
      twoHand: ['clap', 'zoom-in', 'zoom-out', 'steer-left', 'steer-right'],
    };
  }

  reset() { this.tracks = []; this.two.prevD = -1; this.two.grip = ''; }

  private activePoses() { return this.config.pose.experimental ? this.poses : this.poses.filter((p) => !p.experimental); }

  update(inputs: HandInput[], t: number): GestureFrame {
    const events: GestureEvent[] = [];
    const emit = (e: GestureEvent) => events.push(e);
    const live = this.assign(inputs, t);
    // hands that vanished end their pose
    for (const tr of this.tracks) {
      if (t - tr.lastSeen > LOST_MS) {
        if (tr.pose) emit({ kind: 'pose', name: tr.pose, phase: 'end', hand: tr.id, t });
        tr.pose = null;
      }
    }
    this.tracks = this.tracks.filter((tr) => t - tr.lastSeen <= LOST_MS);

    // both hands moving fast in opposite directions → a two-hand gesture, not two one-hand swipes
    const movers = live.map(([tr]) => tr).filter((tr) => Math.hypot(tr.vel.x, tr.vel.y) > 0.5);
    if (movers.length >= 2 && movers[0].vel.x * movers[1].vel.x + movers[0].vel.y * movers[1].vel.y < 0) this.two.busyUntil = t + 300;
    const busy = t < this.two.busyUntil;

    const hands: HandResult[] = [];
    for (const [tr, input] of live) hands.push(this.updateHand(tr, input, t, emit, busy));
    hands.sort((a, b) => a.id - b.id);
    const twoHand = this.updateTwo(hands, t, emit);

    this.frame = { t, hands, twoHand, events };
    for (const e of events) this.dispatch(e);
    return this.frame;
  }

  // ---------------------------------------------------------------- hand identity
  private assign(inputs: HandInput[], t: number): [Track, HandInput][] {
    const out: [Track, HandInput][] = [];
    const free = new Set(this.tracks);
    const centre = (h: HandInput) => { const L = h.landmarks; return { x: (L[0].x + L[9].x) / 2, y: (L[0].y + L[9].y) / 2 }; };
    // explicit ids first
    for (const h of inputs) {
      if (h.landmarks.length !== 21 || h.id === undefined) continue;
      let tr = this.tracks.find((x) => x.id === h.id);
      if (!tr) { tr = this.newTrack(h, h.id); this.tracks.push(tr); }
      free.delete(tr);
      out.push([tr, h]);
    }
    // then nearest previous position
    for (const h of inputs) {
      if (h.landmarks.length !== 21 || h.id !== undefined) continue;
      const c = centre(h);
      let best: Track | null = null, bd = 0.35;
      for (const tr of free) {
        const r = tr.result;
        if (!r) continue;
        const d = Math.hypot(r.features.center.x - c.x, r.features.center.y - c.y) + (tr.handedness === h.handedness ? 0 : 0.1);
        if (d < bd) { bd = d; best = tr; }
      }
      if (!best) { best = this.newTrack(h); this.tracks.push(best); }
      free.delete(best);
      out.push([best, h]);
    }
    for (const [tr] of out) tr.lastSeen = t;
    return out;
  }

  private newTrack(h: HandInput, id?: number): Track {
    const s = this.config.smoothing;
    const mk = () => Array.from({ length: 63 }, () => new OneEuroFilter({ minCutoff: s.minCutoff, beta: s.beta, dCutoff: 1 }));
    return {
      id: id ?? this.nextId++, handedness: h.handedness, lastSeen: 0, filters: mk(), wfilters: mk(),
      pose: null, poseSince: 0, cand: null, candSince: 0, held: false,
      hist: [], mem: {}, cooldown: {}, vel: { x: 0, y: 0 }, result: null,
    };
  }

  // ---------------------------------------------------------------- one hand
  private updateHand(tr: Track, input: HandInput, t: number, emit: (e: GestureEvent) => void, busy = false): HandResult {
    const sec = t / 1000;
    const filt = (pts: Vec3[], f: OneEuroFilter[], scale: number) => pts.map((p, i) => ({
      x: f[i * 3].filter(p.x * scale, sec) / scale,
      y: f[i * 3 + 1].filter(p.y * scale, sec) / scale,
      z: f[i * 3 + 2].filter(p.z * scale, sec) / scale,
    }));
    // world landmarks are in metres (~0.1 per hand): scale up so the filter's speed terms behave alike
    const hand: HandInput = {
      ...input,
      landmarks: filt(input.landmarks, tr.filters, 1),
      world: input.world && input.world.length === 21 ? filt(input.world, tr.wfilters, 10) : undefined,
    };
    tr.handedness = input.handedness;
    const f = computeFeatures(hand);

    // ---- poses
    const scores: Record<string, number> = {};
    let best: string | null = null, bestS = 0;
    for (const p of this.activePoses()) {
      const s = scorePose(p, f);
      scores[p.id] = s;
      if (s > bestS) { bestS = s; best = p.id; }
    }
    const cfg = this.config.pose;
    const cur = tr.pose;
    const curS = cur ? scores[cur] ?? 0 : 0;
    let want: string | null = cur;
    if (cur && curS < cfg.exit) want = null;
    if (best && bestS >= cfg.enter && best !== cur && (!cur || bestS > curS + cfg.margin)) want = best;
    if (want !== cur) {
      if (tr.cand !== want) { tr.cand = want; tr.candSince = t; }
      // dropping to "no pose" waits a little longer, so poses don't blink off between frames
      const need = want === null ? cfg.debounceMs * 1.6 : cfg.debounceMs;
      if (t - tr.candSince >= need) {
        if (cur) emit({ kind: 'pose', name: cur, phase: 'end', hand: tr.id, t, data: { heldMs: Math.round(t - tr.poseSince) } });
        tr.pose = want;
        tr.poseSince = t;
        tr.held = false;
        if (want) emit({ kind: 'pose', name: want, phase: 'start', hand: tr.id, t, data: { score: +bestS.toFixed(2) } });
      }
    } else tr.cand = cur;
    if (tr.pose && !tr.held && t - tr.poseSince >= this.config.motion.holdMs) {
      tr.held = true;
      emit({ kind: 'motion', name: 'hold', hand: tr.id, t, data: { pose: tr.pose } });
    }

    // ---- motion history + velocity
    const pinch = 1 - smooth(0.2, 0.42, f.tipGap[0]);
    const prev = tr.hist[tr.hist.length - 1];
    const sample: Sample = { t, x: f.center.x, y: f.center.y, size: f.size, roll: f.roll, pose: tr.pose, pinch, open: f.openness };
    if (prev && t > prev.t) {
      const dt = (t - prev.t) / 1000, k = 1 - Math.exp(-dt / 0.06);
      tr.vel.x += k * ((sample.x - prev.x) / dt - tr.vel.x);
      tr.vel.y += k * ((sample.y - prev.y) / dt - tr.vel.y);
    }
    tr.hist.push(sample);
    while (tr.hist.length && t - tr.hist[0].t > HISTORY_MS) tr.hist.shift();
    for (const d of this.motions) {
      const mem = (tr.mem[d.id] ??= {});
      const hit = d.detect({ h: tr.hist, now: t, cfg: this.config.motion, mem, busy });
      if (!hit) continue;
      const cd = d.cooldownMs ?? this.config.motion.cooldownMs;
      if (t < (tr.cooldown[d.id] ?? 0)) continue;
      tr.cooldown[d.id] = t + cd;
      emit({ kind: 'motion', name: hit.name, hand: tr.id, t, data: hit.data });
      if (hit.reset) tr.hist = [sample];
    }

    const res: HandResult = {
      id: tr.id, handedness: tr.handedness, features: f, pose: tr.pose, confidence: tr.pose ? scores[tr.pose] ?? 0 : 0,
      scores, heldMs: tr.pose ? t - tr.poseSince : 0, velocity: { ...tr.vel }, pinch, landmarks: hand.landmarks,
    };
    tr.result = res;
    return res;
  }

  // ---------------------------------------------------------------- two hands
  private updateTwo(hands: HandResult[], t: number, emit: (e: GestureEvent) => void): TwoHandState {
    const st = this.two, cfg = this.config.motion;
    const dt = st.lastT ? Math.min(0.1, (t - st.lastT) / 1000) : 0;
    st.lastT = t;
    st.clapCool = Math.max(0, st.clapCool - dt);
    if (hands.length < 2) { st.prevD = -1; st.clapSpeed = 0; st.grip = ''; return { present: false, distance: 0, angle: 0, zoom: 1 }; }
    // left-most on screen first
    const [a, b] = [...hands].sort((p, q) => p.features.center.x - q.features.center.x);
    const ca = a.features.center, cb = b.features.center;
    const d = Math.hypot(cb.x - ca.x, cb.y - ca.y);
    const ang = Math.atan2(cb.y - ca.y, cb.x - ca.x);

    // clap: open hands slammed together
    if (st.prevD >= 0 && dt > 0) st.clapSpeed = Math.max((st.prevD - d) / dt, st.clapSpeed - dt * 6);
    st.prevD = d;
    const opens = (h: HandResult) => h.features.openness > 0.55;
    if (st.clapCool <= 0 && opens(a) && opens(b) && d < cfg.clapDist && st.clapSpeed > cfg.clapSpeed) {
      st.clapCool = 1;
      st.clapSpeed = 0;
      emit({ kind: 'two-hand', name: 'clap', t });
    }

    // grip with both hands (both pinching or both fists) → zoom & steering wheel
    const gripOf = (h: HandResult) => (h.pinch > 0.7 ? 'pinch' : h.pose === 'fist' ? 'fist' : '');
    const g = gripOf(a) && gripOf(a) === gripOf(b) ? gripOf(a) : '';
    if (g !== st.grip) { st.grip = g; st.d0 = d; st.a0 = ang; st.zoomFired = ''; st.steerFired = ''; }
    let zoom = 1;
    if (g) {
      zoom = st.d0 > 1e-3 ? d / st.d0 : 1;
      if (zoom > cfg.zoomIn && st.zoomFired !== 'in') { st.zoomFired = 'in'; emit({ kind: 'two-hand', name: 'zoom-in', t, data: { zoom: +zoom.toFixed(2) } }); }
      if (zoom < cfg.zoomOut && st.zoomFired !== 'out') { st.zoomFired = 'out'; emit({ kind: 'two-hand', name: 'zoom-out', t, data: { zoom: +zoom.toFixed(2) } }); }
      let da = ang - st.a0;
      if (da > Math.PI) da -= 2 * Math.PI;
      if (da < -Math.PI) da += 2 * Math.PI;
      const lim = (cfg.steerDeg * Math.PI) / 180;
      // right hand lower than the left (positive angle on screen) = wheel turned right
      if (da > lim && st.steerFired !== 'r') { st.steerFired = 'r'; emit({ kind: 'two-hand', name: 'steer-right', t, data: { degrees: Math.round((da * 180) / Math.PI) } }); }
      if (da < -lim && st.steerFired !== 'l') { st.steerFired = 'l'; emit({ kind: 'two-hand', name: 'steer-left', t, data: { degrees: Math.round((da * 180) / Math.PI) } }); }
      if (Math.abs(da) < lim * 0.4) st.steerFired = '';
    }
    return { present: true, distance: d, angle: ang, zoom };
  }

  private dispatch(e: GestureEvent) {
    for (const key of [e.name, e.kind, '*']) this.listeners.get(key)?.forEach((fn) => fn(e));
  }
}
