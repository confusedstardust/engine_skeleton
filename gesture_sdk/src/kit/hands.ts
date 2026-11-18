/**
 * The one-call setup: camera + MediaPipe + gesture engine, running every animation frame.
 *
 *   const hands = createHands({ onFrame: (frame) => draw(frame) });
 *   hands.engine.on('fist', (e) => e.phase === 'start' ? grab(e.hand) : release(e.hand));
 *   startButton.onclick = () => hands.startCamera();   // browsers want a click before the camera
 *
 * Without a camera (tests, demos, mouse fallbacks) feed synthetic hands instead:
 *
 *   hands.inject([syntheticHand(0.5, 0.5, SYNTHETIC_POSES.point)]);   // held until inject(null)
 *   hands.feed(clip);                                                  // or a scripted clip, instantly
 */
import { GestureEngine, type EngineConfigInput } from './engine';
import { fromMediaPipe } from './mediapipe';
import { HandTracker, type TrackerOptions } from './tracker';
import type { GestureFrame, HandInput } from './types';

export interface HandsOptions extends TrackerOptions {
  /** Video element for the camera (a hidden one is created if omitted). Show it mirrored: `transform: scaleX(-1)`. */
  video?: HTMLVideoElement;
  /** Engine to drive (default: a new GestureEngine with `config`). */
  engine?: GestureEngine;
  /** Engine thresholds, e.g. JSON exported from the Gesture Lab. */
  config?: EngineConfigInput;
  /** Called with every new gesture frame (camera frames, injected hands and fed clips). */
  onFrame?: (frame: GestureFrame) => void;
}

export interface Hands {
  engine: GestureEngine;
  tracker: HandTracker;
  video: HTMLVideoElement;
  /** The latest frame (same as engine.frame; current inside event listeners too). */
  readonly frame: GestureFrame;
  /** Where frames currently come from. */
  readonly source: 'none' | 'camera' | 'synthetic';
  /** Opens the camera and loads the model. Call from a click handler. Rejects if the camera is unavailable or denied. */
  startCamera(): Promise<void>;
  /** Use these hands every frame instead of the camera; null switches back. */
  inject(hands: HandInput[] | null): void;
  /** Runs a scripted clip through the engine immediately, one entry per frame, `dtMs` apart. Returns every frame. */
  feed(clip: HandInput[][], dtMs?: number): GestureFrame[];
  /** Stops the loop and the camera. */
  stop(): void;
}

export function createHands(opts: HandsOptions = {}): Hands {
  const video = opts.video ?? Object.assign(document.createElement('video'), { muted: true, playsInline: true });
  const engine = opts.engine ?? new GestureEngine(opts.config);
  const tracker = new HandTracker(video, opts);
  let injected: HandInput[] | null = null;
  let camera = false;
  let offset = 0; // virtual time added by feed(), keeps engine time monotonic
  let lastT = -Infinity;
  let raf = 0;

  const step = (hands: HandInput[], t: number) => {
    t = Math.max(t + offset, lastT + 0.5);
    lastT = t;
    const frame = engine.update(hands, t);
    opts.onFrame?.(frame);
    return frame;
  };

  const loop = (now: number) => {
    raf = requestAnimationFrame(loop);
    if (injected) { step(injected, now); return; }
    if (!camera) return;
    const det = tracker.detect(now);
    if (det) step(fromMediaPipe(det.hands, det.aspect), det.frameTime);
  };
  raf = requestAnimationFrame(loop);

  return {
    engine, tracker, video,
    get frame() { return engine.frame; },
    get source() { return injected ? 'synthetic' : camera ? 'camera' : 'none'; },
    async startCamera() { await tracker.start(); camera = true; },
    inject(h) { injected = h; },
    feed(clip, dtMs = 1000 / 30) {
      return clip.map((hands) => { offset += dtMs; return step(hands, performance.now()); });
    },
    stop() { cancelAnimationFrame(raf); tracker.stop(); camera = false; },
  };
}

/** Part of the camera image that maps onto the whole screen, so users don't have to reach the frame edges. */
export interface Region { x0: number; x1: number; y0: number; y1: number }
export const DEFAULT_REGION: Region = { x0: 0.12, x1: 0.88, y0: 0.08, y1: 0.78 };

/** Camera-space point (0..1, mirrored, as in HandResult.features.center) → screen 0..1, clamped. */
export function toScreen(p: { x: number; y: number }, r: Region = DEFAULT_REGION): { x: number; y: number } {
  const c = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
  return { x: c((p.x - r.x0) / (r.x1 - r.x0)), y: c((p.y - r.y0) / (r.y1 - r.y0)) };
}

/** Screen 0..1 → camera space (inverse of toScreen, unclamped). Handy for aiming synthetic hands. */
export function fromScreen(p: { x: number; y: number }, r: Region = DEFAULT_REGION): { x: number; y: number } {
  return { x: r.x0 + p.x * (r.x1 - r.x0), y: r.y0 + p.y * (r.y1 - r.y0) };
}
