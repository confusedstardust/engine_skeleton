"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { LaperInspectorShell } from "./laper-inspector-shell";

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

type LaperAssetWorkbenchProps = {
  imageEnabled: boolean;
  assets: AssetReviewItem[];
  voiceEnabled: boolean;
  voices: TTSVoiceReviewItem[];
  availableVoices: TTSVoiceOption[];
  voiceGeneratingSpeaker: string | null;
  busy: boolean;
  readonly: boolean;
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
};

type AssetSection = "figures" | "backgrounds";

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

export function LaperAssetWorkbench(props: LaperAssetWorkbenchProps) {
  const [section, setSection] = useState<AssetSection>("figures");
  const [voiceSelections, setVoiceSelections] = useState<Record<string, string>>({});
  const [activeVoiceSpeaker, setActiveVoiceSpeaker] = useState<string | null>(null);
  const [openVoicePickerSpeaker, setOpenVoicePickerSpeaker] = useState<string | null>(null);
  const activeAudioRef = useRef<HTMLAudioElement | null>(null);
  const figures = useMemo(() => props.assets.filter((asset) => asset.kind === "角色立绘"), [props.assets]);
  const backgrounds = useMemo(() => props.assets.filter((asset) => asset.kind !== "角色立绘"), [props.assets]);
  const currentList = section === "figures" ? figures : backgrounds;
  const hasUnappliedVoiceSelection = props.voices.some(
    (item) => (voiceSelections[item.speaker] || item.voice) !== item.voice
  );
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

  useEffect(() => {
    if (!props.voiceGeneratingSpeaker || !activeAudioRef.current) return;
    activeAudioRef.current.pause();
    activeAudioRef.current = null;
    setActiveVoiceSpeaker(null);
  }, [props.voiceGeneratingSpeaker]);

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
          <button className={section === "figures" ? "active" : ""} type="button" onClick={() => setSection("figures")}>
            角色卡
            <em>{figures.length}</em>
          </button>
          <button className={section === "backgrounds" ? "active" : ""} type="button" onClick={() => setSection("backgrounds")}>
            场景卡
            <em>{backgrounds.length}</em>
          </button>
        </nav>
        <ol className="laper-rail-list">
          {currentList.map((asset) => (
            <li key={`${asset.subdir}-${asset.filename}`}>
              <button
                className={active?.filename === asset.filename ? "active" : ""}
                type="button"
                onClick={() => props.openAsset(asset)}
              >
                <span>{asset.exists ? "✓" : "·"}</span>
                {props.displayName(asset)}
              </button>
            </li>
          ))}
        </ol>
      </aside>

      <section className="laper-canvas-wrap">
        <div className="laper-toolbar" role="toolbar" aria-label="素材工具栏">
          <button className={section === "figures" ? "active" : ""} type="button" onClick={() => setSection("figures")}>
            角色卡
          </button>
          <button className={section === "backgrounds" ? "active" : ""} type="button" onClick={() => setSection("backgrounds")}>
            场景卡
          </button>
          <span className="laper-toolbar-divider" />
          <span className="laper-toolbar-note">{props.imageEnabled ? "点击图片可编辑 Prompt" : "当前未开启图片生成"}</span>
        </div>

        <div className="laper-canvas laper-asset-canvas">
          {active ? (
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
          note={props.imageEnabled ? "点击图片可查看大图并编辑 Prompt。" : "当前未开启图片生成，仍可查看规划与 Prompt。"}
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
                游戏自动生成中
              </span>
            ) : (
              <button
                className="btn primary"
                type="button"
                disabled={props.busy || props.assets.length === 0 || hasUnappliedVoiceSelection}
                title={hasUnappliedVoiceSelection ? "已选择新音色，请先生成试听或恢复原选择" : undefined}
                onClick={() => void props.buildGame()}
              >
                确认素材并生成游戏
              </button>
            )
          }
        />
      </aside>
    </section>
  );
}
