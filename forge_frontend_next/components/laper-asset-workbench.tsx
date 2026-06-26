"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
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

type LaperAssetWorkbenchProps = {
  imageEnabled: boolean;
  assets: AssetReviewItem[];
  busy: boolean;
  readonly: boolean;
  activeAsset: AssetReviewItem | null;
  assetPrompt: string;
  setAssetPrompt: (value: string) => void;
  openAsset: (asset: AssetReviewItem) => void;
  closeAsset: () => void;
  regenerateAsset: (asset: AssetReviewItem, prompt: string) => Promise<void>;
  buildGame: () => Promise<void>;
  displayName: (asset: AssetReviewItem) => string;
  sceneDisplayName: (asset: AssetReviewItem) => string;
};

type AssetSection = "figures" | "backgrounds";

export function LaperAssetWorkbench(props: LaperAssetWorkbenchProps) {
  const [section, setSection] = useState<AssetSection>("figures");
  const figures = useMemo(() => props.assets.filter((asset) => asset.kind === "角色立绘"), [props.assets]);
  const backgrounds = useMemo(() => props.assets.filter((asset) => asset.kind !== "角色立绘"), [props.assets]);
  const currentList = section === "figures" ? figures : backgrounds;
  const hasGeneratedImages = props.assets.some((asset) => asset.exists);
  const active = props.activeAsset;

  return (
    <section className={`laper-shell laper-asset-shell ${props.readonly ? "readonly" : ""}`}>
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
                  <p>
                    {active.kind} · {props.sceneDisplayName(active)}
                  </p>
                </div>
                <span className={active.exists ? "ready" : ""}>{active.exists ? "已生成" : "待生成"}</span>
              </header>
              <div className="laper-asset-preview">
                {active.exists ? (
                  <Image src={active.url} alt={active.filename} width={960} height={540} unoptimized />
                ) : (
                  <div className="asset-image-placeholder">图片尚未生成</div>
                )}
                {active.avatar_exists && active.avatar_url && (
                  <div className="asset-avatar-preview">
                    <span>头像</span>
                    <Image src={active.avatar_url} alt={`${active.filename} 头像`} width={88} height={88} unoptimized />
                  </div>
                )}
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
                <div className="asset-card-grid laper-asset-grid">
                  {currentList.map((asset) => (
                    <button className="asset-card" key={`${asset.subdir}-${asset.filename}`} type="button" onClick={() => props.openAsset(asset)}>
                      <div className="asset-thumb">
                        {asset.exists ? <Image src={asset.url} alt={asset.filename} width={320} height={180} unoptimized /> : <span>待生成</span>}
                      </div>
                      <div>
                        <strong>{props.displayName(asset)}</strong>
                        <small>{props.sceneDisplayName(asset)}</small>
                      </div>
                      <em className={asset.exists ? "ready" : ""}>{asset.exists ? "已生成" : "待生成"}</em>
                    </button>
                  ))}
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
            { label: "状态", value: hasGeneratedImages ? "有图" : "待图" }
          ]}
          note={props.imageEnabled ? "点击图片可查看大图并编辑 Prompt。" : "当前未开启图片生成，仍可查看规划与 Prompt。"}
          footer={
            props.readonly ? (
              <span className="readonly-status">
                <span className="inline-spinner" aria-hidden="true" />
                游戏自动生成中
              </span>
            ) : (
              <button className="btn primary" type="button" disabled={props.busy || props.assets.length === 0} onClick={() => void props.buildGame()}>
                确认素材并生成游戏
              </button>
            )
          }
        />
      </aside>
    </section>
  );
}
