const adminState = {
  apps: [],
  editingId: "",
  clearCover: false,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

async function loadApps() {
  const { apps } = await api("/api/admin/apps");
  adminState.apps = apps;
  renderList();
}

function renderList() {
  $("adminList").innerHTML = adminState.apps.length
    ? adminState.apps.map(appRow).join("")
    : `<div class="empty-state">暂无样式</div>`;
  document.querySelectorAll("[data-edit-id]").forEach((button) => {
    button.addEventListener("click", () => editApp(button.dataset.editId));
  });
  document.querySelectorAll("[data-disable-id]").forEach((button) => {
    button.addEventListener("click", () => deleteApp(button.dataset.disableId));
  });
}

function appRow(app) {
  return `
    <div class="admin-row">
      <span class="admin-row-thumb" style="${coverStyle(app)}"></span>
      <span>
        <strong>${escapeHtml(app.name)}${app.enabled ? "" : "（停用）"}</strong>
        <small>${escapeHtml(app.category)} · ${app.webapp_id}</small>
      </span>
      <span class="admin-row-actions">
        <button class="tiny-button" type="button" data-edit-id="${app.id}">编辑</button>
        <button class="tiny-button danger" type="button" data-disable-id="${app.id}">删除</button>
      </span>
    </div>
  `;
}

function editApp(id) {
  const app = adminState.apps.find((item) => item.id === id);
  if (!app) return;
  adminState.editingId = app.id;
  adminState.clearCover = false;
  $("formTitle").textContent = "编辑样式";
  $("styleId").value = app.id;
  $("sourceUrlInput").value = app.source_url || "";
  $("nameInput").value = app.name || "";
  $("categoryInput").value = app.category || "";
  $("descriptionInput").value = app.description || "";
  $("webappIdInput").value = app.webapp_id || "";
  $("nodeIdInput").value = app.node_id || "";
  $("fieldNameInput").value = app.field_name || "image";
  $("outputTypeInput").value = app.output_type || "png";
  $("promptNodeInput").value = app.prompt_node_id || "";
  $("promptFieldInput").value = app.prompt_field_name || "";
  $("defaultPromptInput").value = app.default_prompt || "";
  $("inputsInput").value = JSON.stringify(app.inputs || [], null, 2);
  $("sortOrderInput").value = app.sort_order || 100;
  $("accentInput").value = app.accent || "#6657ff";
  $("favoriteInput").checked = Boolean(app.favorite);
  $("autoUnzipInput").checked = Boolean(app.auto_unzip);
  $("enabledInput").checked = Boolean(app.enabled);
  renderInputsPreview();
  setNotice("");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function deleteApp(id) {
  if (!confirm("删除这个应用？历史记录和生成图片会保留，但首页和管理列表里会移除它。")) return;
  try {
    await api(`/api/admin/apps/${id}`, { method: "DELETE" });
    setNotice("已删除应用。");
    await loadApps();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function resetForm() {
  adminState.editingId = "";
  adminState.clearCover = false;
  $("formTitle").textContent = "添加样式";
  $("styleForm").reset();
  $("styleId").value = "";
  $("fieldNameInput").value = "image";
  $("categoryInput").value = "其他";
  $("sortOrderInput").value = "100";
  $("accentInput").value = "#6657ff";
  $("enabledInput").checked = true;
  $("sampleInput").value = "";
  $("inputsInput").value = "";
  renderInputsPreview();
  setNotice("");
}

function extractRunningHubId(value) {
  const text = String(value || "").trim();
  const match = text.match(/(?:ai-detail|api-detail)\/(\d+)/);
  return match ? match[1] : "";
}

function formDataFromInputs() {
  const formData = new FormData();
  const fields = [
    "sourceUrlInput",
    "nameInput",
    "categoryInput",
    "descriptionInput",
    "webappIdInput",
    "nodeIdInput",
    "fieldNameInput",
    "outputTypeInput",
    "promptNodeInput",
    "promptFieldInput",
    "defaultPromptInput",
    "inputsInput",
    "sortOrderInput",
    "accentInput",
  ];
  const names = {
    sourceUrlInput: "source_url",
    nameInput: "name",
    categoryInput: "category",
    descriptionInput: "description",
    webappIdInput: "webapp_id",
    nodeIdInput: "node_id",
    fieldNameInput: "field_name",
    outputTypeInput: "output_type",
    promptNodeInput: "prompt_node_id",
    promptFieldInput: "prompt_field_name",
    defaultPromptInput: "default_prompt",
    inputsInput: "inputs",
    sortOrderInput: "sort_order",
    accentInput: "accent",
  };
  fields.forEach((id) => formData.append(names[id], $(id).value.trim()));
  formData.append("favorite", $("favoriteInput").checked ? "1" : "0");
  formData.append("auto_unzip", $("autoUnzipInput").checked ? "1" : "0");
  formData.append("enabled", $("enabledInput").checked ? "1" : "0");
  const cover = $("coverInput").files[0];
  if (cover) formData.append("cover", cover);
  if (adminState.clearCover) formData.append("clear_cover", "1");
  return formData;
}

function coverStyle(app) {
  if (app.cover_url) return `background-image: url('${app.cover_url}')`;
  return "background-image: url('/default-app-icon.png')";
}

function setNotice(message, kind = "info") {
  const notice = $("adminNotice");
  notice.classList.toggle("hidden", !message);
  notice.dataset.kind = kind;
  notice.textContent = message || "";
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

$("sourceUrlInput").addEventListener("input", () => {
  const id = extractRunningHubId($("sourceUrlInput").value);
  if (id) $("webappIdInput").value = id;
});

$("inspectButton").addEventListener("click", inspectRunningHub);
$("clearSampleButton").addEventListener("click", () => {
  $("sampleInput").value = "";
  setNotice("");
});

$("useDefaultCoverButton").addEventListener("click", () => {
  adminState.clearCover = true;
  $("coverInput").value = "";
  setNotice("保存后会使用默认图标。");
});

$("coverInput").addEventListener("change", () => {
  if ($("coverInput").files[0]) adminState.clearCover = false;
});

$("inputsInput").addEventListener("input", renderInputsPreview);

$("styleForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    JSON.parse($("inputsInput").value || "[]");
    const id = adminState.editingId;
    const path = id ? `/api/admin/apps/${id}` : "/api/admin/apps";
    const method = id ? "PUT" : "POST";
    await api(path, { method, body: formDataFromInputs() });
    setNotice("已保存。");
    await loadApps();
    if (!id) resetForm();
  } catch (error) {
    setNotice(error.message, "error");
  }
});

$("resetButton").addEventListener("click", resetForm);
$("backupInput").addEventListener("change", importBackup);
$("writeBackupButton").addEventListener("click", writeBackup);

loadApps().catch((error) => setNotice(error.message, "error"));

async function importBackup(event) {
  const input = event.target;
  const file = input.files[0];
  if (!file) return;
  if (!confirm("导入会覆盖同 ID 的样式配置，继续？")) {
    input.value = "";
    return;
  }
  const formData = new FormData();
  formData.append("backup", file);
  try {
    const { result } = await api("/api/admin/backup/import", { method: "POST", body: formData });
    setNotice(`已导入 ${result.count} 个样式、${result.prompt_count || 0} 条提示词。`);
    resetForm();
    await loadApps();
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    input.value = "";
  }
}

async function writeBackup() {
  const button = $("writeBackupButton");
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "备份中";
  try {
    const { backup } = await api("/api/admin/backup/write", { method: "POST" });
    setNotice(`已备份到 ${backup}`);
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

async function inspectRunningHub() {
  const sourceUrl = $("sourceUrlInput").value.trim();
  const sampleText = $("sampleInput").value.trim();
  const localId = extractRunningHubId(sourceUrl || sampleText);
  if (localId) $("webappIdInput").value = localId;
  if (!sourceUrl && !sampleText) {
    setNotice("先粘贴 RunningHub 链接，或粘贴请求示例。", "error");
    return;
  }
  $("inspectButton").disabled = true;
  setNotice("正在解析...");
  try {
    const { result } = await api("/api/admin/inspect-runninghub", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_url: sourceUrl, sample_text: sampleText }),
    });
    applyInspectResult(result);
    setNotice(result.message || "解析完成。");
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    $("inspectButton").disabled = false;
  }
}

function applyInspectResult(result) {
  if (result.source_url && !$("sourceUrlInput").value) $("sourceUrlInput").value = result.source_url;
  if (result.app_name && !$("nameInput").value) $("nameInput").value = result.app_name;
  if (result.description && !$("descriptionInput").value) $("descriptionInput").value = result.description;
  if (result.webapp_id) $("webappIdInput").value = result.webapp_id;
  if (result.node_id) $("nodeIdInput").value = result.node_id;
  if (result.field_name) $("fieldNameInput").value = result.field_name;
  if (result.prompt_node_id) $("promptNodeInput").value = result.prompt_node_id;
  if (result.prompt_field_name) $("promptFieldInput").value = result.prompt_field_name;
  if (result.output_type) $("outputTypeInput").value = result.output_type;
  if (Array.isArray(result.inputs) && result.inputs.length) {
    $("inputsInput").value = JSON.stringify(result.inputs, null, 2);
    const imageInput = result.inputs.find((item) => item.type === "image" || item.type === "file") || result.inputs[0];
    if (imageInput) {
      $("nodeIdInput").value = imageInput.nodeId || "";
      $("fieldNameInput").value = imageInput.fieldName || "";
    }
  }
  renderInputsPreview();
}

function renderInputsPreview() {
  const target = $("inputsPreview");
  let inputs = [];
  try {
    inputs = JSON.parse($("inputsInput").value || "[]");
  } catch (error) {
    target.className = "input-preview notice";
    target.textContent = "输入项 JSON 格式有问题。";
    return;
  }
  if (!Array.isArray(inputs) || !inputs.length) {
    target.className = "input-preview empty-state";
    target.textContent = "还没有输入项";
    return;
  }
  target.className = "input-preview";
  target.innerHTML = inputs.map(inputPreviewCard).join("");
}

function inputPreviewCard(item) {
  const options = Array.isArray(item.options) && item.options.length
    ? `<small>${item.options.slice(0, 4).map(escapeHtml).join(" / ")}${item.options.length > 4 ? " ..." : ""}</small>`
    : "";
  const role = item.role === "prompt" ? `<b>提示词框</b>` : "";
  return `
    <div class="input-preview-card">
      <span>${typeLabel(item.type)}</span>
      <strong>${escapeHtml(item.label || item.fieldName || "输入项")}${role}</strong>
      ${options}
      <em>${escapeHtml(item.nodeId || "")} · ${escapeHtml(item.fieldName || "")}</em>
    </div>
  `;
}

function typeLabel(type) {
  return {
    checkbox: "开关",
    hidden: "隐藏",
    image: "图片",
    file: "文件",
    textarea: "文本",
    text: "文本",
    select: "选择",
    number: "数字",
  }[type] || "输入";
}
