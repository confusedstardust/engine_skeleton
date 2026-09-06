/* eslint-disable max-lines-per-function */
import * as PIXI from 'pixi.js';
import { ISentence } from '@/Core/controller/scene/sceneInterface';
import { WebGAL } from '@/Core/WebGAL';
import { getNumberArgByKey, getStringArgByKey } from '@/Core/util/getSentenceArg';
import { registerPerform } from '@/Core/util/pixiPerformManager/pixiPerformManager';
import { SCREEN_CONSTANTS } from '@/Core/util/constants';

type LayerName = 'foreground' | 'background';

type ParticlePreset = {
  id: string;
  asset: string;
  count: number;
  speed: number;
  scale: number;
  angle: number;
  opacity: number;
  drift: number;
  gravity: number;
  rotation_speed: number;
  layer: LayerName;
  blend_mode: 'normal' | 'add' | 'screen';
};

type ParticleConfig = {
  sheet: { frame_width: number; frame_height: number; frame_count: number; columns: number };
  effects: Record<string, ParticlePreset>;
};

interface EffectSprite extends PIXI.Sprite {
  vx: number;
  vy: number;
  vr: number;
}

let invocation = 0;
let configPromise: Promise<ParticleConfig> | null = null;

function loadConfig(): Promise<ParticleConfig> {
  configPromise ??= fetch('./game/effects.json').then((response) => {
    if (!response.ok) throw new Error(`Particle config returned ${response.status}`);
    return response.json() as Promise<ParticleConfig>;
  });
  return configPromise;
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function sentenceNumber(sentence: ISentence, key: string, fallback: number, minimum: number, maximum: number): number {
  const value = getNumberArgByKey(sentence, key);
  return clamp(value ?? fallback, minimum, maximum);
}

function blendMode(name: ParticlePreset['blend_mode']): PIXI.BLEND_MODES {
  if (name === 'add') return PIXI.BLEND_MODES.ADD;
  if (name === 'screen') return PIXI.BLEND_MODES.SCREEN;
  return PIXI.BLEND_MODES.NORMAL;
}

function createLayer(sentence: ISentence, layer: LayerName) {
  const pixiStage = WebGAL.gameplay.pixiStage!;
  const root = new PIXI.Container();
  const effectId = getStringArgByKey(sentence, 'id') || '';
  const tickerKey = `particle-${effectId}-${layer}-${++invocation}`;
  const effectsContainer = layer === 'foreground'
    ? pixiStage.foregroundEffectsContainer
    : pixiStage.backgroundEffectsContainer;
  effectsContainer.addChild(root);

  void loadConfig().then((config) => {
    if (root.destroyed) return;
    const preset = config.effects[effectId];
    const selectedLayer = getStringArgByKey(sentence, 'layer') || preset?.layer;
    if (!preset || selectedLayer !== layer) return;
    const count = Math.round(sentenceNumber(sentence, 'count', preset.count, 1, 300));
    const speed = sentenceNumber(sentence, 'speed', preset.speed, 0.2, 40);
    const scale = sentenceNumber(sentence, 'scale', preset.scale, 0.05, 2);
    const angle = sentenceNumber(sentence, 'angle', preset.angle, -180, 180) * Math.PI / 180;
    const opacity = sentenceNumber(sentence, 'opacity', preset.opacity, 0.05, 1);
    const drift = sentenceNumber(sentence, 'drift', preset.drift, -8, 8);
    const gravity = sentenceNumber(sentence, 'gravity', preset.gravity, -3, 3);
    const rotationSpeed = sentenceNumber(sentence, 'rotation', preset.rotation_speed, -0.1, 0.1);
    const particleContainer = new PIXI.ParticleContainer(count, {
      scale: true,
      position: true,
      rotation: true,
      alpha: true,
      uvs: false,
    });
    root.addChild(particleContainer);

    const sheet = config.sheet;
    const baseTexture = PIXI.BaseTexture.from(`./game/${preset.asset}`);
    const setup = () => {
      if (root.destroyed || !baseTexture.valid) return;
      const textures = Array.from({ length: sheet.frame_count }, (_, index) => {
        const column = index % sheet.columns;
        const row = Math.floor(index / sheet.columns);
        return new PIXI.Texture(
          baseTexture,
          new PIXI.Rectangle(column * sheet.frame_width, row * sheet.frame_height, sheet.frame_width, sheet.frame_height),
        );
      });
      const sprites: EffectSprite[] = [];
      const width = SCREEN_CONSTANTS.width;
      const height = SCREEN_CONSTANTS.height;

      const reset = (sprite: EffectSprite, initial: boolean) => {
        const variedScale = scale * (0.65 + Math.random() * 0.7);
        sprite.scale.set(variedScale);
        sprite.anchor.set(0.5);
        sprite.rotation = angle - preset.angle * Math.PI / 180;
        sprite.alpha = opacity * (0.7 + Math.random() * 0.3);
        const selectedBlend = getStringArgByKey(sentence, 'blend_mode');
        sprite.blendMode = blendMode(selectedBlend === 'add' || selectedBlend === 'screen' ? selectedBlend : preset.blend_mode);
        sprite.x = initial ? Math.random() * width : (Math.cos(angle) >= 0 ? -sprite.width : width + sprite.width);
        sprite.y = Math.random() * height;
        const variedSpeed = speed * (0.75 + Math.random() * 0.5);
        sprite.vx = Math.cos(angle) * variedSpeed + drift;
        sprite.vy = Math.sin(angle) * variedSpeed;
        sprite.vr = rotationSpeed * (0.6 + Math.random() * 0.8);
      };

      for (let index = 0; index < count; index++) {
        const sprite = new PIXI.Sprite(textures[Math.floor(Math.random() * textures.length)]) as EffectSprite;
        reset(sprite, true);
        particleContainer.addChild(sprite);
        sprites.push(sprite);
      }
      pixiStage.registerAnimation({
        setStartState: () => {},
        setEndState: () => {},
        tickerFunc: (delta: number) => {
          for (const sprite of sprites) {
            sprite.vy += gravity * delta * 0.02;
            sprite.x += sprite.vx * delta;
            sprite.y += sprite.vy * delta;
            sprite.rotation += sprite.vr * delta;
            if (sprite.x < -sprite.width * 2 || sprite.x > width + sprite.width * 2 || sprite.y < -sprite.height * 2 || sprite.y > height + sprite.height * 2) {
              reset(sprite, false);
            }
          }
        },
      }, tickerKey);
    };
    if (baseTexture.valid) setup();
    else baseTexture.once('loaded', setup);
  }).catch((error) => console.error(`Unable to start particle effect "${effectId}"`, error));

  return { container: root, tickerKey };
}

registerPerform('particle', {
  fg: (sentence) => createLayer(sentence, 'foreground'),
  bg: (sentence) => createLayer(sentence, 'background'),
});
