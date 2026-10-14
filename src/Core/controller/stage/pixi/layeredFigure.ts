import * as PIXI from 'pixi.js';
import { v4 as uuid } from 'uuid';
import type PixiStage from './PixiController';
import { WebGALPixiContainer } from './WebGALPixiContainer';
import { facialState } from './layeredFigureExpressions';

type LayerRole = 'head' | 'hair' | 'body' | 'arm' | 'fixed' | 'eyeWhite' | 'iris' | 'eyeLash' | 'eyebrow' | 'mouth';
type Bounds = [number, number, number, number];

interface LayerSpec {
  file: string;
  role: LayerRole;
}
interface LayeredFigure {
  version: number;
  width: number;
  height: number;
  headPivot: [number, number];
  bodyPivot: [number, number];
  layers: LayerSpec[];
  faceFeatures?: { eyes: { bounds: Bounds; browBounds: Bounds | null }[]; mouthBounds: Bounds | null };
}

/** Layered PSD animation. This format is independent of Live2D. */
export function addLayeredFigure(this: PixiStage, key: string, url: string, position: 'left' | 'center' | 'right') {
  this.removeStageObjectByKey(key);
  const container = new WebGALPixiContainer();
  const metadata = this.getFigureMetadataByKey(key);
  container.zIndex = metadata?.zIndex ?? 0;
  if (metadata?.blendMode) container.blendMode = metadata.blendMode;
  this.figureContainer.addChild(container);
  const id = uuid();
  const abort = new AbortController();
  let frame = 0;
  let cleanup = () => {};
  this.figureObjects.push({
    uuid: id, key, pixiContainer: container, sourceUrl: url, sourceType: 'layered', sourceExt: 'json',
    dispose: () => { abort.abort(); cancelAnimationFrame(frame); cleanup(); },
  });
  const alive = () => !!this.getStageObjByUuid(id);
  const absolute = new URL(url, document.baseURI);
  const mode = absolute.searchParams.get('motion') ?? 'idle';
  const expression = absolute.searchParams.get('expression') ?? 'normal';
  const talking = absolute.searchParams.get('talk') === 'true';
  void (async () => {
    const response = await fetch(absolute.href, { signal: abort.signal });
    if (!response.ok) throw new Error(`Layered figure HTTP ${response.status}`);
    const model: LayeredFigure = await response.json();
    if (model.version !== 1 || !Number.isFinite(model.width) || model.width <= 0 ||
        !Number.isFinite(model.height) || model.height <= 0 || !Array.isArray(model.layers) ||
        !model.layers.length || model.layers.length > 100 ||
        ![model.headPivot, model.bodyPivot].every(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite))) {
      throw new Error('Invalid layered figure manifest');
    }
    if (model.faceFeatures && (!Array.isArray(model.faceFeatures.eyes) || model.faceFeatures.eyes.length !== 2)) {
      throw new Error('Facial animation requires two calibrated eyes');
    }
    const textures = await Promise.all(model.layers.map(async layer => {
      if (!layer.file || !['head', 'hair', 'body', 'arm', 'fixed', 'eyeWhite', 'iris', 'eyeLash', 'eyebrow', 'mouth'].includes(layer.role)) {
        throw new Error('Invalid layered figure layer');
      }
      const texture = await PIXI.Texture.fromURL(new URL(layer.file, absolute).href);
      return { texture, role: layer.role };
    }));
    if (!alive()) return;
    const scale = Math.min(this.stageWidth / model.width, this.stageHeight / model.height);
    const rig = new PIXI.Container();
    cleanup = () => rig.destroy({ children: true });
    rig.scale.set(scale);
    rig.position.set(-model.width * scale / 2, this.stageHeight - model.height * scale);
    container.pivot.set(0, this.stageHeight / 2);
    container.setBaseY(this.stageHeight / 2);
    container.setBaseX(position === 'center' ? this.stageWidth / 2 :
      position === 'left' ? model.width * scale / 2 : this.stageWidth - model.width * scale / 2);
    container.addChild(rig);
    const facialRoles = ['eyeWhite', 'iris', 'eyeLash', 'eyebrow', 'mouth'];
    const featureSprites: { sprite: PIXI.Sprite; role: LayerRole; eye: number; center: [number, number] }[] = [];
    const closedEyes: { graphic: PIXI.Graphics; bounds: Bounds; eye: number }[] = [];
    let mouth: { plane: PIXI.SimplePlane; original: Float32Array; graphic: PIXI.Graphics; bounds: Bounds } | undefined;
    const crop = (texture: PIXI.Texture, bounds: Bounds) => {
      const [x, y, width, height] = bounds;
      if (![x, y, width, height].every(Number.isFinite) || x < 0 || y < 0 || width <= 0 || height <= 0 ||
          x + width > texture.width || y + height > texture.height) throw new Error('Invalid facial bounds');
      return new PIXI.Texture(texture.baseTexture, new PIXI.Rectangle(x, y, width, height));
    };
    const sprites = textures.map(({ texture, role }) => {
      if (model.faceFeatures && facialRoles.includes(role) && (role !== 'mouth' || model.faceFeatures.mouthBounds)) {
        const node = new PIXI.Container();
        if (role === 'mouth' && model.faceFeatures.mouthBounds) {
          const bounds = model.faceFeatures.mouthBounds;
          const plane = new PIXI.SimplePlane(crop(texture, bounds), 12, 4);
          plane.position.set(bounds[0], bounds[1]);
          const graphic = new PIXI.Graphics();
          node.addChild(plane, graphic);
          mouth = { plane, graphic, bounds, original: new Float32Array(plane.geometry.getBuffer('aVertexPosition').data) };
        } else if (role !== 'mouth') {
          model.faceFeatures.eyes.forEach((eye, index) => {
            const bounds = role === 'eyebrow' ? eye.browBounds : eye.bounds;
            if (!bounds) return;
            const sprite = new PIXI.Sprite(crop(texture, bounds));
            const center: [number, number] = [bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2];
            sprite.pivot.set(bounds[2] / 2, bounds[3] / 2);
            sprite.position.set(...center);
            node.addChild(sprite);
            featureSprites.push({ sprite, role, eye: index, center });
            if (role === 'eyeLash') {
              const graphic = new PIXI.Graphics();
              node.addChild(graphic);
              closedEyes.push({ graphic, bounds, eye: index });
            }
          });
        }
        return { sprite: node, role };
      }
      return { sprite: new PIXI.Sprite(texture), role };
    });
    const isHead = (role: LayerRole) => role === 'head' || role === 'hair' || facialRoles.includes(role);
    for (const { sprite, role } of sprites) {
      const pivot = isHead(role) ? model.headPivot : model.bodyPivot;
      sprite.pivot.set(...pivot);
      sprite.position.set(...pivot);
      rig.addChild(sprite);
    }
    const started = performance.now();
    const animate = (now: number) => {
      if (!alive()) return;
      const t = (now - started) / 1000;
      const breath = Math.sin(t * Math.PI / 2);
      const pulse = (1 - Math.cos(t * Math.PI)) / 2;
      const face = facialState(t, expression, talking);
      for (const { sprite, role } of sprites) {
        const head = isHead(role);
        const pivot = head ? model.headPivot : model.bodyPivot;
        sprite.position.set(pivot[0], pivot[1]);
        sprite.scale.set(1);
        sprite.rotation = 0;
        if (mode !== 'still' && role !== 'fixed') {
          // Move all connected parts together to keep the original seams aligned.
          sprite.y -= breath * 1.8;
          if (mode === 'nod' && head) { sprite.y += pulse * 3; sprite.scale.y = 1 - pulse * 0.009; }
          if (mode === 'tilt' && head) sprite.rotation = Math.sin(t * 1.5) * 0.015;
          if (mode === 'combo' && head) {
            sprite.rotation = face.headTilt + Math.sin(t * 1.1) * 0.009;
            sprite.y += Math.sin(t * 1.4) * 1.5;
          }
          if (role === 'hair') sprite.rotation += Math.sin(t * 1.7) * (mode === 'breeze' ? 0.018 : 0.002);
          if (mode === 'breeze' && role === 'body') sprite.rotation = Math.sin(t * 1.1) * 0.002;
        }
      }
      if (mode !== 'still') {
        for (const feature of featureSprites) {
          const { sprite, role, eye, center } = feature;
          sprite.position.set(...center);
          sprite.scale.set(1);
          sprite.rotation = 0;
          sprite.alpha = 1;
          if (role === 'eyebrow') {
            sprite.y += face.brows[eye];
            sprite.rotation = face.browAngles[eye];
          } else {
            const openness = face.eyes[eye];
            sprite.scale.y = Math.max(0.04, openness);
            sprite.alpha = openness < 0.1 ? 0 : 1;
            if (role === 'iris') sprite.x += Math.sin(t * 0.8) * 1.3;
          }
        }
        for (const { graphic, bounds, eye } of closedEyes) {
          graphic.clear();
          if (face.eyes[eye] < 0.1) {
            const [x, y, width, height] = bounds;
            const cy = y + height / 2;
            graphic.lineStyle(2.3, 0x694635, 0.95);
            graphic.moveTo(x + 5, cy);
            graphic.quadraticCurveTo(x + width / 2, cy + (face.smile > 0.3 ? -5 : 3), x + width - 5, cy - 1);
          }
        }
        if (mouth) {
          const { plane, original, graphic, bounds } = mouth;
          const buffer = plane.geometry.getBuffer('aVertexPosition');
          const vertices = buffer.data as Float32Array;
          for (let i = 0; i < vertices.length; i += 2) {
            const u = (original[i] / bounds[2] - 0.5) * 2;
            vertices[i + 1] = original[i + 1] - face.smile * 4 * (u * u - 0.25);
          }
          buffer.update();
          graphic.clear();
          plane.alpha = face.mouthOpen > 0.12 ? 0 : 1;
          if (face.mouthOpen > 0.12) {
            const cx = bounds[0] + bounds[2] / 2, cy = bounds[1] + bounds[3] / 2;
            const rx = bounds[2] * (face.smile > 0.3 ? 0.4 : 0.22);
            const ry = 1.5 + face.mouthOpen * 7;
            graphic.lineStyle(1.4, 0x9d6756, 0.9).beginFill(0x623b37).drawEllipse(cx, cy, rx, ry).endFill();
            graphic.lineStyle(0).beginFill(0xbf7b78, 0.85).drawEllipse(cx, cy + ry * 0.4, rx * 0.6, ry * 0.33).endFill();
          }
        }
      }
      this.requestRender();
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
  })().catch(error => {
    if (!abort.signal.aborted) console.error('Layered figure failed to load', url, error);
  });
}
