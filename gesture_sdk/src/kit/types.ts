/**
 * GESTURE ENGINE — shared types.
 *
 * Coordinate conventions (everything the engine consumes and produces):
 *  - screen space: x → right, y → down, 0..1 of the *mirrored* (selfie) camera image, so moving your
 *    hand to your right moves it right on screen; z is MediaPipe's relative depth (smaller = closer).
 *  - world space (optional, more accurate): MediaPipe world landmarks in metres, mirrored the same way.
 *  - handedness is the user's real hand.
 */

export interface Vec3 { x: number; y: number; z: number }

/** One hand as fed to the engine. */
export interface HandInput {
  /** 21 MediaPipe landmarks in screen space. */
  landmarks: Vec3[];
  /** 21 world landmarks (metres), mirrored like `landmarks`. Strongly recommended. */
  world?: Vec3[];
  handedness: 'Left' | 'Right';
  /** Camera image width / height (screen landmarks are non-isotropic without it). */
  aspect?: number;
  /** Stable id if the caller tracks hands itself; otherwise the engine matches by position. */
  id?: number;
}

/** Everything measured about one hand in one frame. All 0..1 unless noted. */
export interface HandFeatures {
  /** Bend per finger (thumb, index, middle, ring, pinky): 0 straight … 1 fully curled. */
  curl: [number, number, number, number, number];
  /** Thumb tip away from the palm (0 tucked … 1 sticking out). */
  thumbOut: number;
  /** Thumb tip ↔ fingertip distance / palm length, for index, middle, ring, pinky. */
  tipGap: [number, number, number, number];
  /** Angle (radians) between adjacent fingers: index–middle, middle–ring, ring–pinky. */
  spread: [number, number, number];
  /** +1 palm facing the camera, −1 back of the hand facing it, 0 edge-on. */
  facing: number;
  /** Hand tilt in the image plane, radians (0 = fingers up, + = leaning right). */
  roll: number;
  /** Unit direction (screen) the index finger points. */
  pointDir: { x: number; y: number };
  /** Unit direction (screen) the thumb points. */
  thumbDir: { x: number; y: number };
  /** Palm centre in screen space. */
  center: { x: number; y: number };
  /** Wrist → middle knuckle length in screen heights (bigger = closer to the camera). */
  size: number;
  /** Mean extension of the four fingers (1 = fully open). */
  openness: number;
}

/** Per-finger requirement in a pose definition. */
export type FingerRule = 'ext' | 'curl' | 'half' | 'notcurl' | 'notext' | 'any';

/** A static hand shape, defined as data so games can add their own. */
export interface PoseDef {
  id: string;
  name: string;
  emoji: string;
  /** How to make it (shown in the Gesture Lab). */
  hint: string;
  /** thumb, index, middle, ring, pinky. */
  fingers: [FingerRule, FingerRule, FingerRule, FingerRule, FingerRule];
  /** Extra soft constraints, each 0..1, multiplied into the score. */
  extra?: (f: HandFeatures) => number;
  /** Experimental poses are hidden from games by default. */
  experimental?: boolean;
}

export interface HandResult {
  /** Engine-assigned stable id (0, 1, …) for the life of the hand. */
  id: number;
  handedness: 'Left' | 'Right';
  features: HandFeatures;
  /** Stable (debounced) pose id, or null. */
  pose: string | null;
  /** Its current score. */
  confidence: number;
  /** Raw score of every pose this frame. */
  scores: Record<string, number>;
  /** Milliseconds the current pose has been held. */
  heldMs: number;
  /** Smoothed palm velocity, screen units / s. */
  velocity: { x: number; y: number };
  /** Pinch strength 0..1 (thumb–index). */
  pinch: number;
  landmarks: Vec3[];
}

export type GestureKind = 'pose' | 'motion' | 'two-hand';

export interface GestureEvent {
  kind: GestureKind;
  /** e.g. 'fist', 'swipe-left', 'clap'. */
  name: string;
  /** Pose events: start / end. Others: undefined (instantaneous). */
  phase?: 'start' | 'end';
  /** Hand id (undefined for two-hand gestures). */
  hand?: number;
  t: number;
  data?: Record<string, number | string>;
}

export interface TwoHandState {
  present: boolean;
  /** Distance between palm centres (screen). */
  distance: number;
  /** Angle of the line from the left hand to the right hand, radians. */
  angle: number;
  /** distance / distance when the current two-hand grip began (1 when none). */
  zoom: number;
}

export interface GestureFrame {
  t: number;
  hands: HandResult[];
  twoHand: TwoHandState;
  events: GestureEvent[];
}
