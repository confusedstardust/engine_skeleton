"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import * as Popover from "@radix-ui/react-popover";
import * as ScrollArea from "@radix-ui/react-scroll-area";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import { LaperInspectorShell } from "./laper-inspector-shell";
import { FormSelect, FormSlider } from "./ui/form-controls";

export type AssetReviewItem = {
  filename: string;
  subdir: string;
  kind: string;
  display_name?: string;
  size: string;
  prompt: string;
  available_scene: string;
  scene_display_name?: string;
  exists: boolean;
  url: string;
  avatar_exists: boolean;
  avatar_url: string | null;
};

export type TTSVoiceOption = {
  name: string;
  gender: string;
  description: string;
};

export type TTSVoiceReviewItem = {
  speaker: string;
  speaker_id: string;
  gender: string;
  voice: string;
  tone: string;
  scene: string;
  line_no: number;
  text: string;
  filename: string;
  status: string;
  error?: string | null;
  preview_exists: boolean;
  preview_url: string | null;
};

export type SceneMusicItem = {
  scene_file: string;
  label: string;
  kind: "scene" | "ending";
  system_asset: string | null;
  selected_asset: string | null;
  active_asset: string | null;
};

export type ParticleEffectPreset = {
  id: string;
  label: string;
  description: string;
  asset: string;
  preview_url: string;
  count: number;
  speed: number;
  scale: number;
  angle: number;
  opacity: number;
  drift: number;
  gravity: number;
  rotation_speed: number;
  layer: "foreground" | "background";
  blend_mode: "normal" | "add" | "screen";
  sheet?: { frame_width: number; frame_height: number; frame_count: number; columns: number };
};

export type SceneEffectAssignment = Omit<ParticleEffectPreset, "id" | "label" | "description" | "preview_url"> & {
  effect_id: string;
};

export type ParticleEffectReview = {
  effects: ParticleEffectPreset[];
  scenes: Array<{ scene_file: string; label: string; kind: "scene" | "ending"; assignment: SceneEffectAssignment | null }>;
};

export type StagedScenePresentation = {
  music: Record<string, string | null>;
  effects: Record<string, SceneEffectAssignment | null>;
};

type LaperAssetWorkbenchProps = {
  imageEnabled: boolean;
  assets: AssetReviewItem[];
  voiceEnabled: boolean;
  voices: TTSVoiceReviewItem[];
  availableVoices: TTSVoiceOption[];
  voiceGeneratingSpeaker: string | null;
  busy: boolean;
  readonly: boolean;
  published?: boolean;
  buildState?: string;
  hasDraftChanges?: boolean;
  activeAsset: AssetReviewItem | null;
  assetPrompt: string;
  setAssetPrompt: (value: string) => void;
  openAsset: (asset: AssetReviewItem) => void;
  closeAsset: () => void;
  regenerateAsset: (asset: AssetReviewItem, prompt: string) => Promise<void>;
  previewVoice: (speaker: string, voice: string) => Promise<void>;
  buildGame: (staged?: StagedScenePresentation) => Promise<void>;
  retryAction?: () => void;
  retryLabel?: string;
  displayName: (asset: AssetReviewItem) => string;
  sceneDisplayName: (asset: AssetReviewItem) => string;
  sceneMusic: SceneMusicItem[];
  musicAssets: string[];
  sceneMusicEnabled: boolean;
  previewSceneMusic: (asset: string) => Promise<Blob>;
  particleEffects: ParticleEffectReview;
};

type AssetSection = "figures" | "backgrounds" | "effects";

function assetPreviewClass(asset: AssetReviewItem) {
  const isFigure = asset.kind === "角色立绘";
  if (isFigure && asset.avatar_exists && asset.avatar_url) {
    return "laper-asset-preview poster-duo";
  }
  if (isFigure) {
    return "laper-asset-preview poster-solo";
  }
  return "laper-asset-preview poster-still";
}

type ContainedAssetImageProps = {
  src: string;
  alt: string;
  objectPosition?: string;
};

function ContainedAssetImage({ src, alt, objectPosition = "bottom center" }: ContainedAssetImageProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img className="asset-contained-img" src={src} alt={alt} loading="lazy" style={{ objectPosition }} />
  );
}

