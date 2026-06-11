const zh = {
  newTask: "\u65b0\u5efa\u751f\u6210\u4efb\u52a1",
  taskHistory: "\u4efb\u52a1\u5386\u53f2",
  title: "WebGAL \u751f\u6210\u5de5\u4f5c\u53f0",
  intro:
    "Write source material, characters, routes, endings, and visual style. Backend stages: narrative, game_design, asset_manifest, asset_generation, script_rewrite, scenes, validation.",
  allowMissingAssets: "\u5141\u8bb8\u5148\u7f3a\u56fe",
  generateAssets: "\u751f\u6210\u56fe\u7247",
  run: "\u5f00\u59cb\u751f\u6210",
  jobStatus: "\u4efb\u52a1\u72b6\u6001",
  refresh: "\u5237\u65b0",
  copy: "\u590d\u5236",
  promptPlaceholder:
    "\u5199\u5165\u4f60\u7684\u6545\u4e8b\u3001\u63d0\u793a\u8bcd\u3001\u89d2\u8272\u3001\u5206\u652f\u8981\u6c42\u3001\u7ed3\u5c40\u7c7b\u578b\u3001\u753b\u98ce\u504f\u597d\u2026\u2026",
  emptyJobs: "\u6682\u65e0\u4efb\u52a1",
  emptyArtifacts: "\u6682\u65e0\u6587\u4ef6",
  selectArtifact: "\u9009\u62e9\u4e00\u4e2a artifact \u67e5\u770b\u5185\u5bb9\u3002",
  writeSomething: "\u5148\u5199\u4e00\u70b9\u6545\u4e8b\u6216\u63d0\u793a\u8bcd\u3002",
  created: "\u4efb\u52a1\u5df2\u521b\u5efa",
  handedOff: "\u5df2\u4ea4\u7ed9\u540e\u7aef function-call pipeline \u8fd0\u884c\u3002",
  done: "\u751f\u6210\u5b8c\u6210\u3002\u53f3\u4fa7 Artifacts \u53ef\u4ee5\u67e5\u770b narrative_plan\u3001scene \u6587\u4ef6\u548c validation report\u3002",
  failed: "\u4efb\u52a1\u5931\u8d25",
  requestFailed: "\u8bf7\u6c42\u5931\u8d25",
  pollingFailed: "\u8f6e\u8be2\u5931\u8d25",
  copied: "\u5df2\u590d\u5236 preview \u5185\u5bb9",
};

const phaseList = [
  ["NARRATIVE_PLANNING", "Narrative", "\u7ed3\u6784\u5316\u5267\u60c5\u8ba1\u5212"],
  ["STORY_DESIGN", "Story", "\u6545\u4e8b\u8bbe\u8ba1"],
  ["GAME_DESIGN", "Game Design", "\u4e92\u52a8\u573a\u666f\u8bbe\u8ba1"],
  ["ASSET_PLANNING", "Assets", "\u7d20\u6750 manifest"],
  ["SCRIPT_REWRITE", "Rewrite", "\u63d2\u5165\u89c6\u89c9\u7d20\u6750"],
  ["SOUND_EFFECT_PLANNING", "Sound", "\u97f3\u6548\u7f16\u6392"],
  ["ASSET_GENERATION", "Generate", "\u7d20\u6750\u751f\u6210"],
  ["SCENE_WRITING", "Scenes", "WebGAL \u573a\u666f\u811a\u672c"],
  ["VALIDATING", "Validation", "\u786e\u5b9a\u6027\u6821\u9a8c"],
  ["REPAIRING", "Repair", "\u81ea\u52a8\u4fee\u590d\u5faa\u73af"],
];

const state = {
  jobs: [],
  currentJob: null,
  currentJobId: null,
  artifacts: [],
  selectedArtifact: "",
  polling: null,
  running: false,
};

const el = {
  jobList: document.querySelector("#jobList"),
  messageList: document.querySelector("#messageList"),
  promptInput: document.querySelector("#promptInput"),
  allowMissingAssets: document.querySelector("#allowMissingAssets"),
  generateAssets: document.querySelector("#generateAssets"),
  runButton: document.querySelector("#runButton"),
  newTaskButton: document.querySelector("#newTaskButton"),
  refreshButton: document.querySelector("#refreshButton"),
  refreshCurrentButton: document.querySelector("#refreshCurrentButton"),
  refreshArtifactsButton: document.querySelector("#refreshArtifactsButton"),
  copyPreviewButton: document.querySelector("#copyPreviewButton"),
  statusTag: document.querySelector("#statusTag"),
  jobId: document.querySelector("#jobId"),
  jobStatus: document.querySelector("#jobStatus"),
  jobPhase: document.querySelector("#jobPhase"),
  jobUpdated: document.querySelector("#jobUpdated"),
  phaseSteps: document.querySelector("#phaseSteps"),
  artifactList: document.querySelector("#artifactList"),
  artifactPreview: document.querySelector("#artifactPreview"),
};

