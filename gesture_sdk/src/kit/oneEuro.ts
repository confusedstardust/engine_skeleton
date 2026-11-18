/**
 * One Euro filter (Casiez, Roussel & Vogel, CHI 2012).
 *
 * An adaptive low-pass filter: at low speed the cutoff is `minCutoff` (kills
 * jitter while the hand hovers), and it rises linearly with the (filtered)
 * speed `cutoff = minCutoff + beta * |dx/dt|`, so fast motions get little lag.
 *
 * Units: `minCutoff` / `dCutoff` are in Hz; `beta` is in 1 / (value units),
 * i.e. with screen-normalised values (0..1) a beta of 5 means a 1 screen/s
 * motion raises the cutoff by 5 Hz.
 *
 * Time is passed explicitly (seconds) so the filter is deterministic and
 * robust to irregular frame times.
 */

export interface OneEuroParams {
  /** Cutoff (Hz) at zero speed. Lower = less jitter, more lag at rest. */
  minCutoff: number;
  /** Speed coefficient. Higher = less lag during fast motion. */
  beta: number;
  /** Cutoff (Hz) for the derivative estimate. */
  dCutoff: number;
}

/**
 * Tuned for the hand cursor in screen units (0..1) at 25–60 Hz tracking.
 * MediaPipe jitter at rest is ~0.003–0.006 screen units; at 30 Hz
 * minCutoff 1.1 Hz gives alpha ≈ 0.19 which removes it, while a 1 screen/s
 * swipe pushes the cutoff to ~6.6 Hz (≈ 25 ms lag).
 */
export const CURSOR_FILTER: OneEuroParams = { minCutoff: 1.1, beta: 5.5, dCutoff: 1.2 };

/** Lighter filtering for the landmark *shape* (purely visual). */
export const SHAPE_FILTER: OneEuroParams = { minCutoff: 2.2, beta: 2.5, dCutoff: 1.2 };

function smoothingAlpha(cutoffHz: number, dt: number): number {
  const tau = 1 / (2 * Math.PI * cutoffHz);
  return 1 / (1 + tau / dt);
}

/** Largest dt (s) the filter will integrate over; protects against tab stalls. */
const MAX_DT = 0.1;
/** Smallest dt (s); protects against duplicate timestamps. */
const MIN_DT = 1 / 1000;

export class OneEuroFilter {
  private x = 0;
  private dx = 0;
  private lastT = -1;
  private initialised = false;

  constructor(public params: OneEuroParams = CURSOR_FILTER) {}

  /** Filter value `v` sampled at time `t` (seconds). */
  filter(v: number, t: number): number {
    if (!this.initialised) {
      this.x = v; this.dx = 0; this.lastT = t; this.initialised = true;
      return v;
    }
    let dt = t - this.lastT;
    this.lastT = t;
    if (!(dt > MIN_DT)) dt = MIN_DT;
    if (dt > MAX_DT) dt = MAX_DT;

    const { minCutoff, beta, dCutoff } = this.params;
    const rawDx = (v - this.x) / dt;
    this.dx += smoothingAlpha(dCutoff, dt) * (rawDx - this.dx);
    const cutoff = minCutoff + beta * Math.abs(this.dx);
    this.x += smoothingAlpha(cutoff, dt) * (v - this.x);
    return this.x;
  }

  /** Current filtered value (last output). */
  get value(): number { return this.x; }
  /** Current filtered derivative (value units / s). */
  get derivative(): number { return this.dx; }
  get ready(): boolean { return this.initialised; }

  /** Forget history; the next sample passes through unfiltered. */
  reset(): void { this.initialised = false; this.dx = 0; }

  /** Jump to a value without history (e.g. hand re-acquired). */
  snap(v: number, t: number): void {
    this.x = v; this.dx = 0; this.lastT = t; this.initialised = true;
  }
}

/**
 * 2D One Euro filter. The speed term uses the *vector* speed so both axes
 * open up together on diagonal motion (two independent scalar filters would
 * lag more on the slower axis and bend straight swipes).
 */
export class OneEuroFilter2D {
  private x = 0;
  private y = 0;
  private dx = 0;
  private dy = 0;
  private lastT = -1;
  private initialised = false;

  constructor(public params: OneEuroParams = CURSOR_FILTER) {}

  filter(vx: number, vy: number, t: number): { x: number; y: number } {
    if (!this.initialised) {
      this.snap(vx, vy, t);
      return { x: vx, y: vy };
    }
    let dt = t - this.lastT;
    this.lastT = t;
    if (!(dt > MIN_DT)) dt = MIN_DT;
    if (dt > MAX_DT) dt = MAX_DT;

    const { minCutoff, beta, dCutoff } = this.params;
    const ad = smoothingAlpha(dCutoff, dt);
    this.dx += ad * ((vx - this.x) / dt - this.dx);
    this.dy += ad * ((vy - this.y) / dt - this.dy);
    const speed = Math.hypot(this.dx, this.dy);
    const a = smoothingAlpha(minCutoff + beta * speed, dt);
    this.x += a * (vx - this.x);
    this.y += a * (vy - this.y);
    return { x: this.x, y: this.y };
  }

  get value(): { x: number; y: number } { return { x: this.x, y: this.y }; }
  get ready(): boolean { return this.initialised; }

  reset(): void { this.initialised = false; this.dx = 0; this.dy = 0; }

  snap(x: number, y: number, t: number): void {
    this.x = x; this.y = y; this.dx = 0; this.dy = 0; this.lastT = t; this.initialised = true;
  }
}