function AssetPreviewImage({ asset }: { asset: AssetReviewItem }) {
  const isFigure = asset.kind === "角色立绘";
  const showAvatarStage = isFigure && asset.avatar_exists && asset.avatar_url;

  if (showAvatarStage) {
    return (
      <div className="asset-still-stage">
        <div className="asset-still-panel">
          <span className="asset-still-label">头像</span>
          <div className="asset-still-avatar">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={asset.avatar_url!} alt={`${asset.filename} 头像`} loading="lazy" />
          </div>
        </div>
        <div className="asset-still-panel asset-still-figure-panel">
          <span className="asset-still-label">立绘</span>
          <div className="asset-still-figure">
            <ContainedAssetImage src={asset.url} alt={asset.filename} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="asset-still-figure">
      <ContainedAssetImage src={asset.url} alt={asset.filename} objectPosition={isFigure ? "bottom center" : "center"} />
    </div>
  );
}

type CharacterVoiceControlProps = {
  item: TTSVoiceReviewItem;
  availableVoices: TTSVoiceOption[];
  selectedVoice: string;
  busy: boolean;
  readonly: boolean;
  selectVoice: (voice: string) => void;
  previewVoice: (speaker: string, voice: string) => Promise<void>;
  activeSpeaker: string | null;
  playVoice: (speaker: string, audio: HTMLAudioElement) => Promise<void>;
  stopVoice: (speaker: string, audio: HTMLAudioElement) => void;
  pickerOpen: boolean;
  setPickerOpen: (open: boolean) => void;
};

function normalizedVoiceGender(value: string): "male" | "female" | null {
  const gender = value.trim().toLowerCase();
  if (["女", "女性", "女人", "女子", "female", "woman", "girl"].some((marker) => gender.includes(marker))) return "female";
  if (["男", "男性", "男人", "男子", "male", "man", "boy"].some((marker) => gender.includes(marker))) return "male";
  return null;
}

function CharacterVoiceControl(props: CharacterVoiceControlProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const assignedVoice = props.availableVoices.find((voice) => voice.name === props.item.voice);
  const characterGender = normalizedVoiceGender(props.item.gender) || normalizedVoiceGender(assignedVoice?.gender || "");
  const eligibleVoices = props.availableVoices.filter((voice) => normalizedVoiceGender(voice.gender) === characterGender);
  const selectedVoice = eligibleVoices.some((voice) => voice.name === props.selectedVoice)
    ? props.selectedVoice
    : eligibleVoices[0]?.name || "";
  const selectedOption = eligibleVoices.find((voice) => voice.name === selectedVoice);
  const genderLabel = characterGender === "female" ? "女声音色" : "男声音色";

  useEffect(() => {
    if (!props.readonly && selectedVoice && selectedVoice !== props.selectedVoice) {
      props.selectVoice(selectedVoice);
    }
  }, [props, selectedVoice]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || props.activeSpeaker === props.item.speaker) return;
    audio.pause();
    setPlaying(false);
  }, [props.activeSpeaker, props.item.speaker]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.currentTime = 0;
    setPlaying(false);
  }, [props.item.preview_url]);

  const voiceOptions = eligibleVoices.map((voice, index) => ({
    value: voice.name,
    label: voice.description || `${genderLabel} ${index + 1}`
  }));

  function togglePlayback() {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused) {
      props.stopVoice(props.item.speaker, audio);
      setPlaying(false);
      return;
    }
    void props.playVoice(props.item.speaker, audio).catch(() => setPlaying(false));
  }

  return (
    <div className="character-card-voice" onClick={(event) => event.stopPropagation()}>
      <div className={`voice-preview-row ${props.item.preview_exists && props.item.preview_url ? "" : "missing"}`}>
        {props.item.preview_exists && props.item.preview_url ? (
          <div className="voice-preview-action">
            <audio
              ref={audioRef}
              preload="none"
              src={props.item.preview_url}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
              onEnded={(event) => {
                event.currentTarget.currentTime = 0;
                props.stopVoice(props.item.speaker, event.currentTarget);
              }}
            />
            <button
              className="voice-play-button"
              type="button"
              aria-label={playing ? `暂停 ${props.item.speaker} 的试听` : `播放 ${props.item.speaker} 的试听`}
              onClick={togglePlayback}
            >
              {playing ? (
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zm6 0h4v14h-4z" /></svg>
              ) : (
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7z" /></svg>
              )}
            </button>
          </div>
        ) : (
          <div className="voice-preview-missing">试听暂不可用</div>
        )}
        <p className="character-voice-line">“{props.item.text}”</p>
      </div>
      {!props.readonly && (
        <details
          className="character-voice-options"
          open={props.pickerOpen}
          onToggle={(event) => props.setPickerOpen(event.currentTarget.open)}
        >
          <summary>不满意？更换音色</summary>
          <div className="character-voice-picker">
            <label>
              <span>候选音色</span>
              <FormSelect ariaLabel={`选择${genderLabel}`} value={selectedVoice} disabled={props.busy} options={voiceOptions} onValueChange={props.selectVoice} />
            </label>
            <small>{selectedOption?.description || "选择适合角色的声音描述"}</small>
            <button
              className="btn outline"
              type="button"
              disabled={props.busy || !selectedVoice}
              onClick={() => void props.previewVoice(props.item.speaker, selectedVoice)}
            >
              生成并试听这个音色
            </button>
          </div>
        </details>
      )}
    </div>
  );
}

type ScenePickerOption = { value: string; label: string; kind: "scene" | "ending"; configured?: boolean };

