"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
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
};

export type SceneEffectAssignment = Omit<ParticleEffectPreset, "id" | "label" | "description" | "preview_url"> & {
  effect_id: string;
};

export type ParticleEffectReview = {
  effects: ParticleEffectPreset[];
  scenes: Array<{ scene_file: string; label: string; kind: "scene" | "ending"; assignment: SceneEffectAssignment | null }>;
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
  buildGame: () => Promise<void>;
  retryAction?: () => void;
  retryLabel?: string;
  displayName: (asset: AssetReviewItem) => string;
  sceneDisplayName: (asset: AssetReviewItem) => string;
  sceneMusic: SceneMusicItem[];
  musicAssets: string[];
  sceneMusicEnabled: boolean;
  saveSceneMusic: (sceneFile: string, asset: string | null) => Promise<void>;
  previewSceneMusic: (asset: string) => Promise<Blob>;
  particleEffects: ParticleEffectReview;
  saveSceneEffect: (sceneFile: string, assignment: SceneEffectAssignment | null) => Promise<void>;
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

  const voiceOptions = eligibleVoices.map((voice, index) => (
    <option key={voice.name} value={voice.name}>{voice.description || `${genderLabel} ${index + 1}`}</option>
  ));

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
              <select
                value={selectedVoice}
                disabled={props.busy}
                onChange={(event) => props.selectVoice(event.target.value)}
              >
                <optgroup label={genderLabel}>{voiceOptions}</optgroup>
              </select>
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
    const previewCount = Math.max(1, Math.min(60, Math.round(config.count / 4)));
    const travelAngle = config.angle * Math.PI / 180;
    const spriteRotation = (config.angle - preset.angle) * Math.PI / 180;
    const particles = Array.from({ length: previewCount }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      frame: Math.floor(Math.random() * 10),
      scale: config.scale * (0.65 + Math.random() * 0.7),
      velocity: config.speed * (0.75 + Math.random() * 0.5),
      rotation: spriteRotation,
      rotationVelocity: config.rotation_speed * (0.6 + Math.random() * 0.8)
    }));

    const reset = (particle: typeof particles[number]) => {
      particle.x = Math.cos(travelAngle) >= 0 ? -70 : canvas.width + 70;
      particle.y = Math.random() * canvas.height;
      particle.velocity = config.speed * (0.75 + Math.random() * 0.5);
      particle.frame = Math.floor(Math.random() * 10);
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
        context.save();
        context.globalAlpha = config.opacity * (0.72 + (particle.frame % 3) * 0.1);
        context.translate(particle.x, particle.y);
        context.rotate(particle.rotation);
        context.drawImage(image, particle.frame * 128, 0, 128, 128, -size / 2, -size / 2, size, size);
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

const directionPresets = [
  { value: -135, label: "↖", title: "左上" }, { value: -90, label: "↑", title: "向上" },
  { value: -45, label: "↗", title: "右上" }, { value: 180, label: "←", title: "向左" },
  { value: 0, label: "→", title: "向右" }, { value: 135, label: "↙", title: "左下" },
  { value: 90, label: "↓", title: "向下" }, { value: 45, label: "↘", title: "右下" }
];

function DirectionDial(props: { value: number; disabled: boolean; onChange: (value: number) => void }) {
  const dialRef = useRef<HTMLDivElement | null>(null);

  function updateFromPointer(event: ReactPointerEvent<HTMLDivElement>) {
    if (props.disabled) return;
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
      <span className="direction-dial-title">运动方向 <output>{props.value}°</output></span>
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
        <span className="direction-axis horizontal" /><span className="direction-axis vertical" />
        <span className="direction-arrow" style={{ transform: `rotate(${props.value}deg)` }}><i /></span>
        <b>拖动</b>
      </div>
      <div className="direction-presets" aria-label="快捷方向">
        {directionPresets.map((item) => <button key={item.value} type="button" disabled={props.disabled} className={props.value === item.value ? "active" : ""} title={`${item.title} · ${item.value}°`} onClick={() => props.onChange(item.value)}>{item.label}</button>)}
      </div>
      <label className="direction-precision"><span>精确角度</span><input type="number" min={-180} max={180} value={props.value} disabled={props.disabled} onChange={(event) => props.onChange(Math.max(-180, Math.min(180, Number(event.target.value))))} /><em>°</em></label>
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
  const [musicAsset, setMusicAsset] = useState("");
  const [musicPreviewingAsset, setMusicPreviewingAsset] = useState<string | null>(null);
  const [musicPreviewError, setMusicPreviewError] = useState("");
  const [effectSceneFile, setEffectSceneFile] = useState("");
  const [effectDraft, setEffectDraft] = useState<SceneEffectAssignment | null>(null);
  const [effectDirty, setEffectDirty] = useState(false);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicPreviewAudioRef = useRef<HTMLAudioElement | null>(null);
  const musicPreviewUrlRef = useRef<string | null>(null);
  const musicFormHydratedRef = useRef("");
  const figures = useMemo(() => props.assets.filter((asset) => asset.kind === "角色立绘"), [props.assets]);
  const backgrounds = useMemo(() => props.assets.filter((asset) => asset.kind !== "角色立绘"), [props.assets]);
  const currentList = section === "figures" ? figures : backgrounds;
  const hasUnappliedVoiceSelection = props.voices.some(
    (item) => (voiceSelections[item.speaker] || item.voice) !== item.voice
  );

  const selectedMusicScene = props.sceneMusic.find((item) => item.scene_file === musicSceneFile) || props.sceneMusic[0] || null;
  const selectedEffectScene = props.particleEffects.scenes.find((item) => item.scene_file === effectSceneFile) || props.particleEffects.scenes[0] || null;

  useEffect(() => {
    if (!selectedMusicScene) return;
    const persistedKey = `${selectedMusicScene.scene_file}|${selectedMusicScene.selected_asset || ""}`;
    if (musicSceneFile !== selectedMusicScene.scene_file || musicFormHydratedRef.current !== persistedKey) {
      setMusicSceneFile(selectedMusicScene.scene_file);
      setMusicAsset(selectedMusicScene.selected_asset || "");
      musicFormHydratedRef.current = persistedKey;
    }
  }, [musicSceneFile, selectedMusicScene]);

  useEffect(() => {
    if (!selectedEffectScene || effectDirty) return;
    setEffectSceneFile(selectedEffectScene.scene_file);
    setEffectDraft(selectedEffectScene.assignment ? { ...selectedEffectScene.assignment } : null);
  }, [effectDirty, selectedEffectScene]);

  function chooseEffect(effectId: string) {
    const preset = props.particleEffects.effects.find((item) => item.id === effectId);
    if (!preset) {
      setEffectDraft(null);
    } else {
      setEffectDraft({
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
    setEffectDirty(true);
  }

  function changeEffectNumber(key: keyof SceneEffectAssignment, value: number) {
    setEffectDraft((current) => current ? { ...current, [key]: value } : current);
    setEffectDirty(true);
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

  async function playMusicPreview() {
    const asset = musicAsset || selectedMusicScene?.system_asset || "";
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
                      || "从右侧下拉菜单选择特效后，可在这里实时查看呈现方式。"}
                  </p>
                </div>
                <section className="particle-effect-controls">
                  <label className="ui-form-field"><span>场景</span>
                    <FormSelect ariaLabel="选择场景" value={selectedEffectScene?.scene_file || ""} disabled={props.readonly || props.busy} options={props.particleEffects.scenes.map((item) => ({ value: item.scene_file, label: `${item.kind === "ending" ? "结局 · " : "场景 · "}${item.label}` }))} onValueChange={(value) => {
                      setEffectSceneFile(value);
                      const next = props.particleEffects.scenes.find((item) => item.scene_file === value);
                      setEffectDraft(next?.assignment ? { ...next.assignment } : null);
                      setEffectDirty(false);
                    }} />
                  </label>
                  <label className="ui-form-field"><span>特效</span>
                    <FormSelect ariaLabel="选择特效" value={effectDraft?.effect_id || ""} disabled={props.readonly || props.busy} options={[{ value: "", label: "不使用特效" }, ...props.particleEffects.effects.map((effect) => ({ value: effect.id, label: effect.label }))]} onValueChange={chooseEffect} />
                  </label>
                  {effectDraft && (
                    <div className="particle-sliders">
                      {([
                        ["count", "密度", 1, 300, 1], ["speed", "速度", 0.2, 40, 0.2], ["scale", "大小", 0.05, 2, 0.05],
                        ["opacity", "透明度", 0.05, 1, 0.05]
                      ] as const).map(([key, label, min, max, step]) => (
                        <FormSlider key={key} label={label} min={min} max={max} step={step} value={effectDraft[key]} disabled={props.readonly || props.busy} onValueChange={(value) => changeEffectNumber(key, value)} />
                      ))}
                      <DirectionDial value={effectDraft.angle} disabled={props.readonly || props.busy} onChange={(value) => changeEffectNumber("angle", value)} />
                      <label className="ui-form-field"><span>图层</span><FormSelect ariaLabel="选择图层" value={effectDraft.layer} disabled={props.readonly || props.busy} options={[{ value: "foreground", label: "前景" }, { value: "background", label: "背景" }]} onValueChange={(value) => { setEffectDraft({ ...effectDraft, layer: value as "foreground" | "background" }); setEffectDirty(true); }} /></label>
                      <details className="particle-advanced-controls">
                        <summary>高级运动参数</summary>
                        {([
                          ["drift", "横向漂移", -8, 8, 0.1], ["gravity", "重力", -3, 3, 0.1], ["rotation_speed", "旋转速度", -0.1, 0.1, 0.002]
                        ] as const).map(([key, label, min, max, step]) => (
                          <FormSlider key={key} label={label} min={min} max={max} step={step} value={effectDraft[key]} disabled={props.readonly || props.busy} onValueChange={(value) => changeEffectNumber(key, value)} />
                        ))}
                        <label className="ui-form-field"><span>混合模式</span><FormSelect ariaLabel="选择混合模式" value={effectDraft.blend_mode} disabled={props.readonly || props.busy} options={[{ value: "normal", label: "普通" }, { value: "add", label: "发光叠加" }, { value: "screen", label: "滤色" }]} onValueChange={(value) => { setEffectDraft({ ...effectDraft, blend_mode: value as "normal" | "add" | "screen" }); setEffectDirty(true); }} /></label>
                      </details>
                    </div>
                  )}
                  <button className="btn primary" type="button" disabled={props.readonly || props.busy || !selectedEffectScene || !effectDirty} onClick={async () => {
                    if (!selectedEffectScene) return;
                    await props.saveSceneEffect(selectedEffectScene.scene_file, effectDraft);
                    setEffectDirty(false);
                  }}>{effectDraft ? "保存场景特效" : "移除场景特效"}</button>
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
                  disabled={props.busy || props.assets.length === 0 || hasUnappliedVoiceSelection || (Boolean(props.published) && !props.hasDraftChanges)}
                  title={
                    hasUnappliedVoiceSelection
                      ? "已选择新音色，请先生成试听或恢复原选择"
                      : props.published && !props.hasDraftChanges
                        ? "草稿没有新的已保存改动，无需同步"
                        : undefined
                  }
                  onClick={() => void props.buildGame()}
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
            <p>不设置时保持系统自动选择；保存后点击“应用修改到游戏”，只更新当前场景的音乐。</p>
            <label>
              <span>场景</span>
              <select
                value={selectedMusicScene?.scene_file || ""}
                disabled={props.readonly || props.busy}
                onChange={(event) => {
                  stopMusicPreview();
                  setMusicSceneFile(event.target.value);
                }}
              >
                {props.sceneMusic.map((item) => (
                  <option key={item.scene_file} value={item.scene_file}>{item.kind === "ending" ? "结局 · " : "场景 · "}{item.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>音乐</span>
              <select
                value={musicAsset}
                disabled={props.readonly || props.busy}
                onChange={(event) => {
                  stopMusicPreview();
                  setMusicAsset(event.target.value);
                }}
              >
                <option value="">系统自动{selectedMusicScene?.system_asset ? `（${selectedMusicScene.system_asset}）` : ""}</option>
                {props.musicAssets.map((asset) => <option key={asset} value={asset}>{asset}</option>)}
              </select>
            </label>
            <div className="scene-music-preview">
              <button
                className={`scene-music-play ${musicPreviewingAsset ? "is-playing" : ""}`}
                type="button"
                disabled={props.busy || !(musicAsset || selectedMusicScene?.system_asset)}
                aria-label={musicPreviewingAsset ? "停止音乐试听" : "试听所选音乐"}
                aria-pressed={Boolean(musicPreviewingAsset)}
                title={musicPreviewingAsset ? "停止试听" : "试听所选音乐"}
                onClick={() => musicPreviewingAsset ? stopMusicPreview() : void playMusicPreview()}
              >
                {musicPreviewingAsset ? (
                  <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" rx="1" /><rect x="13.5" y="6" width="3.5" height="12" rx="1" /></svg>
                ) : (
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.8v12.4a1.1 1.1 0 0 0 1.7.94l9.2-6.2a1.12 1.12 0 0 0 0-1.86l-9.2-6.2A1.1 1.1 0 0 0 8 5.8Z" /></svg>
                )}
              </button>
              <div className="scene-music-preview-copy">
                <strong>{musicPreviewingAsset ? "正在试听" : "试听当前选择"}</strong>
                <span>{musicPreviewingAsset || musicAsset || selectedMusicScene?.system_asset || "暂无可试听音乐"}</span>
              </div>
            </div>
            {musicPreviewError ? <small className="scene-music-error">{musicPreviewError}</small> : null}
            <button
              className="btn outline"
              type="button"
              disabled={props.readonly || props.busy || !selectedMusicScene || musicAsset === (selectedMusicScene.selected_asset || "")}
              onClick={() => selectedMusicScene && void props.saveSceneMusic(selectedMusicScene.scene_file, musicAsset || null)}
            >
              {musicAsset ? "保存场景音乐" : "恢复系统选择"}
            </button>
          </section>
        ) : null}
      </aside>
    </section>
  );
}
