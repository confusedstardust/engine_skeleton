/*
 * NarrativeOS approved in-frame control adapter, SDK v1.
 * Only normalized coordinates and explicit game actions leave this module.
 * The owner HTML controls the camera lifecycle. No network or telemetry.
 */
import { createHands, toScreen, LANDMARK } from './hand-gesture-kit.esm.js';

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const pointOf = (hand) => {
  const tip = hand.landmarks?.[LANDMARK.INDEX_TIP] || hand.features.center;
  return toScreen(tip);
};
export class GestureControls {
  constructor({ video, onAction, onPointer = () => {}, onStatus = () => {} }) {
    this.video = video;
    this.onAction = onAction;
    this.onPointer = onPointer;
    this.onStatus = onStatus;
    this.hands = null;
    this.off = null;
    this.running = false;
    this.starting = false;
    this.pressed = false;
    this.last = null;
    this.dwell = null;
    this.dwellFired = false;
    this.openFired = false;
  }
  resetInput() {
    if (this.pressed) this.onAction('pinch-end', this.last || { x: .5, y: .5 });
    this.pressed = false;
    this.last = null;
    this.dwell = null;
    this.dwellFired = false;
    this.openFired = false;
    this.onPointer(null);
  }
  update(frame) {
    const hand = frame.hands[0];
    if (!hand) { this.resetInput(); return; }
    const pos = pointOf(hand);
    this.onPointer({ ...pos, pose: hand.pose });
    const pinching = this.pressed ? hand.pinch > .36 : hand.pinch >= .72;
    if (pinching && !this.pressed) this.onAction('pinch-start', pos);
    if (pinching) this.onAction('pinch-move', pos);
    if (!pinching && this.pressed) this.onAction('pinch-end', pos);
    this.pressed = pinching;
    if (hand.pose === 'fist') {
      if (this.last?.pose === 'fist') {
        const cx = toScreen(hand.features.center).x;
        const delta = clamp(cx - this.last.centerX, -.10, .10);
        if (Math.abs(delta) > .002) this.onAction('fist-rotate', { delta });
      }
    }
    const centerX = toScreen(hand.features.center).x;
    this.last = { ...pos, centerX, pose: hand.pose };
    if (hand.pose === 'open' && hand.heldMs >= 900 && !this.openFired) {
      this.openFired = true;
      this.onAction('open-reset', pos);
    }
    if (hand.pose !== 'open') this.openFired = false;
    if (hand.pose !== 'point') { this.dwell = null; this.dwellFired = false; return; }
    const element = document.elementFromPoint(pos.x * innerWidth, pos.y * innerHeight)?.closest('[data-gesture-dwell]');
    const target = element instanceof HTMLElement ? element : null;
    if (!target) { this.dwell = null; this.dwellFired = false; return; }
    const stable = this.dwell?.target === target && Math.hypot(pos.x - this.dwell.x, pos.y - this.dwell.y) < .045;
    if (!stable) { this.dwell = { target, x: pos.x, y: pos.y, t: frame.t }; this.dwellFired = false; }
    else if (!this.dwellFired && frame.t - this.dwell.t >= 700) {
      this.dwellFired = true;
      this.onAction('index-dwell', { target, ...pos });
    }
  }
  async start() {
    if (this.running || this.starting) return;
    this.starting = true;
    try {
      this.hands = createHands({
        video: this.video, assetBase: '/gesture-sdk/v1/', numHands: 1,
        config: { pose: { experimental: false } },
        onFrame: frame => this.update(frame),
      });
      this.off = this.hands.engine.on('fist', event => {
        this.onStatus(event.phase === 'start' ? '握拳移动可旋转卡片' : '握拳结束');
      });
      this.hands.tracker.onEnded = () => { this.stop(); this.onStatus('摄像头已断开，请重新开启'); };
      await this.hands.startCamera();
      this.running = true;
      this.onStatus('摄像头已开启，视频只在本机分析');
    } catch (error) {
      this.stop();
      throw error;
    } finally {
      this.starting = false;
    }
  }
  stop() {
    this.resetInput();
    this.off?.(); this.off = null;
    this.hands?.stop(); this.hands = null;
    this.running = false;
    if (this.video) this.video.srcObject = null;
    this.onStatus('摄像头已关闭');
  }
}
