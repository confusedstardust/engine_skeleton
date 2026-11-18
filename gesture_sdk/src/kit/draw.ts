/**
 * Canvas helpers for showing hands. Landmarks are in 0..1 space, so pass the canvas size and,
 * optionally, a mapping (e.g. `toScreen`) to place them.
 */
import type { Vec3 } from './types';

/** Bones of the 21-point hand (pairs of landmark indices). */
export const HAND_CONNECTIONS: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17],
];

export interface DrawHandOpts {
  color?: string;
  lineWidth?: number;
  jointRadius?: number;
  /** Maps a 0..1 landmark to 0..1 canvas space (default: identity). */
  map?: (p: { x: number; y: number }) => { x: number; y: number };
}

/** Draws one hand skeleton onto a 2D canvas of size w × h (in canvas pixels). */
export function drawHand(ctx: CanvasRenderingContext2D, landmarks: Vec3[], w: number, h: number, o: DrawHandOpts = {}): void {
  if (landmarks.length < 21) return;
  const map = o.map ?? ((p) => p);
  const pts = landmarks.map((p) => { const q = map(p); return { x: q.x * w, y: q.y * h }; });
  ctx.save();
  ctx.strokeStyle = ctx.fillStyle = o.color ?? '#7cf';
  ctx.lineWidth = o.lineWidth ?? 4;
  ctx.lineCap = 'round';
  ctx.beginPath();
  for (const [a, b] of HAND_CONNECTIONS) { ctx.moveTo(pts[a].x, pts[a].y); ctx.lineTo(pts[b].x, pts[b].y); }
  ctx.stroke();
  const r = o.jointRadius ?? 4;
  for (const p of pts) { ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill(); }
  ctx.restore();
}
