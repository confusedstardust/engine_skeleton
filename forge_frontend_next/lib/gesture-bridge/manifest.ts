/** Versioned platform gesture semantics. Thresholds live here, not in LLM prompts. */
export const GESTURE_MANIFEST = {
  version:1,
  pinchEnter:0.72, pinchExit:0.36,
  rotateDeltaLimit:0.1,
  swipeMinMs:120, swipeMaxMs:650, swipeMinX:0.18, swipeMaxY:0.09, swipeCooldownMs:650,
  openHoldMs:900, pointerMaxHz:30,
  dwellMs:700, dwellRadius:0.045,
  region:{x0:0.12,x1:0.88,y0:0.08,y1:0.78},
} as const;
export const AVAILABLE_GESTURES = ["pinch-drag","fist-rotate","index-pointer","index-swipe","open-palm-hold"] as const;
