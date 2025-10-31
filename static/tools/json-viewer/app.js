const textarea = document.getElementById("json-input");
const previewTree = document.getElementById("preview-tree");
const formatBtn = document.getElementById("format-btn");
const clearBtn = document.getElementById("clear-btn");
const sampleBtn = document.getElementById("sample-btn");
const errorMessage = document.getElementById("error-message");
const footerVersion = document.getElementById("fd-version");
const modal = document.getElementById("modal");
const modalClose = modal.querySelector(".fd-modal__close");
const modalContent = document.getElementById("modal-content");
const nodeTemplate = document.getElementById("json-node-template");

const STRING_CUTOFF = 120;
const AUTO_PREVIEW_DELAY_MS = 350;
const SAMPLE_JSON = {
  name: "FengDock",
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
      openModal(fullValue);
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

function updatePreview({ normalizeTextarea = false, showErrorOnEmpty = false } = {}) {
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
    showError("解析失败：" + err.message);
  }
}

function createNode(key, value) {
  const wrapper = document.createDocumentFragment();
  const node = nodeTemplate.content.firstElementChild.cloneNode(true);
  const keyEl = node.querySelector(".json-node__key");
  const valueEl = node.querySelector(".json-node__value");
  const separatorEl = node.querySelector(".json-node__separator");
  const toggleBtn = node.querySelector(".json-node__toggle");

  if (typeof key !== "undefined") {
    keyEl.textContent = JSON.stringify(String(key));
  } else {
    keyEl.textContent = "(root)";
    keyEl.style.color = "rgba(255,255,255,0.5)";
    separatorEl.hidden = true;
  }

 if (value === null) {
    valueEl.textContent = "null";
    valueEl.classList.add("json-node__value--null");
  } else if (Array.isArray(value)) {
    const count = value.length;
    valueEl.textContent = `Array(${count})`;
    if (count > 0) {
      toggleBtn.hidden = false;
      toggleBtn.textContent = "−";
      toggleBtn.setAttribute("aria-expanded", "true");
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
      toggleBtn.hidden = false;
      toggleBtn.textContent = "−";
      toggleBtn.setAttribute("aria-expanded", "true");
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

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.hidden = false;
}

function hideError() {
  errorMessage.hidden = true;
}

function openModal(text) {
  modal.hidden = false;
  modalContent.textContent = text;
}

function closeModal() {
  modal.hidden = true;
  modalContent.textContent = "";
}

// Initialize preview
resetPreview();
if (footerVersion) {
  footerVersion.textContent = `build: ${document.lastModified}`;
}
