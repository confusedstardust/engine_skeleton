const baseTheme = {
  name: "base",
  textbox: {
    left: 9,
    right: 9,
    bottom: 6,
    height: 25,
    paddingTop: 8,
    paddingX: 5,
    paddingBottom: 4,
    backgroundColor: "rgba(10, 15, 17, 0.56)",
    borderColor: "rgba(239, 247, 250, 0.9)",
    borderWidth: 2.2,
    radius: 34,
    blur: 2,
    noiseOpacity: 0.28
  },
  nameBox: {
    left: 4.5,
    top: 2.4,
    width: 172,
    height: 54,
    backgroundColor: "rgba(18, 24, 27, 0.56)",
    borderColor: "rgba(239, 247, 250, 0.9)",
    borderWidth: 2,
    radius: 10,
    textColor: "#dcfcff",
    fontSize: 30,
    letterSpacing: 0.08
  },
  text: {
    color: "#ffffff",
    fontSize: 34,
    lineHeight: 1.85,
    letterSpacing: 0.04,
    weight: 600,
    shadowStrength: 0.25
  }
};

const noirDraft = structuredClone(baseTheme);
noirDraft.name = "noir";
noirDraft.textbox.backgroundColor = "rgba(12, 18, 20, 0.52)";
noirDraft.textbox.height = 27;
noirDraft.textbox.bottom = 6.4;
noirDraft.textbox.radius = 36;
noirDraft.nameBox.backgroundColor = "rgba(18, 24, 27, 0.5)";

const controls = [
  ["textbox.left", "Textbox left", "range", 3, 18, 0.5, "%"],
  ["textbox.right", "Textbox right", "range", 3, 18, 0.5, "%"],
  ["textbox.bottom", "Textbox bottom", "range", 1, 12, 0.2, "%"],
  ["textbox.height", "Textbox height", "range", 16, 36, 0.5, "%"],
  ["textbox.paddingTop", "Text padding top", "range", 3, 14, 0.2, "%"],
  ["textbox.paddingX", "Text padding X", "range", 2, 10, 0.2, "%"],
  ["textbox.paddingBottom", "Text padding bottom", "range", 1, 8, 0.2, "%"],
  ["textbox.backgroundColor", "Textbox background", "text"],
  ["textbox.borderColor", "Textbox border", "text"],
  ["textbox.borderWidth", "Textbox border width", "range", 0, 8, 0.1, "px"],
  ["textbox.radius", "Textbox radius", "range", 0, 70, 1, "px"],
  ["textbox.blur", "Backdrop blur", "range", 0, 12, 0.5, "px"],
  ["textbox.noiseOpacity", "Noise opacity", "range", 0, 0.8, 0.01, ""],
  ["nameBox.left", "Name left", "range", 0, 12, 0.2, "%"],
  ["nameBox.top", "Name top", "range", 0, 8, 0.2, "%"],
  ["nameBox.width", "Name width", "range", 80, 320, 2, "px"],
  ["nameBox.height", "Name height", "range", 32, 90, 1, "px"],
  ["nameBox.backgroundColor", "Name background", "text"],
  ["nameBox.borderColor", "Name border", "text"],
  ["nameBox.borderWidth", "Name border width", "range", 0, 8, 0.1, "px"],
  ["nameBox.radius", "Name radius", "range", 0, 36, 1, "px"],
  ["nameBox.textColor", "Name text color", "text"],
  ["nameBox.fontSize", "Name font size", "range", 16, 48, 1, "px"],
  ["nameBox.letterSpacing", "Name letter spacing", "range", 0, 0.4, 0.01, "em"],
  ["text.color", "Text color", "text"],
  ["text.fontSize", "Text font size", "range", 18, 54, 1, "px"],
  ["text.lineHeight", "Text line height", "range", 1, 2.6, 0.05, ""],
  ["text.letterSpacing", "Text letter spacing", "range", 0, 0.3, 0.01, "em"],
  ["text.weight", "Text weight", "range", 300, 900, 50, ""],
  ["text.shadowStrength", "Text glow strength", "range", 0, 0.8, 0.01, ""]
];

let theme = loadInitialTheme();

const stage = document.getElementById("stage");
const textbox = document.getElementById("textbox");
const nameBox = document.getElementById("nameBox");
const dialogText = document.getElementById("dialogText");
const controlsEl = document.getElementById("controls");
const jsonOutput = document.getElementById("jsonOutput");
const scssOutput = document.getElementById("scssOutput");

function loadInitialTheme() {
  const saved = localStorage.getItem("webgal-ui-theme-simulator");
  if (!saved) return structuredClone(noirDraft);
  try {
    return JSON.parse(saved);
  } catch {
    return structuredClone(noirDraft);
  }
}

function getValue(path) {
  return path.split(".").reduce((value, key) => value[key], theme);
}

function setValue(path, value) {
  const parts = path.split(".");
  const last = parts.pop();
  const target = parts.reduce((current, key) => current[key], theme);
  target[last] = value;
}

