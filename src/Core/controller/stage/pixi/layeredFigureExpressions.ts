/** Shared facial presets. Values are calibrated by each PSD's feature bounds. */
export interface FacialPreset {
  title: string;
  eyes: [number, number];
  brows: [number, number];
  browAngles: [number, number];
  smile: number;
  mouthOpen: number;
  headTilt: number;
}

export const facialPresets: Record<string, FacialPreset> = {
  normal: { title: '自然', eyes: [1, 1], brows: [0, 0], browAngles: [0, 0], smile: 0, mouthOpen: 0, headTilt: 0 },
  happy: { title: '开心', eyes: [0.65, 0.65], brows: [-2, -2], browAngles: [0, 0], smile: 1, mouthOpen: 0, headTilt: 0.025 },
  joy: { title: '大笑', eyes: [0.04, 0.04], brows: [-3, -3], browAngles: [0, 0], smile: 1, mouthOpen: 0.7, headTilt: -0.018 },
  sad: { title: '难过', eyes: [0.65, 0.65], brows: [-1, -1], browAngles: [-0.22, 0.22], smile: -1, mouthOpen: 0, headTilt: -0.035 },
  angry: { title: '生气', eyes: [0.72, 0.72], brows: [4, 4], browAngles: [0.22, -0.22], smile: -0.7, mouthOpen: 0, headTilt: 0 },
  surprised: { title: '惊讶', eyes: [1.2, 1.2], brows: [-7, -7], browAngles: [0, 0], smile: 0, mouthOpen: 0.85, headTilt: -0.015 },
  curious: { title: '疑惑', eyes: [0.72, 1.05], brows: [1, -5], browAngles: [0.1, -0.1], smile: -0.2, mouthOpen: 0, headTilt: 0.06 },
  sleepy: { title: '困倦', eyes: [0.28, 0.28], brows: [1, 1], browAngles: [0, 0], smile: -0.2, mouthOpen: 0, headTilt: -0.04 },
  wink: { title: '眨眼示意', eyes: [0.04, 1], brows: [-2, -2], browAngles: [0, 0], smile: 0.8, mouthOpen: 0, headTilt: 0.035 },
};

export const expressionSequence = ['normal', 'happy', 'joy', 'sad', 'angry', 'surprised', 'curious', 'sleepy', 'wink'];

export function blinkOpenness(time: number): number {
  const phase = time % 4.3;
  if (phase < 3.9) return 1;
  if (phase < 4.02) return 1 - (phase - 3.9) / 0.12;
  if (phase < 4.08) return 0;
  return Math.min(1, (phase - 4.08) / 0.22);
}

export function facialState(time: number, expression: string, talking: boolean): FacialPreset {
  const index = Math.floor(time / 4) % expressionSequence.length;
  const target = facialPresets[expression === 'demo' ? expressionSequence[index] : expression] ?? facialPresets.normal;
  const from = expression === 'demo' ? facialPresets[expressionSequence[(index + expressionSequence.length - 1) % expressionSequence.length]] : facialPresets.normal;
  const mix = Math.min(1, (expression === 'demo' ? time % 4 : time) / 0.4);
  const smooth = mix * mix * (3 - 2 * mix);
  const lerp = (a: number, b: number) => a + (b - a) * smooth;
  const pair = (a: [number, number], b: [number, number]): [number, number] => [lerp(a[0], b[0]), lerp(a[1], b[1])];
  const eyes = pair(from.eyes, target.eyes);
  const blink = blinkOpenness(time);
  return { title: target.title, eyes: [eyes[0] * blink, eyes[1] * blink],
    brows: pair(from.brows, target.brows), browAngles: pair(from.browAngles, target.browAngles),
    smile: lerp(from.smile, target.smile), headTilt: lerp(from.headTilt, target.headTilt),
    mouthOpen: talking ? (0.15 + 0.65 * Math.abs(Math.sin(time * 9) * Math.sin(time * 3.1))) : lerp(from.mouthOpen, target.mouthOpen),
  };
}
