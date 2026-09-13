import type { InteractionConfig, Rect } from './types';

const id = /^[a-z][a-z0-9_]{0,63}$/;
const validRect = (rect: Rect, normalized = false) => rect.width > 0 && rect.height > 0 && (!normalized || rect.x >= 0 && rect.y >= 0 && rect.x + rect.width <= 1 && rect.y + rect.height <= 1);
export function validateInteractionConfig(value: unknown): asserts value is InteractionConfig {
  const config = value as InteractionConfig;
  if (!config || config.schemaVersion !== 1 || !id.test(config.id) || !['investigation', 'qte', 'movement'].includes(config.type) || !config.sceneFile || !config.payload) throw new Error('交互配置不符合 interaction-v1。');
  if (config.type === 'investigation') {
    if (config.resumePolicy !== 'resume' || config.payload.hotspots.length > 30 || !config.payload.hotspots.every((h) => id.test(h.id) && validRect(h.rect, true))) throw new Error('搜证热点配置无效。');
  } else if (config.type === 'qte') {
    if (config.resumePolicy !== 'restart' || config.payload.steps.length === 0 || config.payload.steps.length > 12 || !config.payload.steps.every((s) => s.windowMs >= 500 && s.windowMs <= 10000) || config.payload.timeScale < 1 || config.payload.timeScale > 3) throw new Error('QTE 配置无效。');
  } else if (config.resumePolicy !== 'resume' || !validRect(config.payload.bounds) || !validRect(config.payload.goal.rect) || config.payload.speed <= 0) throw new Error('移动配置无效。');
}
export async function loadInteractionConfig(configPath: string, signal: AbortSignal): Promise<InteractionConfig> {
  if (!/^interactions\/[a-zA-Z0-9_./-]+\.json$/.test(configPath) || configPath.includes('..')) throw new Error('交互配置必须位于 game/interactions/。');
  const response = await fetch(`./game/${configPath}`, { signal });
  if (!response.ok) throw new Error(`无法加载交互配置（${response.status}）。`);
  const text = await response.text();
  if (text.length > 128 * 1024) throw new Error('交互配置超过 128 KiB 限制。');
  const config = JSON.parse(text);
  validateInteractionConfig(config);
  return config;
}
