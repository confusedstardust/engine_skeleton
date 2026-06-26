"use client";

import { useEffect, useMemo, useState } from "react";

export type SceneLine = {
  id: string;
  kind: "narration" | "dialogue" | "command" | "choice" | "branch";
  speaker: string;
  text: string;
  rawPrefix: string;
  choices?: SceneChoice[];
  branchLabel?: string;
};

export type SceneChoice = {
  text: string;
  target: string;
  target_scene_file?: string;
  targetSceneFile?: string;
};

export type EditableScene = {
  header: string;
  title: string;
  lines: SceneLine[];
  marker?: "Scene" | "Ending";
  sourceNode?: string;
  strtype?: string;
};

type TargetOption = { file: string; label: string };

type LaperSceneWorkbenchProps = {
  mode: "draft" | "complete";
  title: string;
  subtitle: string;
  plan: { characters: { name: string }[] } | null;
  scenes: EditableScene[];
  activeScene: number;
  setActiveScene: (index: number) => void;
  onScenesChange: (scenes: EditableScene[]) => void;
  readonly: boolean;
  busy: boolean;
  routeLabel: (scene: EditableScene) => string;
  markerLabel: (scene: EditableScene) => string;
  targetOptions?: TargetOption[];
  inspector: React.ReactNode;
  toolbarExtra?: React.ReactNode;
};

function reorder<T>(items: T[], from: number, to: number) {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) return items;
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

function draftLineRows(text: string) {
  return Math.max(2, text.split(/\r?\n/).reduce((total, line) => total + Math.ceil(Math.max(line.length, 1) / 36), 0));
}

function choiceTargetValue(choice: SceneChoice) {
  return choice.target_scene_file || choice.targetSceneFile || choice.target || "";
}

function lineKindLabel(line: SceneLine) {
  if (line.kind === "choice") return "分支";
  if (line.kind === "branch") return "分支";
  if (line.kind === "dialogue") return "对话";
  return "旁白";
}