function renderControls() {
  controlsEl.innerHTML = "";
  controls.forEach(([path, label, type, min, max, step, unit]) => {
    const card = document.createElement("div");
    card.className = "control-card";

    const labelEl = document.createElement("label");
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("span");
    value.textContent = `${getValue(path)}${unit ?? ""}`;
    labelEl.append(name, value);

    const row = document.createElement("div");
    row.className = "control-row";

    const input = document.createElement("input");
    input.type = type === "range" ? "range" : "text";
    input.value = getValue(path);
    if (type === "range") {
      input.min = min;
      input.max = max;
      input.step = step;
    }

    const numberInput = document.createElement("input");
    numberInput.type = type === "range" ? "number" : "text";
    numberInput.value = getValue(path);
    if (type === "range") {
      numberInput.min = min;
      numberInput.max = max;
      numberInput.step = step;
    }

    const update = (rawValue) => {
      const next = type === "range" ? Number(rawValue) : rawValue;
      setValue(path, next);
      value.textContent = `${next}${unit ?? ""}`;
      input.value = next;
      numberInput.value = next;
      applyTheme();
    };

    input.addEventListener("input", () => update(input.value));
    numberInput.addEventListener("input", () => update(numberInput.value));

    row.append(input, numberInput);
    card.append(labelEl, row);
    controlsEl.append(card);
  });
}

function applyTheme() {
  const t = theme.textbox;
  const n = theme.nameBox;
  const text = theme.text;

  textbox.style.left = `${t.left}%`;
  textbox.style.right = `${t.right}%`;
  textbox.style.bottom = `${t.bottom}%`;
  textbox.style.minHeight = `${t.height}%`;
  textbox.style.padding = `${t.paddingTop}% ${t.paddingX}% ${t.paddingBottom}%`;
  textbox.style.background = t.backgroundColor;
  textbox.style.border = `${t.borderWidth}px solid ${t.borderColor}`;
  textbox.style.borderRadius = `${t.radius}px`;
  textbox.style.backdropFilter = `blur(${t.blur}px) saturate(0.85)`;
  textbox.style.setProperty("--noise-opacity", t.noiseOpacity);

  nameBox.style.left = `${n.left}%`;
  nameBox.style.top = `${n.top}%`;
  nameBox.style.width = `${n.width}px`;
  nameBox.style.height = `${n.height}px`;
  nameBox.style.background = n.backgroundColor;
  nameBox.style.border = `${n.borderWidth}px solid ${n.borderColor}`;
  nameBox.style.borderRadius = `${n.radius}px`;
  nameBox.style.color = n.textColor;
  nameBox.style.fontSize = `${n.fontSize}px`;
  nameBox.style.letterSpacing = `${n.letterSpacing}em`;
  nameBox.style.textShadow = `0 0 8px ${n.textColor}`;

  dialogText.style.color = text.color;
  dialogText.style.fontSize = `${text.fontSize}px`;
  dialogText.style.lineHeight = text.lineHeight;
  dialogText.style.letterSpacing = `${text.letterSpacing}em`;
  dialogText.style.fontWeight = text.weight;
  dialogText.style.textShadow =
    `0 0 8px rgba(255,255,255,${text.shadowStrength}), 0 2px 8px rgba(0,0,0,0.65)`;

  localStorage.setItem("webgal-ui-theme-simulator", JSON.stringify(theme));
  jsonOutput.value = JSON.stringify(theme, null, 2);
  scssOutput.value = toScss(theme);
}

function toScss(current) {
  const t = current.textbox;
  const n = current.nameBox;
  const text = current.text;
  return `/* Generated by tools/ui_theme_simulator */

.TextBox_main {
  left: ${t.left}%;
  right: ${t.right}%;
  bottom: ${t.bottom}%;
  min-height: ${t.height}%;
  max-height: ${t.height}%;
  padding: ${t.paddingTop}% ${t.paddingX}% ${t.paddingBottom}%;
  background: transparent;
  border: 0;
  border-radius: ${t.radius}px;
  letter-spacing: ${text.letterSpacing}em;
  font-weight: ${text.weight};
}

.TextBox_Background {
  border: ${t.borderWidth}px solid ${t.borderColor};
  border-radius: ${t.radius}px;
  background: ${t.backgroundColor};
  backdrop-filter: blur(${t.blur}px) saturate(0.85);
}

.TextBox_Background::before {
  content: '';
  pointer-events: none;
  position: absolute;
  inset: 0;
  border-radius: inherit;
  opacity: ${t.noiseOpacity};
}

.TextBox_showName {
  left: ${n.left}%;
  top: ${n.top}%;
  width: ${n.width}px;
  height: ${n.height}px;
  line-height: ${Math.max(0, n.height - 6)}px;
  border: ${n.borderWidth}px solid ${n.borderColor};
  border-radius: ${n.radius}px;
  color: ${n.textColor};
  font-size: ${n.fontSize}px;
  letter-spacing: ${n.letterSpacing}em;
}

.TextBox_ShowName_Background {
  background: ${n.backgroundColor};
  border-color: ${n.borderColor};
}

.text {
  color: ${text.color};
  font-size: ${text.fontSize}px;
  line-height: ${text.lineHeight};
  text-shadow: 0 0 8px rgba(255, 255, 255, ${text.shadowStrength});
}
`;
}

function downloadJson() {
  const blob = new Blob([JSON.stringify(theme, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${theme.name || "theme"}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function copyText(textarea) {
  textarea.select();
  document.execCommand("copy");
}

document.getElementById("loadBaseButton").addEventListener("click", () => {
  theme = structuredClone(baseTheme);
  renderControls();
  applyTheme();
});

document.getElementById("loadNoirButton").addEventListener("click", () => {
  theme = structuredClone(noirDraft);
  renderControls();
  applyTheme();
});

document.getElementById("resetButton").addEventListener("click", () => {
  localStorage.removeItem("webgal-ui-theme-simulator");
  theme = structuredClone(noirDraft);
  renderControls();
  applyTheme();
});

document.getElementById("downloadButton").addEventListener("click", downloadJson);
document.getElementById("copyJsonButton").addEventListener("click", () => copyText(jsonOutput));
document.getElementById("copyScssButton").addEventListener("click", () => copyText(scssOutput));

renderControls();
applyTheme();
