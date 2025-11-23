const textarea = document.getElementById("json-input");
const previewTree = document.getElementById("preview-tree");
const formatBtn = document.getElementById("format-btn");
const clearBtn = document.getElementById("clear-btn");
const sampleBtn = document.getElementById("sample-btn");
const errorMessage = document.getElementById("error-message");
const modal = document.getElementById("modal");
const modalClose = modal.querySelector(".fd-modal__close");
const modalContent = document.getElementById("modal-content");
const nodeTemplate = document.getElementById("json-node-template");

const STRING_CUTOFF = 120;
const AUTO_PREVIEW_DELAY_MS = 350;
const SAMPLE_JSON = {
  name: "尝试修正",
  version: "0.1.0",
  description: "A personal portal with scheduled link checks and handy utilities.",
  features: ["Static homepage", "FastAPI backend", "SQLite data store", "Scheduler"],
  maintainer: {
    handle: "L1nwatch",
    languages: ["Python", "TypeScript"],
    socials: {
      github: "https://github.com/L1nwatch",
      site: "https://watch0.top",
    },
  },
  lastUpdated: new Date().toISOString(),
};

let autoPreviewTimerId = null;

formatBtn.addEventListener("click", () => {
  clearTimeout(autoPreviewTimerId);
  updatePreview({ normalizeTextarea: true, showErrorOnEmpty: true });
});

clearBtn.addEventListener("click", () => {
  textarea.value = "";
  clearTimeout(autoPreviewTimerId);
  resetPreview();
  hideError();
  textarea.focus();
});

sampleBtn.addEventListener("click", () => {
  textarea.value = JSON.stringify(SAMPLE_JSON, null, 2);
  clearTimeout(autoPreviewTimerId);
  updatePreview();
});

textarea.addEventListener("input", schedulePreview);

previewTree.addEventListener("click", (event) => {
  const toggle = event.target.closest(".json-node__toggle");
  if (toggle) {
    const node = toggle.closest(".json-node");
    const children = node.nextElementSibling;
    if (children && children.classList.contains("json-node__children")) {
      const collapsed = children.hidden;
      children.hidden = !collapsed;
      toggle.textContent = collapsed ? "−" : "+";
      toggle.setAttribute("aria-expanded", String(collapsed));
    }
    return;
  }

  const expand = event.target.closest(".json-node__expand");
  if (expand) {
    const { fullValue } = expand.dataset;
    if (fullValue) {
      openModal(parseFullValue(fullValue));
    }
  }
});

previewTree.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const toggle = event.target.closest(".json-node__toggle");
  if (toggle) {
    event.preventDefault();
    toggle.click();
  }
});

modal.addEventListener("click", (event) => {
  if (event.target === modal || event.target === modalClose) {
    closeModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.hidden) {
    closeModal();
  }
});

function renderTree(data) {
  const fragment = document.createDocumentFragment();
  const root = createNode(undefined, data);
  fragment.appendChild(root);
  previewTree.replaceChildren(fragment);
}

function resetPreview() {
  previewTree.replaceChildren(createEmptyPlaceholder());
}

function schedulePreview() {
  clearTimeout(autoPreviewTimerId);
  if (!textarea.value.trim()) {
    resetPreview();
    hideError();
    return;
  }
  autoPreviewTimerId = setTimeout(() => updatePreview(), AUTO_PREVIEW_DELAY_MS);
}

function updatePreview({
  normalizeTextarea = false,
  showErrorOnEmpty = false,
  autoFixAttempted = false,
} = {}) {
  const raw = textarea.value;
  if (!raw.trim()) {
    resetPreview();
    if (showErrorOnEmpty) {
      showError("请输入 JSON 字符串");
    } else {
      hideError();
    }
    return;
  }

  try {
    const parsed = JSON.parse(raw);
    renderTree(parsed);
    hideError();
    if (normalizeTextarea) {
      textarea.value = JSON.stringify(parsed, null, 2);
    }
  } catch (err) {
    if (!autoFixAttempted) {
      const normalized = normalizeSingleQuotes(raw);
      if (normalized !== raw) {
        textarea.value = normalized;
        return updatePreview({ normalizeTextarea, showErrorOnEmpty, autoFixAttempted: true });
      }
    }
    handleParseError(err, raw);
  }
}

