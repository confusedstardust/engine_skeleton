import type { HandFeatures, HandInput, Vec3 } from './types';

/** MediaPipe landmark indices. */
export const L = {
  WRIST: 0, THUMB_CMC: 1, THUMB_MCP: 2, THUMB_IP: 3, THUMB_TIP: 4,
  INDEX_MCP: 5, INDEX_PIP: 6, INDEX_DIP: 7, INDEX_TIP: 8,
  MIDDLE_MCP: 9, MIDDLE_PIP: 10, MIDDLE_DIP: 11, MIDDLE_TIP: 12,
  RING_MCP: 13, RING_PIP: 14, RING_DIP: 15, RING_TIP: 16,
  PINKY_MCP: 17, PINKY_PIP: 18, PINKY_DIP: 19, PINKY_TIP: 20,
} as const;

/** Joint chains per finger (thumb … pinky), each starting at the wrist. */
const CHAINS = [
  [0, 1, 2, 3, 4],
  [0, 5, 6, 7, 8],
  [0, 9, 10, 11, 12],
  [0, 13, 14, 15, 16],
  [0, 17, 18, 19, 20],
] as const;

/** Bend (radians) that counts as fully curled / fully straight. Tuned on MediaPipe world landmarks. */
const FINGER_BEND = { straight: 0.45, curled: 3.1 };
const THUMB_BEND = { straight: 0.35, curled: 1.5 };

export const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const smooth = (e0: number, e1: number, x: number) => {
  const t = clamp01((x - e0) / (e1 - e0));
  return t * t * (3 - 2 * t);
};

const sub = (a: Vec3, b: Vec3): Vec3 => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
const dot = (a: Vec3, b: Vec3) => a.x * b.x + a.y * b.y + a.z * b.z;
const len = (a: Vec3) => Math.sqrt(dot(a, a));
const cross = (a: Vec3, b: Vec3): Vec3 => ({ x: a.y * b.z - a.z * b.y, y: a.z * b.x - a.x * b.z, z: a.x * b.y - a.y * b.x });
const dist = (a: Vec3, b: Vec3) => len(sub(a, b));
/** Bend at joint b: 0 when a-b-c is a straight line, π when folded back. */
function bend(a: Vec3, b: Vec3, c: Vec3) {
  const u = sub(b, a), v = sub(c, b);
  const lu = len(u), lv = len(v);
  if (lu < 1e-9 || lv < 1e-9) return 0;
  return Math.acos(Math.max(-1, Math.min(1, dot(u, v) / (lu * lv))));
}
const unit2 = (x: number, y: number) => { const l = Math.hypot(x, y) || 1; return { x: x / l, y: y / l }; };
const angle2 = (a: { x: number; y: number }, b: { x: number; y: number }) =>
  Math.acos(Math.max(-1, Math.min(1, a.x * b.x + a.y * b.y)));

/**
 * 3D points to measure shapes with: world landmarks when present (true metres, rotation-proof),
 * else screen landmarks made isotropic.
 */
function shapePoints(h: HandInput): Vec3[] {
  if (h.world && h.world.length === 21) return h.world;
  const a = h.aspect ?? 16 / 9;
  return h.landmarks.map((p) => ({ x: p.x * a, y: p.y, z: p.z * a * 0.6 }));
}

export function computeFeatures(h: HandInput): HandFeatures {
  const P = shapePoints(h);
  const S = h.landmarks;
  const aspect = h.aspect ?? 16 / 9;

  const palmLen = Math.max(dist(P[0], P[9]), 1e-6);
  const curl = [0, 0, 0, 0, 0] as HandFeatures['curl'];
  for (let f = 0; f < 5; f++) {
    const c = CHAINS[f];
    if (f === 0) {
      const b = bend(P[c[1]], P[c[2]], P[c[3]]) + bend(P[c[2]], P[c[3]], P[c[4]]);
      curl[0] = clamp01((b - THUMB_BEND.straight) / (THUMB_BEND.curled - THUMB_BEND.straight));
    } else {
      // knuckle bend counts half: a flat hand bent at the knuckles is still "open"
      const b = 0.5 * bend(P[c[0]], P[c[1]], P[c[2]]) + bend(P[c[1]], P[c[2]], P[c[3]]) + bend(P[c[2]], P[c[3]], P[c[4]]);
      curl[f] = clamp01((b - FINGER_BEND.straight) / (FINGER_BEND.curled - FINGER_BEND.straight));
    }
  }

  // thumb sticking out: tip far from the index knuckle and the middle knuckle
  const tOut = Math.min(dist(P[4], P[5]), dist(P[4], P[9]) * 1.15) / palmLen;
  const thumbOut = smooth(0.32, 0.62, tOut) * (1 - 0.5 * smooth(0.6, 1, curl[0]));

  const tipGap = [8, 12, 16, 20].map((t) => dist(P[4], P[t]) / palmLen) as HandFeatures['tipGap'];

  // finger directions in the image plane (for spread / pointing), from knuckle to tip
  const dir = (m: number, t: number) => unit2((S[t].x - S[m].x) * aspect, S[t].y - S[m].y);
  const dI = dir(5, 8), dM = dir(9, 12), dR = dir(13, 16), dP = dir(17, 20);
  const spread: HandFeatures['spread'] = [angle2(dI, dM), angle2(dM, dR), angle2(dR, dP)];

  // palm normal (shape space); its sign depends on handedness because a left hand is a mirror image
  const n = cross(sub(P[5], P[0]), sub(P[17], P[0]));
  const nl = len(n) || 1;
  // world landmarks: z grows away from the camera; screen landmarks too (MediaPipe z)
  const facing = (h.handedness === 'Right' ? 1 : -1) * (n.z / nl);

  const up = unit2((S[9].x - S[0].x) * aspect, S[9].y - S[0].y);
  const roll = Math.atan2(up.x, -up.y);
  const pointDir = dI;
  const thumbDir = unit2((S[4].x - S[2].x) * aspect, S[4].y - S[2].y);
  const center = {
    x: (S[0].x + S[5].x + S[9].x + S[13].x + S[17].x) / 5,
    y: (S[0].y + S[5].y + S[9].y + S[13].y + S[17].y) / 5,
  };
  const size = Math.hypot((S[9].x - S[0].x) * aspect, S[9].y - S[0].y);
  const openness = 1 - (curl[1] + curl[2] + curl[3] + curl[4]) / 4;

  return { curl, thumbOut, tipGap, spread, facing, roll, pointDir, thumbDir, center, size, openness };
}
