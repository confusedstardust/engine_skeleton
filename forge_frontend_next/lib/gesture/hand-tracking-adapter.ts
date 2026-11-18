import { withBasePath } from "../../app/base-path";
import type { Landmark } from "./gesture-types";
import type { HandLandmarker as HandLandmarkerType } from "@mediapipe/tasks-vision";

/** Trusted player only. Self-hosted model + WASM, fixed via npm lockfile/build copy. */
export class HandTrackingAdapter {
  private landmarker: HandLandmarkerType | null = null;
  private lastVideoTime = -1;
  async initialize() {
    const {FilesetResolver,HandLandmarker} = await import("@mediapipe/tasks-vision");
    const wasm = await FilesetResolver.forVisionTasks(withBasePath("/gesture/wasm"));
    const baseOptions = {modelAssetPath:withBasePath("/gesture/hand_landmarker.task")};
    try {
      this.landmarker = await HandLandmarker.createFromOptions(wasm,{
        baseOptions:{...baseOptions,delegate:"GPU"},runningMode:"VIDEO",numHands:1
      });
    } catch {
      this.landmarker = await HandLandmarker.createFromOptions(wasm,{
        baseOptions:{...baseOptions,delegate:"CPU"},runningMode:"VIDEO",numHands:1
      });
    }
  }
  detect(video: HTMLVideoElement, timestamp: number): Landmark[] | null | undefined {
    if (!this.landmarker || video.readyState < 2 || video.currentTime === this.lastVideoTime) return undefined;
    this.lastVideoTime = video.currentTime;
    const result = this.landmarker.detectForVideo(video,timestamp);
    const hand = result.landmarks[0];
    return hand ? hand.map(p => ({x:p.x,y:p.y,z:p.z})) : null;
  }
  dispose() { this.landmarker?.close(); this.landmarker = null; this.lastVideoTime = -1; }
}
