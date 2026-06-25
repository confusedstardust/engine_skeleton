"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { withBasePath } from "./base-path";

type Choice = {
  name: string;
  desc: string;
};

type Job = {
  id: string;
  status: string;
};

type GenerationMode = "auto" | "advanced";

const durations: Choice[] = [
  { name: "5分钟", desc: "课前导入" },
  { name: "10分钟", desc: "知识速通" },
  { name: "20分钟", desc: "沉浸游戏" },
  { name: "40分钟", desc: "完整课堂" },
  { name: "自定义", desc: "稍后细化" }
];

const modes: Choice[] = [
  { name: "角色扮演", desc: "人物分析 / 文学历史" },
  { name: "闯关解谜", desc: "知识复习 / 文本细读" },
  { name: "分支选择", desc: "价值冲突 / 道德判断" },
  { name: "探案推理", desc: "文本证据 / 情节分析" },
  { name: "时间旅行", desc: "历史文化 / 古诗文" },
  { name: "课堂辩论", desc: "观点分析 / 文学评价" }
];

const packages = ["学生端游戏", "教师操作说明", "课堂流程", "课堂提问链", "课后巩固题"];
const voicePresets = ["古风男声", "古风女声", "少年声", "旁白声", "沉稳教师声", "多角色配音"];

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(withBasePath(`/api/forge${path}`), {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

function fallbackText(value: string, fallback: string) {
  return value.trim() || fallback;
}

function validDuration(value: string) {
  return /\d/.test(value) ? value : "20分钟";
}

export default function ClassroomGeneratorPage() {
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sourceTab, setSourceTab] = useState<"paste" | "upload" | "library">("paste");
  const [topic, setTopic] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [grade, setGrade] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [teacherGoal, setTeacherGoal] = useState("");
  const [studentGoal, setStudentGoal] = useState("");
  const [duration, setDuration] = useState("20分钟");
  const [mode, setMode] = useState("角色扮演");
  const [generationMode, setGenerationMode] = useState<GenerationMode>("advanced");
  const [characterCount, setCharacterCount] = useState(3);
  const [taskCount, setTaskCount] = useState(6);
  const [voiceOn, setVoiceOn] = useState(false);
  const [voice, setVoice] = useState("");
  const [ttsScope, setTtsScope] = useState<"key_lines" | "all">("key_lines");
  const [checkedPackages, setCheckedPackages] = useState(new Set(packages.slice(0, 3)));
  const [allowMissingAssets, setAllowMissingAssets] = useState(true);
  const [generateAssets, setGenerateAssets] = useState(false);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("");

  const selectedDuration = durations.find((item) => item.name === duration) || durations[2];
  const selectedMode = modes.find((item) => item.name === mode) || modes[0];
  const durationNumber = Number.parseInt(validDuration(duration), 10);

  async function runGeneration() {
    const source = sourceText.trim();
    const title = topic.trim();
    if (!source && !title) {
      setMessage("请至少填写课堂主题或教学文本，然后再点击入境生成。");
      return;
    }

    const sourceMaterial = [
      `课堂主题：${title || "未填写"}`,
      `教学文本 / 知识材料：${source || title}`,
      `适用年级：${grade || "未填写"}`,
      `学习难度：${difficulty || "未填写"}`,
      `教学目标：${teacherGoal || "未填写"}`,
      `学生学习目标：${studentGoal || "未填写"}`,
      `叙事模式：${mode}`
    ].join("\n");

    setRunning(true);
    setMessage("正在创建生成任务...");
    try {
      const created = await api<Job>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          source_material: sourceMaterial,
          options: {
            allow_missing_assets: allowMissingAssets,
            generate_assets: generateAssets,
            generation_mode: generationMode,
            classroom_topic: fallbackText(topic, source.slice(0, 30) || "未命名课堂"),
            grade: fallbackText(grade, "高中语文"),
            difficulty: fallbackText(difficulty, "基础理解"),
            teacher_goal: fallbackText(teacherGoal, "帮助学生理解文本情节、人物关系和核心主题。"),
            student_goal: fallbackText(studentGoal, "学生能够复述关键情节，分析角色动机，并表达自己的理解。"),
            duration: validDuration(duration),
            narrative_mode: fallbackText(mode, "角色扮演"),
            character_count: characterCount,
            interactive_task_count: taskCount,
            voice_enabled: voiceOn,
            generate_tts: voiceOn,
            voice_preset: voiceOn ? voice || voicePresets[0] : "",
            tts_scope: ttsScope,
            tts_max_lines_per_scene: 3,
            tts_max_total_lines: 60,
            output_packages: Array.from(checkedPackages)
          }
        })
      });
      if (generationMode === "auto") {
        setMessage("任务已创建，Auto 模式会自动完成全部生成流程...");
        await api<Job>(`/jobs/${created.id}/run`, {
          method: "POST",
          body: JSON.stringify({ background: true })
        });
      } else {
        setMessage("任务已创建，正在生成故事大纲...");
        await api<Job>(`/jobs/${created.id}/phases/narrative`, {
          method: "POST",
          body: JSON.stringify({ background: true })
        });
      }
      router.push(withBasePath(`/jobs/${created.id}`));
    } catch (error) {
      setRunning(false);
      setMessage(error instanceof Error ? error.message : "请求失败，请检查后端服务。");
    }
  }

  function togglePackage(name: string) {
    setCheckedPackages((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  return (
    <>
      <CloudDecorations />

      <header className="top-nav">
        <div className="brand">
          <div className="brand-seal">文</div>
          <div className="brand-copy">
            <span className="brand-name">文境 · AI叙事课堂生成平台</span>
            <span className="brand-subtitle">WEBGAL FORGE CLASSROOM AI</span>
          </div>
        </div>
        <nav className="nav-links" aria-label="主导航">
          <a href="#library">我的游戏库</a>
          <a href="#templates">资源模板</a>
          <a href="#history">生成记录</a>
          <a className="nav-login" href="#login">账号登录</a>
        </nav>
        <button className={`hamburger ${mobileOpen ? "open" : ""}`} type="button" onClick={() => setMobileOpen((open) => !open)} aria-label="展开菜单">
          <span />
          <span />
          <span />
        </button>
      </header>

      {mobileOpen && (
        <nav className="mobile-menu" aria-label="移动端导航">
          <a href="#library">我的游戏库</a>
          <a href="#templates">资源模板</a>
          <a href="#history">生成记录</a>
          <a className="mobile-login" href="#login">账号登录</a>
        </nav>
      )}

      <main className="main-wrapper">
        <section className="page-header" aria-labelledby="page-title">
          <h1 id="page-title">创建一场新的课堂叙事游戏</h1>
          <p>先输入主题或文本即可开始生成。大纲生成后会进入工作台，供你删改阶段、角色和场景内容。</p>
          <div className="header-line">
            <span>叙事课堂工坊</span>
          </div>
        </section>

        <div className="content-grid">
          <section className="form-panel" aria-label="课堂生成表单">
            <FormSection title="核心教学信息">
              <Field label="课堂主题">
                <input value={topic} onChange={(event) => setTopic(event.target.value)} placeholder="例如：《垓下歌》中的英雄悲剧 / 《关雎》中的爱情与礼教" />
              </Field>

              <Field label="教学文本 / 知识材料">
                <div className="tab-group">
                  <button className={sourceTab === "paste" ? "active" : ""} type="button" onClick={() => setSourceTab("paste")}>直接粘贴文本</button>
                  <button className={sourceTab === "upload" ? "active" : ""} type="button" onClick={() => setSourceTab("upload")}>上传文档</button>
                  <button className={sourceTab === "library" ? "active" : ""} type="button" onClick={() => setSourceTab("library")}>从资源库选择</button>
                </div>
                {sourceTab === "paste" && (
                  <textarea value={sourceText} onChange={(event) => setSourceText(event.target.value)} placeholder={"请粘贴原文、节选、知识点或直接写一句需求。\n\n例如：给我生成一个《归去来兮辞》相关的沉浸式课堂游戏。"} />
                )}
                {sourceTab === "upload" && <div className="upload-area"><span>文</span>文档上传将在下一步接入，当前可先粘贴文本。</div>}
                {sourceTab === "library" && <div className="resource-area"><span>书</span>资源库即将上线，敬请期待。</div>}
              </Field>

              <div className="field-row">
                <Field label="适用年级 / 课程体系" compact>
                  <select value={grade} onChange={(event) => setGrade(event.target.value)}>
                    <option value="">不确定，使用默认</option>
                    <option>小学高年级语文</option>
                    <option>初中语文</option>
                    <option>初中历史</option>
                    <option>高中语文</option>
                    <option>高中历史</option>
                    <option>DSE 中国文学</option>
                    <option>IB 中文</option>
                    <option>成人 / 企业培训</option>
                  </select>
                </Field>
                <Field label="学习难度" compact>
                  <select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
                    <option value="">不确定，使用默认</option>
                    <option>基础理解</option>
                    <option>进阶分析</option>
                    <option>高阶探究</option>
                    <option>考试冲刺</option>
                    <option>公开课展示</option>
                  </select>
                </Field>
              </div>
            </FormSection>

            <FormSection title="教学目标设定">
              <Field label="教学目标" hint="可选，不填会使用通用目标">
                <textarea rows={3} value={teacherGoal} onChange={(event) => setTeacherGoal(event.target.value)} placeholder="例如：理解诗歌中的战争创伤，分析人物形象，体会叙事视角的情感张力。" />
              </Field>
              <Field label="学生学习目标" hint="可选，不填会使用通用目标">
                <textarea rows={3} value={studentGoal} onChange={(event) => setStudentGoal(event.target.value)} placeholder="例如：学生能够说出人物的核心处境，找出文本证据，并解释作品如何表现时代悲剧。" />
              </Field>
            </FormSection>

            <FormSection title="游戏设计配置">
              <GenerationModeRadio value={generationMode} onChange={setGenerationMode} />
              <ChoiceGrid label="游戏时长与课堂场景" items={durations} value={duration} onChange={setDuration} columns="five" />
              <ChoiceGrid label="叙事模式" items={modes} value={mode} onChange={setMode} columns="three" />

              <div className="number-grid">
                <NumberControl label="AI角色数" value={characterCount} min={1} max={8} onChange={setCharacterCount} />
                <NumberControl label="互动任务数" value={taskCount} min={1} max={12} onChange={setTaskCount} />
              </div>

              <Field label="角色配音">
                <div className="toggle-row">
                  <div>
                    <strong>开启配音</strong>
                    <span>为游戏角色添加 AI 语音，增强沉浸感</span>
                  </div>
                  <label className="toggle-switch">
                    <input type="checkbox" checked={voiceOn} onChange={(event) => setVoiceOn(event.target.checked)} />
                    <span />
                  </label>
                </div>
                {voiceOn && (
                  <>
                    <div className="voice-options">
                      {voicePresets.map((item) => (
                        <button className={voice === item ? "selected" : ""} key={item} type="button" onClick={() => setVoice(item)}>{item}</button>
                      ))}
                    </div>
                    <div className="voice-options">
                      <button className={ttsScope === "key_lines" ? "selected" : ""} type="button" onClick={() => setTtsScope("key_lines")}>关键句配音</button>
                      <button className={ttsScope === "all" ? "selected" : ""} type="button" onClick={() => setTtsScope("all")}>全部台词</button>
                    </div>
                  </>
                )}
              </Field>

              <div className="backend-options">
                <label><input type="checkbox" checked={allowMissingAssets} onChange={(event) => setAllowMissingAssets(event.target.checked)} /> 允许先缺图生成</label>
                <label><input type="checkbox" checked={generateAssets} onChange={(event) => setGenerateAssets(event.target.checked)} /> 生成图片素材</label>
              </div>
            </FormSection>

            <FormSection title="生成内容包" hint="选择需要生成的课堂配套内容">
              <div className="checkbox-group">
                {packages.map((item) => (
                  <button className={`check-item ${checkedPackages.has(item) ? "checked" : ""}`} key={item} type="button" onClick={() => togglePackage(item)}>
                    <span className="check-box" />
                    <span>{item}</span>
                  </button>
                ))}
              </div>
            </FormSection>

            <div className="form-actions">
              <button className="btn ghost" type="button">保存草稿</button>
              <button className="btn outline" type="button">预览方案</button>
              <span />
              <button className="btn primary" disabled={running} type="button" onClick={runGeneration}>
                {running ? "正在创建..." : "入境生成"}
              </button>
            </div>
          </section>

          <aside className="preview-panel" aria-label="生成预览">
            <div className="preview-card">
              <div className="preview-header">
                <span>即将生成 · PREVIEW</span>
                <h2>{selectedDuration.name}沉浸式文学游戏</h2>
                <p>{selectedDuration.desc} · AI叙事生成</p>
              </div>
              <div className="preview-body">
                <PreviewRow k="主题" v={topic || "未填写"} />
                <PreviewRow k="适用" v={grade || "默认：高中语文"} />
                <PreviewRow k="叙事模式" v={<span className="preview-tag">{selectedMode.name}</span>} />
                <div className="preview-divider" />
                <PreviewRow k="生成模式" v={<span className="preview-tag">{generationMode === "auto" ? "Auto 一键生成" : "Advance 节点审阅"}</span>} />
                <PreviewRow k="内容预计" v={<span className="muted">{characterCount}个角色<br />{taskCount}道互动任务<br />{generationMode === "auto" ? "自动生成完整游戏" : "生成后进入节点工作台"}</span>} />
                <PreviewRow k="角色配音" v={<span><i className={`status-dot ${voiceOn ? "on" : "off"}`} />{voiceOn ? `已开启 · ${voice || voicePresets[0]}` : "未开启"}</span>} />
                <PreviewRow k="难度" v={difficulty || "默认：基础理解"} />
              </div>
              <div className="preview-stats">
                <Stat value={Number.isNaN(durationNumber) ? 20 : durationNumber} label="时长（分钟）" />
                <Stat value={characterCount} label="AI角色数" />
                <Stat value={taskCount} label="互动任务" />
              </div>
              <div className="scroll-deco">文境 · 叙事课堂</div>
            </div>

            <div className="runtime-card">
              <div className="runtime-head">
                <strong>生成状态</strong>
              </div>
              <p>{message || "填写主题或材料后即可生成。生成成功会自动进入任务工作台。"}</p>
            </div>
          </aside>
        </div>
      </main>
    </>
  );
}

function FormSection({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="form-section">
      <h2>{title}</h2>
      {hint && <p className="section-hint">{hint}</p>}
      {children}
    </section>
  );
}

function GenerationModeRadio({ value, onChange }: { value: GenerationMode; onChange: (value: GenerationMode) => void }) {
  const items: Array<{ value: GenerationMode; title: string; desc: string; meta: string }> = [
    {
      value: "auto",
      title: "Auto 模式",
      desc: "一键跑完整生成流程，中途不进入人工审阅，适合快速拿到可玩的初版。",
      meta: "全自动"
    },
    {
      value: "advanced",
      title: "Advance 模式",
      desc: "按大纲、场景、素材逐步确认，允许修改节点内容并单独重生成。",
      meta: "可编辑"
    }
  ];
  return (
    <div className="mode-radio" role="radiogroup" aria-label="生成工作台模式">
      {items.map((item) => (
        <button
          className={value === item.value ? "selected" : ""}
          key={item.value}
          type="button"
          role="radio"
          aria-checked={value === item.value}
          onClick={() => onChange(item.value)}
        >
          <span className="mode-radio-dot" aria-hidden="true" />
          <span>
            <strong>{item.title}</strong>
            <small>{item.desc}</small>
          </span>
          <em>{item.meta}</em>
        </button>
      ))}
    </div>
  );
}

function Field({ label, hint, required, compact, children }: { label: string; hint?: string; required?: boolean; compact?: boolean; children: React.ReactNode }) {
  return (
    <label className={`field-group ${compact ? "compact" : ""}`}>
      <span className="field-label">{label}{required && <em>*</em>}</span>
      {hint && <span className="field-hint">{hint}</span>}
      {children}
    </label>
  );
}

function ChoiceGrid({ label, items, value, onChange, columns }: { label: string; items: Choice[]; value: string; onChange: (value: string) => void; columns: "three" | "five" }) {
  return (
    <div className="field-group">
      <span className="field-label">{label}</span>
      <div className={`card-grid ${columns}`}>
        {items.map((item) => (
          <button className={`select-card ${value === item.name ? "selected" : ""}`} key={item.name} type="button" onClick={() => onChange(item.name)}>
            <strong>{item.name}</strong>
            <small>{item.desc}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

function NumberControl({ label, value, min, max, onChange }: { label: string; value: number; min: number; max: number; onChange: (value: number) => void }) {
  function setSafe(next: number) {
    onChange(Math.max(min, Math.min(max, next)));
  }

  return (
    <div className="number-control">
      <span>{label}</span>
      <div>
        <button type="button" onClick={() => setSafe(value - 1)} aria-label={`${label}减少`}>-</button>
        <strong>{value}</strong>
        <button type="button" onClick={() => setSafe(value + 1)} aria-label={`${label}增加`}>+</button>
      </div>
    </div>
  );
}

function PreviewRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="preview-row">
      <span>{k}</span>
      <strong>{v}</strong>
    </div>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function CloudDecorations() {
  return (
    <>
      <svg className="cloud-deco cloud-one" viewBox="0 0 200 80" fill="none" aria-hidden="true">
        <path d="M20 60Q10 60 10 50Q10 38 22 38Q22 20 38 20Q46 20 50 28Q56 22 66 22Q82 22 84 36Q92 36 96 44Q96 60 80 60Z" />
        <path d="M100 50Q92 50 92 42Q92 34 102 34Q106 24 118 26Q124 20 134 22Q144 24 144 34Q150 36 152 42Q152 50 140 50Z" />
      </svg>
      <svg className="cloud-deco cloud-two" viewBox="0 0 160 60" fill="none" aria-hidden="true">
        <path d="M16 48Q8 48 8 40Q8 30 18 30Q18 16 32 16Q38 16 42 22Q46 18 54 18Q66 18 68 28Q74 28 78 36Q78 48 64 48Z" />
      </svg>
    </>
  );
}