function normalizeSingleQuotes(input) {
  if (!input) return input;
  const straightQuotes = input.replace(/[‘’]/g, "'").replace(/[“”]/g, '"');
  return straightQuotes.replace(/'([^'\\]*(?:\\.[^'\\]*)*)'/g, (_, content) => {
    const withoutEscapedSingles = content.replace(/\\'/g, "'");
    const escapedForDoubles = withoutEscapedSingles.replace(/"/g, '\\"');
    return `"${escapedForDoubles}"`;
  });
}

function createNode(key, value) {
  const wrapper = document.createDocumentFragment();
  const node = nodeTemplate.content.firstElementChild.cloneNode(true);
  const keyEl = node.querySelector(".json-node__key");
  const valueEl = node.querySelector(".json-node__value");
  const separatorEl = node.querySelector(".json-node__separator");
  const toggleBtn = node.querySelector(".json-node__toggle");
  const isRoot = typeof key === "undefined";

  if (typeof key !== "undefined") {
    keyEl.textContent = JSON.stringify(String(key));
  } else {
    keyEl.textContent = "(root)";
    keyEl.style.color = "rgba(255,255,255,0.5)";
    separatorEl.hidden = true;
    toggleBtn.hidden = true;
  }

 if (value === null) {
    valueEl.textContent = "null";
    valueEl.classList.add("json-node__value--null");
  } else if (Array.isArray(value)) {
    const count = value.length;
    valueEl.textContent = `Array(${count})`;
    if (count > 0) {
      if (!isRoot) {
        toggleBtn.hidden = false;
        toggleBtn.textContent = "−";
        toggleBtn.setAttribute("aria-expanded", "true");
      } else {
        toggleBtn.hidden = true;
      }
      const children = document.createElement("div");
      children.className = "json-node__children";
      value.forEach((item, index) => {
        const child = createNode(index, item);
        children.appendChild(child);
      });
      wrapper.append(node, children);
      return wrapper;
    }
    toggleBtn.hidden = true;
  } else if (typeof value === "object") {
    const entries = Object.entries(value);
    valueEl.textContent = `Object(${entries.length})`;
    if (entries.length > 0) {
      if (!isRoot) {
        toggleBtn.hidden = false;
        toggleBtn.textContent = "−";
        toggleBtn.setAttribute("aria-expanded", "true");
      } else {
        toggleBtn.hidden = true;
      }
      const children = document.createElement("div");
      children.className = "json-node__children";
      entries.forEach(([childKey, childValue]) => {
        const child = createNode(childKey, childValue);
        children.appendChild(child);
      });
      wrapper.append(node, children);
      return wrapper;
    }
    toggleBtn.hidden = true;
  } else if (typeof value === "number") {
    valueEl.textContent = String(value);
    valueEl.classList.add("json-node__value--number");
  } else if (typeof value === "boolean") {
    valueEl.textContent = String(value);
    valueEl.classList.add("json-node__value--boolean");
  } else if (typeof value === "string") {
    const fullText = JSON.stringify(value);
    if (value.length > STRING_CUTOFF) {
      valueEl.textContent = JSON.stringify(value.slice(0, STRING_CUTOFF)) + "…";
      valueEl.dataset.collapsed = "true";
      valueEl.classList.add("json-node__value--string");
      const expandBtn = document.createElement("button");
      expandBtn.type = "button";
      expandBtn.className = "json-node__expand";
      expandBtn.dataset.fullValue = fullText;
      expandBtn.textContent = "展开";
      node.appendChild(expandBtn);
    } else {
      valueEl.textContent = fullText;
      valueEl.classList.add("json-node__value--string");
    }
  } else {
    valueEl.textContent = JSON.stringify(value);
  }

  wrapper.appendChild(node);
  return wrapper;
}

function createEmptyPlaceholder() {
  const placeholder = document.createElement("p");
  placeholder.textContent = "在左侧输入 JSON 即可自动预览";
  placeholder.style.color = "rgba(255,255,255,0.6)";
  placeholder.style.margin = "16px 0";
  return placeholder;
}

function showError(message, snippetParts = null) {
  errorMessage.innerHTML = "";
  const messageEl = document.createElement("div");
  messageEl.textContent = message;
  errorMessage.appendChild(messageEl);

  if (snippetParts) {
    const snippetEl = document.createElement("pre");
    snippetEl.className = "fd-input__error-snippet";
    if (snippetParts.truncatedBefore) {
      snippetEl.append("…");
    }

    const beforeSpan = document.createElement("span");
    beforeSpan.textContent = snippetParts.before;
    snippetEl.appendChild(beforeSpan);

    const highlight = document.createElement("mark");
    highlight.textContent = snippetParts.highlight || "⏎";
    if (!snippetParts.highlight) {
      highlight.dataset.placeholder = "true";
    }
    snippetEl.appendChild(highlight);

    const afterSpan = document.createElement("span");
    afterSpan.textContent = snippetParts.after;
    snippetEl.appendChild(afterSpan);

    if (snippetParts.truncatedAfter) {
      snippetEl.append("…");
    }

    if (!snippetParts.highlight) {
      const hint = document.createElement("span");
      hint.className = "fd-input__error-snippet-hint";
      hint.textContent = "（输入结束）";
      snippetEl.appendChild(hint);
    }

    errorMessage.appendChild(snippetEl);
  }

  errorMessage.hidden = false;
}

function hideError() {
  errorMessage.hidden = true;
  errorMessage.textContent = "";
}

function openModal(text) {
  modal.hidden = false;
  modalContent.textContent = text;
}

function closeModal() {
  modal.hidden = true;
  modalContent.textContent = "";
}

function parseFullValue(raw) {
  try {
    return JSON.parse(raw);
  } catch (error) {
    return raw;
  }
}

function handleParseError(error, raw) {
  const { position, reason } = extractJsonErrorDetails(error, raw);
  if (typeof position === "number") {
    const normalizedPos = Math.max(0, Math.min(position, raw.length));
    const { line, column } = getLineAndColumn(raw, normalizedPos);
    const snippetParts = createSnippetParts(raw, normalizedPos);
    showError(`解析失败（第 ${line} 行，第 ${column} 列）：${reason}`, snippetParts);
  } else {
    showError("解析失败：" + reason);
  }
}

function extractJsonErrorDetails(error, raw) {
  const message = error && error.message ? String(error.message) : "未知错误";
  const positionMatch = message.match(/position (\d+)/i);
  let position = positionMatch ? Number(positionMatch[1]) : null;
  if (position === null && /end of JSON input/i.test(message)) {
    position = raw.length;
  }
  const cutoffIndex = message.indexOf(" in JSON");
  const reason =
    cutoffIndex > -1 ? message.slice(0, cutoffIndex) : message;
  return { position, reason };
}

function getLineAndColumn(text, position) {
  const safePos = Math.max(0, Math.min(position, text.length));
  let line = 1;
  let column = 1;
  for (let i = 0; i < safePos; i += 1) {
    if (text[i] === "\n") {
      line += 1;
      column = 1;
    } else {
      column += 1;
    }
  }
  return { line, column };
}

function createSnippetParts(text, position) {
  const radius = 30;
  const start = Math.max(0, position - radius);
  const end = Math.min(text.length, position + radius);
  const highlightChar = text[position] || "";
  const before = text.slice(start, position);
  const after = highlightChar ? text.slice(position + 1, end) : "";

  return {
    before,
    after,
    highlight: highlightChar,
    truncatedBefore: start > 0,
    truncatedAfter: end < text.length || (!highlightChar && position < text.length),
  };
}

// Initialize preview
resetPreview();
