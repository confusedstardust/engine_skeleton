/**
 * Motion gestures: detectors over a short per-hand history (position, size, roll, pose, pinch).
 * Each detector is a plain function so games can add their own with `engine.registerMotion`.
 */

export interface Sample {
  t: number;          // ms
  x: number; y: number;
  size: number;       // palm size (depth proxy)
  roll: number;       // radians
  pose: string | null;
  pinch: number;      // 0..1
  /** Raw (undebounced) mean finger extension 0..1. */
  open: number;
}

export interface MotionConfig {
  /** Swipe: travel (screen fraction) within `swipeMs`, and how dominant the main axis must be. */
  swipeDist: number; swipeMs: number; swipeAxis: number;
  /** Push / pull: palm size ratio change within `pushMs` while staying roughly in place. */
  pushRatio: number; pushMs: number; pushDrift: number;
  /** Circle: fraction of a full turn, minimum radius, time window. */
  circleTurns: number; circleRadius: number; circleMs: number;
  /** Wave (x) / shake (y): direction reversals of at least `waveAmp` within `waveMs`. */
  waveReversals: number; waveAmp: number; waveMs: number;
  /** Twist: roll change (degrees) within `twistMs`. */
  twistDeg: number; twistMs: number;
  /** Tap: pinch closed then opened within `tapMs`; double tap: two within `doubleTapMs`. */
  tapMs: number; doubleTapMs: number;
  /** Throw: fist opening while moving faster than this (screen / s). */
  throwSpeed: number;
  /** Hold: a pose kept this long. */
  holdMs: number;
  /** Two hands: clap closing speed and distance; zoom ratios; steering angle (degrees). */
  clapSpeed: number; clapDist: number;
  zoomIn: number; zoomOut: number;
  steerDeg: number;
  /** Same detector on the same hand can't fire again for this long. */
  cooldownMs: number;
}

export const DEFAULT_MOTION: MotionConfig = {
  swipeDist: 0.2, swipeMs: 380, swipeAxis: 1.8,
  pushRatio: 1.28, pushMs: 450, pushDrift: 0.09,
  circleTurns: 0.85, circleRadius: 0.035, circleMs: 1500,
  waveReversals: 3, waveAmp: 0.035, waveMs: 1300,
  twistDeg: 55, twistMs: 600,
  tapMs: 350, doubleTapMs: 550,
  throwSpeed: 1.1,
  holdMs: 800,
  clapSpeed: 0.9, clapDist: 0.2,
  zoomIn: 1.45, zoomOut: 0.7,
  steerDeg: 35,
  cooldownMs: 650,
};

export interface MotionHit { name: string; data?: Record<string, number | string>; /** clear the history after firing */ reset?: boolean }

export interface MotionContext {
  h: Sample[];
  now: number;
  cfg: MotionConfig;
  /** Per-hand scratch space a detector may keep between frames. */
  mem: Record<string, number>;
  /** Both hands are moving fast in opposite directions: a two-hand gesture (clap, zoom, wheel) is under way. */
  busy?: boolean;
}

export type MotionDetector = {
  id: string;
  names: string[];
  detect: (c: MotionContext) => MotionHit | null;
  /** Override MotionConfig.cooldownMs (e.g. 0 for taps, which must allow double taps). */
  cooldownMs?: number;
};

/** Latest sample at least `ms` old (or the oldest one). */
function back(h: Sample[], now: number, ms: number): Sample {
  for (let i = h.length - 1; i >= 0; i--) if (now - h[i].t >= ms) return h[i];
  return h[0];
}
const within = (h: Sample[], now: number, ms: number) => h.filter((s) => now - s.t <= ms);

