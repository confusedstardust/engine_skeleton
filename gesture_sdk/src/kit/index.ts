/**
 * hand-gesture-kit: webcam hand gestures for the browser. See README.md and AGENTS.md.
 */
export { createHands, toScreen, fromScreen, DEFAULT_REGION, type Hands, type HandsOptions, type Region } from './hands';
export { HandTracker, CAMERA_CONSTRAINTS, type TrackerOptions, type RawHand, type RawLandmark, type DetectionFrame } from './tracker';
export { GestureEngine, DEFAULT_CONFIG, DEFAULT_POSE, type EngineConfig, type EngineConfigInput, type PoseConfig } from './engine';
export { computeFeatures, smooth, clamp01, L as LANDMARK } from './features';
export { POSES, scorePose, ruleScore } from './poses';
export { MOTIONS, MOTION_INFO, DEFAULT_MOTION, type MotionConfig, type MotionDetector, type MotionContext, type MotionHit, type Sample } from './motions';
export { fromMediaPipe } from './mediapipe';
export { OneEuroFilter, OneEuroFilter2D, type OneEuroParams } from './oneEuro';
export { drawHand, HAND_CONNECTIONS, type DrawHandOpts } from './draw';
export { syntheticHand, screenHandLandmarks, handShape, SYNTHETIC_POSES, type HandPose, type SyntheticHandOpts } from './synthetic';
export type * from './types';