function localize() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    if (zh[key]) node.textContent = zh[key];
  });
  el.promptInput.placeholder = zh.promptPlaceholder;
  el.artifactPreview.textContent = zh.selectArtifact;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function compactId(id) {
  if (!id) return "-";
  return `${id.slice(0, 8)}...${id.slice(-4)}`;
}

function summarize(text) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean ? clean.slice(0, 48) : "\u672a\u547d\u540d\u4efb\u52a1";
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function statusClass(status) {
  if (status === "DONE" || status === "VALIDATION_PASSED") return "success";
  if (status === "FAILED" || status === "VALIDATION_FAILED") return "danger";
  if (status === "RUNNING" || status === "QUEUED") return "warning";
  return "default";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function notify(text, type = "info") {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = text;
  document.body.appendChild(node);
  window.setTimeout(() => node.remove(), 2600);
}

function addMessage(role, text) {
  const article = document.createElement("article");
  article.className = `message ${role}`;
  article.innerHTML = `
    <div class="avatar">${role === "user" ? "U" : "F"}</div>
    <div class="message-card">
      <div class="message-name">${role === "user" ? "You" : "WebGAL Forge"}</div>
      <p>${escapeHtml(text)}</p>
    </div>
  `;
  el.messageList.appendChild(article);
  el.messageList.scrollTop = el.messageList.scrollHeight;
}

function renderJobs() {
  if (!state.jobs.length) {
    el.jobList.innerHTML = `<div class="empty-box">${zh.emptyJobs}</div>`;
    return;
  }
  el.jobList.innerHTML = state.jobs
    .map((job) => {
      const active = job.id === state.currentJobId ? " active" : "";
      const tag = statusClass(job.status);
      return `
        <button class="job-card${active}" type="button" data-job-id="${escapeHtml(job.id)}">
          <span class="job-title">${escapeHtml(summarize(job.source_material))}</span>
          <span class="job-meta">
            <span class="mini-tag ${tag}">${escapeHtml(job.status || "-")}</span>
            <span>${escapeHtml(compactId(job.id))}</span>
          </span>
        </button>
      `;
    })
    .join("");
}

function renderJobDetails() {
  const job = state.currentJob;
  const status = job?.status || "Idle";
  el.statusTag.textContent = status;
  el.statusTag.className = `ant-tag status-tag ${statusClass(status)}`;
  el.jobId.textContent = job ? compactId(job.id) : "-";
  el.jobId.title = job?.id || "";
  el.jobStatus.textContent = job?.status || "-";
  el.jobPhase.textContent = job?.phase || "-";
  el.jobUpdated.textContent = formatTime(job?.updated_at);
  renderSteps(job);
  renderPlayButton(job);
}

function renderPlayButton(job) {
  const playCard = document.querySelector("#playCard");
  const playButton = document.querySelector("#playButton");
  if (job && job.status === "DONE") {
    playCard.style.display = "block";
    playButton.href = `/play/${job.id}/`;
  } else {
    playCard.style.display = "none";
  }
}

function renderSteps(job) {
  const activeIndex = phaseList.findIndex(([phase]) => phase === job?.phase);
  const done = job?.status === "DONE";
  el.phaseSteps.innerHTML = phaseList
    .map(([, title, desc], index) => {
      const stepClass = done || index < activeIndex ? "done" : index === activeIndex ? "active" : "";
      return `
        <div class="step ${stepClass}">
          <span class="step-dot"></span>
          <span class="step-copy">
            <strong>${title}</strong>
            <em>${desc}</em>
          </span>
        </div>
      `;
    })
    .join("");
}

function renderArtifacts() {
  if (!state.artifacts.length) {
    el.artifactList.innerHTML = `<div class="empty-box light">${zh.emptyArtifacts}</div>`;
    return;
  }
  el.artifactList.innerHTML = state.artifacts
    .map((artifact) => {
      const selected = artifact === state.selectedArtifact ? " selected" : "";
      return `<button class="artifact-button${selected}" type="button" data-artifact="${escapeHtml(artifact)}">${escapeHtml(artifact)}</button>`;
    })
    .join("");
}

async function loadJobs() {
  const data = await api("/jobs");
  state.jobs = data.jobs || [];
  renderJobs();
}

async function selectJob(jobId) {
  const job = await api(`/jobs/${jobId}`);
  state.currentJob = job;
  state.currentJobId = job.id;
  renderJobDetails();
  await loadJobs();
  await loadArtifacts();
}

async function loadArtifacts() {
  state.artifacts = [];
  if (!state.currentJobId) {
    renderArtifacts();
    return;
  }
  const data = await api(`/jobs/${state.currentJobId}/artifacts`);
  state.artifacts = data.artifacts || [];
  renderArtifacts();
}

async function previewArtifact(path) {
  if (!state.currentJobId) return;
  state.selectedArtifact = path;
  renderArtifacts();
  const response = await fetch(`/jobs/${state.currentJobId}/artifacts/${path}`);
  el.artifactPreview.textContent = await response.text();
}

function setRunning(isRunning) {
  state.running = isRunning;
  el.runButton.disabled = isRunning;
  el.runButton.classList.toggle("loading", isRunning);
  el.runButton.querySelector("[data-i18n='run']").textContent = isRunning
    ? "\u8fd0\u884c\u4e2d"
    : zh.run;
}

async function runPrompt() {
  const source = el.promptInput.value.trim();
  if (!source) {
    notify(zh.writeSomething, "warning");
    el.promptInput.focus();
    return;
  }

  setRunning(true);
  addMessage("user", source);

  try {
    const job = await api("/jobs", {
      method: "POST",
      body: JSON.stringify({
        source_material: source,
        options: {
          allow_missing_assets: el.allowMissingAssets.checked,
          generate_assets: el.generateAssets.checked,
        },
      }),
    });

    state.currentJob = job;
    state.currentJobId = job.id;
    renderJobDetails();
    await loadJobs();
    addMessage("assistant", `${zh.created}: ${compactId(job.id)}。${zh.handedOff}`);

    await api(`/jobs/${job.id}/run`, {
      method: "POST",
      body: JSON.stringify({ background: true }),
    });

    el.promptInput.value = "";
    startPolling(job.id);
  } catch (error) {
    addMessage("assistant", `${zh.requestFailed}: ${error.message}`);
    notify(zh.requestFailed, "danger");
  } finally {
    setRunning(false);
  }
}

function startPolling(jobId) {
  if (state.polling) clearInterval(state.polling);
  state.polling = setInterval(async () => {
    try {
      const job = await api(`/jobs/${jobId}`);
      state.currentJob = job;
      state.currentJobId = job.id;
      renderJobDetails();
      await loadJobs();

      if (["DONE", "FAILED"].includes(job.status)) {
        clearInterval(state.polling);
        state.polling = null;
        await loadArtifacts();
        addMessage("assistant", job.status === "DONE" ? zh.done : `${zh.failed}: ${job.error || "-"}`);
      }
    } catch (error) {
      clearInterval(state.polling);
      state.polling = null;
      addMessage("assistant", `${zh.pollingFailed}: ${error.message}`);
    }
  }, 1800);
}

function resetComposer() {
  state.currentJob = null;
  state.currentJobId = null;
  state.artifacts = [];
  state.selectedArtifact = "";
  el.promptInput.value = "";
  el.artifactPreview.textContent = zh.selectArtifact;
  renderJobDetails();
  renderArtifacts();
}

function bindEvents() {
  el.newTaskButton.addEventListener("click", resetComposer);
  el.runButton.addEventListener("click", runPrompt);
  el.refreshButton.addEventListener("click", refreshAll);
  el.refreshCurrentButton.addEventListener("click", refreshCurrent);
  el.refreshArtifactsButton.addEventListener("click", loadArtifacts);
  el.copyPreviewButton.addEventListener("click", async () => {
    await navigator.clipboard.writeText(el.artifactPreview.textContent);
    notify(zh.copied, "success");
  });
  el.promptInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      runPrompt();
    }
  });
  el.jobList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-job-id]");
    if (button) selectJob(button.dataset.jobId);
  });
  el.artifactList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-artifact]");
    if (button) previewArtifact(button.dataset.artifact);
  });
}

async function refreshCurrent() {
  if (state.currentJobId) await selectJob(state.currentJobId);
}

async function refreshAll() {
  await loadJobs();
  if (state.currentJobId) await selectJob(state.currentJobId);
}

async function init() {
  localize();
  bindEvents();
  renderJobDetails();
  renderSteps(null);
  renderArtifacts();
  try {
    await loadJobs();
  } catch (error) {
    addMessage("assistant", `${zh.requestFailed}: ${error.message}`);
  }
}

init();
