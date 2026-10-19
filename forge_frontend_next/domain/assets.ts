import type { Job } from "./jobs";

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
  crop_source_url?: string;
  avatar_exists: boolean;
  avatar_url: string | null;
};

export type TTSVoiceOption = {
  name: string;
  label?: string;
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

export type AssetReviewResponse = {
  job: Job;
  assets: AssetReviewItem[];
  image_enabled: boolean;
  voice_enabled: boolean;
  voices: TTSVoiceReviewItem[];
  available_voices: TTSVoiceOption[];
  scene_music: SceneMusicItem[];
  music_assets: string[];
  music_asset_names?: Record<string, string>;
  particle_effects: ParticleEffectReview;
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

export type PersonalLibraryAsset = Omit<LibraryAsset, "kind" | "source_type" | "owner_user_id" | "size_bytes"> & {
  kind: "FIGURE" | "BACKGROUND" | "BGM";
  source_type: "GENERATED" | "UPLOADED";
};

export type StagedScenePresentation = {
  music: Record<string, string | null>;
  effects: Record<string, SceneEffectAssignment | null>;
  avatarCrops: Record<string, { zoom: number; offsetX: number; offsetY: number }>;
};

export type LibraryAsset = {
  category_label?: string; is_favorite?: boolean; owner_user_id: string; id: string; name: string; kind: string; source_type: string; created_at: string;
  file_id: string; revision: number; variant: string; mime_type: string; size_bytes: number;
  width_px?: number | null; height_px?: number | null; duration_ms?: number | null; url: string;
};