function ScenePicker(props: { value: string; options: ScenePickerOption[]; disabled?: boolean; onChange: (value: string) => void }) {
  const [query, setQuery] = useState("");
  const selected = props.options.find((item) => item.value === props.value) || props.options[0];
  const filtered = props.options.filter((item) => `${item.label} ${item.value}`.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <Popover.Root onOpenChange={(open) => { if (!open) setQuery(""); }}>
      <Popover.Trigger className="scene-picker-trigger" disabled={props.disabled} aria-label="选择场景">
        <span><small>{selected?.kind === "ending" ? "结局" : "场景"}</small><strong>{selected?.label || "选择场景"}</strong></span>
        <em>{selected?.value || ""}</em><b aria-hidden="true">›</b>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content className="scene-picker-popover" side="left" align="start" sideOffset={10} collisionPadding={16}>
          <div className="scene-picker-head"><strong>切换场景</strong><span>{props.options.length} 个场景</span></div>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索场景名称或文件…" aria-label="搜索场景" autoFocus />
          <ScrollArea.Root className="scene-picker-scroll"><ScrollArea.Viewport>
            <div className="scene-picker-list">
              {filtered.map((item) => (
                <Popover.Close asChild key={item.value}>
                  <button type="button" className={item.value === props.value ? "active" : ""} onClick={() => props.onChange(item.value)}>
                    <span><small>{item.kind === "ending" ? "结局" : "场景"}</small><strong>{item.label}</strong><em>{item.value}</em></span>
                    {item.configured ? <i>已配置</i> : null}
                  </button>
                </Popover.Close>
              ))}
              {filtered.length === 0 ? <p>没有匹配的场景</p> : null}
            </div>
          </ScrollArea.Viewport><ScrollArea.Scrollbar className="scene-picker-scrollbar" orientation="vertical"><ScrollArea.Thumb /></ScrollArea.Scrollbar></ScrollArea.Root>
          <Popover.Arrow className="scene-picker-arrow" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function ParticleEffectPreview(props: { preset: ParticleEffectPreset | null; config: SceneEffectAssignment | null }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [playing, setPlaying] = useState(true);
  const [lightBackdrop, setLightBackdrop] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    const preset = props.preset;
    const config = props.config;
    if (!canvas || !preset || !config) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const image = new Image();
    let frameHandle = 0;
    let disposed = false;
    let previousTime = performance.now();
    const sheet = preset.sheet || { frame_width: 128, frame_height: 128, frame_count: 10, columns: 10 };
    const previewCount = Math.max(1, Math.min(60, Math.round(config.count / 4)));
    const travelAngle = config.angle * Math.PI / 180;
    const spriteRotation = (config.angle - preset.angle) * Math.PI / 180;
    const particles = Array.from({ length: previewCount }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      frame: Math.floor(Math.random() * sheet.frame_count),
      scale: config.scale * (0.65 + Math.random() * 0.7),
      velocity: config.speed * (0.75 + Math.random() * 0.5),
      rotation: spriteRotation,
      rotationVelocity: config.rotation_speed * (0.6 + Math.random() * 0.8)
    }));

    const reset = (particle: typeof particles[number]) => {
      if (Math.abs(Math.cos(travelAngle)) >= Math.abs(Math.sin(travelAngle))) {
        particle.x = Math.cos(travelAngle) >= 0 ? -70 : canvas.width + 70;
        particle.y = Math.random() * canvas.height;
      } else {
        particle.x = Math.random() * canvas.width;
        particle.y = Math.sin(travelAngle) >= 0 ? -70 : canvas.height + 70;
      }
      particle.velocity = config.speed * (0.75 + Math.random() * 0.5);
      particle.frame = Math.floor(Math.random() * sheet.frame_count);
      particle.rotation = spriteRotation;
    };

    const drawBackdrop = () => {
      const gradient = context.createLinearGradient(0, 0, canvas.width, canvas.height);
      if (lightBackdrop) {
        gradient.addColorStop(0, "#f4e6cc");
        gradient.addColorStop(1, "#b9d7de");
      } else {
        gradient.addColorStop(0, "#07101f");
        gradient.addColorStop(0.58, "#16213b");
        gradient.addColorStop(1, "#3a2138");
      }
      context.globalCompositeOperation = "source-over";
      context.globalAlpha = 1;
      context.fillStyle = gradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = lightBackdrop ? "rgba(255,255,255,.3)" : "rgba(255,255,255,.52)";
      for (let index = 0; index < 24; index++) {
        const x = (index * 131 + 47) % canvas.width;
        const y = (index * 67 + 29) % canvas.height;
        context.fillRect(x, y, index % 4 === 0 ? 2 : 1, index % 4 === 0 ? 2 : 1);
      }
    };

    const draw = (time: number) => {
      if (disposed) return;
      const delta = Math.min(2.5, (time - previousTime) / 16.67);
      previousTime = time;
      drawBackdrop();
      context.globalCompositeOperation = config.blend_mode === "normal" ? "source-over" : config.blend_mode === "screen" ? "screen" : "lighter";
      for (const particle of particles) {
        if (playing) {
          particle.x += (Math.cos(travelAngle) * particle.velocity + config.drift) * delta * 0.65;
          particle.y += Math.sin(travelAngle) * particle.velocity * delta * 0.65;
          particle.y += config.gravity * delta * delta * 0.2;
          particle.rotation += particle.rotationVelocity * delta;
          if (particle.x < -100 || particle.x > canvas.width + 100 || particle.y < -100 || particle.y > canvas.height + 100) reset(particle);
        }
        const size = 62 * particle.scale;
        const frameX = (particle.frame % sheet.columns) * sheet.frame_width;
        const frameY = Math.floor(particle.frame / sheet.columns) * sheet.frame_height;
        const drawHeight = size * (sheet.frame_height / sheet.frame_width);
        context.save();
        context.globalAlpha = config.opacity * (0.72 + (particle.frame % 3) * 0.1);
        context.translate(particle.x, particle.y);
        context.rotate(particle.rotation);
        context.drawImage(image, frameX, frameY, sheet.frame_width, sheet.frame_height, -size / 2, -drawHeight / 2, size, drawHeight);
        context.restore();
      }
      frameHandle = requestAnimationFrame(draw);
    };
    image.onload = () => { frameHandle = requestAnimationFrame(draw); };
    image.src = preset.preview_url;
    return () => {
      disposed = true;
      cancelAnimationFrame(frameHandle);
    };
  }, [lightBackdrop, playing, props.config, props.preset]);

  return (
    <div className="particle-live-preview">
      <canvas ref={canvasRef} width={720} height={405} aria-label="场景特效实时预览" />
      {!props.config && <div className="particle-live-empty"><span>✦</span><strong>请选择一种特效</strong><small>参数变化会立即显示在这里</small></div>}
      <div className="particle-preview-toolbar">
        <button type="button" disabled={!props.config} onClick={() => setPlaying((current) => !current)}>{playing ? "Ⅱ 暂停" : "▶ 播放"}</button>
        <button type="button" onClick={() => setLightBackdrop((current) => !current)}>{lightBackdrop ? "切换深色背景" : "切换浅色背景"}</button>
        <span>实时预览 · 游戏内效果以实际画面尺寸为准</span>
      </div>
    </div>
  );
}

