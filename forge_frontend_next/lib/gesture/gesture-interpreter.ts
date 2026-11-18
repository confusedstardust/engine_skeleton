import type { Landmark, HandFeatures } from "./gesture-types";

const distance = (a: Landmark, b: Landmark) => Math.hypot(a.x-b.x, a.y-b.y);
const clamp = (v: number) => Math.max(0, Math.min(1, v));
const extended = (lm: Landmark[], mcp: number, pip: number, tip: number) => {
  // Compare with knuckle-to-tip distance, not absolute image orientation.
  const reach = distance(lm[tip], lm[mcp]);
  const bent = distance(lm[pip], lm[mcp]);
  return reach > bent * 1.5;
};
const curled = (lm: Landmark[], mcp: number, pip: number, tip: number) => {
  const reach = distance(lm[tip], lm[mcp]);
  const bent = distance(lm[pip], lm[mcp]);
  return reach < bent * 1.30;
};

/** Camera coordinates are mirrored here, never in generated works. */
export function interpretHand(lm: Landmark[] | undefined): HandFeatures | null {
  if (!lm || lm.length !== 21 || lm.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y))) return null;
  const width = Math.max(0.001, distance(lm[5], lm[17]));
  if (width < 0.005) return null;
  const pinchRatio = distance(lm[4], lm[8]) / width;
  const fist = [[5,6,8],[9,10,12],[13,14,16],[17,18,20]].every(([a,b,c]) => curled(lm,a,b,c));
  const index = extended(lm,5,6,8);
  const othersCurled = [[9,10,12],[13,14,16],[17,18,20]].every(([a,b,c]) => curled(lm,a,b,c));
  const fingersExtended = [[5,6,8],[9,10,12],[13,14,16],[17,18,20]].every(([a,b,c]) => extended(lm,a,b,c));
  const thumbOpen = distance(lm[4], lm[17]) > width * 0.85;
  const cx = (lm[0].x + lm[5].x + lm[9].x + lm[13].x + lm[17].x) / 5;
  const cy = (lm[0].y + lm[5].y + lm[9].y + lm[13].y + lm[17].y) / 5;
  return {
    x: clamp(1 - lm[8].x), y: clamp(lm[8].y),
    cx: clamp(1 - cx), cy: clamp(cy),
    pinchRatio, fist,
    pointer: index && othersCurled && pinchRatio > 0.5,
    palm: fingersExtended && thumbOpen
  };
}
