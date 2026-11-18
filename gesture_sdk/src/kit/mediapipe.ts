import type { RawHand } from './tracker';
import type { HandInput } from './types';

/**
 * Raw MediaPipe detections (un-mirrored camera image, MediaPipe's handedness label) → engine input
 * (mirrored selfie space, the user's real hand). MediaPipe labels handedness as if the image were
 * mirrored, so with a raw camera frame its label is the opposite of the user's hand.
 */
export function fromMediaPipe(hands: RawHand[], aspect: number, opts: { mirror?: boolean; flipLabel?: boolean } = {}): HandInput[] {
  const mirror = opts.mirror ?? true;
  const flip = opts.flipLabel ?? true;
  return hands.map((h) => ({
    landmarks: h.landmarks.map((p) => ({ x: mirror ? 1 - p.x : p.x, y: p.y, z: p.z })),
    world: h.world?.map((p) => ({ x: mirror ? -p.x : p.x, y: p.y, z: p.z })),
    handedness: flip ? (h.label === 'Left' ? 'Right' : 'Left') : h.label,
    aspect,
  }));
}