function DirectionDial(props: { value: number; disabled: boolean; onChange: (value: number) => void }) {
  const dialRef = useRef<HTMLDivElement | null>(null);

  function updateFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    if (props.disabled) return;
    event.preventDefault();
    const rect = dialRef.current?.getBoundingClientRect();
    if (!rect) return;
    props.onChange(Math.round(Math.atan2(event.clientY - rect.top - rect.height / 2, event.clientX - rect.left - rect.width / 2) * 180 / Math.PI));
  }

  function handleKey(event: KeyboardEvent<HTMLDivElement>) {
    if (props.disabled || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    event.preventDefault();
    const delta = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -5 : 5;
    let next = props.value + delta;
    if (next > 180) next -= 360;
    if (next < -180) next += 360;
    props.onChange(next);
  }

  return (
    <div className="direction-dial-field">
      <span className="direction-dial-title">运动方向 <small>拖动圆点调整</small></span>
      <div
        ref={dialRef}
        className={`direction-dial ${props.disabled ? "disabled" : ""}`}
        role="slider"
        tabIndex={props.disabled ? -1 : 0}
        aria-label="粒子运动方向"
        aria-valuemin={-180}
        aria-valuemax={180}
        aria-valuenow={props.value}
        onKeyDown={handleKey}
        onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); updateFromPointer(event); }}
        onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) updateFromPointer(event); }}
      >
        <span className="direction-cardinal north">上</span><span className="direction-cardinal east">右</span><span className="direction-cardinal south">下</span><span className="direction-cardinal west">左</span>
        <span className="direction-arrow" style={{ transform: `rotate(${props.value}deg)` }}><i /></span>
        <b aria-hidden="true" />
      </div>
    </div>
  );
}