export function LaperSceneWorkbench(props: LaperSceneWorkbenchProps) {
  const [speakerMenu, setSpeakerMenu] = useState<string | null>(null);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const disabled = props.readonly || props.busy;
  const activeIndex = Math.min(props.activeScene, Math.max(props.scenes.length - 1, 0));
  const scene = props.scenes[activeIndex];
  const speakers = useMemo(() => ["旁白", ...(props.plan?.characters.map((c) => c.name).filter(Boolean) || [])], [props.plan]);
  const defaultChoiceTarget = props.targetOptions?.[0]?.file || "new_branch";

  useEffect(() => {
    if (props.activeScene > Math.max(props.scenes.length - 1, 0)) {
      props.setActiveScene(Math.max(props.scenes.length - 1, 0));
    }
    setSpeakerMenu(null);
  }, [props.activeScene, props.scenes.length, props]);

  function patchScene(nextScene: EditableScene) {
    props.onScenesChange(props.scenes.map((item, index) => (index === activeIndex ? nextScene : item)));
  }

  function updateLine(lineIndex: number, nextLine: SceneLine) {
    if (!scene || disabled) return;
    patchScene({ ...scene, lines: scene.lines.map((line, index) => (index === lineIndex ? nextLine : line)) });
  }

  function reorderLines(from: number, to: number) {
    if (!scene || disabled) return;
    patchScene({ ...scene, lines: reorder(scene.lines, from, to) });
  }

  function removeLine(lineIndex: number) {
    if (!scene || disabled) return;
    patchScene({ ...scene, lines: scene.lines.filter((_, index) => index !== lineIndex) });
  }

  function addLine(kind: "narration" | "dialogue") {
    if (!scene || disabled) return;
    const nextLine: SceneLine = {
      id: `${scene.header}-${Date.now()}`,
      kind,
      speaker: kind === "dialogue" ? "角色" : "旁白",
      text: kind === "dialogue" ? "新的对话内容" : "新的旁白内容",
      rawPrefix: kind === "dialogue" ? "" : "旁白"
    };
    patchScene({ ...scene, lines: [...scene.lines, nextLine] });
  }

  function switchSpeaker(lineIndex: number, speaker: string) {
    if (!scene || disabled) return;
    const line = scene.lines[lineIndex];
    updateLine(lineIndex, {
      ...line,
      kind: speaker === "旁白" ? "narration" : "dialogue",
      speaker,
      rawPrefix: speaker === "旁白" ? "intro" : ""
    });
    setSpeakerMenu(null);
  }

  function updateChoice(lineIndex: number, choiceIndex: number, nextChoice: SceneChoice) {
    if (!scene || disabled) return;
    const line = scene.lines[lineIndex];
    const choices = [...(line.choices || [])];
    choices[choiceIndex] = nextChoice;
    updateLine(lineIndex, { ...line, choices });
  }

  function updateChoiceTarget(lineIndex: number, choiceIndex: number, choice: SceneChoice, target: string) {
    updateChoice(lineIndex, choiceIndex, {
      ...choice,
      target,
      target_scene_file: /\.txt$/i.test(target) ? target : undefined
    });
  }

  if (!scene) {
    return null;
  }

  return (
    <section className={`laper-shell laper-scene-shell ${props.readonly ? "readonly" : ""}`}>
      <aside className="laper-rail" aria-label="场景导航">
        <div className="laper-rail-brand">
          <strong>{props.title}</strong>
          <span>{props.mode === "draft" ? "场景设计稿" : "详细场景"}</span>
        </div>
        <nav className="laper-rail-nav">
          <button className="active" type="button">
            场次
            <em>{props.scenes.length}</em>
          </button>
        </nav>
        <ol className="laper-rail-list">
          {props.scenes.map((item, index) => (
            <li key={`${item.header}-${index}`}>
              <button className={activeIndex === index ? "active" : ""} type="button" onClick={() => props.setActiveScene(index)}>
                <span>{index + 1}</span>
                {item.title}
              </button>
            </li>
          ))}
        </ol>
      </aside>

      <section className="laper-canvas-wrap">
        {props.readonly && props.mode === "complete" && (
          <div className="readonly-banner">素材阶段已开始，场景内容已锁定为只读状态。</div>
        )}

        <div className="laper-toolbar" role="toolbar" aria-label="场景编辑工具栏">
          <button className="laper-tool" type="button" disabled={disabled} onClick={() => addLine("narration")}>
            旁白
          </button>
          <button className="laper-tool" type="button" disabled={disabled} onClick={() => addLine("dialogue")}>
            对话
          </button>
          <span className="laper-toolbar-divider" />
          <button className="laper-tool accent" type="button" disabled={disabled} onClick={() => addLine("narration")}>
            + 添加行
          </button>
          {props.toolbarExtra}
        </div>

        <div className="laper-shortcuts" aria-hidden="true">
          <span>拖动 ⋮⋮ 排序</span>
          <span>点击角色切换旁白/对话</span>
          <span>分支用 △ 标识</span>
        </div>

        <div className="laper-canvas">
          <header className="laper-canvas-head">
            <div className="laper-scene-title-block">
              {props.mode === "complete" && !disabled ? (
                <input
                  className="laper-scene-heading-input"
                  value={scene.title}
                  onChange={(event) => patchScene({ ...scene, title: event.target.value })}
                  aria-label="场景名称"
                />
              ) : (
                <h2>{scene.title}</h2>
              )}
              <p>
                {props.markerLabel(scene)} · {props.routeLabel(scene)}
              </p>
            </div>
            <span>{scene.lines.length} 行</span>
          </header>

          <div className="laper-block-stack laper-line-stack">
            {scene.lines.map((line, lineIndex) => {
              if (line.kind === "choice") {
                return (
                  <article className="laper-block laper-branch-block" key={line.id}>
                    <div className="laper-branch-marker" aria-hidden="true">
                      △
                    </div>
                    <div className="laper-block-content">
                      <div className="laper-block-head">
                        <span>分支选项</span>
                        <em>分支</em>
                        {!disabled && (
                          <button
                            className="laper-block-delete"
                            type="button"
                            onClick={() =>
                              updateLine(lineIndex, {
                                ...line,
                                choices: [
                                  ...(line.choices || []),
                                  {
                                    text: "新的选择",
                                    target: defaultChoiceTarget,
                                    target_scene_file: /\.txt$/i.test(defaultChoiceTarget) ? defaultChoiceTarget : undefined
                                  }
                                ]
                              })
                            }
                          >
                            添加选项
                          </button>
                        )}
                      </div>
                      <div className="laper-choice-list">
                        {(line.choices || []).map((choice, choiceIndex) => (
                          <div className="laper-choice-row" key={`${line.id}-${choiceIndex}`}>
                            <input
                              value={choice.text}
                              onChange={(event) => updateChoice(lineIndex, choiceIndex, { ...choice, text: event.target.value })}
                              aria-label="选项文本"
                              readOnly={disabled}
                            />
                            <select
                              value={choiceTargetValue(choice)}
                              onChange={(event) => updateChoiceTarget(lineIndex, choiceIndex, choice, event.target.value)}
                              aria-label="跳转场景"
                              disabled={disabled}
                            >
                              {!props.targetOptions?.some((option) => option.file === choiceTargetValue(choice)) && (
                                <option value={choiceTargetValue(choice)}>{choiceTargetValue(choice) || "未设置目标"}</option>
                              )}
                              {props.targetOptions?.map((option) => (
                                <option key={option.file} value={option.file}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                            {!disabled && (
                              <button type="button" onClick={() => updateLine(lineIndex, { ...line, choices: (line.choices || []).filter((_, index) => index !== choiceIndex) })}>
                                删除
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </article>
                );
              }

              if (line.kind === "branch") {
                return (
                  <article className="laper-block laper-branch-block" key={line.id}>
                    <div className="laper-branch-marker" aria-hidden="true">
                      △
                    </div>
                    <div className="laper-block-content">
                      <div className="laper-block-head">
                        <span>分支内容</span>
                        <em>分支</em>
                        {!disabled && (
                          <button className="laper-block-delete" type="button" onClick={() => removeLine(lineIndex)}>
                            删除
                          </button>
                        )}
                      </div>
                      <input
                        className="laper-block-title"
                        value={line.branchLabel || line.text}
                        onChange={(event) => updateLine(lineIndex, { ...line, text: event.target.value, branchLabel: event.target.value })}
                        aria-label="分支标识"
                        readOnly={disabled}
                      />
                    </div>
                  </article>
                );
              }

              const menuKey = `${activeIndex}-${lineIndex}`;
              return (
                <article
                  className={`laper-block laper-line-block ${dragIndex === lineIndex ? "dragging" : ""}`}
                  key={line.id}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    const from = Number(event.dataTransfer.getData("text/plain"));
                    setDragIndex(null);
                    if (!Number.isNaN(from)) reorderLines(from, lineIndex);
                  }}
                >
                  <button
                    className="laper-drag-handle"
                    type="button"
                    aria-label="拖动排序"
                    disabled={disabled}
                    draggable={!disabled}
                    onDragStart={(event) => {
                      event.dataTransfer.setData("text/plain", String(lineIndex));
                      event.dataTransfer.effectAllowed = "move";
                      setDragIndex(lineIndex);
                    }}
                    onDragEnd={() => setDragIndex(null)}
                  >
                    ⋮⋮
                  </button>
                  <div className="laper-block-content">
                    <div className="laper-block-head">
                      <div className="laper-speaker-wrap">
                        <button
                          className={`laper-speaker ${line.kind === "command" || disabled ? "static" : ""}`}
                          type="button"
                          disabled={disabled || line.kind === "command"}
                          onClick={() => setSpeakerMenu(speakerMenu === menuKey ? null : menuKey)}
                        >
                          {line.kind === "narration" || line.kind === "command" ? "旁白" : line.speaker}
                        </button>
                        {speakerMenu === menuKey && (
                          <div className="speaker-popover">
                            {speakers.map((speaker) => (
                              <button key={speaker} type="button" onClick={() => switchSpeaker(lineIndex, speaker)}>
                                {speaker}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <em>{lineKindLabel(line)}</em>
                      {!disabled && (
                        <button className="laper-block-delete" type="button" onClick={() => removeLine(lineIndex)}>
                          删除
                        </button>
                      )}
                    </div>
                    <textarea
                      className="laper-block-body"
                      value={line.text}
                      rows={draftLineRows(line.text)}
                      onChange={(event) => updateLine(lineIndex, { ...line, text: event.target.value })}
                      spellCheck={false}
                      readOnly={disabled}
                      aria-label={`${scene.title} ${lineKindLabel(line)}`}
                    />
                  </div>
                </article>
              );
            })}

            {scene.lines.length === 0 && (
              <div className="laper-empty">
                <p>当前场景还没有内容。使用工具栏添加旁白或对话。</p>
              </div>
            )}
          </div>
        </div>
      </section>

      <aside className="laper-inspector outline-side">{props.inspector}</aside>
      {speakerMenu && (
        <button className="speaker-dismiss-layer" type="button" aria-label="关闭角色菜单" onClick={() => setSpeakerMenu(null)} />
      )}
    </section>
  );
}