export const MOTIONS: MotionDetector[] = [
  // throw first: a throw is also a fast sideways move, and must win over the swipe it contains
  {
    id: 'throw', names: ['throw'],
    detect: ({ h, now, cfg }) => {
      if (h.length < 3) return null;
      const cur = h[h.length - 1];
      // react to the fingers actually opening (raw), not the debounced pose: by the time "open"
      // is confirmed the arm has already slowed down
      if (cur.open < 0.6) return null;
      // was a fist a moment ago?
      const recent = within(h, now, 300);
      if (!recent.some((s) => s.pose === 'fist' || s.pose === 'claw')) return null;
      const old = back(h, now, 120);
      const dt = (cur.t - old.t) / 1000;
      if (dt <= 0) return null;
      const vx = (cur.x - old.x) / dt, vy = (cur.y - old.y) / dt;
      const sp = Math.hypot(vx, vy);
      if (sp < cfg.throwSpeed) return null;
      return { name: 'throw', reset: true, data: { vx: +vx.toFixed(2), vy: +vy.toFixed(2) } };
    },
  },
  {
    id: 'swipe', names: ['swipe-left', 'swipe-right', 'swipe-up', 'swipe-down'],
    detect: ({ h, now, cfg, busy }) => {
      const cur = h[h.length - 1], old = back(h, now, cfg.swipeMs);
      if (now - old.t < cfg.swipeMs * 0.4) return null;
      // each hand of a clap / zoom / wheel looks like a swipe on its own
      if (busy) return null;
      // a moving fist is carrying something (and may be about to throw it), not swiping
      if (cur.pose === 'fist') return null;
      const dx = cur.x - old.x, dy = cur.y - old.y;
      const ax = Math.abs(dx), ay = Math.abs(dy);
      if (Math.max(ax, ay) < cfg.swipeDist) return null;
      if (ax > ay * cfg.swipeAxis) return { name: dx < 0 ? 'swipe-left' : 'swipe-right', reset: true, data: { dist: ax } };
      if (ay > ax * cfg.swipeAxis) return { name: dy < 0 ? 'swipe-up' : 'swipe-down', reset: true, data: { dist: ay } };
      return null;
    },
  },
  {
    id: 'push', names: ['push', 'pull'],
    detect: ({ h, now, cfg }) => {
      const cur = h[h.length - 1], old = back(h, now, cfg.pushMs);
      if (now - old.t < cfg.pushMs * 0.4 || old.size <= 0) return null;
      if (Math.hypot(cur.x - old.x, cur.y - old.y) > cfg.pushDrift) return null;
      const r = cur.size / old.size;
      if (r > cfg.pushRatio) return { name: 'push', reset: true, data: { ratio: r } };
      if (r < 1 / cfg.pushRatio) return { name: 'pull', reset: true, data: { ratio: r } };
      return null;
    },
  },
  {
    id: 'circle', names: ['circle-cw', 'circle-ccw'],
    detect: ({ h, now, cfg }) => {
      const w = within(h, now, cfg.circleMs);
      if (w.length < 10) return null;
      let cx = 0, cy = 0;
      for (const s of w) { cx += s.x; cy += s.y; }
      cx /= w.length; cy /= w.length;
      let r = 0;
      for (const s of w) r += Math.hypot(s.x - cx, s.y - cy);
      r /= w.length;
      if (r < cfg.circleRadius) return null;
      let turn = 0;
      for (let i = 1; i < w.length; i++) {
        let d = Math.atan2(w[i].y - cy, w[i].x - cx) - Math.atan2(w[i - 1].y - cy, w[i - 1].x - cx);
        if (d > Math.PI) d -= 2 * Math.PI;
        if (d < -Math.PI) d += 2 * Math.PI;
        turn += d;
      }
      // screen y points down, so a positive angle sweep is clockwise as seen on screen
      if (Math.abs(turn) < cfg.circleTurns * 2 * Math.PI) return null;
      return { name: turn > 0 ? 'circle-cw' : 'circle-ccw', reset: true, data: { radius: r } };
    },
  },
  {
    id: 'wave', names: ['wave', 'shake'],
    detect: ({ h, now, cfg }) => {
      const w = within(h, now, cfg.waveMs);
      if (w.length < 8) return null;
      // direction changes of at least waveAmp (hysteresis, so jitter doesn't count)
      const reversals = (get: (s: Sample) => number) => {
        let n = 0, dir = 0, hi = get(w[0]), lo = hi;
        for (const s of w) {
          const v = get(s);
          if (v > hi) hi = v;
          if (v < lo) lo = v;
          if (dir !== -1 && hi - v > cfg.waveAmp) { if (dir === 1) n++; dir = -1; hi = lo = v; }
          else if (dir !== 1 && v - lo > cfg.waveAmp) { if (dir === -1) n++; dir = 1; hi = lo = v; }
        }
        return n;
      };
      const rx = reversals((s) => s.x), ry = reversals((s) => s.y);
      if (rx >= cfg.waveReversals && rx > ry) return { name: 'wave', reset: true, data: { reversals: rx } };
      if (ry >= cfg.waveReversals && ry > rx) return { name: 'shake', reset: true, data: { reversals: ry } };
      return null;
    },
  },
  {
    id: 'twist', names: ['twist-cw', 'twist-ccw'],
    detect: ({ h, now, cfg }) => {
      const cur = h[h.length - 1], old = back(h, now, cfg.twistMs);
      if (now - old.t < cfg.twistMs * 0.4) return null;
      let d = cur.roll - old.roll;
      if (d > Math.PI) d -= 2 * Math.PI;
      if (d < -Math.PI) d += 2 * Math.PI;
      if (Math.abs(d) < (cfg.twistDeg * Math.PI) / 180) return null;
      if (Math.hypot(cur.x - old.x, cur.y - old.y) > 0.12) return null; // a swipe, not a twist
      return { name: d > 0 ? 'twist-cw' : 'twist-ccw', reset: true, data: { degrees: Math.round((d * 180) / Math.PI) } };
    },
  },
  {
    id: 'tap', names: ['tap', 'double-tap'], cooldownMs: 0,
    detect: ({ h, now, cfg, mem }) => {
      const cur = h[h.length - 1];
      const closed = mem.closed === 1;
      if (!closed && cur.pinch > 0.75) { mem.closed = 1; mem.closedAt = now; return null; }
      if (closed && cur.pinch < 0.4) {
        mem.closed = 0;
        if (now - mem.closedAt > cfg.tapMs) return null;
        const dbl = now - (mem.lastTap ?? -1e9) < cfg.doubleTapMs;
        mem.lastTap = dbl ? -1e9 : now;
        return { name: dbl ? 'double-tap' : 'tap' };
      }
      return null;
    },
  },
];