export function LaperAssetWorkbench(props: LaperAssetWorkbenchProps) {
  const [section, setSection] = useState<AssetSection>("figures");
  const [expandedSection, setExpandedSection] = useState<AssetSection | null>("figures");
  const [voiceSelections, setVoiceSelections] = useState<Record<string, string>>({});
  const [activeVoiceSpeaker, setActiveVoiceSpeaker] = useState<string | null>(null);
  const [openVoicePickerSpeaker, setOpenVoicePickerSpeaker] = useState<string | null>(null);
  const [musicSceneFile, setMusicSceneFile] = useState("");
  const [musicDrafts, setMusicDrafts] = useState<Record<string, string | null>>({});
  const [musicPreviewingAsset, setMusicPreviewingAsset] = useState<string | null>(null);
  const [musicPreviewError, setMusicPreviewError] = useState("");
  const [effectSceneFile, setEffectSceneFile] = useState("");
  const [effectDrafts, setEffectDrafts] = useState<Record<string, SceneEffectAssignment | null>>({});
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicPreviewAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicPreviewUrlRef = useRef<string | null>(null);
  const figures = useMemo(() => props.assets.filter((asset) => asset.kind === "角色立绘"), [props.assets]);
  const backgrounds = useMemo(() => props.assets.filter((asset) => asset.kind !== "角色立绘"), [props.assets]);
  const currentList = section === "figures" ? figures : backgrounds;
  const hasUnappliedVoiceSelection = props.voices.some(
    (item) => (voiceSelections[item.speaker] || item.voice) !== item.voice
  );

  const selectedMusicScene = props.sceneMusic.find((item) => item.scene_file === musicSceneFile) || props.sceneMusic[0] || null;
  const selectedEffectScene = props.particleEffects.scenes.find((item) => item.scene_file === effectSceneFile) || props.particleEffects.scenes[0] || null;
  const musicAsset = selectedMusicScene && Object.hasOwn(musicDrafts, selectedMusicScene.scene_file)
    ? musicDrafts[selectedMusicScene.scene_file] || ""
    : selectedMusicScene?.selected_asset || "";
  const effectDraft = selectedEffectScene && Object.hasOwn(effectDrafts, selectedEffectScene.scene_file)
    ? effectDrafts[selectedEffectScene.scene_file]
    : selectedEffectScene?.assignment || null;
  const hasStagedPresentation = Object.entries(musicDrafts).some(([scene, asset]) => (props.sceneMusic.find((item) => item.scene_file === scene)?.selected_asset || "") !== (asset || ""))
    || Object.entries(effectDrafts).some(([scene, assignment]) => JSON.stringify(props.particleEffects.scenes.find((item) => item.scene_file === scene)?.assignment || null) !== JSON.stringify(assignment));

  useEffect(() => {
    if (!selectedMusicScene) return;
    if (!musicSceneFile) {
      setMusicSceneFile(selectedMusicScene.scene_file);
    }
  }, [musicSceneFile, selectedMusicScene]);

  useEffect(() => {
    if (!selectedEffectScene || effectSceneFile) return;
    setEffectSceneFile(selectedEffectScene.scene_file);
  }, [effectSceneFile, selectedEffectScene]);

  function setCurrentEffectDraft(value: SceneEffectAssignment | null) {
    if (!selectedEffectScene) return;
    setEffectDrafts((current) => ({ ...current, [selectedEffectScene.scene_file]: value }));
  }

  function chooseEffect(effectId: string) {
    const preset = props.particleEffects.effects.find((item) => item.id === effectId);
    if (!preset) {
      setCurrentEffectDraft(null);
    } else {
      setCurrentEffectDraft({
        effect_id: preset.id,
        asset: preset.asset,
        count: preset.count,
        speed: preset.speed,
        scale: preset.scale,
        angle: preset.angle,
        opacity: preset.opacity,
        drift: preset.drift,
        gravity: preset.gravity,
        rotation_speed: preset.rotation_speed,
        layer: preset.layer,
        blend_mode: preset.blend_mode
      });
    }
  }

  function changeEffectNumber(key: keyof SceneEffectAssignment, value: number) {
    if (effectDraft) setCurrentEffectDraft({ ...effectDraft, [key]: value });
  }
  const hasGeneratedImages = props.assets.some((asset) => asset.exists);
  const active = props.activeAsset;

  async function playVoice(speaker: string, audio: HTMLAudioElement) {
    if (activeAudioRef.current && activeAudioRef.current !== audio) {
      activeAudioRef.current.pause();
    }
    activeAudioRef.current = audio;
    setActiveVoiceSpeaker(speaker);
    try {
      await audio.play();
    } catch (error) {
      if (activeAudioRef.current === audio) {
        activeAudioRef.current = null;
        setActiveVoiceSpeaker(null);
      }
      throw error;
    }
  }

  function stopVoice(speaker: string, audio: HTMLAudioElement) {
    audio.pause();
    if (activeAudioRef.current === audio) {
      activeAudioRef.current = null;
      setActiveVoiceSpeaker((current) => current === speaker ? null : current);
    }
  }

  function stopMusicPreview() {
    const audio = musicPreviewAudioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    musicPreviewAudioRef.current = null;
    if (musicPreviewUrlRef.current) URL.revokeObjectURL(musicPreviewUrlRef.current);
    musicPreviewUrlRef.current = null;
    setMusicPreviewingAsset(null);
  }

  async function playMusicPreview(assetOverride?: string) {
    const asset = assetOverride || musicAsset || selectedMusicScene?.system_asset || "";
    if (!asset) return;
    stopMusicPreview();
    setMusicPreviewError("");
    try {
      const blob = await props.previewSceneMusic(asset);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      musicPreviewUrlRef.current = url;
      musicPreviewAudioRef.current = audio;
      audio.onended = stopMusicPreview;
      setMusicPreviewingAsset(asset);
      await audio.play();
    } catch (error) {
      stopMusicPreview();
      setMusicPreviewError(error instanceof Error ? error.message : "音乐试听加载失败。");
    }
  }

  useEffect(() => {
    if (!props.voiceGeneratingSpeaker || !activeAudioRef.current) return;
    activeAudioRef.current.pause();
    activeAudioRef.current = null;
    setActiveVoiceSpeaker(null);
  }, [props.voiceGeneratingSpeaker]);

  useEffect(() => () => stopMusicPreview(), []);

  return (
    <section className={`laper-shell laper-asset-shell ${props.readonly ? "readonly" : ""}`}>
      {props.voiceGeneratingSpeaker && (
        <div className="voice-generation-lock" role="status" aria-live="assertive" aria-busy="true">
          <div className="voice-generation-card">
            <span className="voice-generation-orbit" aria-hidden="true">
              <span />
              <svg viewBox="0 0 24 24"><path d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-5a3.5 3.5 0 1 0-7 0v5A3.5 3.5 0 0 0 12 15Zm-6-3.5a6 6 0 0 0 12 0M12 17.5V21m-3 0h6" /></svg>
            </span>
            <div>
              <strong>正在生成新的角色试听</strong>
              <p>正在为「{props.voiceGeneratingSpeaker}」重新调制音色，请稍候。</p>
              <small>完成后页面会自动恢复，并替换卡片中的试听。</small>
            </div>
          </div>
        </div>
      )}
      <aside className="laper-rail" aria-label="素材导航">
        <div className="laper-rail-brand">
          <strong>素材审阅</strong>
          <span>Asset Review</span>
        </div>
        <nav className="laper-rail-nav">
          {([
            ["figures", "角色卡", figures],
            ["backgrounds", "场景卡", backgrounds],
            ["effects", "特效素材", props.particleEffects.effects]
          ] as const).map(([sectionId, label, assets]) => (
            <div className="laper-rail-tree-group" key={sectionId}>
              <button
                aria-expanded={expandedSection === sectionId}
                className={section === sectionId ? "active" : ""}
                type="button"
                onClick={() => {
                  setSection(sectionId);
                  setExpandedSection((current) => current === sectionId ? null : sectionId);
                }}
              >
                <span>{label}</span>
                <span className="laper-rail-tree-meta"><em>{assets.length}</em><b aria-hidden="true">{expandedSection === sectionId ? "⌄" : "›"}</b></span>
              </button>
              {expandedSection === sectionId && (
                <ol className="laper-rail-list laper-rail-tree-list">
                  {assets.map((asset) => (
                    <li key={"id" in asset ? asset.id : `${asset.subdir}-${asset.filename}`}>
                      <button
                        className={"filename" in asset && active?.filename === asset.filename ? "active" : ""}
                        type="button"
                        onClick={() => {
                          setSection(sectionId);
                          if ("filename" in asset) props.openAsset(asset);
                        }}
                      >
                        <span>{"id" in asset ? "✦" : asset.exists ? "✓" : "·"}</span>
                        {"id" in asset ? asset.label : props.displayName(asset)}
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          ))}
        </nav>
      </aside>

      <section className="laper-canvas-wrap">
        <div className="laper-toolbar" role="toolbar" aria-label="素材工具栏">
          <button className={section === "figures" ? "active" : ""} type="button" onClick={() => setSection("figures")}>
            角色卡
          </button>
          <button className={section === "backgrounds" ? "active" : ""} type="button" onClick={() => setSection("backgrounds")}>
            场景卡
          </button>
          <button className={section === "effects" ? "active" : ""} type="button" onClick={() => setSection("effects")}>
            特效素材
          </button>
          <span className="laper-toolbar-divider" />
          <span className="laper-toolbar-note">{props.imageEnabled ? "点击图片可编辑 Prompt" : "当前未开启图片生成"}</span>
        </div>

        <div className="laper-canvas laper-asset-canvas">
          {section === "effects" ? (
            <div className="particle-effect-workbench">
              <header className="laper-canvas-head">
                <div>
                  <h2>场景特效</h2>
                  <p>为单独场景选择粒子贴图并调整运动参数；未设置的场景不会额外添加特效。</p>
                </div>
                <span>{props.particleEffects.effects.length} 组素材</span>
              </header>
              <div className="particle-effect-layout">
                <div className="particle-preview-column">
                  <ParticleEffectPreview
                    config={effectDraft}
                    preset={props.particleEffects.effects.find((item) => item.id === effectDraft?.effect_id) || null}
                  />
                  <p>
                    {props.particleEffects.effects.find((item) => item.id === effectDraft?.effect_id)?.description
                      || "从右侧选择特效后，可在这里实时查看呈现方式。"}
                  </p>
                </div>
                <section className="particle-effect-controls">
                  <div className="ui-form-field"><span>场景</span>
                    <ScenePicker value={selectedEffectScene?.scene_file || ""} disabled={props.readonly || props.busy} options={props.particleEffects.scenes.map((item) => ({ value: item.scene_file, label: item.label, kind: item.kind, configured: Boolean(item.assignment) }))} onChange={(value) => {
                      setEffectSceneFile(value);
                    }} />
                  </div>
                  <div className="ui-form-field"><span>特效</span>
                    <ToggleGroup.Root className="effect-toggle-group" type="single" value={effectDraft?.effect_id || "none"} disabled={props.readonly || props.busy} onValueChange={(value) => { if (value) chooseEffect(value === "none" ? "" : value); }} aria-label="选择特效">
                      <ToggleGroup.Item value="none"><b>×</b><span>无</span></ToggleGroup.Item>
                      {props.particleEffects.effects.map((effect) => <ToggleGroup.Item key={effect.id} value={effect.id}><b>✦</b><span>{effect.label}</span></ToggleGroup.Item>)}
                    </ToggleGroup.Root>
                  </div>
                  {effectDraft && (
                    <div className="particle-sliders">
                      {([
                        ["count", "密度", 1, 300, 1], ["speed", "速度", 0.2, 40, 0.2], ["scale", "大小", 0.05, 2, 0.05],
                        ["opacity", "透明度", 0.05, 1, 0.05]
                      ] as const).map(([key, label, min, max, step]) => (
                        <FormSlider key={key} label={label} min={min} max={max} step={step} value={effectDraft[key]} disabled={props.readonly || props.busy} onValueChange={(value) => changeEffectNumber(key, value)} />
                      ))}
                      <DirectionDial value={effectDraft.angle} disabled={props.readonly || props.busy} onChange={(value) => changeEffectNumber("angle", value)} />
                      <div className="ui-form-field"><span>图层</span><ToggleGroup.Root className="segment-toggle" type="single" value={effectDraft.layer} disabled={props.readonly || props.busy} onValueChange={(value) => { if (value) setCurrentEffectDraft({ ...effectDraft, layer: value as "foreground" | "background" }); }} aria-label="选择图层"><ToggleGroup.Item value="foreground">前景</ToggleGroup.Item><ToggleGroup.Item value="background">背景</ToggleGroup.Item></ToggleGroup.Root></div>
                      <details className="particle-advanced-controls">
                        <summary>高级运动参数</summary>
                        {([
                          ["drift", "横向漂移", -8, 8, 0.1], ["gravity", "重力", -3, 3, 0.1], ["rotation_speed", "旋转速度", -0.1, 0.1, 0.002]
                        ] as const).map(([key, label, min, max, step]) => (
                          <FormSlider key={key} label={label} min={min} max={max} step={step} value={effectDraft[key]} disabled={props.readonly || props.busy} onValueChange={(value) => changeEffectNumber(key, value)} />
                        ))}
                        <div className="ui-form-field"><span>混合模式</span><ToggleGroup.Root className="blend-mode-group" type="single" value={effectDraft.blend_mode} disabled={props.readonly || props.busy} onValueChange={(value) => { if (value) setCurrentEffectDraft({ ...effectDraft, blend_mode: value as "normal" | "add" | "screen" }); }} aria-label="选择混合模式"><ToggleGroup.Item value="normal"><b>普通</b><small>保留原色</small></ToggleGroup.Item><ToggleGroup.Item value="add"><b>发光</b><small>亮部相加</small></ToggleGroup.Item><ToggleGroup.Item value="screen"><b>滤色</b><small>柔和提亮</small></ToggleGroup.Item></ToggleGroup.Root></div>
                      </details>
                    </div>
                  )}
                </section>
              </div>
            </div>
          ) : active ? (
            <div className="laper-asset-detail">
              <header className="laper-canvas-head">
                <div>
                  <h2>{props.displayName(active)}</h2>
                  {active.kind !== "角色立绘" && <p>{active.kind} · {props.sceneDisplayName(active)}</p>}
                </div>
                <span className={active.exists ? "ready" : ""}>{active.exists ? "已生成" : "待生成"}</span>
              </header>
              <div className={assetPreviewClass(active)}>
                {active.exists ? <AssetPreviewImage asset={active} /> : <div className="asset-image-placeholder">图片尚未生成</div>}
              </div>
              <dl className="laper-asset-meta">
                <div>
                  <dt>文件</dt>
                  <dd>
                    {active.subdir}/{active.filename}.webp
                  </dd>
                </div>
                <div>
                  <dt>尺寸</dt>
                  <dd>{active.size || "未设置"}</dd>
                </div>
              </dl>
              <label className="asset-prompt-editor laper-asset-prompt">
                <span>Prompt</span>
                <textarea value={props.assetPrompt} onChange={(event) => props.setAssetPrompt(event.target.value)} rows={8} spellCheck={false} readOnly={props.readonly} />
              </label>
              <div className="laper-asset-actions">
                <button className="btn outline" type="button" onClick={props.closeAsset}>
                  返回列表
                </button>
                {!props.readonly && (
                  <button className="btn primary" type="button" disabled={props.busy} onClick={() => void props.regenerateAsset(active, props.assetPrompt)}>
                    重新生成此素材
                  </button>
                )}
              </div>
            </div>
          ) : (
            <>
              <header className="laper-canvas-head">
                <div>
                  <h2>{section === "figures" ? "角色卡" : "场景卡"}</h2>
                  <p>{props.imageEnabled ? "点击卡片查看大图并编辑 Prompt。" : "展示素材规划与 Prompt，可单独重新生成。"}</p>
                </div>
                <span>{currentList.length} 项</span>
              </header>
              {currentList.length === 0 ? (
                <div className="laper-empty">
                  <p>暂无素材</p>
                </div>
              ) : (
                <div className={`asset-card-grid laper-asset-grid ${section === "figures" && props.voiceEnabled ? "character-card-grid" : ""}`}>
                  {currentList.map((asset) => {
                    const voiceItem = section === "figures" && props.voiceEnabled
                      ? props.voices.find((item) => (
                          item.speaker === props.displayName(asset)
                          || (Boolean(item.speaker_id) && asset.filename.toLowerCase().includes(item.speaker_id.toLowerCase()))
                        ))
                      : undefined;
                    const selectedVoice = voiceItem ? voiceSelections[voiceItem.speaker] || voiceItem.voice : "";
                    return (
                      <article className={`asset-card ${voiceItem ? "has-voice" : ""}`} key={`${asset.subdir}-${asset.filename}`}>
                        <button className="asset-card-open" type="button" onClick={() => props.openAsset(asset)}>
                          <div className="asset-thumb">
                            {asset.exists ? (
                              <ContainedAssetImage
                                src={asset.url}
                                alt={asset.filename}
                                objectPosition={asset.kind === "角色立绘" ? "bottom center" : "center"}
                              />
                            ) : (
                              <span>待生成</span>
                            )}
                          </div>
                          <div className="asset-card-body">
                            <div className="asset-card-text">
                              <strong>{props.displayName(asset)}</strong>
                              {asset.kind !== "角色立绘" && <small>{props.sceneDisplayName(asset)}</small>}
                            </div>
                            <em className={asset.exists ? "ready" : ""}>{asset.exists ? "已生成" : "待生成"}</em>
                          </div>
                        </button>
                        {voiceItem && (
                          <CharacterVoiceControl
                            item={voiceItem}
                            availableVoices={props.availableVoices}
                            selectedVoice={selectedVoice}
                            busy={props.busy}
                            readonly={props.readonly}
                            selectVoice={(voice) => setVoiceSelections((current) => ({ ...current, [voiceItem.speaker]: voice }))}
                            previewVoice={props.previewVoice}
                            activeSpeaker={activeVoiceSpeaker}
                            playVoice={playVoice}
                            stopVoice={stopVoice}
                            pickerOpen={openVoicePickerSpeaker === voiceItem.speaker}
                            setPickerOpen={(open) => {
                              setOpenVoicePickerSpeaker((current) => {
                                if (open) return voiceItem.speaker;
                                return current === voiceItem.speaker ? null : current;
                              });
                            }}
                          />
                        )}
                      </article>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      </section>

      <aside className="laper-inspector outline-side">
        <LaperInspectorShell
          eyebrow="信息"
          title="素材概览"
          stats={[
            { label: "角色", value: figures.length },
            { label: "场景", value: backgrounds.length },
            { label: "状态", value: hasGeneratedImages ? "有图" : "待图" },
            ...(props.voiceEnabled ? [{ label: "语音", value: `${props.voices.length} 条试听` }] : [])
          ]}
          note={props.published ? "新素材会先进入草稿；应用修改时只替换实际改过的素材。" : props.imageEnabled ? "点击图片可查看大图并编辑 Prompt。" : "当前未开启图片生成，仍可查看规划与 Prompt。"}
          footer={
            props.retryAction ? (
              <button
                className="btn primary retry-action"
                type="button"
                disabled={props.busy}
                onClick={props.retryAction}
              >
                <span aria-hidden="true">↻</span>
                {props.busy ? "正在重试..." : props.retryLabel || "重试生成"}
              </button>
            ) : props.readonly ? (
              <span className="readonly-status">
                <span className="inline-spinner" aria-hidden="true" />
                {props.published ? "完成态默认只读" : "游戏自动生成中"}
              </span>
            ) : (
              <div className="asset-build-actions">
                {props.published && props.buildState === "FAILED" && (
                  <button className="btn outline" type="button" disabled={props.busy} onClick={() => void props.buildGame()}>
                    重试应用修改
                  </button>
                )}
                <button
                  className="btn primary"
                  type="button"
                  disabled={props.busy || props.assets.length === 0 || hasUnappliedVoiceSelection || (Boolean(props.published) && !props.hasDraftChanges && !hasStagedPresentation)}
                  title={
                    hasUnappliedVoiceSelection
                      ? "已选择新音色，请先生成试听或恢复原选择"
                      : props.published && !props.hasDraftChanges && !hasStagedPresentation
                        ? "草稿没有新的已保存改动，无需同步"
                        : undefined
                  }
                  onClick={() => void props.buildGame(hasStagedPresentation ? { music: musicDrafts, effects: effectDrafts } : undefined)}
                >
                  {props.published ? "应用修改到游戏" : "确认素材并生成游戏"}
                </button>
              </div>
            )
          }
        />
        {props.sceneMusicEnabled && props.sceneMusic.length > 0 ? (
          <section className="scene-music-editor" aria-label="场景音乐">
            <span className="scene-music-kicker">SCENE MUSIC</span>
            <h3>场景音乐</h3>
            <p>选择只在当前编辑中暂存；点击“应用修改到游戏”时统一写入并生效。</p>
            <div className="ui-form-field"><span>场景</span><ScenePicker value={selectedMusicScene?.scene_file || ""} disabled={props.readonly || props.busy} options={props.sceneMusic.map((item) => ({ value: item.scene_file, label: item.label, kind: item.kind, configured: Boolean(item.selected_asset) }))} onChange={(value) => { stopMusicPreview(); setMusicSceneFile(value); }} /></div>
            <div className="ui-form-field"><span>音乐</span>
              <div className="music-choice-list" role="radiogroup" aria-label="选择场景音乐">
                {[{ asset: "", label: "系统自动", hint: selectedMusicScene?.system_asset || "由系统根据场景选择" }, ...props.musicAssets.map((asset) => ({ asset, label: asset.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " "), hint: asset }))].map((item) => {
                  const previewAsset = item.asset || selectedMusicScene?.system_asset || "";
                  const playing = Boolean(previewAsset && musicPreviewingAsset === previewAsset);
                  return <div className={`music-choice ${musicAsset === item.asset ? "active" : ""}`} key={item.asset || "system"}>
                  <button className="music-choice-select" type="button" role="radio" aria-checked={musicAsset === item.asset} disabled={props.readonly || props.busy} onClick={() => { stopMusicPreview(); if (selectedMusicScene) setMusicDrafts((current) => ({ ...current, [selectedMusicScene.scene_file]: item.asset || null })); }}><i /><span><strong>{item.label}</strong><small>{item.hint}</small></span>{!item.asset ? <em>推荐</em> : null}</button>
                    <button className={`music-choice-play ${playing ? "is-playing" : ""}`} type="button" disabled={props.busy || !previewAsset} aria-label={playing ? `停止试听 ${previewAsset}` : `试听 ${previewAsset}`} onClick={() => playing ? stopMusicPreview() : void playMusicPreview(previewAsset)}>{playing ? "Ⅱ" : "▶"}</button>
                  </div>;
                })}
              </div>
            </div>
            {musicPreviewError ? <small className="scene-music-error">{musicPreviewError}</small> : null}
          </section>
        ) : null}
      </aside>
    </section>
  );
}