/** Display info for motion and two-hand gestures (poses carry their own). */
export const MOTION_INFO: Record<string, { name: string; emoji: string; hint: string; hands?: 2 }> = {
  'swipe-left': { name: 'Swipe left', emoji: '⬅️', hint: 'Sweep your hand quickly to the left' },
  'swipe-right': { name: 'Swipe right', emoji: '➡️', hint: 'Sweep your hand quickly to the right' },
  'swipe-up': { name: 'Swipe up', emoji: '⬆️', hint: 'Sweep your hand quickly upward' },
  'swipe-down': { name: 'Swipe down', emoji: '⬇️', hint: 'Sweep your hand quickly downward' },
  push: { name: 'Push', emoji: '🫷', hint: 'Push your open palm toward the camera' },
  pull: { name: 'Pull', emoji: '🫳', hint: 'Pull your hand back away from the camera' },
  'circle-cw': { name: 'Circle clockwise', emoji: '🔃', hint: 'Draw a circle in the air, clockwise' },
  'circle-ccw': { name: 'Circle anticlockwise', emoji: '🔄', hint: 'Draw a circle in the air, anticlockwise' },
  wave: { name: 'Wave', emoji: '👋', hint: 'Wave side to side a few times' },
  shake: { name: 'Shake', emoji: '🫨', hint: 'Shake your hand up and down a few times' },
  'twist-cw': { name: 'Twist clockwise', emoji: '🔩', hint: 'Turn your hand like a doorknob, clockwise' },
  'twist-ccw': { name: 'Twist anticlockwise', emoji: '🗝️', hint: 'Turn your hand like a doorknob, anticlockwise' },
  tap: { name: 'Pinch tap', emoji: '👆', hint: 'Quickly pinch thumb and index, then release' },
  'double-tap': { name: 'Double pinch tap', emoji: '✌️', hint: 'Two quick pinch taps' },
  throw: { name: 'Throw', emoji: '🤾', hint: 'Make a fist, then fling it open while moving fast' },
  hold: { name: 'Hold a pose', emoji: '⏳', hint: 'Keep any pose still for a moment' },
  clap: { name: 'Clap', emoji: '👏', hint: 'Clap both open hands together', hands: 2 },
  'zoom-in': { name: 'Spread (zoom in)', emoji: '↔️', hint: 'Pinch with both hands, then pull them apart', hands: 2 },
  'zoom-out': { name: 'Squeeze (zoom out)', emoji: '🤲', hint: 'Pinch with both hands apart, then bring them together', hands: 2 },
  'steer-left': { name: 'Steer left', emoji: '🛞', hint: 'Both fists on a wheel, turn it left', hands: 2 },
  'steer-right': { name: 'Steer right', emoji: '🏎️', hint: 'Both fists on a wheel, turn it right', hands: 2 },
};
