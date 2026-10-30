const PORTRAIT_CATALOG_CACHE_KEY = "huashiPortraitCatalog:v5";
const PORTRAIT_CATALOG_CACHE_TTL_MS = 12 * 60 * 60 * 1000;
const PORTRAIT_STEP_PAGE_SIZE = 50;
const HISTORY_PAGE_SIZE = 20;
const INITIAL_HASH = window.location.hash.replace("#", "");
const initialRoute = HuashiRooms.parseRoute(INITIAL_HASH);
if(initialRoute.canonicalHash && INITIAL_HASH !== initialRoute.canonicalHash) history.replaceState(null,"", "#"+initialRoute.canonicalHash);

const state = {
  inspirationRoute: initialRoute.inspirationRoute || null,
  apps: [],
  tasks: [],
  queue: null,
  queueLoadError: "",
  queueConfirming: null,
  queueBusy: false,
  taskSubmitting: false,
  prompts: [],
  albums: [],
  albumItems: [],
  selectedAlbumId: "works",
  galleryFolderOpen: true,
  gallerySelected: new Set(),
  albumRequest: 0,
  albumLoading: false,
  galleryPage: 0,
  galleryPageSize: 20,
  galleryQuiet: false,
  promptSampleRequest: 0,
  galleryColumns: 4,
  galleryZoom: 1,
  posePath: "",
  poseData: null,
  facePath: "",
  faceData: null,
  promptModels: [],
  selectedAppId: null,
  selectedTaskId: null,
  selectedPromptField: "",
  selectedArtworkField: "",
  artworkPickerMode: "input",
  artworkPickerAlbumOpen: false,
  artworkPickerAlbumId: "",
  artworkPickerPosePath: "",
  artworkPickerFacePath: "",
  artworkPickerItems: [],
  artworkPickerPage: 0,
  artworkPickerPageSize: 20,
  artworkPickerRequest: 0,
  artworkPickerPoseData: null,
  artworkPickerFaceData: null,
  rewritingPromptId: "",
  galleryIndex: 0,
  galleryViewerOpen: false,
  homeSort: "new",
  homeProvider: "runpod",
  category: "全部",
  historyFilter: "all",
  historyPage: 0,
  historyPageSize: HISTORY_PAGE_SIZE,
  search: "",
  promptSearch: "",
  promptPage: 0,
  promptPageSize: 50,
  promptFolderId: "",
  promptFolderError: "",
  promptAllDirectories: false,
  promptSelected: new Set(),
  promptSelecting: false,
  promptFormFolderControl: null,
  pickerSearch: "",
  pendingComposePrompt: "",
  promptSection: initialRoute.promptSection || "",
  promptTool: initialRoute.promptTool || "",
  rewriteCandidates: [],
  rewriteTranslations: {},
  agentPromptId: "",
  agentAnalysis: null,
  agentEdits: [],
  agentResult: null,
  agentParentVariantId: "",
  agentRoundIndex: 0,
  agentSessionId: "",
  portraitSlots: [],
  portraitMaterials: [],
  portraitCatalogItems: [],
  portraitCategories: [],
  portraitSelected: {},
  portraitManual: {},
  portraitBasePrompt: "",
  portraitImportOpen: false,
  portraitImportPrompt: "",
  portraitImportAnalysis: null,
  portraitImportMappedItems: [],
  portraitQuery: "",
  portraitActiveGroups: {},
  portraitStepIndex: 0,
  portraitPage: 0,
  portraitPageSize: PORTRAIT_STEP_PAGE_SIZE,
  portraitNextOffset: null,
  portraitPreviewId: "",
  portraitLoading: false,
  portraitResult: null,
  portraitDrawerOpen: false,
  loadingTaskDetails: {},
  copyToastTimer: null,
  view: initialView(),
  polling: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

async function copyText(text, button = null, message = "已复制到剪贴板") {
  const value = String(text || "");
  if (!value.trim()) {
    showToast("没有可复制的内容", "error");
    return false;
  }
  try {
    await copyToClipboard(value);
    markCopied(button);
    showToast(message, "info");
    return true;
  } catch (_error) {
    showToast("复制失败，请手动选中复制", "error");
    return false;
  }
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try { await navigator.clipboard.writeText(text); return; } catch (_error) { /* HTTP/modal fallback below. */ }
  }
  const focused = document.activeElement;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.cssText = "position:fixed;left:0;top:0;opacity:0;pointer-events:none";
  const host = [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
  host.appendChild(textarea);
  textarea.focus({preventScroll:true});textarea.select();
  try { if (!document.execCommand("copy")) throw new Error("copy failed"); }
  finally {textarea.remove();focused?.focus({preventScroll:true});}
}

function markCopied(button) {
  flashButtonLabel(button, "已复制");
}

function flashButtonLabel(button, label) {
  if (!button) return;
  if (!button.dataset.originalLabel) button.dataset.originalLabel = button.textContent;
  button.textContent = label;
  button.classList.add("is-copied");
  window.setTimeout(() => {
    button.textContent = button.dataset.originalLabel || "复制";
    button.classList.remove("is-copied");
  }, 1600);
}

function showToast(message, kind = "info") {
  const toast = $("copyToast");
  if (!toast) return;
  toast.textContent = message;
  toast.dataset.kind = kind;
  toast.classList.remove("hidden");
  window.clearTimeout(state.copyToastTimer);
  state.copyToastTimer = window.setTimeout(() => toast.classList.add("hidden"), 1800);
}

function initialView() {
  return HuashiRooms.parseRoute(window.location.hash).view;
}

async function loadData() {
  const [{ apps }, { tasks }, { prompts }, { models }, { folders }, queueData] = await Promise.all([
    api("/api/apps"),
    api(state.view === "history" ? "/api/tasks?summary=1" : "/api/tasks?summary=1&limit=120"),
    api("/api/prompts"),
    api("/api/prompt-models"),
    api("/api/albums"),
    api("/api/runpod/queue").catch(error => ({loadError:error.message})),
  ]);
  try {
    const directoryData = await HuashiPromptFolders.refresh(api);
    const nextFolderId = HuashiPromptFolders.resolveLeaf(directoryData, state.promptFolderId || HuashiPromptFolders.remembered());
    if (nextFolderId !== state.promptFolderId) state.promptSelected.clear();
    state.promptFolderId = nextFolderId;
    state.promptFolderError = nextFolderId ? "" : "没有可用的默认二级目录，请先管理目录。";
  } catch (error) {state.promptFolderId = ""; state.promptFolderError = error.message; state.promptSelected.clear();}
  if (queueData.loadError) state.queueLoadError = queueData.loadError;
  else {state.queue=queueData;state.queueLoadError="";}
  updateQueueNavigation();
  state.apps = apps;
  state.tasks = mergeTaskList(tasks);
  state.prompts = prompts;
  state.promptModels = models;
  state.albums = folders;
  if (!HuashiRooms.displayFolders(state.albums).some((folder) => folder.id === state.selectedAlbumId)) {
    state.selectedAlbumId = "works";
  }
  if (state.view === "gallery") await refreshAlbumItems();
  if (!state.selectedAppId && apps.length) state.selectedAppId = apps[0].id;
  render();
  if (state.promptSection === "portrait") ensurePortraitData();
  managePolling();
}

function mergeTaskList(tasks) {
  const current = new Map(state.tasks.map((task) => [task.id, task]));
  return tasks.map((task) => {
    const existing = current.get(task.id);
    if (existing && !existing.is_summary) {
      if (["queued", "running"].includes(task.status)) {
        return { ...existing, ...task, input_payload: existing.input_payload, prompt: existing.prompt, outputs: existing.outputs, is_summary: false };
      }
      if (existing.updated_at === task.updated_at) return { ...task, ...existing };
    }
    return task;
  });
}

async function loadTaskDetail(taskId) {
  if (!taskId || state.loadingTaskDetails[taskId]) return;
  state.loadingTaskDetails[taskId] = true;
  try {
    const { task } = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
    state.tasks = state.tasks.map((item) => item.id === task.id ? task : item);
    if (!state.tasks.some((item) => item.id === task.id)) state.tasks.unshift(task);
    if (state.view === "result" && (state.selectedTaskId === task.id || (!state.selectedTaskId && state.tasks[0]?.id === task.id))) {
      renderTitle();
      renderResult();
    }
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    delete state.loadingTaskDetails[taskId];
  }
}

async function refreshAlbums() {
  const { folders } = await api("/api/albums");
  state.albums = folders;
  if (!HuashiRooms.displayFolders(state.albums).some((folder) => folder.id === state.selectedAlbumId && !folder.placeholder)) {
    state.selectedAlbumId = state.albums[0]?.id || "works";
  }
  await refreshAlbumItems();
}

async function refreshAlbumItems() {
  const request=++state.albumRequest;
  state.albumLoading=true;
  try {
  const folder = HuashiRooms.displayFolders(state.albums).find((item) => item.id === state.selectedAlbumId);
  if (folder?.placeholder) {
    state.albumItems = [];
    state.poseData = null;
    state.faceData = null;
    return;
  }
  if (HuashiRooms.directoryLibrary(state.selectedAlbumId)) {
    const data = await api(`/api/pose?path=${encodeURIComponent(HuashiRooms.directoryPath(state.selectedAlbumId, state.posePath || ""))}&offset=${state.galleryPage*state.galleryPageSize}&limit=${state.galleryPageSize}`);
    const items = await HuashiMaterialBag.withDirectoryThumbnails(data.items || []);
    if(request!==state.albumRequest)return;
    state.poseData = HuashiRooms.directoryData(state.selectedAlbumId, data);
    state.albumItems = items;
    return;
  }
  if (state.selectedAlbumId === "__faces__") {
    const data = await api(`/api/faces?path=${encodeURIComponent(state.facePath || "")}&offset=${state.galleryPage*state.galleryPageSize}&limit=${state.galleryPageSize}`);
    if(request!==state.albumRequest)return;
    state.faceData = data;
    state.albumItems = data.items || [];
    return;
  }
  const { items } = await api(`/api/albums/items?folder_id=${encodeURIComponent(state.selectedAlbumId || "works")}`);
  if(request!==state.albumRequest)return;
  state.poseData = null;
  state.faceData = null;
  state.albumItems = items;
  } finally {if(request===state.albumRequest)state.albumLoading=false;}
}

function selectedApp() {
  return state.apps.find((app) => app.id === state.selectedAppId) || state.apps[0];
}

function appPromptInput(app) {
  const inputs = appInputs(app || {});
  const roleMatch = inputs.find((input) => input.role === "prompt");
  if (roleMatch) return roleMatch;
  const textInputs = inputs.filter((input) => ["textarea", "text"].includes(input.type));
  const keywordMatch = textInputs.find((input) => {
    const text = `${input.id || ""} ${input.label || ""} ${input.fieldName || ""}`.toLowerCase();
    return ["prompt", "提示词", "正向", "文本", "描述", "输入文本", "caption"].some((keyword) => text.includes(keyword));
  });
  if (keywordMatch) return keywordMatch;
  return textInputs.length === 1 ? textInputs[0] : null;
}

function promptCapableApps() {
  return state.apps.filter((app) => appPromptInput(app));
}

function currentAlbum() {
  return HuashiRooms.displayFolders(state.albums).find((folder) => folder.id === state.selectedAlbumId);
}

function setView(view, {historyMode = "push"} = {}) {
  const route = HuashiRooms.parseRoute(view);
  view = route.view;
  if(state.view==='inspiration' && view!=='inspiration') {
    $('roomUnifiedSearch')?.roomSearch?.destroy();
    $('roomInspiration').inspirationController?.destroy();
    $('roomInspiration').inspirationController=null;
    $('roomInspiration').roomContext=null;
  }
  if(state.view==='prompts' && (view!=='prompts' || route.promptSection==='portrait')) releasePromptPresentation();
  state.view = view;
  if (view === "inspiration") state.inspirationRoute = route.inspirationRoute || HuashiInspirationNav.parse("#inspiration");
  if (view !== "gallery") state.galleryViewerOpen = false;
  if (view === "inspiration" && route.kind) HuashiRooms.inspirationState.kind = route.kind;
  if (view !== "prompts") { state.promptSection = ""; state.promptTool = ""; }
  if (view === "prompts") {
    state.promptSection = route.promptSection || "library";
    state.promptTool = route.promptTool || "";
  }
  if (view === "history") loadHistorySummaries();
  if (view === "queue") loadData().catch(error=>showToast(error.message,"error"));
  if (view === "gallery") {
    state.galleryFolderOpen = true;
    state.galleryViewerOpen = false;
    refreshAlbumItems().then(() => { if (state.view === "gallery") render(); }).catch((error) => showToast(error.message, "error"));
  }
  if (state.promptSection === "portrait") ensurePortraitData();
  const hash = route.canonicalHash || (state.promptSection === "portrait" ? "inspiration/prompts/portrait" : view === "prompts" ? "inspiration/prompts" : state.promptTool || view);
  if (historyMode !== "none" && window.location.hash !== `#${hash}`) history[historyMode === "replace" ? "replaceState" : "pushState"](null, "", `#${hash}`);
  render();
  managePolling();
  if (view !== "inspiration") window.scrollTo(0, 0);
}

function setPromptSection(section) {
  state.view = "prompts";
  state.promptSection = section || "";
  state.promptTool = "";
  if (section === "portrait") ensurePortraitData();
  const hash = section === "portrait" ? "#inspiration/prompts/portrait" : "#inspiration/prompts";
  if (window.location.hash !== hash) history.pushState(null, "", hash);
  render();
  window.scrollTo(0, 0);
}

function render() {
  document.body.classList.toggle("gallery-viewer-open", state.view === "gallery" && state.galleryViewerOpen);
  const shell = $("app");
  shell.dataset.view = state.promptSection === "portrait" ? "portrait" : state.view;
  const activeScreen = state.view === "prompts" && state.promptSection === "portrait" ? "portrait" : state.view;
  document.querySelectorAll("[data-screen]").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screen === activeScreen);
  });
  document.querySelectorAll("[data-nav-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.navView === "queue" ? state.view === "queue" : button.dataset.navView === (HuashiRooms.roomForView(state.view) || state.view));
  });
  $("backButton").classList.toggle("visible", state.view !== "home" || Boolean(state.promptSection));
  renderTitle();
  renderActiveScreen(activeScreen);
}

function renderActiveScreen(activeScreen) {
  if (activeScreen === "home") {
    HuashiRooms.renderHome($("roomHome"), setView);
    return;
  }
  if (activeScreen === "create") {
    renderCategories();
    renderStyles();
    $("pendingInspiration").hidden = !state.pendingComposePrompt;
    return;
  }
  if (activeScreen === "inspiration") {
    HuashiRooms.renderInspiration($("roomInspiration"), {
      navigate: setView, api, copy: copyText, toast: showToast, route: state.inspirationRoute,
      getPrompts: () => state.prompts,
      savePrompt: (content, options) => HuashiCreation.savePrompt(content, state.prompts, {api, toast:showToast, folderId:state.promptFolderId, ...options, saved:prompt=>{state.prompts=[prompt,...state.prompts.filter(p=>p.id!==prompt.id)];HuashiPromptFolders.refresh(api).catch(error=>showToast(error.message,'error'));}}),
      managePrompt: id => {setView('inspiration/prompts'); editPrompt(id);},
      favoritePrompt: togglePersonalPromptFavorite,
      redraw: () => { if (state.view === "inspiration") renderActiveScreen("inspiration"); },
      usePrompt: (prompt) => { state.pendingComposePrompt = prompt; setView("create"); },
    });
    return;
  }
  if (activeScreen === "settings") {
    HuashiRooms.renderSettings($("roomSettings"), state);
    return;
  }
  if (activeScreen === "compose") {
    renderCompose();
    return;
  }
  if (activeScreen === "result") {
    renderResult();
    return;
  }
  if (activeScreen === "queue") {
    renderRunPodQueue();
    return;
  }
  if (activeScreen === "history") {
    renderHistory();
    return;
  }
  if (activeScreen === "gallery") {
    renderGallery();
    return;
  }
  if (activeScreen === "prompts") {
    renderPrompts();
    renderRewriteModels();
    renderAgentModels();
    return;
  }
  if (activeScreen === "portrait") {
    renderPortrait();
  }
}

function renderTitle() {
  const titles = {
    home: ["画室", "个人 AI 创作工作台"],
    create: ["创作间", "选择画布，开始生成"],
    inspiration: ["灵感屋", "提示词 · 动画 · 图像"],
    settings: ["设置", "系统与维护"],
    compose: ["创作间", selectedApp()?.name || "创作画布"],
    result: ["生成结果", resultHint()],
    queue: ["生成队列", "RunPod · 后台依次生成"],
    history: ["生成记录", `${filteredTasks().length} 条记录`],
    gallery: ["陈列室", "作品与素材管理"],
    prompts: promptTitle(),
  };
  const [title, hint] = titles[state.view] || titles.home;
  $("pageTitle").textContent = title;
  $("pageHint").textContent = hint;
}

function promptTitle() {
  if (state.promptSection === "portrait") return ["人像工坊", portraitTitleHint()];
  if (state.promptSection === "library") return ["提示词", `灵感屋 · ${filteredPrompts().length} 条提示词`];
  return ["灵感屋", "选择工具"];
}

function portraitTitleHint() {
  const count = selectedPortraitCount();
  return count ? `已选 ${count} 个素材` : "挑选素材，装袋后带去创作";
}

function resultHint() {
  const task = currentTask();
  return task ? `${task.app_name} · ${formatTime(task.created_at)}` : "暂无";
}

function renderCategories() {
  const providerApps = state.apps.filter((app) => (app.provider || "runninghub") === state.homeProvider);
  const categories = ["全部", ...new Set(providerApps.map((app) => app.category).filter(Boolean))];
  if (!categories.includes(state.category)) state.category = "全部";
  $("categorySelect").innerHTML = categories
    .map((name) => `<option value="${escapeAttr(name)}" ${state.category === name ? "selected" : ""}>${escapeHtml(name)}</option>`)
    .join("");
  if ($("sortSelect")) $("sortSelect").value = state.homeSort;
  document.querySelectorAll("[data-home-provider]").forEach((button) => {
    const active = button.dataset.homeProvider === state.homeProvider;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
}

function renderStyles() {
  const query = state.search.trim().toLowerCase();
  $("styleGrid").classList.toggle("runpod-grid", state.homeProvider === "runpod");
  let apps = state.apps.filter((app) => {
    if ((app.provider || "runninghub") !== state.homeProvider) return false;
    const matchCategory = state.category === "全部" || app.category === state.category;
    const matchSearch = !query || `${app.name} ${app.category} ${app.description}`.toLowerCase().includes(query);
    return matchCategory && matchSearch;
  });
  apps = sortApps(apps);
  const favorites = apps.filter((app) => app.favorite);
  const otherApps = apps.filter((app) => !app.favorite);
  $("favoriteSection").hidden = favorites.length === 0;
  $("favoriteGrid").innerHTML = favorites.map(styleCard).join("");
  $("styleSectionTitle").textContent = state.category === "全部" ? "全部画布" : state.category;
  $("styleGrid").innerHTML = otherApps.length
    ? otherApps.map(styleCard).join("")
    : `<div class="empty-state">${favorites.length ? "暂无其他画布" : "没有匹配的画布"}</div>`;
  document.querySelectorAll("[data-style-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedAppId = button.dataset.styleId;
      setNotice("");
      setView("compose");
    });
  });
}

function sortApps(apps) {
  const list = [...apps];
  if (state.homeSort === "category") {
    return list.sort((a, b) => `${a.category || ""}${a.name || ""}`.localeCompare(`${b.category || ""}${b.name || ""}`, "zh-CN"));
  }
  return list.reverse();
}

function styleCard(app) {
  const inputs = appInputs(app);
  const imageCount = inputs.filter((input) => input.type === "image").length;
  const description = app.description && app.description.length >= 10 && /[\u4e00-\u9fff]/.test(app.description)
    ? app.description : imageCount ? `上传${imageCount > 1 ? ` ${imageCount} 张` : ""}图片，进入编辑画布` : "填写提示词，开始图片创作";
  return `
    <button class="style-card room-app-row" type="button" data-style-id="${escapeAttr(app.id)}">
      <span class="room-app-preview"><img src="${escapeAttr(app.cover_thumb_url || app.cover_url || appVisualUrl(app))}" alt="${escapeAttr(app.name)} 效果图" loading="lazy"></span>
      <span class="room-app-copy"><span class="style-name">${escapeHtml(app.name)}</span><small>${escapeHtml(description)}</small></span>
      <span class="style-meta">${escapeHtml(app.category)}</span><span class="room-app-arrow" aria-hidden="true">→</span>
    </button>
  `;
}

function renderCompose() {
  const app = selectedApp();
  if (!app) return;
  document.querySelector('[data-screen="compose"]').classList.toggle("queue-compose-mode", app.provider === "runpod");
  $("queueComposeFooter").hidden = app.provider !== "runpod";
  $("generateButton").textContent = app.provider === "runpod" ? "＋ 加入队列" : "开始生成";
  $("composeCover").hidden = false;
  $("composeCover").innerHTML = `<img src="${escapeAttr(app.cover_thumb_url || app.cover_url || appVisualUrl(app))}" alt="${escapeAttr(app.name)} 效果图">`;
  $("composeTitle").textContent = app.name;
  $("composeMeta").textContent = `${app.provider === "runpod" ? "RunPod" : "RunningHub"} · ${app.description || app.category}`;
  // Polling or switching rooms must not rebuild an unchanged form and discard uploads.
  if ($("dynamicInputs").dataset.appId !== app.id) {
    const promptId = appPromptInput(app)?.id;
    const { main, advanced } = HuashiRooms.splitInputs(appInputs(app).map(input => input.id === promptId ? {...input, role: "prompt"} : input));
    // Layout follows each live workflow's inputs; field names and submit payload stay unchanged.
    const images = main.filter(input => ["image", "file"].includes(input.type));
    const text = main.filter(input => !["image", "file"].includes(input.type));
    const visibleAdvanced = advanced.filter(input => ["batch_size", "resolution"].includes(input.id));
    const foldedAdvanced = advanced.filter(input => !["batch_size", "resolution"].includes(input.id));
    const promptFields = text.filter(input => input.type === "textarea" || input.role === "prompt");
    const otherFields = [...text.filter(input => !promptFields.includes(input)), ...visibleAdvanced];
    $("dynamicInputs").innerHTML = (images.length ? `<section class="moon-input-images"><h3>参考图片</h3><div class="moon-image-fields">${images.map(inputControl).join("")}</div></section>` : "") +
      `<section class="moon-input-text">${promptFields.map(input => /negative|负向|负面/i.test(`${input.id} ${input.label}`) ? `<details class="moon-negative"><summary>${escapeHtml(input.label || "负向提示词")}</summary>${inputControl(input)}</details>` : inputControl(input)).join("")}</section>` +
      (otherFields.length ? `<section class="moon-input-parameters"><h3>画布参数</h3><div class="moon-parameter-grid">${otherFields.map(inputControl).join("")}</div></section>` : "") +
      (foldedAdvanced.length ? `<details class="room-advanced"><summary>高级参数 <span>采样、步数与随机种子</span></summary><div class="room-advanced-fields">${foldedAdvanced.map(inputControl).join("")}</div></details>` : "");
    $("dynamicInputs").classList.toggle("moon-has-images", images.length > 0);
    $("dynamicInputs").classList.toggle("moon-two-images", images.length > 1);
    $("dynamicInputs").dataset.appId = app.id;
    bindDynamicInputs();
  }
  applyPendingComposePrompt(app);
  updateGenerateState();
}

function applyPendingComposePrompt(app) {
  const content = String(state.pendingComposePrompt || "").trim();
  if (!content) return;
  const promptInput = appPromptInput(app);
  if (!promptInput) return;
  const field = $("createTaskForm").querySelector(`[name="${CSS.escape(`input_${promptInput.id}`)}"]`);
  if (!field) return;
  field.value = content;
  field.dispatchEvent(new Event("input", { bubbles: true }));
  state.pendingComposePrompt = "";
  showToast("已把提示词填入应用", "info");
}

function appInputs(app) {
  if (Array.isArray(app.inputs) && app.inputs.length) return app.inputs;
  const inputs = [];
  if (app.node_id && app.field_name) {
    inputs.push({
      id: "image",
      nodeId: app.node_id,
      fieldName: app.field_name,
      type: "image",
      label: "图片",
      required: true,
      defaultValue: "",
      options: [],
    });
  }
  if (app.prompt_node_id && app.prompt_field_name) {
    inputs.push({
      id: "prompt",
      nodeId: app.prompt_node_id,
      fieldName: app.prompt_field_name,
      type: "textarea",
      label: "提示词",
      required: false,
      defaultValue: app.default_prompt || "",
      options: [],
      role: "prompt",
    });
  }
  return inputs;
}

function inputControl(input) {
  const inputId = `input_${escapeAttr(input.id)}`;
  const name = `input_${escapeAttr(input.id)}`;
  const label = escapeHtml(input.label || input.fieldName);
  const required = input.required ? "required" : "";
  if (input.type === "image" || input.type === "file") {
    const emptyLabel = input.required ? "未选择" : "未选择（留空将不使用默认图）";
    return `
      <div class="file-field" data-required="${input.required ? "1" : "0"}">
        <div class="field-title">${label}</div>
        <div class="picker-row">
          <button type="button" class="upload-drop compact bag-upload-button" data-material-bag="${escapeAttr(input.id)}">从素材袋选择</button>
          <label class="upload-drop compact" for="${inputId}_gallery">
            <input id="${inputId}_gallery" name="${name}" type="file" accept="image/*" data-file-input="${escapeAttr(input.id)}" />
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M20 16.5V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.5" /></svg></span>
            <span>上传图片</span>
          </label>
          <button class="upload-drop compact" type="button" data-artwork-target="${escapeAttr(input.id)}">
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5Zm3 12 3.2-3.2 2.3 2.3L16 11l3 4.2M8.5 8.5h.01" /></svg></span>
            <span>从陈列室选择</span>
          </button>
        </div>
        <img class="creation-input-preview" data-input-preview="${escapeAttr(input.id)}" alt="当前参考图片" hidden>
        <input type="hidden" name="${name}_artwork" data-artwork-input="${escapeAttr(input.id)}" />
        <div class="file-status-row">
          <small class="file-name" data-file-label="${escapeAttr(input.id)}" data-empty-label="${escapeAttr(emptyLabel)}">${emptyLabel}</small>
          <button class="tiny-button" type="button" data-clear-file-target="${escapeAttr(input.id)}">清空</button>
        </div>
      </div>
    `;
  }
  if (input.type === "checkbox") {
    const checked = truthy(input.defaultValue) ? "checked" : "";
    return `
      <label class="check-line form-check">
        <input name="${name}" type="checkbox" ${checked} />
        ${label}
      </label>
    `;
  }
  if (input.type === "hidden") {
    return `<input name="${name}" type="hidden" value="${escapeAttr(input.defaultValue || "")}" />`;
  }
  if (input.type === "select") {
    const options = (input.options && input.options.length ? input.options : [input.defaultValue]).filter(Boolean);
    return `
      <label class="field-block">
        <span>${label}</span>
        <select name="${name}" ${required}>
          ${options.map((option) => `<option value="${escapeAttr(option)}" ${option === input.defaultValue ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}
        </select>
      </label>
    `;
  }
  const tag = input.type === "textarea" ? "textarea" : "input";
  if (tag === "textarea") {
    const promptButton = input.role === "prompt"
      ? `<button class="inline-tool" type="button" data-prompt-target="${escapeAttr(input.id)}">从灵感屋选择</button><button class="inline-tool" type="button" data-save-canvas-prompt="${escapeAttr(input.id)}">保存到提示词库</button>`
      : "";
    return `
      <div class="field-block ${input.role === "prompt" ? "prompt-field" : ""}">
        <span><label for="${inputId}">${label}</label>${promptButton}</span>
        <textarea id="${inputId}" name="${name}" rows="3" ${required}>${escapeHtml(input.defaultValue || "")}</textarea>
      </div>
    `;
  }
  return `
    <div class="field-block">
      <span><label for="${inputId}">${label}</label>${input.role === 'prompt' ? `<button class="inline-tool" type="button" data-prompt-target="${escapeAttr(input.id)}">从灵感屋选择</button><button class="inline-tool" type="button" data-save-canvas-prompt="${escapeAttr(input.id)}">保存到提示词库</button>` : ''}</span>
      <input id="${inputId}" name="${name}" type="${input.type === 'number' ? 'number' : 'text'}" ${input.type === 'number' && ['cfg', 'denoise', 'lora_strength'].includes(input.id) ? 'step="any"' : ''} value="${escapeAttr(input.defaultValue || '')}" ${required} />
    </div>
  `;
}

function bindDynamicInputs() {
  document.querySelectorAll("[data-file-input]").forEach((input) => {
    input.addEventListener("change", () => {
      const key = input.dataset.fileInput;
      const file = input.files[0];
      if (!file) return;
      document.querySelectorAll(`[data-file-input="${CSS.escape(key)}"]`).forEach((other) => {
        if (other !== input) other.value = "";
      });
      const artworkInput = document.querySelector(`[data-artwork-input="${CSS.escape(key)}"]`);
      if (artworkInput) artworkInput.value = "";
      showInputPreview(key, "");
      const label = document.querySelector(`[data-file-label="${CSS.escape(key)}"]`);
      if (label) label.textContent = file.name;
      updateGenerateState();
    });
  });
  $("dynamicInputs").querySelectorAll("input, textarea, select").forEach((input) => {
    input.addEventListener("input", updateGenerateState);
    input.addEventListener("change", updateGenerateState);
  });
  $("dynamicInputs").querySelectorAll("[data-prompt-target]").forEach((button) => {
    button.addEventListener("click", () => openPromptPicker(button.dataset.promptTarget));
  });
  $("dynamicInputs").querySelectorAll("[data-save-canvas-prompt]").forEach(button => {
    button.onclick = () => {
      const field = $("createTaskForm").querySelector(`[name="${CSS.escape(`input_${button.dataset.saveCanvasPrompt}`)}"]`);
      HuashiCreation.savePrompt(field?.value || "", state.prompts, {api,toast:showToast,folderId:state.promptFolderId,saved:prompt => {
        state.prompts = [prompt, ...state.prompts];
        HuashiPromptFolders.refresh(api).catch(error => showToast(error.message,"error"));
      }});
    };
  });
  $("dynamicInputs").querySelectorAll("[data-artwork-target]").forEach((button) => {
    button.addEventListener("click", () => openArtworkPicker(button.dataset.artworkTarget));
  });
  $("dynamicInputs").querySelectorAll("[data-clear-file-target]").forEach((button) => {
    button.addEventListener("click", () => clearImageInput(button.dataset.clearFileTarget));
  });
}

function clearImageInput(key) {
  if (!key) return;
  showInputPreview(key, "");
  document.querySelectorAll(`[data-file-input="${CSS.escape(key)}"]`).forEach((input) => {
    input.value = "";
  });
  const artworkInput = document.querySelector(`[data-artwork-input="${CSS.escape(key)}"]`);
  if (artworkInput) artworkInput.value = "";
  const label = document.querySelector(`[data-file-label="${CSS.escape(key)}"]`);
  if (label) label.textContent = label.dataset.emptyLabel || "未选择";
  updateGenerateState();
}

function updateGenerateState() {
  const app = selectedApp();
  const inputs = app ? appInputs(app) : [];
  const form = $("createTaskForm");
  const ok = inputs.every((input) => {
    if (!input.required) return true;
    const name = `input_${input.id}`;
    if (input.type === "image" || input.type === "file") {
      const hasFile = Array.from(form.querySelectorAll(`[name="${CSS.escape(name)}"]`)).some((item) => item.files && item.files.length);
      const artwork = form.querySelector(`[name="${CSS.escape(`${name}_artwork`)}"]`);
      return hasFile || Boolean(artwork && String(artwork.value || "").trim());
    }
    const field = form.querySelector(`[name="${CSS.escape(name)}"]`);
    return field && String(field.value || "").trim();
  });
  $("generateButton").disabled = !ok || state.taskSubmitting;
}

async function loadHistorySummaries() {
  try {
    const {tasks}=await api("/api/tasks?summary=1");
    if(state.view!=="history")return;
    state.tasks=mergeTaskList(tasks);renderHistory();renderTitle();
  }catch(error){showToast(error.message,"error");}
}

function renderHistory() {
  const tasks=filteredTasks(),w=HuashiPages.windowFor(tasks.length,state.historyPage,state.historyPageSize);
  state.historyPage=w.page;
  $("taskList").innerHTML=tasks.length ? tasks.slice(w.start,w.end).map(recordRow).join("") : '<div class="empty-state">暂无记录</div>';
  $("historyPagination").innerHTML=HuashiPages.markup(tasks.length,w.page,w.size);
  HuashiPages.bind($("historyPagination"),next=>{state.historyPage=next.page;state.historyPageSize=next.size;renderHistory();});
  $("taskList").querySelectorAll("[data-task-id]").forEach(row=>row.onclick=()=>{state.selectedTaskId=row.dataset.taskId;setView("result");});
}

function artworkItems() {
  return (state.albumItems || [])
    .filter((item) => isVisibleImageOutput(item))
    .map((item, index) => ({ ...item, index }));
}

function renderGallery() {
  document.body.classList.toggle("gallery-viewer-open", state.view === "gallery" && state.galleryViewerOpen);
  const target = $("artworkGallery");
  if (!target) return;
  renderAlbumFolders();
  renderGallerySelection();
  const folder = currentAlbum();
  $("galleryName").textContent = folder?.displayName || folder?.name || "我的作品";
  $("galleryCount").textContent = folder?.virtual ? "只读参考素材" : `${artworkItems().length} 张图片 · 按分类整理`;
  $("galleryPagination").innerHTML = "";
  $("albumUploadInput").disabled = Boolean(state.albumLoading || folder?.placeholder || folder?.virtual);
  $("albumUploadInput").parentElement.classList.toggle("is-disabled", $("albumUploadInput").disabled);
  target.style.setProperty("--gallery-columns", state.galleryColumns);
  if(state.albumLoading){target.className='artwork-gallery room-empty';target.textContent='正在读取分类…';return;}
  if (folder?.placeholder) {
    target.className = "artwork-gallery room-empty";
    target.innerHTML = folder.virtual
      ? `<strong>${escapeHtml(folder.displayName)}暂未挂载</strong><p>保留只读素材入口，正式素材目录不做任何变更。</p>`
      : `<strong>${escapeHtml(folder.displayName)}</strong><p>${folder.id === "__inbox__" ? "为尚未归类的素材留一个位置，之后可以请 Codex 帮你整理。" : "在这里分类收藏其他参考素材。"}</p><button class="secondary-button" type="button" data-create-room-folder>创建这个分类</button>`;
    target.querySelector("[data-create-room-folder]")?.addEventListener("click", async () => {
      try {
        const { folder: created } = await api("/api/albums", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: folder.displayName }) });
        state.selectedAlbumId = created.id;
        state.galleryPage = 0;
        await refreshAlbums();
        render();
      } catch (error) { showToast(error.message, "error"); }
    });
    return;
  }
  if (HuashiRooms.directoryLibrary(state.selectedAlbumId)) { renderPoseGallery(target); return; }
  if (state.selectedAlbumId === "__faces__") { renderFaceGallery(target); return; }
  const items = artworkItems();
  if (!items.length) {
    target.className = "artwork-gallery room-empty";
    target.innerHTML = `<strong>这里还没有图片</strong><p>上传素材到当前分类，或从创作间生成你的第一张作品。</p>`;
    return;
  }
  const pages = Math.max(1, Math.ceil(items.length / state.galleryPageSize));
  state.galleryPage = Math.min(state.galleryPage, pages - 1);
  const start = state.galleryPage * state.galleryPageSize;
  const visible = items.slice(start, start + state.galleryPageSize);
  state.galleryIndex = Math.min(Math.max(state.galleryIndex, 0), items.length - 1);
  target.className = "artwork-gallery room-gallery-grid";
  target.innerHTML = `<div class="photo-grid">${visible.map((thumb, index) => `
    <div class="room-gallery-item"><label class="room-image-select"><input type="checkbox" data-gallery-select="${escapeAttr(thumb.id)}" aria-label="选择${escapeAttr(thumb.title || '图片')}" ${state.gallerySelected.has(thumb.id) ? 'checked' : ''}></label><button class="photo-tile" type="button" data-gallery-index="${start + index}" aria-label="打开图片 ${start + index + 1}">
      <img class="${thumb.blurred ? "is-blurred" : ""}" loading="lazy" src="${escapeAttr(previewUrl(thumb))}" alt="">
      <span class="room-photo-caption">${escapeHtml(thumb.title || thumb.app_name || thumb.path?.split("/").pop() || "图片")}</span>
    </button></div>`).join("")}</div>${state.galleryViewerOpen ? galleryViewer(items[state.galleryIndex], items.length) : ""}`;
  const pageNumbers = pages <= 7 ? Array.from({length:pages},(_,i)=>i) : [...new Set([0,pages-1,state.galleryPage-1,state.galleryPage,state.galleryPage+1])].filter(n=>n>=0&&n<pages).sort((a,b)=>a-b);
  const pageLinks = pageNumbers.map((n,i)=>`${i && n-pageNumbers[i-1]>1?'<span>…</span>':''}<button type="button" class="gallery-page-number ${n===state.galleryPage?'active':''}" data-gallery-page="${n}" ${n===state.galleryPage?'aria-current="page"':''}>${n+1}</button>`).join('');
  $("galleryPagination").innerHTML = `<button class="secondary-button" type="button" data-gallery-page="${state.galleryPage - 1}" ${state.galleryPage === 0 ? "disabled" : ""}>上一页</button>${pageLinks}<span>共 ${items.length} 张</span><button class="secondary-button" type="button" data-gallery-page="${state.galleryPage + 1}" ${state.galleryPage + 1 === pages ? "disabled" : ""}>下一页</button>`;
  $("galleryPagination").querySelectorAll("[data-gallery-page]").forEach((button) => button.addEventListener("click", () => {
    state.galleryPage = Number(button.dataset.galleryPage);
    state.galleryViewerOpen = false;
    renderGallery();
    $("galleryName").scrollIntoView({ block: "start", behavior: "smooth" });
  }));
  target.querySelectorAll('[data-gallery-select]').forEach(input=>input.onchange=()=>{
    if(input.checked) state.gallerySelected.add(input.dataset.gallerySelect); else state.gallerySelected.delete(input.dataset.gallerySelect);
    renderGallerySelection();
  });
  bindGalleryActions(target, items);
  bindRoomViewer(target, items);
}

function galleryViewer(item, total) {
  if (!item) return "";
  return HuashiGallery.viewer(item, {folders:state.albums || [],index:state.galleryIndex,total,zoom:state.galleryZoom,quiet:state.galleryQuiet,time:formatTime(item.created_at),creationActions:HuashiCreation.imageActions(item.path,item.title,previewUrl(item))});
}

function bindRoomViewer(root, items) {
  bindCreationImages(root);
  root.querySelector("[data-gallery-stage]")?.focus({preventScroll:true});
  root.querySelector('[data-viewer-quiet]')?.addEventListener('click',()=>{state.galleryQuiet=!state.galleryQuiet;renderGallery();});
  root.querySelector('[data-room-zoom-reset]')?.addEventListener('click',()=>{state.galleryZoom=1;renderGallery();});
  root.querySelector('.room-viewer-image')?.addEventListener('click',event=>{if(event.target===event.currentTarget){state.galleryViewerOpen=false;renderGallery();}});
  const move = (delta) => { state.galleryIndex = (state.galleryIndex + delta + items.length) % items.length; state.galleryZoom = 1; renderGallery(); };
  root.querySelector("[data-room-image-prev]")?.addEventListener("click", () => move(-1));
  root.querySelector("[data-room-image-next]")?.addEventListener("click", () => move(1));
  root.querySelectorAll("[data-room-zoom]").forEach((button) => button.addEventListener("click", () => {
    state.galleryZoom = Math.min(3, Math.max(0.5, state.galleryZoom + Number(button.dataset.roomZoom)));
    renderGallery();
  }));
  root.querySelector("[data-room-copy-image]")?.addEventListener("click", (event) => copyText(new URL(items[state.galleryIndex].url, location.origin).href, event.currentTarget));
}

function renderAlbumFolders() {
  const target = $("albumFolderList");
  if (!target) return;
  target.innerHTML = HuashiRooms.displayFolders(state.albums).map((folder) => `<button class="album-folder ${folder.id === state.selectedAlbumId ? "active" : ""}" type="button" data-album-folder="${escapeAttr(folder.id)}"><span>${escapeHtml(folder.displayName)}</span><small>${folder.placeholder ? (folder.virtual ? "未挂载" : "未创建") : folder.virtual ? "参考" : Number(folder.item_count || 0)}</small></button>`).join("");
  target.querySelectorAll("[data-album-folder]").forEach((button) => button.addEventListener("click", async () => {
    state.gallerySelected.clear();
    state.selectedAlbumId = button.dataset.albumFolder || "works";
    state.albumLoading=true;state.albumItems=[];state.poseData=null;state.faceData=null;renderGallery();
    state.posePath = ""; state.facePath = ""; state.galleryPage = 0; state.galleryIndex = 0; state.galleryZoom = 1; state.galleryViewerOpen = false; state.galleryFolderOpen = true;
    try {await refreshAlbumItems();} catch(error){showToast(error.message,"error");}
    renderGallery(); renderTitle();
  }));
}

function renderPoseGallery(target) {
  const data = state.poseData || { directories: [], items: [], breadcrumbs: [], next_offset: null, image_count: 0 };
  const items = artworkItems();
  state.galleryIndex = Math.min(Math.max(state.galleryIndex, 0), Math.max(items.length - 1, 0));
  const item = items[state.galleryIndex];
  target.className = "artwork-gallery pose-browser";
  target.innerHTML = `
    <div class="pose-path-bar">
      <button type="button" data-pose-path="">${escapeHtml(HuashiRooms.directoryLibrary(state.selectedAlbumId).label)}</button>
      ${(data.breadcrumbs || []).map((crumb) => `
        <span>/</span>
        <button type="button" data-pose-path="${escapeAttr(crumb.path)}">${escapeHtml(crumb.name)}</button>
      `).join("")}
    </div>
    ${(data.directories || []).length ? `
      <div class="album-folder-grid pose-folder-grid">
        ${data.directories.map((folder) => `
          <button class="album-folder-card pose-folder-card" type="button" data-pose-path="${escapeAttr(folder.path)}">
            <span class="folder-shape" aria-hidden="true"></span>
            <strong>${escapeHtml(folder.name)}</strong>
            <small>文件夹</small>
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${items.length ? `
      <div class="photo-grid">
        ${items.map((thumb, index) => `
          <button class="photo-tile" type="button" data-gallery-index="${index}" aria-label="打开图片 ${index + 1}">
            <img loading="lazy" src="${escapeAttr(previewUrl(thumb))}" alt="">
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${HuashiPages.markup(data.image_count || 0,state.galleryPage,state.galleryPageSize)}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个素材文件夹没有图片</div>` : ""}
    ${state.galleryViewerOpen && item ? galleryViewer(item, items.length) : ""}
  `;
  bindPoseGalleryActions(target, items);
  HuashiPages.bind(target,async next=>{state.galleryPage=next.page;state.galleryPageSize=next.size;state.galleryViewerOpen=false;state.galleryIndex=0;await refreshAlbumItems();renderGallery();});
  bindRoomViewer(target, items);
}

function bindPoseGalleryActions(root, items) {
  root.querySelectorAll("[data-pose-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.posePath = button.dataset.posePath || "";
      state.galleryPage = 0;
      state.galleryIndex = 0;
      state.galleryViewerOpen = false;
      await refreshAlbumItems();
      renderGallery();
      renderTitle();
    });
  });
  root.querySelectorAll("[data-gallery-index]").forEach((button) => {
    button.addEventListener("click", () => {
      state.galleryIndex = Number(button.dataset.galleryIndex || 0);
      state.galleryZoom = 1;
      state.galleryViewerOpen = true;
      renderGallery();
    });
  });
  root.querySelector("[data-gallery-close]")?.addEventListener("click", () => {
    state.galleryViewerOpen = false;
    renderGallery();
  });
  const stage = root.querySelector("[data-gallery-stage]");
  const image = stage?.querySelector("img");
  let startX = 0;
  let currentX = 0;
  stage?.addEventListener("touchstart", (event) => {
    startX = event.touches[0]?.clientX || 0;
    currentX = startX;
    image?.classList.add("dragging");
  }, { passive: true });
  stage?.addEventListener("touchmove", (event) => {
    currentX = event.touches[0]?.clientX || startX;
    const delta = currentX - startX;
    if (image && Math.abs(delta) > 4) {
      image.style.transform = `translateX(${delta * 0.28}px) scale(0.985)`;
      image.style.opacity = String(Math.max(0.72, 1 - Math.abs(delta) / 420));
    }
  }, { passive: true });
  stage?.addEventListener("touchend", (event) => {
    const endX = event.changedTouches[0]?.clientX || 0;
    const delta = endX - startX;
    if (image) {
      image.classList.remove("dragging");
      image.style.transform = "";
      image.style.opacity = "";
    }
    if (Math.abs(delta) > 45 && items.length) {
      state.galleryIndex = (state.galleryIndex + (delta > 0 ? -1 : 1) + items.length) % items.length;
      renderGallery();
    }
  }, { passive: true });
}

function renderFaceGallery(target) {
  const data = state.faceData || { directories: [], items: [], breadcrumbs: [], next_offset: null, image_count: 0 };
  const items = artworkItems();
  state.galleryIndex = Math.min(Math.max(state.galleryIndex, 0), Math.max(items.length - 1, 0));
  const item = items[state.galleryIndex];
  target.className = "artwork-gallery pose-browser face-browser";
  target.innerHTML = `
    <div class="pose-path-bar">
      <button type="button" data-face-path="">人脸库</button>
      ${(data.breadcrumbs || []).map((crumb) => `
        <span>/</span>
        <button type="button" data-face-path="${escapeAttr(crumb.path)}">${escapeHtml(crumb.name)}</button>
      `).join("")}
    </div>
    ${(data.directories || []).length ? `
      <div class="album-folder-grid pose-folder-grid">
        ${data.directories.map((folder) => `
          <button class="album-folder-card pose-folder-card" type="button" data-face-path="${escapeAttr(folder.path)}">
            <span class="folder-shape" aria-hidden="true"></span>
            <strong>${escapeHtml(folder.name)}</strong>
            <small>文件夹</small>
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${items.length ? `
      <div class="photo-grid">
        ${items.map((thumb, index) => `
          <button class="photo-tile" type="button" data-gallery-index="${index}" aria-label="打开图片 ${index + 1}">
            <img loading="lazy" src="${escapeAttr(previewUrl(thumb))}" alt="">
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${HuashiPages.markup(data.image_count || 0,state.galleryPage,state.galleryPageSize)}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个人脸库文件夹没有图片</div>` : ""}
    ${state.galleryViewerOpen && item ? galleryViewer(item, items.length) : ""}
  `;
  bindFaceGalleryActions(target, items);
  HuashiPages.bind(target,async next=>{state.galleryPage=next.page;state.galleryPageSize=next.size;state.galleryViewerOpen=false;state.galleryIndex=0;await refreshAlbumItems();renderGallery();});
  bindRoomViewer(target, items);
}

function bindFaceGalleryActions(root, items) {
  root.querySelectorAll("[data-face-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.facePath = button.dataset.facePath || "";
      state.galleryPage = 0;
      state.galleryIndex = 0;
      state.galleryViewerOpen = false;
      await refreshAlbumItems();
      renderGallery();
      renderTitle();
    });
  });
  root.querySelectorAll("[data-gallery-index]").forEach((button) => {
    button.addEventListener("click", () => {
      state.galleryIndex = Number(button.dataset.galleryIndex || 0);
      state.galleryViewerOpen = true;
      renderGallery();
    });
  });
  root.querySelector("[data-gallery-close]")?.addEventListener("click", () => {
    state.galleryViewerOpen = false;
    renderGallery();
  });
  const stage = root.querySelector("[data-gallery-stage]");
  const image = stage?.querySelector("img");
  let startX = 0;
  let currentX = 0;
  stage?.addEventListener("touchstart", (event) => {
    startX = event.touches[0]?.clientX || 0;
    currentX = startX;
    image?.classList.add("dragging");
  }, { passive: true });
  stage?.addEventListener("touchmove", (event) => {
    currentX = event.touches[0]?.clientX || startX;
    const delta = currentX - startX;
    if (image && Math.abs(delta) > 4) {
      image.style.transform = `translateX(${delta * 0.28}px) scale(0.985)`;
      image.style.opacity = String(Math.max(0.72, 1 - Math.abs(delta) / 420));
    }
  }, { passive: true });
  stage?.addEventListener("touchend", (event) => {
    const endX = event.changedTouches[0]?.clientX || 0;
    const delta = endX - startX;
    if (image) {
      image.classList.remove("dragging");
      image.style.transform = "";
      image.style.opacity = "";
    }
    if (Math.abs(delta) > 45 && items.length) {
      state.galleryIndex = (state.galleryIndex + (delta > 0 ? -1 : 1) + items.length) % items.length;
      renderGallery();
    }
  }, { passive: true });
}

function renderAlbumLanding() {
  const folders = HuashiRooms.displayFolders(state.albums || []).filter(folder => !folder.placeholder);
  return folders.length
    ? `
      <div class="album-folder-grid">
        ${folders.map((folder) => `
          <button class="album-folder-card" type="button" data-open-album-folder="${escapeAttr(folder.id)}">
            <span class="folder-shape" aria-hidden="true"></span>
            <strong>${escapeHtml(folder.name)}</strong>
            <small>${folder.virtual ? `${Number(folder.directory_count || 0)} 个文件夹` : `${Number(folder.item_count || 0)} 张图片`}</small>
          </button>
        `).join("")}
      </div>
    `
    : `<div class="empty-state">还没有文件夹</div>`;
}

function bindAlbumLanding(root) {
  root.querySelectorAll("[data-open-album-folder]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedAlbumId = button.dataset.openAlbumFolder || "works";
      state.posePath = "";
      state.facePath = "";
      state.galleryIndex = 0;
      state.galleryViewerOpen = false;
      state.galleryFolderOpen = true;
      await refreshAlbumItems();
      renderGallery();
      renderTitle();
    });
  });
}

function bindGalleryActions(root, items) {
  const move = (delta) => {
    if (!items.length) return;
    state.galleryIndex = (state.galleryIndex + delta + items.length) % items.length;
    renderGallery();
  };
  root.querySelector("[data-gallery-prev]")?.addEventListener("click", () => move(-1));
  root.querySelector("[data-gallery-next]")?.addEventListener("click", () => move(1));
  root.querySelectorAll("[data-gallery-index]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.draggingDone === "1") {
        delete button.dataset.draggingDone;
        return;
      }
      state.galleryIndex = Number(button.dataset.galleryIndex || 0);
      state.galleryZoom = 1;
      state.galleryViewerOpen = true;
      renderGallery();
    });
    bindAlbumTileDrag(button, items);
  });
  root.querySelector("[data-gallery-close]")?.addEventListener("click", () => {
    state.galleryViewerOpen = false;
    renderGallery();
  });
  root.querySelector("[data-toggle-output-blur]")?.addEventListener("click", (event) => toggleOutputBlur(event.currentTarget));
  root.querySelector("[data-delete-album-item]")?.addEventListener("click", (event) => deleteAlbumItem(event.currentTarget));
  root.querySelectorAll("[data-reorder-album-item]").forEach((button) => {
    button.addEventListener("click", () => reorderAlbumItem(button));
  });
  root.querySelector("[data-move-album-item]")?.addEventListener("change", (event) => moveAlbumItem(event.currentTarget));
  root.querySelector("[data-gallery-task]")?.addEventListener("click", (event) => {
    state.selectedTaskId = event.currentTarget.dataset.galleryTask;
    setView("result");
  });
  const stage = root.querySelector("[data-gallery-stage]");
  const image = stage?.querySelector("img");
  let startX = 0;
  let currentX = 0;
  stage?.addEventListener("touchstart", (event) => {
    startX = event.touches[0]?.clientX || 0;
    currentX = startX;
    image?.classList.add("dragging");
  }, { passive: true });
  stage?.addEventListener("touchmove", (event) => {
    currentX = event.touches[0]?.clientX || startX;
    const delta = currentX - startX;
    if (image && Math.abs(delta) > 4) {
      image.style.transform = `translateX(${delta * 0.28}px) scale(0.985)`;
      image.style.opacity = String(Math.max(0.72, 1 - Math.abs(delta) / 420));
    }
  }, { passive: true });
  stage?.addEventListener("touchend", (event) => {
    const endX = event.changedTouches[0]?.clientX || 0;
    const delta = endX - startX;
    if (image) {
      image.classList.remove("dragging");
      image.style.transform = "";
      image.style.opacity = "";
    }
    if (Math.abs(delta) > 45) move(delta > 0 ? -1 : 1);
  }, { passive: true });
}

function bindAlbumTileDrag(tile, items) {
  let timer = null;
  let dragging = false;
  let pointerId = null;
  let startX = 0;
  let startY = 0;
  const sourceIndex = Number(tile.dataset.galleryIndex || 0);
  const sourceItem = items[sourceIndex];
  if (!sourceItem) return;
  const clearTimer = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  tile.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    pointerId = event.pointerId;
    startX = event.clientX;
    startY = event.clientY;
    clearTimer();
    timer = setTimeout(() => {
      dragging = true;
      tile.classList.add("dragging");
      tile.setPointerCapture?.(pointerId);
    }, 260);
  });
  tile.addEventListener("pointermove", (event) => {
    if (!dragging) {
      if (Math.hypot(event.clientX - startX, event.clientY - startY) > 10) clearTimer();
      return;
    }
    event.preventDefault();
    tile.style.transform = `translate(${event.clientX - startX}px, ${event.clientY - startY}px) scale(1.04)`;
    tile.style.zIndex = "6";
    document.querySelectorAll(".photo-tile.drop-target").forEach((item) => item.classList.remove("drop-target"));
    const targetTile = document.elementFromPoint(event.clientX, event.clientY)?.closest?.("[data-gallery-index]");
    if (targetTile && targetTile !== tile) targetTile.classList.add("drop-target");
  });
  const finish = async (event) => {
    clearTimer();
    tile.releasePointerCapture?.(pointerId);
    tile.classList.remove("dragging");
    tile.style.transform = "";
    tile.style.zIndex = "";
    document.querySelectorAll(".photo-tile.drop-target").forEach((item) => item.classList.remove("drop-target"));
    if (!dragging) return;
    dragging = false;
    tile.dataset.draggingDone = "1";
    const targetTile = document.elementFromPoint(event.clientX, event.clientY)?.closest?.("[data-gallery-index]");
    if (!targetTile || targetTile === tile) return;
    await positionAlbumItem(sourceItem.id, Number(targetTile.dataset.galleryIndex || 0));
  };
  tile.addEventListener("pointerup", finish);
  tile.addEventListener("pointercancel", finish);
}

function openArtworkPicker(inputId, mode = "input") {
  // Keep the draft while the existing full-screen picker is in use.
  state.promptEditorSuspended = mode === "promptSample" && $("promptEditorDialog").open;
  if (state.promptEditorSuspended) $("promptEditorDialog").close();
  ++state.artworkPickerRequest;
  state.selectedArtworkField = inputId;
  state.artworkPickerMode = mode;
  state.artworkPickerAlbumOpen = false;
  state.artworkPickerAlbumId = "";
  state.artworkPickerPosePath = "";
  state.artworkPickerFacePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPage = 0;
  state.artworkPickerPoseData = null;
  state.artworkPickerFaceData = null;
  $("artworkPicker").classList.remove("hidden");
  $("artworkPicker").setAttribute("aria-hidden", "false");
  renderArtworkPicker();
  $('artworkPicker').querySelector('button')?.focus();
}

function closeArtworkPicker() {
  ++state.artworkPickerRequest;
  $("artworkPicker").classList.add("hidden");
  $("artworkPicker").setAttribute("aria-hidden", "true");
  state.selectedArtworkField = "";
  state.artworkPickerAlbumOpen = false;
  state.artworkPickerAlbumId = "";
  state.artworkPickerPosePath = "";
  state.artworkPickerFacePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPage = 0;
  state.artworkPickerPoseData = null;
  state.artworkPickerFaceData = null;
  if (state.promptEditorSuspended) {
    state.promptEditorSuspended = false;
    if (!$("promptForm").classList.contains("hidden")) $("promptEditorDialog").showModal();
  }
}

function renderArtworkPicker() {
  const target = $("artworkPickerList");
  $('artworkPickerBack').hidden = !state.artworkPickerAlbumOpen;
  $('artworkPickerBack').onclick=()=>{state.artworkPickerAlbumOpen=false;renderArtworkPicker();};
  if (!state.artworkPickerAlbumOpen) {
    target.className = "artwork-picker-folders album-folder-grid";
    target.innerHTML = HuashiRooms.displayFolders(state.albums).filter(folder => !folder.placeholder).map((folder) => `
      <button class="album-folder-card" type="button" data-picker-folder="${escapeAttr(folder.id)}">
        <span class="folder-shape" aria-hidden="true"></span>
        <strong>${escapeHtml(folder.displayName || folder.name)}</strong>
        <small>${folder.virtual ? `${Number(folder.directory_count || 0)} 个文件夹` : `${Number(folder.item_count || 0)} 张图片`}</small>
      </button>
    `).join("");
    target.querySelectorAll("[data-picker-folder]").forEach((button) => {
      button.addEventListener("click", () => openArtworkPickerFolder(button.dataset.pickerFolder || "works").catch(error=>showToast(error.message,"error")));
    });
    return;
  }
  if (HuashiRooms.directoryLibrary(state.artworkPickerAlbumId)) {
    renderArtworkPosePicker(target);
    return;
  }
  if (state.artworkPickerAlbumId === "__faces__") {
    renderArtworkFacePicker(target);
    return;
  }
  const items = state.artworkPickerItems || [];
  const pages=Math.max(1,Math.ceil(items.length/state.artworkPickerPageSize));state.artworkPickerPage=Math.min(state.artworkPickerPage,pages-1);
  const start=state.artworkPickerPage*state.artworkPickerPageSize;
  target.className = 'room-artwork-picker';
  const folder=HuashiRooms.displayFolders(state.albums).find(item=>item.id===state.artworkPickerAlbumId);
  target.innerHTML = `<p class="room-muted">${escapeHtml(folder?.displayName || '图片')} · ${items.length} 张</p>${items.length ? `<div class="artwork-picker-grid">${artworkPickerImageButtons(items.slice(start,start+state.artworkPickerPageSize),start)}</div>` : '<div class="empty-state">这个文件夹还没有可复用图片</div>'}${HuashiPages.markup(items.length,state.artworkPickerPage,state.artworkPickerPageSize)}`;
  HuashiPages.bind(target,next=>{state.artworkPickerPage=next.page;state.artworkPickerPageSize=next.size;renderArtworkPicker();});
  target.querySelectorAll('[data-use-artwork]').forEach(button=>button.onclick=()=>useArtwork(Number(button.dataset.useArtwork || 0)));
}

async function openArtworkPickerFolder(folderId) {
  state.artworkPickerAlbumOpen = true;
  state.artworkPickerAlbumId = folderId;
  state.artworkPickerPosePath = "";
  state.artworkPickerFacePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPage = 0;
  state.artworkPickerPoseData = null;
  state.artworkPickerFaceData = null;
  if (HuashiRooms.directoryLibrary(folderId)) {
    await refreshArtworkPickerPose("");
  } else if (folderId === "__faces__") {
    await refreshArtworkPickerFace("");
  } else {
    const { items } = await api(`/api/albums/items?folder_id=${encodeURIComponent(folderId || "works")}`);
    state.artworkPickerItems = (items || []).filter((item) => isVisibleImageOutput(item));
  }
  renderArtworkPicker();
}

function artworkPickerImageButtons(items, offset = 0) {
  return items.map((item, index) => `
    <button class="artwork-choice" type="button" data-use-artwork="${offset + index}">
      <img loading="lazy" class="${item.blurred ? "is-blurred" : ""}" src="${escapeAttr(previewUrl(item))}" alt="">
      <span>${escapeHtml(item.title || item.app_name || "画册图片")}</span>
    </button>
  `).join("");
}

function renderArtworkPosePicker(target) {
  const data = state.artworkPickerPoseData || { directories: [], items: [], breadcrumbs: [], next_offset: null, image_count: 0 };
  const items = state.artworkPickerItems || [];
  target.className = "artwork-picker-pose";
  target.innerHTML = `
    <div class="pose-path-bar">
      <button type="button" data-picker-pose-path="">${escapeHtml(HuashiRooms.directoryLibrary(state.artworkPickerAlbumId).label)}</button>
      ${(data.breadcrumbs || []).map((crumb) => `
        <span>/</span>
        <button type="button" data-picker-pose-path="${escapeAttr(crumb.path)}">${escapeHtml(crumb.name)}</button>
      `).join("")}
    </div>
    ${(data.directories || []).length ? `
      <div class="album-folder-grid pose-folder-grid">
        ${data.directories.map((folder) => `
          <button class="album-folder-card pose-folder-card" type="button" data-picker-pose-path="${escapeAttr(folder.path)}">
            <span class="folder-shape" aria-hidden="true"></span>
            <strong>${escapeHtml(folder.name)}</strong>
            <small>文件夹</small>
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${items.length ? `<div class="artwork-picker-grid">${artworkPickerImageButtons(items)}</div>` : ""}
    ${HuashiPages.markup(data.image_count || 0,state.artworkPickerPage,state.artworkPickerPageSize)}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个素材文件夹没有图片</div>` : ""}
  `;
  target.querySelectorAll("[data-picker-pose-path]").forEach((button) => {
    button.addEventListener("click", () => refreshArtworkPickerPose(button.dataset.pickerPosePath || "").then(renderArtworkPicker));
  });
  HuashiPages.bind(target,async next=>{state.artworkPickerPage=next.page;state.artworkPickerPageSize=next.size;await refreshArtworkPickerPose(state.artworkPickerPosePath,false);renderArtworkPicker();});
  target.querySelectorAll("[data-use-artwork]").forEach((button) => {
    button.addEventListener("click", () => useArtwork(Number(button.dataset.useArtwork || 0)));
  });
}

async function refreshArtworkPickerPose(path, reset = true) {
  const request=++state.artworkPickerRequest;
  state.artworkPickerPosePath=path || "";if(reset)state.artworkPickerPage=0;
  const data=await api(`/api/pose?path=${encodeURIComponent(HuashiRooms.directoryPath(state.artworkPickerAlbumId, state.artworkPickerPosePath))}&offset=${state.artworkPickerPage*state.artworkPickerPageSize}&limit=${state.artworkPickerPageSize}`);
  const items=await HuashiMaterialBag.withDirectoryThumbnails(data.items || []);
  if(request!==state.artworkPickerRequest)return;
  state.artworkPickerPoseData=HuashiRooms.directoryData(state.artworkPickerAlbumId,data);state.artworkPickerItems=items;
}

function renderArtworkFacePicker(target) {
  const data = state.artworkPickerFaceData || { directories: [], items: [], breadcrumbs: [], next_offset: null, image_count: 0 };
  const items = state.artworkPickerItems || [];
  target.className = "artwork-picker-pose artwork-picker-face";
  target.innerHTML = `
    <div class="pose-path-bar">
      <button type="button" data-picker-face-path="">人脸库</button>
      ${(data.breadcrumbs || []).map((crumb) => `
        <span>/</span>
        <button type="button" data-picker-face-path="${escapeAttr(crumb.path)}">${escapeHtml(crumb.name)}</button>
      `).join("")}
    </div>
    ${(data.directories || []).length ? `
      <div class="album-folder-grid pose-folder-grid">
        ${data.directories.map((folder) => `
          <button class="album-folder-card pose-folder-card" type="button" data-picker-face-path="${escapeAttr(folder.path)}">
            <span class="folder-shape" aria-hidden="true"></span>
            <strong>${escapeHtml(folder.name)}</strong>
            <small>文件夹</small>
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${items.length ? `<div class="artwork-picker-grid">${artworkPickerImageButtons(items)}</div>` : ""}
    ${HuashiPages.markup(data.image_count || 0,state.artworkPickerPage,state.artworkPickerPageSize)}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个人脸库文件夹没有图片</div>` : ""}
  `;
  target.querySelectorAll("[data-picker-face-path]").forEach((button) => {
    button.addEventListener("click", () => refreshArtworkPickerFace(button.dataset.pickerFacePath || "").then(renderArtworkPicker));
  });
  HuashiPages.bind(target,async next=>{state.artworkPickerPage=next.page;state.artworkPickerPageSize=next.size;await refreshArtworkPickerFace(state.artworkPickerFacePath,false);renderArtworkPicker();});
  target.querySelectorAll("[data-use-artwork]").forEach((button) => {
    button.addEventListener("click", () => useArtwork(Number(button.dataset.useArtwork || 0)));
  });
}

async function refreshArtworkPickerFace(path, reset = true) {
  const request=++state.artworkPickerRequest;
  state.artworkPickerFacePath=path || "";if(reset)state.artworkPickerPage=0;
  const data=await api(`/api/faces?path=${encodeURIComponent(state.artworkPickerFacePath)}&offset=${state.artworkPickerPage*state.artworkPickerPageSize}&limit=${state.artworkPickerPageSize}`);
  if(request!==state.artworkPickerRequest)return;
  state.artworkPickerFaceData=data;state.artworkPickerItems=data.items || [];
}

function useArtwork(index) {
  const item = (state.artworkPickerItems || [])[index];
  if (!item || !state.selectedArtworkField) return;
  if (state.artworkPickerMode === "promptSample") {
    setPromptSample(item.path || "", item.url || "");
    closeArtworkPicker();
    return;
  }
  const key = state.selectedArtworkField;
  const form = $("createTaskForm");
  const artworkInput = form.querySelector(`[name="${CSS.escape(`input_${key}_artwork`)}"]`);
  if (artworkInput) artworkInput.value = item.path || "";
  showInputPreview(key, item.thumb_url || item.url);
  form.querySelectorAll(`[data-file-input="${CSS.escape(key)}"]`).forEach((input) => {
    input.value = "";
  });
  const label = document.querySelector(`[data-file-label="${CSS.escape(key)}"]`);
  if (label) label.textContent = `作品库：${item.download_name || item.path?.split("/").pop() || "作品"}`;
  closeArtworkPicker();
  updateGenerateState();
}

function renderPrompts() {
  $("promptHubPanel")?.classList.toggle("hidden", Boolean(state.promptSection));
  $("promptToolHint").hidden = true;
  $("promptToolHint").textContent = state.promptTool === "rewrite" ? "选择一条提示词，点击「AI 改写」继续。" : "选择一条提示词，点击「翻译」继续。";
  $("promptLibraryPanel")?.classList.toggle("hidden", state.promptSection !== "library");
  const target = $("promptList");
  if (!target) return;
  renderPromptDirectories();
  if (state.promptFolderError || !state.promptFolderId) {
    target.innerHTML = `<div class="empty-state">${escapeHtml(state.promptFolderError || "正在读取目录…")}</div>`;
    return;
  }
  const prompts = filteredPrompts();
  const page=HuashiPages.windowFor(prompts.length,state.promptPage,state.promptPageSize);state.promptPage=page.page;
  $("promptPagination").innerHTML=HuashiPages.markup(prompts.length,page.page,page.size);
  HuashiPages.bind($("promptPagination"),next=>{state.promptPage=next.page;state.promptPageSize=next.size;renderPrompts();});
  const visibleIds = new Set(prompts.map(prompt => prompt.id));
  state.promptSelected = new Set([...state.promptSelected].filter(id => visibleIds.has(id)));
  renderPromptSelection();
  target.innerHTML = prompts.length
    ? prompts.slice(page.start,page.end).map((prompt) => promptCard(prompt, { mode: "manage", presentation: "grid" })).join("")
    : `<div class="empty-state">${state.promptSearch ? "当前搜索没有匹配结果" : "这个目录还没有提示词，可点击「新建」保存"}</div>`;
  bindPromptListActions(target);
  ensurePromptImages().bind(target);
}

let personalImages=null,personalDetailReturn=null;
function ensurePromptImages(){return personalImages??=HuashiInspirationImages.create({loadEntry:(id,options)=>api('/api/inspiration/v2/entry?id='+encodeURIComponent(id),options),imageURL:u=>typeof u==='string'&&u.startsWith('/')&&!u.startsWith('//')?u:''})}
function closePromptDetail(){const d=$('inspirationDetail');if(d?.dataset.owner==='personal'){HuashiInspirationDetail.release(d);if(d.open)d.close();delete d.dataset.owner;personalImages?.close();personalDetailReturn?.isConnected&&personalDetailReturn.focus({preventScroll:true});}}
function releasePromptPresentation(){closePromptDetail();personalImages?.destroy();personalImages=null;}
async function togglePersonalPromptFavorite(id){
  const p=state.prompts.find(x=>x.id===id);if(!p)throw new Error('提示词暂不可用，请刷新后重试');
  const next=!p.favorite;await api('/api/prompts/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:p.title,content:p.content,tags:p.tags,note:p.note,sample_path:p.sample_path,favorite:next,app_ids:(p.apps||[]).map(a=>a.id)})});
  p.favorite=next;renderPrompts();return next;
}
function openPromptDetail(id){
  const p=state.prompts.find(x=>x.id===id);if(!p)return;
  const d=$('inspirationDetail');ensurePromptImages().hidePreview();if(!d.open)personalDetailReturn=document.activeElement;d.dataset.owner='personal';
  const scratch=document.createElement('div');scratch.innerHTML=promptCard(p,{mode:'manage'});
  const variants=scratch.querySelector('.variant-list')?.outerHTML||'';
  HuashiInspirationDetail.show(d,{id:'prompt:'+p.id,domain:'prompt',kind:'prompt',title:p.title,image:p.sample_url||'',thumbnail:p.sample_url?previewUrl(p):'',category:p.folder_path||'我的提示词',folder_path:p.folder_path,description:p.note||'',tags:p.tags,variants:p.variants,prompts:{original:p.content},source_urls:[]},{
    images:ensurePromptImages(),copy:copyText,toast:showToast,close:closePromptDetail,favorite:p.favorite,toggleFavorite:()=>togglePersonalPromptFavorite(p.id),
    managePrompt:()=>editPrompt(p.id),extraHTML:variants,
    extraActions:`<button class="button" type="button" data-move-prompt="${escapeAttr(p.id)}">移动目录</button><button class="button" type="button" data-agent-prompt="${escapeAttr(p.id)}">局部修改</button><button class="button danger" type="button" data-delete-prompt="${escapeAttr(p.id)}">删除</button>`,
    bindExtra:root=>{bindPromptListActions(root);root.querySelectorAll('[data-move-prompt],[data-agent-prompt],[data-delete-prompt]').forEach(button=>button.addEventListener('click',closePromptDetail,{capture:true}));},
  });
}

function filteredPrompts(source = state.prompts, query = state.promptSearch) {
  const text = String(query || "").trim().toLowerCase();
  if (!state.promptFolderId || state.promptFolderError) return [];
  return HuashiPromptFolders.filterPrompts(source, state.promptFolderId, state.promptAllDirectories).filter((prompt) => {
    if (!text) return true;
    const variantText = (prompt.variants || []).map((variant) => `${variant.title} ${variant.content} ${variant.translation} ${variant.edit_idea}`).join(" ");
    const haystack = `${prompt.title} ${prompt.content} ${variantText} ${(prompt.tags || []).join(" ")} ${(prompt.apps || []).map((app) => app.name).join(" ")}`.toLowerCase();
    return haystack.includes(text);
  });
}

function changePromptDirectory(folderId) {
  if (folderId === state.promptFolderId) return;
  state.promptFolderId = folderId;
  state.promptPage = 0;
  state.promptSelected.clear();
  state.promptAllDirectories = false;
  $("promptSearchAll").checked = false;
  HuashiPromptFolders.remember(folderId);
  if (window.matchMedia("(max-width:760px)").matches) $("promptDirectoryPanel").open = false;
  renderPrompts();
}

function renderPromptDirectories() {
  const directoryData = HuashiPromptFolders.snapshot();
  const current = directoryData?.folders.find(folder => folder.id === state.promptFolderId);
  $("promptDirectoryPath").textContent = state.promptFolderError ? `目录读取失败：${state.promptFolderError}` : current?.path || current?.name || "正在读取目录…";
  $("promptDirectoryCount").textContent = current ? `${Number(current.count || 0)} 条${state.promptAllDirectories ? " · 搜索全部目录" : ""}` : "";
  $("promptDirectoryRetry").hidden = !state.promptFolderError;
  $("newPromptButton").disabled = !current;
  HuashiPromptFolders.mountTree($("promptDirectoryTree"), {api,value:state.promptFolderId,onChange:changePromptDirectory,onMutate:loadData,toast:showToast});
}

function renderPromptSelection() {
  const count = state.promptSelected.size;
  $("promptSelectMode").textContent = state.promptSelecting ? "结束选择" : "选择";
  $("promptSelectVisible").hidden = !state.promptSelecting;
  $("promptMoveSelected").hidden = !state.promptSelecting;
  $("promptMoveSelected").disabled = !count;
  $("promptSelectionCount").textContent = count ? `已选 ${count} 条` : "";
}

function movePromptIds(ids) {
  HuashiPromptFolders.move(ids,{api,value:state.promptFolderId,toast:showToast,onMoved:async () => {state.promptSelected.clear();await loadData();}});
}

function promptCard(prompt, options = {}) {
  const grid = options.presentation === "grid";
  if(grid)return HuashiInspirationPresentation.card({id:'prompt:'+prompt.id,domain:'prompt',title:prompt.title,thumbnail:prompt.sample_url?previewUrl(prompt):'',description:prompt.note,content:prompt.content,tags:prompt.tags,variants:prompt.variants},{attributes:`data-prompt-detail="${escapeAttr(prompt.id)}"`,extraClass:'prompt-card prompt-grid-card',selection:state.promptSelecting?`<label class="reference-card-select"><input type="checkbox" aria-label="选择${escapeAttr(prompt.title)}" data-select-prompt="${escapeAttr(prompt.id)}" ${state.promptSelected.has(prompt.id)?'checked':''}>选择</label>`:''});
  const tags = (prompt.tags || []).slice(0, 4).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  const variants = prompt.variants || [];
  // Only the library changes presentation; pickers retain their existing controls.
  const coverAction = grid ? `data-edit-prompt="${escapeAttr(prompt.id)}" aria-label="${escapeAttr(`查看和编辑：${prompt.title}`)}"` : `data-agent-prompt="${escapeAttr(prompt.id)}"`;
  let excerpt = prompt.content;
  if (grid) {
    try {
      const structured = JSON.parse(prompt.content);
      if (typeof structured?.prompt === "string") excerpt = structured.prompt;
    } catch { /* Plain text prompts keep their original excerpt. */ }
  }
  const sample = prompt.sample_url
    ? `<button class="prompt-sample${grid ? " inspiration-card-cover" : ""}" type="button" ${coverAction}><img loading="lazy" src="${escapeAttr(previewUrl(prompt))}" alt=""></button>`
    : `<button class="prompt-sample empty${grid ? " inspiration-card-cover inspiration-text-cover" : ""}" type="button" ${coverAction}>${grid ? `<span class="prompt-paper-label">文字提示词</span><span class="prompt-paper-title">${escapeHtml(prompt.title)}</span><span class="prompt-paper-rule" aria-hidden="true"></span>` : "提示词"}</button>`;
  const pickButton = options.mode === "picker"
    ? `<button class="tiny-button" type="button" data-use-prompt="${prompt.id}">使用</button>`
    : "";
  const manageButtons = options.mode === "manage"
    ? `
      <button class="tiny-button" type="button" data-copy-prompt="${prompt.id}">复制</button>
      ${grid ? `<button class="tiny-button" type="button" data-edit-prompt="${escapeAttr(prompt.id)}">查看 / 编辑</button>` : ""}
      <details class="prompt-row-menu"><summary>更多</summary><div>
      <button class="tiny-button" type="button" data-agent-prompt="${prompt.id}">局部修改</button>
      <button class="tiny-button" type="button" data-edit-prompt="${prompt.id}">编辑</button>
      <button class="tiny-button" type="button" data-move-prompt="${escapeAttr(prompt.id)}">移动目录</button>
      <button class="tiny-button danger" type="button" data-delete-prompt="${prompt.id}">删除</button>
      </div></details>
    `
    : "";
  return `
    <article class="prompt-card${grid ? " prompt-grid-card inspiration-card" : ""}">
      ${sample}
      <div class="prompt-card-main${grid ? " inspiration-card-body" : ""}">
        ${grid ? `<small class="inspiration-card-meta">提示词 · ${escapeHtml(prompt.folder_path || "我的提示词")}${prompt.favorite ? " · 常用" : ""}</small>` : ""}
        <strong class="${grid ? "inspiration-card-title" : ""}"><button class="prompt-open-text" type="button" data-edit-prompt="${prompt.id}" title="查看和编辑提示词">${escapeHtml(prompt.title)}</button></strong>
        <p class="${grid ? "inspiration-card-summary" : ""}" title="${escapeAttr(prompt.content)}">${escapeHtml(excerpt)}</p>
        <small>使用 ${Number(prompt.use_count || 0)} 次${variants.length ? ` · ${variants.length} 个衍生` : ""}${state.promptAllDirectories ? ` · ${escapeHtml(prompt.folder_path || "目录待确认")}` : ""}</small>
        ${tags ? `<div class="tag-row${grid ? " inspiration-card-tags" : ""}">${tags}</div>` : ""}
        ${variants.length ? `
          <details class="variant-list">
            <summary>查看 AI 衍生提示词</summary>
            ${variants.map((variant) => `
              <article class="variant-card">
                <strong>${escapeHtml(variant.title || "AI 衍生提示词")}</strong>
                ${variant.edit_idea ? `<small>修改：${escapeHtml(variant.edit_idea)}</small>` : ""}
                ${variant.translation ? `
                  <div class="variant-cn">
                    <span>中文</span>
                    <p>${escapeHtml(variant.translation)}</p>
                  </div>
                ` : ""}
                <details class="variant-en">
                  <summary>英文原文</summary>
                  <p>${escapeHtml(variant.content)}</p>
                </details>
                ${variant.explanation_cn || variant.feature_cn ? `
                  <details class="variant-note">
                    <summary>修改说明</summary>
                    ${variant.explanation_cn ? `<p>${escapeHtml(variant.explanation_cn)}</p>` : ""}
                    ${variant.feature_cn ? `<p>${escapeHtml(variant.feature_cn)}</p>` : ""}
                  </details>
                ` : ""}
                <div class="variant-actions">
                  <button class="tiny-button" type="button" data-copy-variant="${escapeAttr(variant.id)}">复制</button>
                  ${options.mode === "picker" ? `<button class="tiny-button" type="button" data-use-variant="${escapeAttr(variant.id)}">使用这段</button>` : ""}
                  ${options.mode === "manage" ? `<button class="tiny-button danger" type="button" data-delete-variant="${escapeAttr(variant.id)}">删除</button>` : ""}
                </div>
              </article>
            `).join("")}
          </details>
        ` : ""}
      </div>
      <div class="prompt-card-actions${grid ? " inspiration-card-actions" : ""}">
        ${options.mode === "manage" && state.promptSelecting ? `<label class="prompt-folder-row-check"><input type="checkbox" aria-label="选择${escapeAttr(prompt.title)}" data-select-prompt="${escapeAttr(prompt.id)}" ${state.promptSelected.has(prompt.id) ? "checked" : ""}>选择</label>` : ""}
        ${prompt.favorite ? `<span class="star-mark">常用</span>` : ""}
        ${pickButton}
        ${manageButtons}
      </div>
    </article>
  `;
}

function bindPromptListActions(root) {
  root.querySelectorAll('[data-prompt-detail]').forEach(button=>button.onclick=()=>openPromptDetail(button.dataset.promptDetail));
  root.querySelectorAll("[data-select-prompt]").forEach(input => input.onchange = () => {
    if (input.checked) state.promptSelected.add(input.dataset.selectPrompt); else state.promptSelected.delete(input.dataset.selectPrompt);
    renderPromptSelection();
  });
  root.querySelectorAll("[data-move-prompt]").forEach(button => button.onclick = () => movePromptIds([button.dataset.movePrompt]));
  root.querySelectorAll("[data-rewrite-prompt]").forEach((button) => {
    button.addEventListener("click", () => openRewriteDrawer(button.dataset.rewritePrompt));
  });
  root.querySelectorAll("[data-translate-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = state.prompts.find((item) => item.id === button.dataset.translatePrompt);
      if (!prompt) return;
      openRewriteDrawer(prompt.id);
      $("rewriteDrawer").dataset.mode = "translate";
      $("rewriteDrawerTitle").textContent = "翻译提示词";
      state.rewriteCandidates = [prompt.content];
      renderRewriteResults(state.rewriteCandidates);
      setRewriteStatus("选择模型后，点击原文下的「翻译」。");
    });
  });
  root.querySelectorAll("[data-edit-prompt]").forEach((button) => {
    button.addEventListener("click", () => editPrompt(button.dataset.editPrompt));
  });
  root.querySelectorAll("[data-delete-prompt]").forEach((button) => {
    button.addEventListener("click", () => deletePrompt(button.dataset.deletePrompt));
  });
  root.querySelectorAll("[data-use-prompt]").forEach((button) => {
    button.addEventListener("click", () => usePrompt(button.dataset.usePrompt));
  });
  root.querySelectorAll("[data-use-variant]").forEach((button) => {
    button.addEventListener("click", () => usePromptVariant(button.dataset.useVariant));
  });
  root.querySelectorAll("[data-copy-prompt]").forEach((button) => {
    button.addEventListener("click", () => copyPrompt(button.dataset.copyPrompt, button));
  });
  root.querySelectorAll("[data-copy-variant]").forEach((button) => {
    button.addEventListener("click", async () => {
      const variant = findPromptVariant(button.dataset.copyVariant)?.variant;
      await copyText(variant?.content || "", button);
    });
  });
  root.querySelectorAll("[data-delete-variant]").forEach((button) => {
    button.addEventListener("click", () => deletePromptVariant(button.dataset.deleteVariant));
  });
  root.querySelectorAll("[data-agent-prompt]").forEach((button) => {
    button.addEventListener("click", () => openAgentDrawer(button.dataset.agentPrompt));
  });
}

async function copyPrompt(promptId, button = null) {
  const prompt = state.prompts.find((item) => item.id === promptId);
  await copyText(prompt?.content || "", button);
}

function openPromptForm(prompt = null) {
  $("promptForm").classList.remove("hidden");
  $("promptIdInput").value = prompt?.id || "";
  $("promptTitleInput").value = prompt?.title || "";
  $("promptContentInput").value = prompt?.content || "";
  $("promptOptionalFields").open=Boolean(prompt?.sample_path || prompt?.note || prompt?.tags?.length || prompt?.favorite);
  $("promptTagsInput").value = (prompt?.tags || []).join(", ");
  $("promptFavoriteInput").checked = Boolean(prompt?.favorite);
  $("promptNoteInput").value = prompt?.note || "";
  setPromptSample(prompt?.sample_path || "", prompt?.sample_url || "");
  const submit = $("promptForm").querySelector('[type="submit"]'); submit.disabled = true;
  state.promptDraftFolderInitial = null;
  state.promptFormFolderControl = HuashiPromptFolders.mountSelector($("promptFormFolder"), {api,value:prompt?.folder_id || state.promptFolderId,onReady:id => {submit.disabled = !id; if (state.promptDraftFolderInitial === null) state.promptDraftFolderInitial = id;}});
  if(!$("promptEditorDialog").open)$("promptEditorDialog").showModal();
  state.promptDraftBaseline = promptDraftFingerprint();
  $("promptTitleInput").focus();
}

function promptDraftFingerprint() {
  return JSON.stringify([$("promptTitleInput").value,$("promptContentInput").value,$("promptTagsInput").value,$("promptFavoriteInput").checked,$("promptNoteInput").value,$("promptSamplePathInput").value]);
}

function closePromptForm(discard = false) {
  if (discard !== true && state.promptDraftBaseline && (promptDraftFingerprint() !== state.promptDraftBaseline || (state.promptDraftFolderInitial !== null && state.promptFormFolderControl?.value !== state.promptDraftFolderInitial))) {
    if (!$("promptDiscardDialog").open) $("promptDiscardDialog").showModal();
    return;
  }
  state.promptDraftBaseline = "";
  if($("promptEditorDialog").open)$("promptEditorDialog").close();
  state.promptFormFolderControl?.destroy(); state.promptFormFolderControl = null;
  $("promptForm").classList.add("hidden");
  $("promptForm").reset();
  $("promptIdInput").value = "";
  setPromptSample("", "");
}

function editPrompt(promptId) {
  closePromptDetail();
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (prompt) openPromptForm(prompt);
}

async function deletePrompt(promptId) {
  if (!confirm("删除这条提示词？")) return;
  try {
    await api(`/api/prompts/${promptId}`, { method: "DELETE" });
    await loadData();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function promptFormPayload() {
  const folderId = state.promptFormFolderControl?.value;
  if (!folderId) throw new Error("请先选择可用的保存目录");
  return {
    folder_id: folderId,
    title: $("promptTitleInput").value.trim(),
    content: $("promptContentInput").value.trim(),
    tags: $("promptTagsInput").value.trim(),
    favorite: $("promptFavoriteInput").checked,
    note: $("promptNoteInput").value.trim(),
    sample_path: $("promptSamplePathInput").value.trim(),
    app_ids: [],
  };
}

async function uploadPromptSample(input) {
  const file=input.files?.[0];if(!file)return;
  const request=++state.promptSampleRequest;
  const submit=$('promptForm').querySelector('[type="submit"]');submit.disabled=true;input.disabled=true;
  const form=new FormData();form.append('image',file);
  try {
    const {item}=await api('/api/albums/upload',{method:'POST',body:form});
    if(request===state.promptSampleRequest && !$('promptForm').classList.contains('hidden'))setPromptSample(item.path,item.url);
    const {folders}=await api('/api/albums');state.albums=folders;
    showToast('配图已上传到待整理','info');
  }catch(error){showToast(error.message,'error');}
  finally{input.value='';input.disabled=false;submit.disabled=!state.promptFormFolderControl?.value;}
}

function setPromptSample(path, url = "") {
  ++state.promptSampleRequest;
  $("promptSamplePathInput").value = path || "";
  const preview = $("promptSamplePreview");
  if (!path) {
    preview.innerHTML = "配图";
    return;
  }
  const imageUrl = url || `/files/${path}`;
  preview.innerHTML = `<img src="${escapeAttr(imageUrl)}" alt="">`;
}

function openPromptPicker(inputId) {
  state.selectedPromptField = inputId;
  state.pickerSearch = "";
  $('promptPicker').classList.remove('hidden');
  $('promptPicker').setAttribute('aria-hidden', 'false');
  renderPromptPicker();
  $('pickerSearchInput').focus();
}

function closePromptPicker() {
  $('pickerPromptList').roomSearch?.destroy();
  $('promptPicker').classList.add('hidden');
  $('promptPicker').setAttribute('aria-hidden', 'true');
  state.selectedPromptField = '';
}

function renderPromptPicker() {
  if ($('promptPicker').classList.contains('hidden')) return;
  HuashiSearch.mount($('pickerPromptList'), {api, copy:copyText, picker:true, usePrompt(content, {mode="replace"}={}) {
    const key=state.selectedPromptField;
    if (key==='portraitBasePrompt') usePortraitBasePrompt(HuashiCreation.mergePrompt(state.portraitBasePrompt || "",content,mode));
    else {
      const field=$('createTaskForm').querySelector(`[name="${CSS.escape(`input_${key}`)}"]`);
      if (!field) {showToast('当前画布没有这个提示词字段','error');return;}
      field.value=HuashiCreation.mergePrompt(field.value,field.tagName==='INPUT' ? content.replace(/\r?\n/g," ") : content,mode,field.tagName==='INPUT' ? " " : "\n\n");field.dispatchEvent(new Event('input',{bubbles:true}));
    }
    closePromptPicker();showToast(mode==='append'?'已追加到提示词':'已替换提示词','info');
  }}, {query:state.pickerSearch,kind:'prompt',offset:0});
}

async function usePrompt(promptId) {
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (!prompt || !state.selectedPromptField) return;
  if (state.selectedPromptField === "portraitBasePrompt") {
    usePortraitBasePrompt(prompt.content || "");
    closePromptPicker();
    try {
      const { prompt: updated } = await api(`/api/prompts/${promptId}/use`, { method: "POST" });
      state.prompts = state.prompts.map((item) => item.id === updated.id ? updated : item);
    } catch (_error) {
      // 使用成功比计数更重要，计数失败不打断生成流程。
    }
    return;
  }
  const field = $("createTaskForm").querySelector(`[name="${CSS.escape(`input_${state.selectedPromptField}`)}"]`);
  if (field) {
    field.value = prompt.content;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  closePromptPicker();
  try {
    const { prompt: updated } = await api(`/api/prompts/${promptId}/use`, { method: "POST" });
    state.prompts = state.prompts.map((item) => item.id === updated.id ? updated : item);
  } catch (_error) {
    // 使用成功比计数更重要，计数失败不打断生成流程。
  }
}

async function usePromptVariant(variantId) {
  const found = findPromptVariant(variantId);
  if (!found || !state.selectedPromptField) return;
  if (state.selectedPromptField === "portraitBasePrompt") {
    usePortraitBasePrompt(found.variant.content || "");
    closePromptPicker();
    try {
      const { prompt } = await api(`/api/prompt-variants/${variantId}/use`, { method: "POST" });
      state.prompts = state.prompts.map((item) => item.id === prompt.id ? prompt : item);
    } catch (_error) {
      // 使用成功比计数更重要，计数失败不打断生成流程。
    }
    return;
  }
  const field = $("createTaskForm").querySelector(`[name="${CSS.escape(`input_${state.selectedPromptField}`)}"]`);
  if (field) {
    field.value = found.variant.content;
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
  closePromptPicker();
  try {
    const { prompt } = await api(`/api/prompt-variants/${variantId}/use`, { method: "POST" });
    state.prompts = state.prompts.map((item) => item.id === prompt.id ? prompt : item);
  } catch (_error) {
    // 使用成功比计数更重要，计数失败不打断生成流程。
  }
}

function findPromptVariant(variantId) {
  for (const prompt of state.prompts) {
    const variant = (prompt.variants || []).find((item) => item.id === variantId);
    if (variant) return { prompt, variant };
  }
  return null;
}

async function deletePromptVariant(variantId) {
  if (!confirm("删除这条 AI 衍生提示词？")) return;
  try {
    const { prompt } = await api(`/api/prompt-variants/${variantId}`, { method: "DELETE" });
    state.prompts = state.prompts.map((item) => item.id === prompt.id ? prompt : item);
    renderPrompts();
    // The shared search drawer keeps its query and selected kind during background updates.
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function renderRewriteModels() {
  const input = $("rewriteModelInput");
  if (!input) return;
  input.innerHTML = state.promptModels
    .map((model) => `
      <option value="${escapeAttr(model.id)}" ${model.default ? "selected" : ""} ${model.available ? "" : "disabled"}>
        ${escapeHtml(model.label)}${model.available ? "" : "（未配置）"}
      </option>
    `)
    .join("");
}

function renderAgentModels() {
  const input = $("agentModelInput");
  if (!input) return;
  input.innerHTML = state.promptModels
    .map((model) => {
      const selected = model.default;
      return `
        <option value="${escapeAttr(model.id)}" ${selected ? "selected" : ""} ${model.available ? "" : "disabled"}>
          ${escapeHtml(model.label)}${model.available ? "" : "（未配置）"}
        </option>
      `;
    })
    .join("");
}

async function ensurePortraitData() {
  if(window.HuashiMaterialBag){HuashiMaterialBag.mount();return;}
  if (state.portraitLoading) return;
  state.portraitLoading = true;
  setPortraitStatus("正在读取素材库...");
  try {
    if (!state.portraitSlots.length) {
      const { slots } = await api("/api/portrait/slots");
      state.portraitSlots = slots || [];
    }
    if (!state.portraitCatalogItems.length) await loadPortraitCatalog();
    await loadPortraitMaterials(true);
    setPortraitStatus("");
  } catch (error) {
    setPortraitStatus(error.message, "error");
  } finally {
    state.portraitLoading = false;
    renderPortrait();
  }
}

async function loadPortraitCatalog() {
  const cached = readPortraitCatalogCache();
  if (cached) {
    state.portraitCatalogItems = cached.items || [];
    state.portraitCategories = cached.categories || [];
    return;
  }
  const items = [];
  let offset = 0;
  let categories = [];
  while (offset !== null) {
    const result = await api(`/api/portrait/materials?limit=160&offset=${offset}`);
    items.push(...(result.items || []));
    categories = result.categories || categories;
    offset = result.next_offset;
  }
  state.portraitCatalogItems = items;
  state.portraitCategories = categories;
  writePortraitCatalogCache({ items, categories });
}

async function loadPortraitMaterials(reset = false) {
  const step = currentPortraitStep();
  if (step?.final) {
    state.portraitMaterials = [];
    state.portraitNextOffset = null;
    return;
  }
  if(reset)state.portraitPage=0;
  const allItems=filteredPortraitStepItems(step),w=HuashiPages.windowFor(allItems.length,state.portraitPage,state.portraitPageSize);
  state.portraitPage=w.page;state.portraitMaterials=allItems.slice(w.start,w.end);
  state.portraitNextOffset=null;
}

function readPortraitCatalogCache() {
  try {
    const raw = window.localStorage?.getItem(PORTRAIT_CATALOG_CACHE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || Date.now() - Number(data.savedAt || 0) > PORTRAIT_CATALOG_CACHE_TTL_MS) return null;
    if (!Array.isArray(data.items) || !Array.isArray(data.categories)) return null;
    return data;
  } catch (_error) {
    return null;
  }
}

function writePortraitCatalogCache(data) {
  try {
    window.localStorage?.setItem(PORTRAIT_CATALOG_CACHE_KEY, JSON.stringify({ ...data, savedAt: Date.now() }));
  } catch (_error) {
    // 本地缓存不可用时不影响正常使用。
  }
}

function renderPortrait() {
  if(window.HuashiMaterialBag){HuashiMaterialBag.mount();return;}
  if (!$("portraitMaterialGrid")) return;
  renderPortraitImport();
  renderPortraitSlotEditor();
  renderPortraitFlow();
  renderPortraitStepHeader();
  renderPortraitMaterials();
  renderPortraitSummary();
  renderPortraitModels();
  renderPortraitResult();
  $("portraitSelectedSummary").textContent = selectedPortraitCount() ? `${selectedPortraitCount()} 个素材` : "未选择";
  $("portraitGenerateButton").disabled = !portraitCanGenerate() || state.portraitLoading;
  $("portraitSlotDrawer").classList.toggle("hidden", !state.portraitDrawerOpen);
  $("portraitSlotDrawer").setAttribute("aria-hidden", state.portraitDrawerOpen ? "false" : "true");
}

function renderPortraitImport() {
  const body = $("portraitImportBody");
  if (!body) return;
  body.classList.toggle("hidden", !state.portraitImportOpen);
  if ($("portraitImportToggleButton")) $("portraitImportToggleButton").textContent = state.portraitImportOpen ? "收起" : "展开";
  if ($("portraitImportPromptInput") && $("portraitImportPromptInput") !== document.activeElement) {
    $("portraitImportPromptInput").value = state.portraitImportPrompt || "";
  }
  const result = $("portraitImportResult");
  if (!result) return;
  if (!state.portraitImportAnalysis) {
    result.classList.add("hidden");
    result.innerHTML = "";
    return;
  }
  result.classList.remove("hidden");
  result.innerHTML = portraitImportResultHtml();
  bindPortraitImportControls(result);
}

function portraitImportResultHtml() {
  const analysis = state.portraitImportAnalysis || {};
  const drafts = portraitImportSlotDrafts();
  const filledCount = drafts.filter((draft) => draft.values.length).length;
  const suggestionCount = drafts.reduce((sum, draft) => sum + draft.suggestions.length, 0);
  return `
    <div class="portrait-import-summary">
      <div>
        <strong>已填入 ${filledCount} 个槽位</strong>
        <p>${escapeHtml(analysis.summary || "原提示词已作为融合底稿保留；可在下面的槽位编辑器里调整。")}</p>
      </div>
      <small>${suggestionCount ? `${suggestionCount} 个建议已进入下拉` : "可继续用素材补强"}</small>
    </div>
    <details class="portrait-import-locked">
      <summary>查看原文翻译和默认保留项</summary>
      ${analysis.translation_cn ? `<p><b>中文翻译：</b>${escapeHtml(analysis.translation_cn)}</p>` : ""}
      ${(analysis.locked_context || []).length ? `<p><b>保留：</b>${escapeHtml((analysis.locked_context || []).join("、"))}</p>` : ""}
      ${analysis.guide ? `<p><b>修改建议：</b>${escapeHtml(analysis.guide)}</p>` : ""}
    </details>
  `;
}

function portraitImportDraftHtml(draft, index) {
  const value = draft.values.length ? draft.values.join("、") : "这个槽位还没有明确原值";
  const suggestions = draft.suggestions.slice(0, 4);
  return `
    <article class="portrait-import-draft ${draft.values.length ? "" : "is-empty"}">
      <div class="portrait-import-item-head">
        <strong>${escapeHtml(draft.label)}</strong>
        <span>${draft.values.length ? "已填入" : "可补强"}</span>
      </div>
      <p>${escapeHtml(value)}</p>
      <div class="portrait-import-suggestions">
        ${draft.values.length ? `<button type="button" data-portrait-import-apply-draft="${index}" data-portrait-import-value="${escapeAttr(draft.values.join("、"))}">用草稿</button>` : ""}
        ${suggestions.map((suggestion) => `
          <button type="button" data-portrait-import-apply-draft="${index}" data-portrait-import-value="${escapeAttr(suggestion)}">${escapeHtml(suggestion)}</button>
        `).join("")}
      </div>
      <div class="portrait-import-item-actions">
        ${draft.categoryName ? `<button class="tiny-button" type="button" data-portrait-import-focus-draft="${index}">去选${escapeHtml(draft.label)}素材</button>` : ""}
      </div>
    </article>
  `;
}

function bindPortraitImportControls(root) {
  root.querySelectorAll("[data-portrait-import-apply-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      const draft = portraitImportSlotDrafts()[Number(button.dataset.portraitImportApplyDraft || 0)];
      applyPortraitImportValue(portraitImportDraftItem(draft), button.dataset.portraitImportValue || draft?.values?.join("、") || "");
    });
  });
  root.querySelectorAll("[data-portrait-import-focus-draft]").forEach((button) => {
    button.addEventListener("click", () => focusPortraitImportDraft(Number(button.dataset.portraitImportFocusDraft || 0)));
  });
}

function renderPortraitSlotEditor() {
  const target = $("portraitSlotEditor");
  if (!target) return;
  const steps = portraitSteps().filter((step) => !step.final);
  if (!steps.length) {
    target.innerHTML = `<div class="empty-state compact-empty">素材槽位加载中</div>`;
    return;
  }
  target.innerHTML = `
    <div class="portrait-slot-editor-head">
      <div>
        <strong>槽位编辑</strong>
        <p>先用文字下拉快速定方向；需要看图时再打开对应图库。</p>
      </div>
      <div class="portrait-slot-editor-actions">
        <span>${selectedPortraitCount()} 个素材</span>
        <button class="primary-button" type="button" data-portrait-inline-generate ${portraitCanGenerate() && !state.portraitLoading ? "" : "disabled"}>生成</button>
      </div>
    </div>
    <div class="portrait-slot-rows">
      ${steps.map((step, index) => portraitSlotEditorRow(step, index)).join("")}
    </div>
    <div class="portrait-slot-extra">
      <label class="portrait-slot-wide-field">
        <span>整体补充</span>
        <textarea id="portraitGlobalIdeaInput" rows="2" placeholder="例如：整体更清冷，场景更高级，避免低俗和网红感">${escapeHtml(state.portraitManual.global || "")}</textarea>
      </label>
      <label class="portrait-slot-wide-field">
        <span class="portrait-field-head">
          融合成熟提示词（可选）
          <button class="tiny-button" id="portraitChooseBasePromptButton" type="button">从提示词库选</button>
        </span>
        <textarea id="portraitBasePromptInput" rows="3" placeholder="粘贴一段成熟提示词；不填就是直接根据素材生成">${escapeHtml(state.portraitBasePrompt || "")}</textarea>
      </label>
    </div>
  `;
  target.querySelectorAll("[data-portrait-slot-select]").forEach((select) => {
    select.addEventListener("change", async () => {
      const step = portraitSteps().find((item) => item.id === select.dataset.portraitSlotSelect);
      await selectPortraitSlotOption(step, select.value);
    });
  });
  target.querySelectorAll("[data-portrait-slot-manual]").forEach((input) => {
    input.addEventListener("input", (event) => {
      state.portraitManual[event.currentTarget.dataset.portraitSlotManual] = event.currentTarget.value;
      syncPortraitInputs();
    });
  });
  target.querySelectorAll("[data-portrait-slot-clear]").forEach((button) => {
    button.addEventListener("click", () => clearPortraitStepSelection(button.dataset.portraitSlotClear));
  });
  target.querySelectorAll("[data-portrait-editor-step]").forEach((button) => {
    button.addEventListener("click", () => goPortraitStep(Number(button.dataset.portraitEditorStep || 0)));
  });
  target.querySelector("[data-portrait-inline-generate]")?.addEventListener("click", generatePortraitPrompt);
  $("portraitGlobalIdeaInput")?.addEventListener("input", syncPortraitGlobalIdea);
  $("portraitBasePromptInput")?.addEventListener("input", syncPortraitBasePrompt);
  $("portraitChooseBasePromptButton")?.addEventListener("click", () => openPromptPicker("portraitBasePrompt"));
}

function portraitSlotEditorRow(step, index) {
  const manualKey = stepManualKey(step);
  const selected = portraitSelectedItemsForCategory(step.category?.name);
  const value = selected.length === 1 ? `material:${selected[0].id}` : (selected.length > 1 ? "__mixed__" : "");
  const active = index === state.portraitStepIndex ? "active" : "";
  const mode = portraitStepSelectionMode(step) === "multi" ? "可多选" : "单选";
  return `
    <article class="portrait-slot-row ${active}">
      <button class="portrait-slot-jump" type="button" data-portrait-editor-step="${index}">
        <span>${index + 1}</span>
        <strong>${escapeHtml(step.title)}</strong>
        <small>${mode}</small>
      </button>
      <select data-portrait-slot-select="${escapeAttr(step.id)}" aria-label="${escapeAttr(step.title)}">
        ${portraitSlotOptionsHtml(step, value)}
      </select>
      <input data-portrait-slot-manual="${escapeAttr(manualKey)}" value="${escapeAttr(state.portraitManual[manualKey] || "")}" placeholder="手写补充" />
      <button class="tiny-button" type="button" data-portrait-slot-clear="${escapeAttr(step.category?.name || "")}">清空</button>
    </article>
  `;
}

function portraitSlotOptionsHtml(step, selectedValue) {
  const options = new Map();
  options.set("", "未选择");
  if (selectedValue === "__mixed__") options.set("__mixed__", "已选多项，继续添加或清空");
  portraitSelectedItemsForCategory(step.category?.name).forEach((item) => options.set(`material:${item.id}`, item.title_cn || "已选素材"));
  portraitDraftsForCategory(step.category?.name).forEach((draft) => {
    [...draft.values, ...draft.suggestions].slice(0, 8).forEach((text) => options.set(`manual:${text}`, `建议：${text}`));
  });
  portraitItemsForCategory(step.category?.name).slice(0, 220).forEach((item) => {
    const prefix = item.slot && item.slot !== cleanPortraitCategoryName(step.category?.name) ? `${item.slot} · ` : "";
    options.set(`material:${item.id}`, `${prefix}${item.title_cn || item.title_en || "素材"}`);
  });
  return [...options.entries()].map(([value, label]) => `
    <option value="${escapeAttr(value)}" ${value === selectedValue ? "selected" : ""}>${escapeHtml(label)}</option>
  `).join("");
}

function portraitItemsForCategory(categoryName) {
  return (state.portraitCatalogItems || []).filter((item) => item.category === categoryName);
}

function portraitSelectedItemsForCategory(categoryName) {
  return Object.values(state.portraitSelected)
    .flat()
    .filter((item) => item.category === categoryName);
}

function portraitDraftsForCategory(categoryName) {
  return portraitImportSlotDrafts().filter((draft) => draft.categoryName === categoryName);
}

function portraitStepSelectionMode(step) {
  const name = String(step?.category?.name || "");
  if (name.startsWith("06_") || name.startsWith("07_") || name.startsWith("09_")) return "multi";
  return "single";
}

function portraitStepAutoAdvance(step) {
  return portraitStepSelectionMode(step) === "single";
}

async function selectPortraitSlotOption(step, value) {
  if (!step) return;
  if (!value) {
    clearPortraitStepSelection(step.category?.name);
    return;
  }
  if (value === "__mixed__") return;
  if (value.startsWith("manual:")) {
    state.portraitManual[stepManualKey(step)] = value.slice("manual:".length);
    renderPortrait();
    syncPortraitInputs();
    return;
  }
  if (!value.startsWith("material:")) return;
  const item = (state.portraitCatalogItems || []).find((entry) => entry.id === value.slice("material:".length));
  if (!item) return;
  addPortraitMaterial(item, { replaceCategory: portraitStepSelectionMode(step) === "single" });
  renderTitle();
  renderPortrait();
}

function clearPortraitStepSelection(categoryName) {
  if (!categoryName) return;
  removePortraitMaterialsByCategory(categoryName);
  state.portraitManual[`category:${categoryName}`] = "";
  renderPortrait();
  syncPortraitInputs();
}

function renderPortraitFlow() {
  const steps = portraitSteps();
  const current = currentPortraitStep();
  if ($("portraitFlowProgress")) $("portraitFlowProgress").textContent = steps.length ? `第 ${state.portraitStepIndex + 1}/${steps.length} 步` : "读取中";
  if ($("portraitStepList")) {
    $("portraitStepList").innerHTML = steps.length
      ? steps.map((step, index) => `
        <button class="portrait-step-item ${index === state.portraitStepIndex ? "active" : ""} ${portraitStepDone(step) ? "done" : ""}" type="button" data-portrait-step="${index}">
          <span>${index + 1}</span>
          <strong>${escapeHtml(step.title)}</strong>
          <small>${escapeHtml(portraitStepSubtitle(step))}</small>
        </button>
      `).join("")
      : `<div class="empty-state compact-empty">正在读取素材目录</div>`;
    $("portraitStepList").querySelectorAll("[data-portrait-step]").forEach((button) => {
      button.addEventListener("click", () => goPortraitStep(Number(button.dataset.portraitStep || 0)));
    });
  }
  if ($("portraitSearchInput")) $("portraitSearchInput").value = state.portraitQuery;
  if ($("portraitMobileSearchInput")) $("portraitMobileSearchInput").value = state.portraitQuery;
  if ($("portraitPrevStepButton")) $("portraitPrevStepButton").disabled = state.portraitStepIndex <= 0 || state.portraitLoading;
  if ($("portraitNextStepButton")) $("portraitNextStepButton").textContent = current?.final ? "回到开头" : "下一步";
}

function renderPortraitStepHeader() {
  const step = currentPortraitStep();
  if (!step) {
    $("portraitStepKicker").textContent = "素材选择";
    $("portraitStepTitle").textContent = "读取素材中";
    $("portraitStepHint").textContent = "素材库加载后会自动进入第一步。";
    $("portraitStepManualBox").innerHTML = "";
    return;
  }
  $("portraitStepKicker").textContent = step.final ? "最后补充" : portraitStepCountLabel(step);
  $("portraitStepTitle").textContent = step.title;
  $("portraitStepHint").textContent = step.final
    ? "这里可以直接生成，也可以粘贴成熟提示词，让 AI 把你的素材需求融进去。"
    : "先看配图和提示片段，点“查看图片”看完整素材；单选目录选中后自动进入下一步。";
  if (step.final) {
    $("portraitStepManualBox").innerHTML = `
      <div class="portrait-final-box">
        <label class="field-block">
          <span>最后补充</span>
          <textarea id="portraitStepGlobalInput" rows="3" placeholder="例如：整体更清冷，像高级商业杂志封面">${escapeHtml(state.portraitManual.global || "")}</textarea>
        </label>
        <label class="field-block">
          <span class="portrait-field-head">
            融合成熟提示词（可选）
            <button class="tiny-button" type="button" data-portrait-base-prompt-picker>从提示词库选</button>
          </span>
          <textarea id="portraitStepBasePromptInput" rows="5" placeholder="粘贴一段成熟提示词；不填就是直接根据素材生成">${escapeHtml(state.portraitBasePrompt || "")}</textarea>
        </label>
      </div>
    `;
    $("portraitStepGlobalInput")?.addEventListener("input", syncPortraitGlobalIdea);
    $("portraitStepBasePromptInput")?.addEventListener("input", syncPortraitBasePrompt);
    $("portraitStepManualBox")?.querySelector("[data-portrait-base-prompt-picker]")?.addEventListener("click", () => openPromptPicker("portraitBasePrompt"));
    return;
  }
  const manualKey = stepManualKey(step);
  $("portraitStepManualBox").innerHTML = `
    ${portraitSubgroupControls(step)}
    <label class="portrait-step-note">
      <span>这个步骤也可以手写</span>
      <input id="portraitStepManualInput" value="${escapeAttr(state.portraitManual[manualKey] || "")}" placeholder="没有喜欢的图，就写一个想法" />
    </label>
  `;
  $("portraitStepManualInput")?.addEventListener("input", (event) => {
    state.portraitManual[manualKey] = event.currentTarget.value;
    syncPortraitInputs();
  });
  $("portraitStepManualBox")?.querySelectorAll("[data-portrait-group]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.portraitActiveGroups[step.category.name] = button.dataset.portraitGroup || "";
      await reloadPortraitMaterials();
    });
  });
}

function renderPortraitMaterials() {
  const target = $("portraitMaterialGrid");
  if (!target) return;
  const step = currentPortraitStep();
  if (step?.final) {
    target.innerHTML = portraitFinalReviewHtml();
  } else {
    const skip = step ? portraitSkipCard(step) : "";
    const preview = step ? portraitPreviewHtml(step) : "";
    target.innerHTML = state.portraitMaterials.length
      ? `${preview}${skip}${state.portraitMaterials.map(portraitMaterialCard).join("")}`
      : `${preview}${skip}<div class="empty-state portrait-empty">当前步骤没有素材，直接跳过即可。</div>`;
  }
  target.querySelectorAll("[data-portrait-material]").forEach((button) => {
    button.addEventListener("click", () => togglePortraitMaterial(button.dataset.portraitMaterial));
  });
  target.querySelectorAll("[data-portrait-preview]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openPortraitReference(button.dataset.portraitPreview || "");
    });
  });
  target.querySelector("[data-close-portrait-preview]")?.addEventListener("click", () => {
    state.portraitPreviewId = "";
    renderPortraitMaterials();
  });
  target.querySelector("[data-portrait-skip]")?.addEventListener("click", () => nextPortraitStep());
  target.querySelector("[data-portrait-final-generate]")?.addEventListener("click", generatePortraitPrompt);
  ensurePromptImages().bind(target);
  $("portraitLoadMoreButton").hidden=true;
  const pager=$("portraitPagination");pager.hidden=Boolean(step?.final);
  if(!step?.final){pager.innerHTML=HuashiPages.markup(filteredPortraitStepItems(step).length,state.portraitPage,state.portraitPageSize);HuashiPages.bind(pager,async next=>{state.portraitPage=next.page;state.portraitPageSize=next.size;await loadPortraitMaterials(false);renderPortraitMaterials();});}
}

function portraitSkipCard(step) {
  return `
    <button class="portrait-material-card portrait-skip-card" type="button" data-portrait-skip>
      <span class="portrait-skip-icon">跳过</span>
      <span class="portrait-material-title">这个目录先不选</span>
      <small>${escapeHtml(step.title)}</small>
    </button>
  `;
}

function portraitPreviewHtml(step) {
  const item = state.portraitPreviewId
    ? state.portraitMaterials.find((entry) => entry.id === state.portraitPreviewId && portraitItemInStep(entry, step))
    : null;
  if (!item) return "";
  return `
    <article class="portrait-preview-card">
      <button class="tiny-button" type="button" data-close-portrait-preview>收起预览</button>
      <img loading="lazy" src="${escapeAttr(item.image_url)}" alt="">
      <div>
        <strong>${escapeHtml(item.title_cn || "素材")}</strong>
        <p>${escapeHtml(item.prompt_hint_cn || item.prompt_cn || item.title_en || "")}</p>
      </div>
    </article>
  `;
}

function portraitMaterialCard(item) {
  const selected = isPortraitSelected(item.id),title=item.title_cn || "素材";
  return `
    <article class="portrait-material-card inspiration-card reference-card ${selected ? "selected" : ""}">
      <button class="portrait-material-image inspiration-card-cover reference-cover" type="button" data-preview-image data-full-thumb="${escapeAttr(item.image_url)}" data-full-title="${escapeAttr(title)}" data-preview-caption="完整构图 · 点击查看详情" data-portrait-preview="${escapeAttr(item.id)}" aria-label="查看完整图片：${escapeAttr(title)}">
        <img loading="lazy" decoding="async" src="${escapeAttr(item.image_url)}" alt="${escapeAttr(title)}">
      </button>
      <div class="inspiration-card-body reference-card-copy">
        <strong class="portrait-material-title inspiration-card-title">${escapeHtml(title)}</strong>
        <p class="inspiration-card-summary">${escapeHtml(item.prompt_hint_cn || item.prompt_cn || item.title_en || "打开图片查看素材细节。")}</p>
      </div>
      <div class="portrait-material-actions inspiration-card-actions">
        <button type="button" data-portrait-preview="${escapeAttr(item.id)}">查看图片</button>
        <button type="button" data-portrait-material="${escapeAttr(item.id)}" aria-pressed="${selected}">${selected ? "✓ 已选" : "＋ 选择"}</button>
      </div>
    </article>
  `;
}

function openPortraitReference(id){
  const item=state.portraitMaterials.find(x=>x.id===id);if(!item)return;
  const d=$('inspirationDetail');ensurePromptImages().hidePreview();personalDetailReturn=document.activeElement;d.dataset.owner='personal';
  HuashiInspirationDetail.show(d,{id:'portrait:'+id,domain:'portrait',title:item.title_cn||'人像素材',image:item.image_url,category:item.slot||item.category,description:item.prompt_hint_cn||item.prompt_cn||'',prompts:{zh:item.prompt_hint_cn||item.prompt_cn||'',en:item.prompt_hint_en||''},source_urls:[]},{images:ensurePromptImages(),copy:copyText,toast:showToast,close:closePromptDetail,primaryHTML:`<button type="button" class="button" data-select-portrait-reference>${isPortraitSelected(id)?'移出已选':'选择素材'}</button>`,bindExtra:root=>{root.querySelector('[data-select-portrait-reference]').onclick=()=>{closePromptDetail();togglePortraitMaterial(id);}}});
}

function portraitFinalReviewHtml() {
  return `
    <div class="portrait-final-review">
      <strong>已经过完一遍素材</strong>
      <p>现在可以直接生成，或者粘贴一段成熟提示词，让模型把你选的素材和补充想法融入进去。</p>
      <button class="primary-button" type="button" data-portrait-final-generate>生成提示词</button>
    </div>
  `;
}

function renderPortraitSummary() {
  const html = portraitSummaryHtml();
  if ($("portraitSlotList")) $("portraitSlotList").innerHTML = html;
  if ($("portraitDrawerSlotList")) $("portraitDrawerSlotList").innerHTML = html;
  bindPortraitSummaryControls($("portraitSlotList"));
  bindPortraitSummaryControls($("portraitDrawerSlotList"));
}

function portraitSummaryHtml() {
  if (!state.portraitSlots.length) return `<div class="empty-state compact-empty">素材槽位加载中</div>`;
  const knownManualKeys = new Set(["global", ...state.portraitSlots.map((slot) => slot.id)]);
  const slotSections = state.portraitSlots
    .filter((slot) => slot.id !== "negative")
    .map((slot) => {
      const selected = state.portraitSelected[slot.id] || [];
      const manual = state.portraitManual[slot.id] || "";
      if (!selected.length && !manual.trim()) return "";
      return `
        <section class="portrait-summary-group">
          <div class="portrait-slot-head">
            <span>${escapeHtml(slot.label)}</span>
            <small>${selected.length}${manual.trim() ? " + 手写" : ""}</small>
          </div>
          <div class="portrait-selected-chips">
            ${selected.map((item) => `
              <button class="portrait-chip" type="button" data-remove-portrait-material="${escapeAttr(item.id)}">
                ${escapeHtml(item.title_cn)} <b>×</b>
              </button>
            `).join("")}
            ${manual.trim() ? `
              <button class="portrait-chip is-manual" type="button" data-clear-portrait-manual="${escapeAttr(slot.id)}">
                ${escapeHtml(manual.trim())} <b>×</b>
              </button>
            ` : ""}
          </div>
        </section>
      `;
    })
    .join("");
  const manualSections = Object.entries(state.portraitManual || {})
    .filter(([key, value]) => !knownManualKeys.has(key) && String(value || "").trim())
    .map(([key, value]) => `
      <section class="portrait-summary-group">
        <div class="portrait-slot-head">
          <span>${escapeHtml(portraitManualKeyLabel(key))}</span>
          <small>手写</small>
        </div>
        <div class="portrait-selected-chips">
          <button class="portrait-chip is-manual" type="button" data-clear-portrait-manual="${escapeAttr(key)}">
            ${escapeHtml(String(value || "").trim())} <b>×</b>
          </button>
        </div>
      </section>
    `)
    .join("");
  const sections = `${slotSections}${manualSections}`;
  return sections || `<div class="empty-state compact-empty">还没选素材。按步骤点喜欢的图，或在步骤里手写。</div>`;
}

function bindPortraitSummaryControls(root) {
  if (!root) return;
  root.querySelectorAll("[data-remove-portrait-material]").forEach((button) => {
    button.addEventListener("click", () => removePortraitMaterial(button.dataset.removePortraitMaterial));
  });
  root.querySelectorAll("[data-clear-portrait-manual]").forEach((button) => {
    button.addEventListener("click", () => {
      state.portraitManual[button.dataset.clearPortraitManual] = "";
      renderPortrait();
      syncPortraitInputs();
    });
  });
}

function renderPortraitModels() {
  const input = $("portraitModelInput");
  if (!input) return;
  input.innerHTML = state.promptModels
    .map((model) => `
      <option value="${escapeAttr(model.id)}" ${model.default ? "selected" : ""} ${model.available ? "" : "disabled"}>
        ${escapeHtml(model.label)}${model.available ? "" : "（未配置）"}
      </option>
    `)
    .join("");
}

function renderPortraitResult() {
  const result = state.portraitResult;
  const targets = [$("portraitResult"), $("portraitMobileResult")].filter(Boolean);
  if (!result) {
    targets.forEach((target) => {
      target.className = target.id === "portraitMobileResult" ? "portrait-mobile-result-panel portrait-result empty-state" : "portrait-result empty-state";
      target.innerHTML = "选择素材或输入想法后生成";
    });
    return;
  }
  const html = portraitResultHtml(result);
  targets.forEach((target) => {
    target.className = target.id === "portraitMobileResult" ? "portrait-mobile-result-panel portrait-result" : "portrait-result";
    target.innerHTML = html;
    bindPortraitResultControls(target);
  });
}

function portraitResultHtml(result) {
  const importApps = promptCapableApps();
  const defaultAppId = (appPromptInput(selectedApp()) ? selectedApp()?.id : importApps[0]?.id) || "";
  return `
    <div class="portrait-result-toolbar">
      <button class="secondary-button" type="button" data-save-portrait-prompt>保存到预设</button>
      <div class="portrait-import-control">
        <select data-portrait-app-target ${importApps.length ? "" : "disabled"}>
          ${importApps.length
            ? importApps.map((app) => `<option value="${escapeAttr(app.id)}" ${app.id === defaultAppId ? "selected" : ""}>${escapeHtml(app.name)}</option>`).join("")
            : `<option value="">暂无可填提示词的应用</option>`}
        </select>
        <button class="primary-button" type="button" data-import-portrait-prompt ${importApps.length ? "" : "disabled"}>导入应用</button>
      </div>
    </div>
    <article class="portrait-result-card">
      <div class="portrait-result-head">
        <strong>中文提示词</strong>
        <button class="tiny-button" type="button" data-copy-portrait="prompt_cn">复制</button>
      </div>
      <p>${escapeHtml(result.prompt_cn)}</p>
    </article>
    <article class="portrait-result-card">
      <div class="portrait-result-head">
        <strong>英文生图提示词</strong>
        <button class="tiny-button" type="button" data-copy-portrait="prompt_en">复制</button>
      </div>
      <p>${escapeHtml(result.prompt_en)}</p>
    </article>
    <article class="portrait-result-card">
      <div class="portrait-result-head">
        <strong>负面提示词</strong>
        <button class="tiny-button" type="button" data-copy-portrait="negative_prompt">复制</button>
      </div>
      <p>${escapeHtml(result.negative_prompt)}</p>
    </article>
    ${result.safety_note_cn ? `<div class="portrait-safe-note">${escapeHtml(result.safety_note_cn)}</div>` : ""}
    ${(result.next_steps_cn || []).length ? `
      <div class="portrait-next">
        <strong>下一步可以这样改</strong>
        ${(result.next_steps_cn || []).map((item) => `<button type="button" data-portrait-next="${escapeAttr(item)}">${escapeHtml(item)}</button>`).join("")}
      </div>
    ` : ""}
  `;
}

function bindPortraitResultControls(target) {
  if (!target) return;
  target.querySelector("[data-save-portrait-prompt]")?.addEventListener("click", (event) => {
    savePortraitPromptPreset(event.currentTarget);
  });
  target.querySelector("[data-import-portrait-prompt]")?.addEventListener("click", (event) => {
    const select = target.querySelector("[data-portrait-app-target]");
    importPortraitPromptToApp(select?.value || "", event.currentTarget);
  });
  target.querySelectorAll("[data-copy-portrait]").forEach((button) => {
    button.addEventListener("click", async () => {
      await copyText(state.portraitResult?.[button.dataset.copyPortrait] || "", button);
    });
  });
  target.querySelectorAll("[data-portrait-next]").forEach((button) => {
    button.addEventListener("click", () => {
      state.portraitManual.global = button.dataset.portraitNext || "";
      syncPortraitInputs();
      $("portraitGlobalIdeaInput")?.focus();
      $("portraitStepGlobalInput")?.focus();
    });
  });
}

function portraitPromptContent() {
  const result = state.portraitResult || {};
  return String(result.prompt_en || result.prompt_cn || "").trim();
}

async function savePortraitPromptPreset(button = null) {
  const content = portraitPromptContent();
  if (!content) {
    showToast("没有可保存的提示词", "error");
    return;
  }
  const result = state.portraitResult || {};
  const noteParts = [
    result.prompt_cn ? `中文：${result.prompt_cn}` : "",
    result.negative_prompt ? `负面提示词：${result.negative_prompt}` : "",
    result.safety_note_cn ? `说明：${result.safety_note_cn}` : "",
  ].filter(Boolean);
  HuashiCreation.savePrompt(content, state.prompts, {
    api,toast:showToast,folderId:state.promptFolderId,
    title:`人像提示词 ${formatTime(new Date().toISOString())}`,
    tags:"人像, 人像工坊",note:noteParts.join("\n\n"),
    saved:prompt => {
      state.prompts = [prompt, ...state.prompts.filter(item => item.id !== prompt.id)];
      flashButtonLabel(button,"已保存");
      HuashiPromptFolders.refresh(api).then(renderPrompts).catch(error => showToast(error.message,"error"));
    },
  });
}

function importPortraitPromptToApp(appId, button = null) {
  const content = portraitPromptContent();
  if (!content) {
    showToast("没有可导入的提示词", "error");
    return;
  }
  const app = state.apps.find((item) => item.id === appId);
  if (!app || !appPromptInput(app)) {
    showToast("这个应用没有可填写的提示词字段", "error");
    return;
  }
  state.selectedAppId = app.id;
  state.pendingComposePrompt = content;
  flashButtonLabel(button, "已导入");
  setNotice(`已导入到 ${app.name}，可继续补图或生成。`, "info");
  setView("compose");
}

async function togglePortraitMaterial(id) {
  const item = state.portraitMaterials.find((entry) => entry.id === id);
  if (!item) return;
  if (isPortraitSelected(id)) {
    removePortraitMaterial(id);
    return;
  }
  const step = currentPortraitStep();
  const added = addPortraitMaterial(item, { replaceCategory: portraitStepSelectionMode(step) === "single" });
  if (!added) return;
  renderTitle();
  renderPortrait();
  if (portraitStepAutoAdvance(step)) await nextPortraitStep();
}

function addPortraitMaterial(item, options = {}) {
  if (!item) return false;
  const slotId = item.slot_id || "uncategorized";
  const slotInfo = portraitSlotById(slotId);
  const limit = Number(slotInfo?.limit || 1);
  if (options.replaceCategory && item.category) {
    removePortraitMaterialsByCategory(item.category);
    state.portraitManual[`category:${item.category}`] = "";
  }
  const selected = state.portraitSelected[slotId] || [];
  if (selected.length >= limit) {
    showToast(`${slotInfo?.label || item.slot} 最多选 ${limit} 个`, "error");
    return false;
  }
  const conflict = portraitConflict(slotInfo, item, selected);
  if (conflict) {
    showToast(`可能冲突：${conflict}。可先移除旧素材再选。`, "error");
    return false;
  }
  state.portraitSelected[slotId] = [...selected, item];
  return true;
}

function removePortraitMaterial(id) {
  Object.keys(state.portraitSelected).forEach((slotId) => {
    state.portraitSelected[slotId] = (state.portraitSelected[slotId] || []).filter((item) => item.id !== id);
  });
  renderTitle();
  renderPortrait();
}

function removePortraitMaterialsByCategory(categoryName) {
  Object.keys(state.portraitSelected).forEach((slotId) => {
    state.portraitSelected[slotId] = (state.portraitSelected[slotId] || []).filter((item) => item.category !== categoryName);
  });
}

function portraitConflict(slotInfo, item, selected) {
  const text = `${item.title_cn} ${(item.tags || []).join(" ")}`;
  for (const rule of slotInfo?.conflicts || []) {
    const hit = (rule.keywords || []).find((keyword) => text.includes(keyword));
    if (!hit) continue;
    const old = selected.find((entry) => (rule.keywords || []).some((keyword) => `${entry.title_cn} ${(entry.tags || []).join(" ")}`.includes(keyword)) && !`${entry.title_cn} ${(entry.tags || []).join(" ")}`.includes(hit));
    if (old) return `${old.title_cn} / ${item.title_cn}`;
  }
  return "";
}

function isPortraitSelected(id) {
  return Object.values(state.portraitSelected).some((items) => (items || []).some((item) => item.id === id));
}

function selectedPortraitCount() {
  return Object.values(state.portraitSelected).reduce((sum, items) => sum + (items || []).length, 0);
}

function portraitCanGenerate() {
  return selectedPortraitCount() > 0 || Object.values(state.portraitManual).some((value) => String(value || "").trim()) || state.portraitBasePrompt.trim();
}

function portraitSlotById(slotId) {
  return state.portraitSlots.find((slot) => slot.id === slotId);
}

function setPortraitStatus(message, kind = "info") {
  [$("portraitStatus"), $("portraitMobileStatus")].filter(Boolean).forEach((target) => {
    target.classList.toggle("hidden", !message);
    target.dataset.kind = kind;
    target.textContent = message || "";
  });
}

async function reloadPortraitMaterials() {
  state.portraitLoading = true;
  renderPortrait();
  try {
    await loadPortraitMaterials(true);
  } catch (error) {
    setPortraitStatus(error.message, "error");
  } finally {
    state.portraitLoading = false;
    renderPortrait();
  }
}

async function goPortraitStep(index) {
  const steps = portraitSteps();
  if (!steps.length) return;
  state.portraitStepIndex = Math.max(0, Math.min(index, steps.length - 1));
  state.portraitQuery = "";
  state.portraitPreviewId = "";
  if (currentPortraitStep()?.final) {
    state.portraitMaterials = [];
    state.portraitNextOffset = null;
    renderPortrait();
    return;
  }
  await reloadPortraitMaterials();
}

async function nextPortraitStep() {
  const steps = portraitSteps();
  if (!steps.length) return;
  if (state.portraitStepIndex >= steps.length - 1) {
    await goPortraitStep(0);
    return;
  }
  await goPortraitStep(state.portraitStepIndex + 1);
}

async function prevPortraitStep() {
  await goPortraitStep(state.portraitStepIndex - 1);
}

async function loadMorePortraitMaterials() {
  if (state.portraitNextOffset === null || state.portraitLoading) return;
  state.portraitLoading = true;
  renderPortrait();
  try {
    await loadPortraitMaterials(false);
  } catch (error) {
    setPortraitStatus(error.message, "error");
  } finally {
    state.portraitLoading = false;
    renderPortrait();
  }
}

function usePortraitBasePrompt(content) {
  state.portraitBasePrompt = content || "";
  syncPortraitInputs();
  renderPortrait();
  showToast("已填入成熟提示词", "info");
}

function syncPortraitImportPrompt(event) {
  state.portraitImportPrompt = event.currentTarget.value;
}

async function analyzePortraitImportPrompt() {
  const prompt = String(state.portraitImportPrompt || "").trim();
  if (!prompt) {
    setPortraitStatus("先粘贴一段提示词。", "error");
    return;
  }
  state.portraitLoading = true;
  setPortraitStatus("正在拆解提示词，并映射到人像槽位...");
  renderPortrait();
  try {
    const payload = await api("/api/prompt-agent/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        model: $("portraitModelInput")?.value || "",
      }),
    });
    state.portraitImportAnalysis = payload.analysis || null;
    state.portraitImportMappedItems = mapPortraitImportItems(state.portraitImportAnalysis);
    applyPortraitImportAnalysis(prompt);
    setPortraitStatus("已拆到人像槽位。你可以直接生成，也可以点建议或去对应目录换素材。", "info");
  } catch (error) {
    setPortraitStatus(error.message, "error");
  } finally {
    state.portraitLoading = false;
    renderPortrait();
  }
}

function applyPortraitImportAnalysis(prompt) {
  state.portraitBasePrompt = prompt;
  state.portraitImportMappedItems.forEach((item) => {
    if (item.slotId && item.slotId !== "global" && portraitImportUsefulText(item.original)) {
      applyPortraitImportValue(item, item.original, { quiet: true, append: true });
    }
  });
  syncPortraitInputs();
}

function mapPortraitImportItems(analysis) {
  const items = Array.isArray(analysis?.editable_items) ? analysis.editable_items : [];
  return items.map((item) => {
    const mapping = portraitImportMapping(item);
    return {
      id: item.id || "",
      label: item.label || mapping.label,
      original: item.original || "",
      placeholder: item.placeholder || "",
      suggestions: Array.isArray(item.suggestions) ? item.suggestions.filter(portraitImportUsefulText).slice(0, 5) : [],
      slotId: mapping.slotId,
      slotLabel: mapping.label,
      categoryName: mapping.categoryName,
      manualKey: mapping.manualKey,
      searchText: item.original || item.placeholder || "",
    };
  });
}

function portraitImportMapping(item) {
  const id = String(item?.id || "").toLowerCase();
  const label = String(item?.label || "");
  const text = `${id} ${label}`.toLowerCase();
  if (text.includes("hair") || label.includes("发型") || label.includes("发色")) {
    return portraitImportSlot("appearance", "发型", "02_发型");
  }
  if (text.includes("expression") || text.includes("mood") || label.includes("表情") || label.includes("神情") || label.includes("气质")) {
    return portraitImportSlot("appearance", "表情", "08_表情");
  }
  if (text.includes("person") || text.includes("subject") || label.includes("人物") || label.includes("身份")) {
    return portraitImportSlot("subject", "人物", "01_人物");
  }
  if (text.includes("clothing") || text.includes("outfit") || label.includes("服") || label.includes("穿")) {
    return portraitImportSlot("clothing", "服饰", "03_服饰");
  }
  if (text.includes("pose") || text.includes("action") || label.includes("姿势") || label.includes("动作")) {
    return portraitImportSlot("pose", "姿势", "04_姿势");
  }
  if (text.includes("camera") || text.includes("shot") || text.includes("angle") || label.includes("镜头") || label.includes("景别") || label.includes("角度") || label.includes("构图")) {
    return portraitImportSlot("camera", "镜头", "06_镜头");
  }
  if (text.includes("light") || label.includes("光") || label.includes("时间")) {
    return portraitImportSlot("lighting", "光线", "07_光线");
  }
  if (text.includes("scene") || text.includes("location") || label.includes("场景") || label.includes("地点") || label.includes("背景")) {
    return portraitImportSlot("scene", "场景", "05_场景");
  }
  if (text.includes("prop") || label.includes("道具") || label.includes("细节")) {
    return portraitImportSlot("scene", "细节", "09_细节");
  }
  if (text.includes("quality") || text.includes("style") || text.includes("color") || label.includes("画感") || label.includes("画质") || label.includes("质感") || label.includes("色彩") || label.includes("氛围")) {
    return portraitImportSlot("image_feel", "画感", "");
  }
  return { slotId: "global", label: "补充", categoryName: "", manualKey: "global" };
}

function portraitImportSlot(slotId, label, categoryName) {
  return { slotId, label, categoryName, manualKey: categoryName ? `category:${categoryName}` : slotId };
}

function portraitImportUsefulText(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  const normalized = text.toLowerCase();
  const weakValues = new Set(["无", "无明确", "未明确", "未指定", "未明确指定", "不明确", "none", "n/a", "na", "随机", "自然", "普通", "保持原样", "原样"]);
  if (weakValues.has(normalized)) return false;
  if (/^(无|未明确|未指定|不明确)/.test(text)) return false;
  return true;
}

function portraitImportSlotDrafts() {
  const order = ["01_人物", "02_发型", "03_服饰", "04_姿势", "05_场景", "06_镜头", "07_光线", "08_表情", "09_细节", "image_feel", "global"];
  const groups = new Map();
  (state.portraitImportMappedItems || []).forEach((item) => {
    const key = item.categoryName || item.manualKey || item.slotId || "global";
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        label: item.slotLabel || item.label || "补充",
        manualKey: item.manualKey || "global",
        slotId: item.slotId || "global",
        categoryName: item.categoryName || "",
        values: [],
        suggestions: [],
      });
    }
    const group = groups.get(key);
    if (portraitImportUsefulText(item.original) && !group.values.includes(item.original)) group.values.push(item.original);
    (item.suggestions || []).forEach((suggestion) => {
      if (portraitImportUsefulText(suggestion) && !group.values.includes(suggestion) && !group.suggestions.includes(suggestion)) {
        group.suggestions.push(suggestion);
      }
    });
  });
  return [...groups.values()]
    .filter((group) => group.values.length || group.suggestions.length)
    .sort((a, b) => {
      const ai = order.indexOf(a.categoryName || a.slotId || a.key);
      const bi = order.indexOf(b.categoryName || b.slotId || b.key);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
}

function portraitImportDraftItem(draft) {
  if (!draft) return null;
  return {
    manualKey: draft.manualKey || draft.slotId || "global",
    slotId: draft.slotId || "global",
    slotLabel: draft.label || "槽位",
    categoryName: draft.categoryName || "",
  };
}

function applyPortraitImportValue(item, value, options = {}) {
  const text = String(value || "").trim();
  if (!item || !text) return;
  const key = item.manualKey || item.slotId || `import:${item.label || "补充"}`;
  if (options.append) {
    const old = String(state.portraitManual[key] || "").trim();
    state.portraitManual[key] = old && !old.includes(text) ? `${old}、${text}` : (old || text);
  } else {
    state.portraitManual[key] = text;
  }
  if (!options.quiet) {
    syncPortraitInputs();
    renderPortrait();
    showToast(`已填入${item.slotLabel || "槽位"}`, "info");
  }
}

async function focusPortraitImportDraft(index) {
  const draft = portraitImportSlotDrafts()[index];
  if (!draft) return;
  const categoryName = draft.categoryName;
  if (!categoryName) {
    const value = draft.values[0] || draft.suggestions[0] || "";
    if (value) state.portraitManual[draft.manualKey || "global"] = value;
    renderPortrait();
    return;
  }
  const steps = portraitSteps();
  const targetIndex = steps.findIndex((step) => step.category?.name === categoryName);
  if (targetIndex >= 0) {
    await goPortraitStep(targetIndex);
    state.portraitQuery = "";
  }
}

function clearPortraitImport() {
  state.portraitImportPrompt = "";
  state.portraitImportAnalysis = null;
  state.portraitImportMappedItems = [];
  if ($("portraitImportPromptInput")) $("portraitImportPromptInput").value = "";
  renderPortrait();
  setPortraitStatus("已清空导入解析，已选素材和手写槽位会保留。", "info");
}

async function generatePortraitPrompt() {
  if (!portraitCanGenerate()) {
    setPortraitStatus("先选择素材，或至少写一个想法。", "error");
    return;
  }
  state.portraitLoading = true;
  state.portraitResult = null;
  setPortraitStatus("正在组织素材并生成一条提示词...");
  renderPortrait();
  try {
    const result = await api("/api/portrait/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected: state.portraitSelected,
        manual: state.portraitManual,
        base_prompt: state.portraitBasePrompt,
        model: $("portraitModelInput").value,
      }),
    });
    state.portraitResult = result;
    setPortraitStatus("已生成。英文可直接复制去生图，中文方便你检查。", "info");
  } catch (error) {
    setPortraitStatus(error.message, "error");
  } finally {
    state.portraitLoading = false;
    renderPortrait();
  }
}

function portraitSteps() {
  const categories = state.portraitCategories || [];
  return [
    ...categories.map((category) => ({
      id: category.name,
      title: cleanPortraitCategoryName(category.name),
      category,
      final: false,
    })),
    { id: "__final__", title: "最后补充", final: true },
  ];
}

function currentPortraitStep() {
  const steps = portraitSteps();
  return steps[Math.min(state.portraitStepIndex, Math.max(steps.length - 1, 0))] || null;
}

function filteredPortraitStepItems(step) {
  if (!step || step.final) return [];
  const query = state.portraitQuery.trim().toLowerCase();
  return (state.portraitCatalogItems || [])
    .filter((item) => portraitItemInStep(item, step))
    .filter((item) => {
      if (!query) return true;
      return `${item.title_cn} ${item.title_en} ${item.category} ${item.slot}`.toLowerCase().includes(query);
    });
}

function portraitItemInStep(item, step) {
  if (!step?.category || item.category !== step.category.name) return false;
  const groupId = state.portraitActiveGroups[step.category.name] || "";
  return !groupId || groupId === portraitSubgroupId(step.category.name, item);
}

function portraitSubgroupControls(step) {
  if (!step?.category) return "";
  const items = (state.portraitCatalogItems || []).filter((item) => item.category === step.category.name);
  const groups = portraitSubgroups(step.category.name, items);
  if (!groups.length) return "";
  const active = state.portraitActiveGroups[step.category.name] || "";
  return `
    <div class="portrait-subgroup-strip">
      <button class="${!active ? "active" : ""}" type="button" data-portrait-group="">全部 ${items.length}</button>
      ${groups.map((group) => `
        <button class="${active === group.id ? "active" : ""}" type="button" data-portrait-group="${escapeAttr(group.id)}">
          ${escapeHtml(group.title)} ${Number(group.count || 0)}
        </button>
      `).join("")}
    </div>
  `;
}

function portraitSubgroups(categoryName, items) {
  const definitions = portraitSubgroupDefinitions(categoryName);
  const counts = new Map();
  items.forEach((item) => {
    const groupId = portraitSubgroupId(categoryName, item);
    counts.set(groupId, (counts.get(groupId) || 0) + 1);
  });
  return definitions
    .map((definition) => ({ ...definition, count: counts.get(definition.id) || 0 }))
    .filter((definition) => definition.count > 0);
}

function portraitSubgroupId(categoryName, item) {
  const text = `${item.title_cn || ""} ${item.title_en || ""}`.toLowerCase();
  const definitions = portraitSubgroupDefinitions(categoryName);
  const hit = definitions.find((definition) => (definition.keywords || []).some((keyword) => text.includes(keyword.toLowerCase())));
  return hit?.id || "other";
}

function portraitSubgroupDefinitions(categoryName) {
  const name = String(categoryName || "");
  if (name.startsWith("01_")) {
    return [
      subgroup("everyday", "日韩日常", ["日韩", "日常", "通勤", "刚入职", "清爽", "自然", "japanese", "korean", "everyday", "commuter"]),
      subgroup("fresh", "清新温柔", ["清新", "温柔", "邻家", "年轻", "休息", "fresh", "soft", "gentle", "young"]),
      subgroup("urban", "都市轻熟", ["都市", "轻熟", "画廊", "成熟", "urban", "elegant", "gallery", "polished"]),
      subgroup("literary", "文艺清冷", ["文艺", "清冷", "电影", "安静", "literary", "cool", "cinematic", "quiet"]),
      subgroup("special", "特色身份", ["古典", "缪斯", "演员", "度假", "classical", "muse", "actress", "resort"]),
      subgroup("other", "其他人物", []),
    ];
  }
  if (name.startsWith("02_")) {
    return [
      subgroup("long", "长发", ["长发", "长直", "波浪", "大波浪", "好莱坞", "及腰", "long"]),
      subgroup("medium", "中长发", ["中长", "锁骨", "及肩", "lob", "medium", "shoulder"]),
      subgroup("short", "短发", ["短发", "波波", "寸头", "底削", "pixie", "bob", "short"]),
      subgroup("updo", "盘发马尾", ["发髻", "丸子", "马尾", "盘发", "髻", "bun", "ponytail", "updo"]),
      subgroup("braid", "编发", ["辫", "braid"]),
      subgroup("bangs", "刘海分线", ["刘海", "中分", "侧分", "八字", "part", "bang"]),
      subgroup("other", "其他发型", []),
    ];
  }
  if (name.startsWith("03_")) {
    return [
      subgroup("dress", "连衣裙礼服", ["裙", "礼服", "dress", "gown"]),
      subgroup("top", "衬衫上衣", ["衬衫", "上衣", "吊带", "背心", "shirt", "blouse", "top", "camisole"]),
      subgroup("outer", "外套针织", ["外套", "针织", "开衫", "西装", "coat", "cardigan", "knit", "jacket", "blazer"]),
      subgroup("suit", "套装裤装", ["套装", "裤", "西裤", "suit", "pants", "trousers"]),
      subgroup("hanfu", "国风古风", ["汉服", "旗袍", "敦煌", "古", "国风", "hanfu", "qipao"]),
      subgroup("vacation", "泳装度假", ["泳", "比基尼", "沙滩", "bikini", "swim", "beach"]),
      subgroup("material", "材质细节", ["真丝", "薄纱", "缎", "纱", "蕾丝", "皮革", "silk", "satin", "lace", "sheer"]),
      subgroup("other", "其他服饰", []),
    ];
  }
  if (name.startsWith("04_")) {
    return [
      subgroup("stand", "站姿", ["站", "standing"]),
      subgroup("sit", "坐姿", ["坐", "sitting", "seated"]),
      subgroup("hand", "手部动作", ["手", "整理", "触碰", "抬手", "hand"]),
      subgroup("walk", "行走动态", ["走", "跑", "转身", "动态", "walking", "motion"]),
      subgroup("lean", "倚靠侧身", ["倚", "靠", "侧身", "lean", "side"]),
      subgroup("lie", "躺卧", ["躺", "卧", "reclining", "lying"]),
      subgroup("backside", "背影回眸", ["背", "回眸", "背影", "back", "glance"]),
      subgroup("other", "其他姿势", []),
    ];
  }
  if (name.startsWith("05_")) {
    return [
      subgroup("indoor", "室内日常", ["白墙", "窗边", "卧室", "客厅", "房间", "床", "white room", "window", "bedroom", "living"]),
      subgroup("street", "街边咖啡", ["街", "咖啡", "通勤", "neighborhood", "street", "cafe"]),
      subgroup("outdoor", "公园户外", ["公园", "树", "海", "沙滩", "park", "tree", "coastal", "beach"]),
      subgroup("hotel", "酒店民宿", ["酒店", "民宿", "公寓", "hotel", "apartment"]),
      subgroup("studio", "影棚画廊", ["影棚", "画廊", "studio", "gallery"]),
      subgroup("night", "夜景雨天", ["夜", "雨", "天台", "rooftop", "night", "rain"]),
      subgroup("other", "其他场景", []),
    ];
  }
  if (name.startsWith("06_")) {
    return [
      subgroup("shot", "景别", ["特写", "半身", "全身", "近景", "中景", "close", "full", "medium"]),
      subgroup("angle", "角度", ["俯拍", "仰拍", "平视", "低角度", "高角度", "angle"]),
      subgroup("lens", "焦段", ["mm", "广角", "长焦", "镜头", "lens", "wide", "telephoto"]),
      subgroup("composition", "构图", ["构图", "居中", "留白", "三分", "composition", "negative space"]),
      subgroup("view", "视角运动", ["自拍", "视角", "跟拍", "俯视", "pov", "selfie", "tracking"]),
      subgroup("other", "其他镜头", []),
    ];
  }
  if (name.startsWith("07_")) {
    return [
      subgroup("natural", "自然窗光", ["自然光", "窗", "日光", "daylight", "window", "natural"]),
      subgroup("soft", "柔光", ["柔", "雾", "散射", "soft", "mist", "diffused"]),
      subgroup("side", "侧光逆光", ["侧光", "逆光", "轮廓", "rim", "backlight", "side light"]),
      subgroup("time", "晨昏夜光", ["晨", "黄昏", "夜", "月光", "sunset", "night", "moon", "morning"]),
      subgroup("studio", "棚拍明暗", ["伦勃朗", "棚", "硬光", "主光", "rembrandt", "studio", "key light"]),
      subgroup("other", "其他光线", []),
    ];
  }
  if (name.startsWith("08_")) {
    return [
      subgroup("smile", "微笑", ["笑", "smile"]),
      subgroup("bright", "元气自然", ["元气", "清新", "自然", "明朗", "bright", "fresh", "natural"]),
      subgroup("gentle", "温柔平静", ["温柔", "平静", "安静", "serene", "calm", "gentle", "quiet"]),
      subgroup("cool", "清冷", ["清冷", "冷", "cool", "cold"]),
      subgroup("calm", "清冷平静", ["清冷", "平静", "冷", "serene", "calm", "cold"]),
      subgroup("side", "回眸侧脸", ["回眸", "侧脸", "侧", "profile", "glance"]),
      subgroup("down", "低头闭眼", ["低头", "闭眼", "垂眸", "closed", "downcast"]),
      subgroup("lazy", "慵懒神秘", ["慵懒", "神秘", "lazy", "mysterious"]),
      subgroup("heavy", "忧郁强情绪", ["忧郁", "脆弱", "悲伤", "凶", "melancholy", "vulnerable", "sad", "fierce"]),
      subgroup("other", "其他表情", []),
    ];
  }
  if (name.startsWith("09_")) {
    return [
      subgroup("hair", "发饰", ["发夹", "发卡", "发带", "丝巾", "簪", "步摇", "帽", "头纱", "珍珠", "珠宝", "clip", "scarf", "pin", "hat", "pearl"]),
      subgroup("wall", "墙面窗帘", ["白墙", "墙", "窗帘", "窗影", "wall", "curtain", "shadow"]),
      subgroup("furniture", "家具床品", ["床", "床品", "木椅", "地板", "wood", "bedding", "chair", "floor"]),
      subgroup("table", "桌面花束", ["咖啡", "台灯", "花束", "桌", "coffee", "lamp", "flower", "table"]),
      subgroup("glass", "玻璃水汽", ["玻璃", "水汽", "镜", "steam", "glass", "mirror"]),
      subgroup("ground", "地面反光", ["地面", "石材", "反光", "floor", "reflective", "stone"]),
      subgroup("other", "其他细节", []),
    ];
  }
  return [subgroup("all", cleanPortraitCategoryName(categoryName), [])];
}

function subgroup(id, title, keywords) {
  return { id, title, keywords };
}

function portraitStepCountLabel(step) {
  const total = filteredPortraitStepItems(step).length;
  const visible = Math.min(state.portraitMaterials.length, total);
  return `${visible}${state.portraitNextOffset !== null ? `/${total}` : ""} 个素材`;
}

function stepSlotId(step) {
  const sample = state.portraitMaterials.find((item) => item.category === step?.category?.name);
  if (sample) return sample.slot_id || "uncategorized";
  const name = step?.category?.name || "";
  if (name.startsWith("01_")) return "subject";
  if (name.startsWith("02_") || name.startsWith("08_")) return "appearance";
  if (name.startsWith("03_")) return "clothing";
  if (name.startsWith("04_")) return "pose";
  if (name.startsWith("05_")) return "scene";
  if (name.startsWith("06_")) return "camera";
  if (name.startsWith("07_")) return "lighting";
  if (name.startsWith("09_")) return "appearance";
  return "uncategorized";
}

function stepManualKey(step) {
  if (step?.category?.name) return `category:${step.category.name}`;
  return stepSlotId(step);
}

function cleanPortraitCategoryName(name) {
  return String(name || "素材").replace(/^\d+_/, "");
}

function portraitManualKeyLabel(key) {
  if (String(key || "").startsWith("step:")) return String(key).split(":", 2)[1] || "手写补充";
  if (String(key || "").startsWith("category:")) return cleanPortraitCategoryName(String(key).split(":", 2)[1]);
  return portraitSlotById(key)?.label || key;
}

function portraitStepSubtitle(step) {
  if (step.final) return portraitCanGenerate() ? "可以生成" : "补充想法";
  const selected = Object.values(state.portraitSelected)
    .flat()
    .filter((item) => item.category === step.category?.name)
    .length;
  const manual = state.portraitManual[stepManualKey(step)]?.trim();
  if (selected || manual) return selected ? `已选 ${selected}` : "已手写";
  return `${Number(step.category?.count || 0)} 张`;
}

function portraitStepDone(step) {
  if (step.final) return Boolean(state.portraitManual.global?.trim() || state.portraitBasePrompt.trim());
  return portraitStepSubtitle(step).startsWith("已");
}

function syncPortraitGlobalIdea(event) {
  state.portraitManual.global = event.currentTarget.value;
  syncPortraitInputs();
}

function syncPortraitBasePrompt(event) {
  state.portraitBasePrompt = event.currentTarget.value;
  syncPortraitInputs();
}

function syncPortraitInputs() {
  if ($("portraitGlobalIdeaInput")) $("portraitGlobalIdeaInput").value = state.portraitManual.global || "";
  if ($("portraitBasePromptInput")) $("portraitBasePromptInput").value = state.portraitBasePrompt || "";
  if ($("portraitStepGlobalInput")) $("portraitStepGlobalInput").value = state.portraitManual.global || "";
  if ($("portraitStepBasePromptInput")) $("portraitStepBasePromptInput").value = state.portraitBasePrompt || "";
  $("portraitGenerateButton").disabled = !portraitCanGenerate() || state.portraitLoading;
  document.querySelectorAll("[data-portrait-inline-generate]").forEach((button) => {
    button.disabled = !portraitCanGenerate() || state.portraitLoading;
  });
  renderTitle();
}

function openRewriteDrawer(promptId) {
  showToast("翻译和改写已下线，请手动编辑提示词","info");return;
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (!prompt) return;
  $("rewriteDrawer").dataset.mode = "rewrite";
  $("rewriteDrawerTitle").textContent = "AI 改写提示词";
  state.rewritingPromptId = promptId;
  $("rewritePromptTitle").textContent = prompt.title || "提示词";
  $("rewritePromptPreview").textContent = prompt.content || "";
  $("rewriteIdeaInput").value = "";
  $("rewriteStatus").classList.add("hidden");
  $("rewriteStream").classList.add("hidden");
  $("rewriteStream").textContent = "";
  state.rewriteCandidates = [];
  state.rewriteTranslations = {};
  $("rewriteResults").innerHTML = "";
  renderRewriteModels();
  $("rewriteDrawer").classList.remove("hidden");
  $("rewriteDrawer").setAttribute("aria-hidden", "false");
  $("rewriteIdeaInput").focus();
}

function closeRewriteDrawer() {
  $("rewriteDrawer").classList.add("hidden");
  $("rewriteDrawer").setAttribute("aria-hidden", "true");
  state.rewritingPromptId = "";
}

async function runPromptRewrite() {
  const prompt = state.prompts.find((item) => item.id === state.rewritingPromptId);
  const idea = $("rewriteIdeaInput").value.trim();
  if (!prompt) return;
  if (!idea) {
    setRewriteStatus("先写一下你想怎么改。", "error");
    return;
  }
  $("rewriteButton").disabled = true;
  state.rewriteCandidates = [];
  state.rewriteTranslations = {};
  $("rewriteResults").innerHTML = "";
  $("rewriteStream").textContent = "";
  $("rewriteStream").classList.remove("hidden");
  setRewriteStatus("正在发送请求...");
  try {
    const response = await fetch("/api/prompts/rewrite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt.content,
        idea,
        model: $("rewriteModelInput").value,
        count: Number($("rewriteCountInput").value || 3),
      }),
    });
    if (!response.ok || !response.body) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `请求失败：${response.status}`);
    }
    await readPromptAIStream(response.body, {
      onStatus: (message) => setRewriteStatus(message),
      onToken: (_text, fullText) => {
        $("rewriteStream").textContent = displayRewriteStream(fullText);
        $("rewriteStream").scrollTop = $("rewriteStream").scrollHeight;
      },
      onDone: (event, fullText) => {
        setRewriteStatus("已生成，可直接复制喜欢的候选。", "info");
        const candidates = event.candidates || splitLocalCandidates(fullText);
        renderRewriteResults(candidates);
        if ($("rewriteAutoTranslateInput").checked) autoTranslateEnglishCandidates(candidates);
      },
    });
  } catch (error) {
    setRewriteStatus(error.message, "error");
  } finally {
    $("rewriteButton").disabled = false;
  }
}

async function readPromptAIStream(body, handlers = {}) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      let event = {};
      try {
        event = JSON.parse(line);
      } catch (_error) {
        continue;
      }
      if (event.type === "status") handlers.onStatus?.(event.message);
      if (event.type === "token") {
        fullText += event.text || "";
        handlers.onToken?.(event.text || "", fullText);
      }
      if (event.type === "done") {
        handlers.onDone?.(event, fullText);
      }
      if (event.type === "error") {
        handlers.onError?.(event.message);
        throw new Error(event.message || "模型返回错误");
      }
    }
  }
}

function renderRewriteResults(candidates) {
  state.rewriteCandidates = candidates;
  $("rewriteResults").innerHTML = candidates.length
    ? candidates.map((item, index) => `
      <article class="rewrite-card">
        <strong>候选 ${index + 1}</strong>
        <p>${escapeHtml(item)}</p>
        <div class="rewrite-actions">
          <button class="secondary-button" type="button" data-copy-rewrite="${index}">复制</button>
          <button class="secondary-button" type="button" data-translate-rewrite="${index}">翻译</button>
          <button class="secondary-button" type="button" data-save-rewrite="${index}">存回原词</button>
        </div>
        ${state.rewriteTranslations[index] ? `
          <div class="translation-box">
            <strong>中文翻译</strong>
            <p>${escapeHtml(state.rewriteTranslations[index])}</p>
          </div>
        ` : ""}
      </article>
    `).join("")
    : `<div class="empty-state">没有生成候选</div>`;
  $("rewriteResults").querySelectorAll("[data-copy-rewrite]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = state.rewriteCandidates[Number(button.dataset.copyRewrite)] || "";
      await copyText(text, button);
    });
  });
  $("rewriteResults").querySelectorAll("[data-translate-rewrite]").forEach((button) => {
    button.addEventListener("click", () => translateRewriteCandidate(Number(button.dataset.translateRewrite), button));
  });
  $("rewriteResults").querySelectorAll("[data-save-rewrite]").forEach((button) => {
    button.addEventListener("click", () => saveRewriteCandidate(Number(button.dataset.saveRewrite), button));
  });
}

function splitLocalCandidates(text) {
  const markers = Array.from({ length: 6 }, (_, index) => `<<<HUASHI_CANDIDATE_${index + 1}>>>`);
  const marked = markers.map((marker, index) => {
    const start = text.indexOf(marker);
    if (start < 0) return "";
    const next = markers[index + 1];
    const end = next ? text.indexOf(next, start + marker.length) : text.length;
    return text.slice(start + marker.length, end < 0 ? text.length : end).trim();
  }).filter(Boolean);
  const maxCount = Number($("rewriteCountInput")?.value || 5);
  if (marked.length) return marked.slice(0, maxCount);
  return text.split(/\n+/).map((item) => item.trim().replace(/^\d+[.、)]\s*/, "")).filter(Boolean).slice(0, maxCount);
}

function displayRewriteStream(text) {
  return Array.from({ length: 6 }, (_, index) => index + 1).reduce(
    (value, index) => value.replaceAll(`<<<HUASHI_CANDIDATE_${index}>>>`, `${index === 1 ? "" : "\n\n"}候选 ${index}`),
    text
  ).trim();
}

function mostlyEnglish(text) {
  const latin = (text.match(/[A-Za-z]/g) || []).length;
  const han = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  return latin > 80 && latin > han * 2;
}

async function autoTranslateEnglishCandidates(candidates) {
  for (let index = 0; index < candidates.length; index += 1) {
    if (mostlyEnglish(candidates[index]) && !state.rewriteTranslations[index]) {
      await translateRewriteCandidate(index);
    }
  }
}

async function translateRewriteCandidate(index, button) {
  showToast("翻译和改写已下线，请手动编辑提示词","info");return;
  const prompt = state.rewriteCandidates[index] || "";
  if (!prompt) return;
  const oldText = button?.textContent || "翻译";
  if (button) {
    button.disabled = true;
    button.textContent = "翻译中";
  }
  setRewriteStatus(`正在翻译候选 ${index + 1}...`);
  let translated = "";
  try {
    const response = await fetch("/api/prompts/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        model: $("rewriteModelInput").value,
      }),
    });
    if (!response.ok || !response.body) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `请求失败：${response.status}`);
    }
    await readPromptAIStream(response.body, {
      onStatus: (message) => setRewriteStatus(message),
      onToken: (text) => {
        translated += text;
        state.rewriteTranslations[index] = translated;
        renderRewriteResults(state.rewriteCandidates);
      },
      onDone: (_event, fullText) => {
        state.rewriteTranslations[index] = fullText.trim();
        renderRewriteResults(state.rewriteCandidates);
        setRewriteStatus(`候选 ${index + 1} 已翻译。`, "info");
      },
    });
  } catch (error) {
    setRewriteStatus(error.message, "error");
  } finally {
    const freshButton = $("rewriteResults").querySelector(`[data-translate-rewrite="${index}"]`);
    if (freshButton) {
      freshButton.disabled = false;
      freshButton.textContent = oldText;
    }
  }
}

async function saveRewriteCandidate(index, button) {
  const source = state.prompts.find((item) => item.id === state.rewritingPromptId);
  const candidate = state.rewriteCandidates[index] || "";
  if (!source || !candidate) return;
  button.disabled = true;
  const translation = state.rewriteTranslations[index] || "";
  const idea = $("rewriteIdeaInput").value.trim();
  const stamp = new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  try {
    const { prompt } = await api(`/api/prompts/${source.id}/variants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: `AI 衍生 ${stamp}`,
        content: candidate,
        translation,
        edit_idea: idea,
        model_id: $("rewriteModelInput").value,
      }),
    });
    state.prompts = state.prompts.map((item) => item.id === prompt.id ? prompt : item);
    button.textContent = "已保存";
    renderPrompts();
    setRewriteStatus("已保存为这条提示词下面的独立衍生。", "info");
  } catch (error) {
    button.disabled = false;
    setRewriteStatus(error.message, "error");
  }
}

function openAgentDrawer(promptId) {
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (!prompt) return;
  state.agentPromptId = promptId;
  state.agentAnalysis = null;
  state.agentEdits = [];
  state.agentResult = null;
  state.agentParentVariantId = "";
  state.agentRoundIndex = 0;
  state.agentSessionId = newSessionId();
  $("agentPromptTitle").textContent = prompt.title || "提示词";
  $("agentPromptPreview").textContent = prompt.content || "";
  $("agentInstructionInput").value = "";
  $("agentInstructionLabel").textContent = "其他补充";
  $("agentAnalysis").innerHTML = "";
  $("agentResult").innerHTML = "";
  setAgentStatus("");
  renderAgentModels();
  $("agentDrawer").classList.remove("hidden");
  $("agentDrawer").setAttribute("aria-hidden", "false");
}

function closeAgentDrawer() {
  $("agentDrawer").classList.add("hidden");
  $("agentDrawer").setAttribute("aria-hidden", "true");
  state.agentPromptId = "";
}

async function runAgentAnalyze() {
  const prompt = state.prompts.find((item) => item.id === state.agentPromptId);
  if (!prompt) return;
  $("agentAnalyzeButton").disabled = true;
  setAgentStatus("正在翻译并识别可修改项...");
  $("agentAnalysis").innerHTML = "";
  try {
    const { analysis } = await api("/api/prompt-agent/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt.content,
        model: $("agentModelInput").value,
      }),
    });
    state.agentAnalysis = analysis;
    state.agentEdits = buildAgentEdits(analysis);
    renderAgentAnalysis();
    setAgentStatus("识别完成。点建议或填写新值；默认保留项如果想改，也可以直接填。", "info");
    const firstInput = $("agentAnalysis").querySelector("[data-agent-edit]");
    (firstInput || $("agentInstructionInput")).focus();
  } catch (error) {
    setAgentStatus(error.message, "error");
  } finally {
    $("agentAnalyzeButton").disabled = false;
  }
}

async function runAgentGenerate() {
  const prompt = state.prompts.find((item) => item.id === state.agentPromptId);
  const extraInstruction = $("agentInstructionInput").value.trim();
  const edits = collectAgentEdits();
  const instruction = agentInstructionSummary(edits, extraInstruction);
  if (!prompt) return;
  if (!state.agentAnalysis) {
    setAgentStatus("先点一次“识别可修改项”，让 AI 看懂原提示词。", "error");
    return;
  }
  if (!instruction) {
    setAgentStatus("至少填写一个新值，或写一条其他补充。", "error");
    return;
  }
  const isRefine = Boolean(state.agentResult?.prompt_en);
  $("agentGenerateButton").disabled = true;
  $("agentResult").innerHTML = "";
  setAgentStatus(isRefine ? "正在基于当前结果继续局部微调..." : "正在生成 1 条完整提示词...");
  try {
    const endpoint = isRefine ? "/api/prompt-agent/refine" : "/api/prompt-agent/generate";
    const body = isRefine
      ? {
          prompt: prompt.content,
          analysis: state.agentAnalysis,
          current: state.agentResult,
          instruction,
          model: $("agentModelInput").value,
        }
      : {
          prompt: prompt.content,
          analysis: state.agentAnalysis,
          instruction,
          edits,
          extra_instruction: extraInstruction,
          model: $("agentModelInput").value,
        };
    const { result, model } = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    state.agentResult = { ...result, model_id: model, instruction };
    state.agentRoundIndex += 1;
    renderAgentResult();
    setAgentStatus("已生成英文新提示词，并附中文翻译。可以复制、保存，或继续调整。", "info");
  } catch (error) {
    setAgentStatus(error.message, "error");
  } finally {
    $("agentGenerateButton").disabled = false;
  }
}

function renderAgentAnalysis() {
  const analysis = state.agentAnalysis;
  if (!analysis) return;
  $("agentAnalysis").innerHTML = `
    <section class="analysis-card">
      <div class="analysis-kicker">${escapeHtml(analysis.prompt_type || "提示词")}</div>
      <strong>${escapeHtml(analysis.summary || analysis.core_image || "")}</strong>
      ${analysis.translation_cn ? `
        <div class="prompt-translation">
          <span>中文翻译</span>
          <p>${escapeHtml(analysis.translation_cn)}</p>
        </div>
      ` : ""}
      ${renderAgentEditList()}
      <p class="agent-guide">${escapeHtml(analysis.guide || "只改你想改的地方，默认保留项不填就保持原样，想改也可以填。")}</p>
    </section>
  `;
  bindAgentEditInputs();
}

function buildAgentEdits(analysis = {}) {
  const editable = (analysis.editable_items || []).map((item) => ({
    ...item,
    value: "",
    locked: false,
    suggestions: uniqueStrings(item.suggestions || []).slice(0, 5),
  }));
  const locked = (analysis.locked_context || [])
    .map((text, index) => String(text || "").trim() ? ({
      id: `locked_context_${index + 1}`,
      label: "默认保留",
      original: String(text || "").trim(),
      placeholder: "想改就写新方向，不填继续保留",
      suggestions: ["弱化一点", "换成更自然", "删除这类词", "改成更高级"],
      value: "",
      locked: true,
    }) : null)
    .filter(Boolean);
  return [...editable, ...locked];
}

function uniqueStrings(values = []) {
  const seen = new Set();
  return values.map((item) => String(item || "").trim()).filter((item) => {
    if (!item || seen.has(item)) return false;
    seen.add(item);
    return true;
  });
}

function renderAgentEditList() {
  const items = state.agentEdits || [];
  if (!items.length) {
    return `<div class="empty-state compact-empty">没有识别到明确可修改项，可以直接在“其他补充”里描述想法。</div>`;
  }
  const editableRows = items.map((item, index) => ({ ...item, index })).filter((item) => !item.locked);
  const lockedRows = items.map((item, index) => ({ ...item, index })).filter((item) => item.locked);
  return `
    <div class="agent-edit-list">
      ${renderAgentEditGroup("局部修改", "点建议会自动填入；留空保持原样", editableRows)}
      ${lockedRows.length ? renderAgentEditGroup("默认保留，也可改", "这些默认不动；想改哪条就填哪条", lockedRows) : ""}
    </div>
  `;
}

function renderAgentEditGroup(title, hint, items) {
  if (!items.length) return "";
  return `
    <div class="agent-edit-group">
      <div class="agent-edit-head">
        <span>${escapeHtml(title)}</span>
        <small>${escapeHtml(hint)}</small>
      </div>
      ${items.map((item) => `
        <div class="agent-edit-row ${item.locked ? "is-locked" : ""}">
          <span class="agent-edit-label">${escapeHtml(item.label || "可修改项")}</span>
          <span class="agent-original">${escapeHtml(item.original || "未识别")}</span>
          <div class="agent-edit-control">
            <input
              type="text"
              data-agent-edit="${item.index}"
              value="${escapeAttr(item.value || "")}"
              placeholder="${escapeAttr(item.placeholder || "保持原样")}"
              aria-label="${escapeAttr(item.label || "可修改项")}"
            />
            ${item.suggestions?.length ? `
              <div class="agent-suggestions">
                ${item.suggestions.map((suggestion) => `
                  <button
                    class="suggestion-chip"
                    type="button"
                    data-agent-suggestion="${item.index}"
                    data-suggestion-value="${escapeAttr(suggestion)}"
                  >${escapeHtml(suggestion)}</button>
                `).join("")}
              </div>
            ` : ""}
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function bindAgentEditInputs() {
  $("agentAnalysis").querySelectorAll("[data-agent-edit]").forEach((input) => {
    input.addEventListener("input", (event) => {
      const index = Number(event.currentTarget.dataset.agentEdit);
      if (state.agentEdits[index]) {
        state.agentEdits[index].value = event.currentTarget.value;
      }
    });
  });
  $("agentAnalysis").querySelectorAll("[data-agent-suggestion]").forEach((button) => {
    button.addEventListener("click", (event) => {
      const index = Number(event.currentTarget.dataset.agentSuggestion);
      const value = event.currentTarget.dataset.suggestionValue || "";
      if (!state.agentEdits[index]) return;
      state.agentEdits[index].value = value;
      const input = $("agentAnalysis").querySelector(`[data-agent-edit="${index}"]`);
      if (input) {
        input.value = value;
        input.focus();
      }
    });
  });
}

function collectAgentEdits() {
  return (state.agentEdits || []).map((item) => ({
    id: item.id || "",
    label: item.label || "可修改项",
    original: item.original || "",
    value: (item.value || "").trim(),
  })).filter((item) => item.value);
}

function agentInstructionSummary(edits, extraInstruction = "") {
  const parts = edits.map((item) => `${item.label}：${item.original || "原值"} -> ${item.value}`);
  if (extraInstruction.trim()) parts.push(`其他补充：${extraInstruction.trim()}`);
  return parts.join("\n");
}

function analysisPointSection(title, points = [], showSuggestions = false) {
  if (!points.length) return "";
  return `
    <div class="analysis-section">
      <span>${escapeHtml(title)}</span>
      <ul>
        ${points.map((item) => `
          <li>
            <b>${escapeHtml(item.label || "要点")}</b>
            ${item.current ? `<em>${escapeHtml(item.current)}</em>` : ""}
            ${showSuggestions && item.suggestions?.length ? `<small>${escapeHtml(item.suggestions.join(" / "))}</small>` : ""}
          </li>
        `).join("")}
      </ul>
    </div>
  `;
}

function analysisTextSection(title, items = []) {
  if (!items.length) return "";
  return `
    <div class="analysis-section compact-list">
      <span>${escapeHtml(title)}</span>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `;
}

function renderAgentResult() {
  const result = state.agentResult;
  if (!result) return;
  $("agentResult").innerHTML = `
    <article class="rewrite-card agent-result-card">
      <strong>智能衍生 ${state.agentRoundIndex}</strong>
      <p>${escapeHtml(result.prompt_en)}</p>
      <div class="translation-box">
        <strong>中文翻译</strong>
        <p>${escapeHtml(result.translation_cn || result.explanation_cn || "暂无翻译")}</p>
      </div>
      ${result.explanation_cn || result.feature_cn ? `
        <details class="variant-note">
          <summary>修改说明</summary>
          ${result.explanation_cn ? `<p>${escapeHtml(result.explanation_cn)}</p>` : ""}
          ${result.feature_cn ? `<p>${escapeHtml(result.feature_cn)}</p>` : ""}
        </details>
      ` : ""}
      <div class="rewrite-actions agent-actions">
        <button class="secondary-button" type="button" data-copy-agent-result>复制</button>
        <button class="secondary-button" type="button" data-save-agent-result>保存为衍生</button>
        <button class="secondary-button" type="button" data-focus-agent-refine>继续修改</button>
      </div>
    </article>
  `;
  $("agentResult").querySelector("[data-copy-agent-result]").addEventListener("click", async (event) => {
    await copyText(state.agentResult?.prompt_en || "", event.currentTarget);
  });
  $("agentResult").querySelector("[data-save-agent-result]").addEventListener("click", (event) => saveAgentResult(event.currentTarget));
  $("agentResult").querySelector("[data-focus-agent-refine]").addEventListener("click", () => {
    $("agentInstructionInput").focus();
    setAgentStatus("写一句追加修改要求，我会基于当前这条继续改。", "info");
  });
}

async function saveAgentResult(button) {
  const source = state.prompts.find((item) => item.id === state.agentPromptId);
  const result = state.agentResult;
  if (!source || !result?.prompt_en) return;
  button.disabled = true;
  const stamp = new Date().toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  try {
    const { prompt } = await api(`/api/prompts/${source.id}/variants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: `智能拆解衍生 ${stamp}`,
        content: result.prompt_en,
        translation: result.translation_cn || result.explanation_cn || "",
        edit_idea: result.instruction || "",
        user_instruction: result.instruction || "",
        model_id: result.model_id || $("agentModelInput").value,
        parent_variant_id: state.agentParentVariantId,
        session_id: state.agentSessionId,
        round_index: state.agentRoundIndex,
        explanation_cn: result.explanation_cn || "",
        feature_cn: result.feature_cn || "",
        analysis_snapshot: JSON.stringify(state.agentAnalysis || {}),
      }),
    });
    const saved = (prompt.variants || [])[0];
    state.agentParentVariantId = saved?.id || state.agentParentVariantId;
    state.prompts = state.prompts.map((item) => item.id === prompt.id ? prompt : item);
    renderPrompts();
    button.textContent = "已保存";
    setAgentStatus("已保存到原提示词下面的衍生列表。", "info");
  } catch (error) {
    button.disabled = false;
    setAgentStatus(error.message, "error");
  }
}

function setAgentStatus(message, kind = "info") {
  const target = $("agentStatus");
  target.classList.toggle("hidden", !message);
  target.dataset.kind = kind;
  target.textContent = message || "";
}

function newSessionId() {
  return window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setRewriteStatus(message, kind = "info") {
  const target = $("rewriteStatus");
  target.classList.toggle("hidden", !message);
  target.dataset.kind = kind;
  target.textContent = message || "";
}

function filteredTasks() {
  return state.tasks.filter((task) => {
    if (state.historyFilter === "success") return task.status === "success";
    if (state.historyFilter === "failed") return task.status === "failed";
    if (state.historyFilter === "running") return task.status === "queued" || task.status === "running";
    return true;
  });
}

function recordRow(task) {
  const thumb = taskThumb(task);
  return `
    <button class="record-row" type="button" data-task-id="${task.id}">
      ${thumb}
      <span>
        <strong>${escapeHtml(task.app_name)}</strong>
        <small><span class="provider-badge ${escapeAttr(task.provider || "runninghub")}">${providerLabel(task.provider)}</span> ${formatTime(task.created_at)}${task.provider === "runpod" && task.status === "running" ? ` · ${escapeHtml(runpodStageLabel(task))}` : ""}</small>
      </span>
      <em class="${task.status}">${shortStatus(task.status)}</em>
    </button>
  `;
}

function renderResult() {
  const task = currentTask();
  if (!task) {
    $("resultView").className = "result-view empty-state";
    $("resultView").innerHTML = "暂无结果";
    return;
  }
  if (task.is_summary) {
    $("resultView").className = "result-view empty-state";
    $("resultView").innerHTML = "正在读取详情";
    loadTaskDetail(task.id);
    return;
  }
  if (task.status === "queued" || task.status === "running") {
    $("resultView").className = "result-view";
    $("resultView").innerHTML = `
      <div class="progress-card">
        <div class="compare-strip">
          ${task.input_url ? `<img src="${task.input_url}" alt="原图">` : "<span></span>"}
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
          <span class="pending-preview">生成中</span>
        </div>
        <p>${escapeHtml(task.provider === "runpod" ? runpodStageLabel(task) : "正在调用 RunningHub")}</p>
        <div class="progress-line"><span></span></div>
      </div>
      ${taskRemoteCard(task)}
    `;
    return;
  }
  if (task.status === "failed" || task.status === "cancelled") {
    $("resultView").className = "result-view";
    $("resultView").innerHTML = `
      <div class="notice">${escapeHtml(task.error || (task.status === "cancelled" ? "已取消排队，原输入与记录仍保留。" : "任务失败"))}</div>
      ${taskRemoteCard(task)}
      <div class="action-grid">
        ${task.remote_submission_state === "unknown" ? "" : `<button class="secondary-button" type="button" data-action="retry" data-task-id="${task.id}">重试</button>`}
        ${task.remote_submission_state === "unknown" ? "" : `<button class="danger-button" type="button" data-action="delete" data-task-id="${task.id}">删除</button>`}
      </div>
      ${taskSettingsCard(task)}
    `;
    bindTaskActions();
    return;
  }
  const images = (task.outputs || []).filter((item) => isVisibleImageOutput(item));
  const packages = (task.outputs || []).filter((item) => !item.deleted && item.type === "zip");
  $("resultView").className = "result-view";
  $("resultView").innerHTML = `
    ${taskRemoteCard(task)}
    <div class="result-gallery">
      ${images.length ? images.map((item) => `
        <figure class="result-image ${item.blurred ? "blurred" : ""}">
          <a href="${item.url}" target="_blank"><img loading="lazy" src="${item.url}" alt="生成结果"></a>
          <div class="result-image-actions">
            <button class="tiny-button" type="button" data-toggle-output-blur="${escapeAttr(task.id)}" data-output-path="${escapeAttr(item.path)}">
              ${item.blurred ? "还原" : "模糊"}
            </button>
            <button class="tiny-button danger" type="button" data-delete-output="${escapeAttr(task.id)}" data-output-path="${escapeAttr(item.path)}">删除</button>
          </div>
          ${HuashiCreation.imageActions(item.path, item.download_name, previewUrl(item))}
        </figure>
      `).join("") : `<div class="empty-state">暂无预览</div>`}
    </div>
    <div class="action-grid">
      <button class="primary-button" type="button" data-action="archive" data-task-id="${task.id}" ${task.saved ? "disabled" : ""}>${task.saved ? "已保存" : "保存"}</button>
      ${downloadButton(images, packages)}
      <button class="secondary-button" type="button" data-action="retry" data-task-id="${task.id}">重做</button>
      <button class="danger-button" type="button" data-action="delete" data-task-id="${task.id}">删除</button>
    </div>
    ${taskSettingsCard(task)}
  `;
  bindTaskActions();
}

function providerLabel(provider) {
  return provider === "runpod" ? "RunPod" : "RunningHub";
}

function runpodStageLabel(task) {
  return {
    queue_waiting: "已加入队列，等待前面的任务",
    recovery_wait: "正在恢复原任务查询，后续任务等待",
    cancelled: "已取消排队",
    preparing: "正在准备输入",
    checking_network: "正在检查 RunPod 网络",
    submitting: "正在提交 RunPod（结果尚未确认）",
    waiting_worker: "等待 Worker",
    remote_running: "RunPod 运行中",
    fetching_result: "正在获取结果",
    completed: "完成",
    submission_unknown: "提交结果未知",
    failed: "失败",
  }[task.stage] || (task.status === "queued" ? "已创建" : "正在查询 RunPod 状态");
}

function taskRemoteCard(task) {
  const submitted = task.remote_submission_state === "submitted" ? "已确认提交" : task.remote_submission_state === "unknown" ? "提交结果未知" : "尚未提交";
  const rows = [
    ["来源", providerLabel(task.provider)],
    ["经过时间", elapsedTime(task.created_at, task.completed_at)],
  ];
  if (task.provider === "runpod") {
    rows.push(["阶段", runpodStageLabel(task)], ["远端提交", submitted]);
    if (task.runpod_job_id) rows.push(["RunPod Job ID", task.runpod_job_id]);
    if (task.remote_status) rows.push(["远端状态", task.remote_status]);
  }
  return `<dl class="task-remote-card">${rows.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>`;
}

function elapsedTime(start, end) {
  const elapsed = Math.max(0, Math.floor((new Date(end || Date.now()) - new Date(start)) / 1000));
  if (!Number.isFinite(elapsed)) return "—";
  return elapsed < 60 ? `${elapsed} 秒` : elapsed < 3600 ? `${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒` : `${Math.floor(elapsed / 3600)} 小时 ${Math.floor((elapsed % 3600) / 60)} 分`;
}

function taskSettingsCard(task) {
  const rows = taskSettingRows(task);
  const prompt = String(task.prompt || "").trim();
  if (!rows.length && !prompt) return "";
  return `
    <section class="settings-card">
      <div class="section-heading compact">
        <span>完整设定</span>
        <div class="settings-actions">
          ${prompt ? `<button class="tiny-button" type="button" data-copy-task-prompt="${escapeAttr(task.id)}">复制提示词</button>` : ""}
          ${prompt ? `<button class="tiny-button" type="button" data-save-task-prompt="${escapeAttr(task.id)}">保存提示词</button>` : ""}
        </div>
      </div>
      ${prompt ? `
        <div class="settings-prompt">
          <strong>提示词</strong>
          <p>${escapeHtml(prompt)}</p>
        </div>
      ` : ""}
      ${rows.length ? `
        <dl class="settings-list">
          ${rows.map((row) => `
            <div class="settings-row">
              <dt>${escapeHtml(row.label)}</dt>
              <dd>${escapeHtml(row.value)}</dd>
            </div>
          `).join("")}
        </dl>
      ` : ""}
    </section>
  `;
}

function taskSettingRows(task) {
  const app = state.apps.find((item) => item.id === task.app_id);
  const inputs = app ? appInputs(app) : [];
  const payload = task.input_payload || {};
  const values = payload.values || {};
  const files = payload.files || {};
  const rows = [];
  inputs.forEach((input) => {
    if (input.type === "hidden") return;
    const value = values[input.id];
    if (input.role === "prompt" && String(value || "").trim() === String(task.prompt || "").trim()) return;
    const label = input.id === "negative_prompt" ? (input.label || "负向提示词") : (input.role === "prompt" ? "提示词" : (input.label || input.fieldName || input.id));
    if (input.type === "image" || input.type === "file") {
      const file = files[input.id];
      if (file?.name || file?.path) rows.push({ label, value: file.name || file.path });
      return;
    }
    if (value) rows.push({ label, value: String(value) });
  });
  Object.entries(values).forEach(([key, value]) => {
    if (inputs.some((input) => input.id === key) || !value) return;
    rows.push({ label: key, value: String(value) });
  });
  Object.entries(files).forEach(([key, file]) => {
    if (inputs.some((input) => input.id === key) || !file) return;
    rows.push({ label: key, value: file.name || file.path || "" });
  });
  return rows.filter((row) => row.value);
}

function taskSettingsText(task) {
  const rows = taskSettingRows(task);
  const lines = [
    `应用：${task.app_name || ""}`,
    `分类：${task.app_category || ""}`,
    `时间：${formatTime(task.created_at)}`,
  ];
  const prompt = String(task.prompt || "").trim();
  if (prompt) lines.push("", "提示词：", prompt);
  if (rows.length) {
    lines.push("", "完整输入设定：");
    rows.forEach((row) => lines.push(`${row.label}：${row.value}`));
  }
  return lines.join("\n");
}

function currentTask() {
  return state.tasks.find((task) => task.id === state.selectedTaskId) || state.tasks[0];
}

function downloadButton(images, packages) {
  const item = packages[0] || images[0];
  return item
    ? `<a class="secondary-button link-button" href="${item.url}" download="${escapeAttr(item.download_name || "")}">下载</a>`
    : `<button class="secondary-button" type="button" disabled>下载</button>`;
}

function taskThumb(task) {
  const image = (task.outputs || []).find((item) => isVisibleImageOutput(item));
  if (image) return `<img class="record-thumb ${image.blurred ? "is-blurred" : ""}" src="${escapeAttr(previewUrl(image))}" alt="">`;
  if (task.input_url) return `<img class="record-thumb" src="${escapeAttr(task.input_thumb_url || task.input_url)}" alt="">`;
  return `<span class="record-thumb"></span>`;
}

async function restoreTaskToCompose(taskId) {
  // History lists contain summaries; always restore the saved, complete inputs.
  const { task } = await api(`/api/tasks/${encodeURIComponent(taskId)}`);
  const app = state.apps.find((item) => item.id === task.app_id && item.enabled !== false);
  if (!app) throw new Error("原画布已下架或不可用，无法恢复这条记录。");
  const inputs = appInputs(app);
  const values = task.input_payload?.values || {};
  const files = { ...(task.input_payload?.files || {}) };
  // Older records only stored their first image and prompt at the task level.
  if (!Object.keys(files).length && task.input_path) {
    const firstImage = inputs.find((input) => ["image", "file"].includes(input.type));
    if (firstImage) files[firstImage.id] = { path: task.input_path, name: task.input_name };
  }
  state.selectedAppId = app.id;
  state.pendingComposePrompt = "";
  // Rebuild even the same canvas so previous drafts and uploads cannot leak in.
  delete $("dynamicInputs").dataset.appId;
  setView("compose");
  const form = $("createTaskForm");
  const promptId = appPromptInput(app)?.id;
  inputs.forEach((input) => {
    const field = form.querySelector(`[name="${CSS.escape(`input_${input.id}`)}"]`);
    if (!field) return;
    if (["image", "file"].includes(input.type)) {
      const file = files[input.id];
      if (!file?.path) return;
      const artwork = form.querySelector(`[data-artwork-input="${CSS.escape(input.id)}"]`);
      if (artwork) artwork.value = file.path;
      showInputPreview(input.id, `/files/${file.path.split("/").map(encodeURIComponent).join("/")}`);
      const label = form.querySelector(`[data-file-label="${CSS.escape(input.id)}"]`);
      if (label) label.textContent = `原图：${file.name || file.path.split("/").pop()}`;
      return;
    }
    const value = Object.hasOwn(values, input.id) ? values[input.id] : input.id === promptId ? task.prompt : undefined;
    if (value === undefined || value === null) return;
    if (input.type === "checkbox") field.checked = truthy(value);
    else field.value = String(value);
  });
  updateGenerateState();
  setNotice("已恢复原记录的图片、提示词和参数，可换图或微调后点击开始生成。");
}

function bindTaskActions() {
  bindCreationImages($("resultView"));
  document.querySelectorAll("[data-copy-task-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      const task = state.tasks.find((item) => item.id === button.dataset.copyTaskPrompt);
      await copyText(task?.prompt || "", button);
    });
  });
  document.querySelectorAll("[data-save-task-prompt]").forEach((button) => {
    button.addEventListener("click", () => savePromptFromTask(button.dataset.saveTaskPrompt));
  });
  document.querySelectorAll("[data-toggle-output-blur]").forEach((button) => {
    button.addEventListener("click", () => toggleOutputBlur(button));
  });
  document.querySelectorAll("[data-delete-output]").forEach((button) => {
    button.addEventListener("click", () => deleteTaskOutput(button));
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      const taskId = button.dataset.taskId;
      try {
        if (button.dataset.action === "archive") {
          await api(`/api/tasks/${taskId}/archive`, { method: "POST" });
          setNotice("已保存。");
        }
        if (button.dataset.action === "retry") {
          button.disabled = true;
          try { await restoreTaskToCompose(taskId); }
          finally { button.disabled = false; }
          return;
        }
        if (button.dataset.action === "delete") {
          if (!confirm("删除这条记录？")) return;
          await api(`/api/tasks/${taskId}`, { method: "DELETE" });
          state.selectedTaskId = null;
        }
        await loadData();
      } catch (error) {
        setNotice(error.message, "error");
      }
    });
  });
}

function savePromptFromTask(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task?.prompt) return;
  const image = (task.outputs || []).find((item) => isVisibleImageOutput(item));
  setView("prompts");
  openPromptForm({
    title: `${task.app_name || "生成记录"} ${formatTime(task.created_at)}`,
    content: task.prompt,
    tags: [task.app_category || task.app_name || "生成记录"].filter(Boolean),
    sample_path: image?.path || "",
    sample_url: image?.url || "",
  });
}

async function toggleOutputBlur(button) {
  const taskId = button.dataset.toggleOutputBlur;
  const path = button.dataset.outputPath;
  const foundTask = state.tasks.find((item) => item.id === taskId);
  const output = (foundTask?.outputs || []).find((item) => item.path === path);
  if (!taskId || !path || !output) return;
  try {
    const { task } = await api(`/api/tasks/${taskId}/outputs/blur`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, blurred: !output.blurred }),
    });
    state.tasks = state.tasks.map((item) => item.id === task.id ? task : item);
    // A privacy action must not leave its image queued for a later batch deletion.
    (state.albumItems || []).filter(item => item.task_id === taskId && item.output_path === path)
      .forEach(item => state.gallerySelected.delete(item.id));
    await refreshAlbumItems();
    renderResult();
    renderGallery();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function createAlbumFolder() {
  HuashiAlbums.createFolder({api,folders:state.albums,toast:showToast,onCreated:async folder=>{
    state.selectedAlbumId=folder.id;state.galleryPage=0;state.gallerySelected.clear();
    await refreshAlbums();render();
  }});
}

function renderGallerySelection() {
  const bar=$('gallerySelection'),folder=currentAlbum();
  bar.hidden=Boolean(state.albumLoading || folder?.virtual || folder?.placeholder);
  if(bar.hidden)return;
  const items=artworkItems();
  for(const id of state.gallerySelected)if(!items.some(item=>item.id===id))state.gallerySelected.delete(id);
  bar.innerHTML=`<span>已选 ${state.gallerySelected.size} 张</span><button type="button" class="tiny-button" data-select-gallery-all>全选</button><button type="button" class="tiny-button" data-select-gallery-page>选择本页</button><button type="button" class="tiny-button" data-clear-gallery-selection>取消选择</button><label class="gallery-page-size">每页<select aria-label="每页图片数量">${[20,50,100].map(n=>`<option value="${n}" ${n===state.galleryPageSize?'selected':''}>${n} 张</option>`).join('')}</select></label><button type="button" class="secondary-button" id="moveSelectedImages" ${state.gallerySelected.size?'':'disabled'}>移动到分类</button><button type="button" class="tiny-button danger" id="deleteSelectedImages" ${state.gallerySelected.size?'':'disabled'}>删除</button>`;
  bar.querySelector('[data-select-gallery-all]').onclick=()=>{items.forEach(item=>state.gallerySelected.add(item.id));renderGallery();};
  bar.querySelector('[data-select-gallery-page]').onclick=()=>{items.slice(state.galleryPage*state.galleryPageSize,(state.galleryPage+1)*state.galleryPageSize).forEach(item=>state.gallerySelected.add(item.id));renderGallery();};
  bar.querySelector('[data-clear-gallery-selection]').onclick=()=>{state.gallerySelected.clear();renderGallery();};
  bar.querySelector('select').onchange=event=>{state.galleryPageSize=Number(event.target.value);state.galleryPage=0;state.galleryViewerOpen=false;renderGallery();};
  $('moveSelectedImages').onclick=()=>openAlbumMove(items.filter(item=>state.gallerySelected.has(item.id)));
  $('deleteSelectedImages').onclick=()=>removeGalleryItems(items.filter(item=>state.gallerySelected.has(item.id)));
}

function removeGalleryItems(items) {
  HuashiGallery.remove(items,{api,toast:showToast,onDeleted:async ids=>{
    ids.forEach(id=>state.gallerySelected.delete(id));
    state.galleryViewerOpen=false;
    await refreshAlbums();renderGallery();
  }});
}

function openAlbumMove(items, initialTarget='') {
  HuashiAlbums.move({api,folders:state.albums,toast:showToast,onMoved:async()=>{
    state.gallerySelected.clear();state.galleryViewerOpen=false;
    await refreshAlbums();render();
  }},items,initialTarget);
}

async function uploadAlbumImage(input, defaultInbox = false) {
  const file = input.files?.[0];
  if (!file) return;
  if (!defaultInbox && HuashiRooms.directoryLibrary(state.selectedAlbumId)) {
    input.value = "";
    setNotice(`${HuashiRooms.directoryLibrary(state.selectedAlbumId).label}是只读参考库，不能上传到这里。`, "error");
    return;
  }
  if (!defaultInbox && state.selectedAlbumId === "__faces__") {
    input.value = "";
    setNotice("人脸库是只读参考库，不能在这里直接上传。", "error");
    return;
  }
  const formData = new FormData();
  if (!defaultInbox) formData.append("folder_id", state.selectedAlbumId || "");
  formData.append("image", file);
  try {
    const {item} = await api("/api/albums/upload", { method: "POST", body: formData });
    if (defaultInbox) {state.gallerySelected.clear();state.selectedAlbumId=item.folder_id;state.galleryPage=0;state.galleryViewerOpen=false;}
    showToast(defaultInbox ? "素材已进入待整理" : "已上传到当前分类","info");
    input.value = "";
    await refreshAlbums();
    render();
  } catch (error) {
    input.value = "";
    setNotice(error.message, "error");
  }
}

async function moveAlbumItem(select) {
  const item=artworkItems().find(item=>item.id===select.dataset.moveAlbumItem);
  if(item && select.value!==item.folder_id)openAlbumMove([item],select.value);
}

async function reorderAlbumItem(button) {
  const itemId = button.dataset.reorderAlbumItem;
  const direction = button.dataset.direction;
  if (!itemId || !direction) return;
  try {
    await api(`/api/albums/items/${itemId}/reorder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction }),
    });
    await refreshAlbumItems();
    const items = artworkItems();
    state.galleryIndex = Math.max(0, items.findIndex((item) => item.id === itemId));
    renderGallery();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function positionAlbumItem(itemId, toIndex) {
  if (!itemId || !Number.isFinite(toIndex)) return;
  try {
    await api(`/api/albums/items/${itemId}/position`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to_index: toIndex }),
    });
    await refreshAlbumItems();
    const items = artworkItems();
    state.galleryIndex = Math.max(0, items.findIndex((item) => item.id === itemId));
    renderGallery();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function deleteAlbumItem(button) {
  const item=artworkItems().find(item=>item.id===button.dataset.deleteAlbumItem);
  if(item)removeGalleryItems([item]);
}

async function deleteTaskOutput(button) {
  const taskId = button.dataset.deleteOutput;
  const path = button.dataset.outputPath;
  if (!taskId || !path) return;
  if (!confirm("删除这张作品？记录里的其他图片会保留。")) return;
  try {
    const { task } = await api(`/api/tasks/${taskId}/outputs/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    state.tasks = state.tasks.map((item) => item.id === task.id ? task : item);
    await refreshAlbums();
    const items = artworkItems();
    if (!items.length) state.galleryViewerOpen = false;
    state.galleryIndex = Math.min(state.galleryIndex, Math.max(items.length - 1, 0));
    renderResult();
    renderHistory();
    renderGallery();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

function updateQueueNavigation() {
  const count=HuashiTaskQueue.model(state.queue||{}).count;
  document.querySelectorAll('[data-queue-count]').forEach(el=>el.textContent=count?`· ${count}`:'');
}

async function queueControl(path) {
  if(state.queueBusy)return;
  state.queueBusy=true;
  try {
    state.queue=await api(path,{method:'POST'});
    state.queueConfirming=null;state.queueLoadError='';
    updateQueueNavigation();renderRunPodQueue();managePolling();
  } catch(error) {showToast(error.message,'error');await loadData().catch(()=>{});}
  finally {state.queueBusy=false;}
}

function renderRunPodQueue() {
  $('queueError').textContent=state.queueLoadError;
  $('queueError').classList.toggle('hidden',!state.queueLoadError);
  if(!state.queue){$('runpodQueueView').textContent=state.queueLoadError?'队列暂时无法读取，请稍后刷新。':'正在读取队列…';return;}
  HuashiTaskQueue.render($('runpodQueueView'),state.queue,{
    confirming:state.queueConfirming,stage:runpodStageLabel,elapsed:start=>'已加入 '+elapsedTime(start),
    detail:async id=>{try {const {task}=await api(`/api/tasks/${encodeURIComponent(id)}`);state.tasks=[task,...state.tasks.filter(t=>t.id!==id)];state.selectedTaskId=id;setView('result');}catch(error){showToast(error.message,'error');}},
    history:filter=>{state.historyFilter=filter;state.historyPage=0;setView('history');},
    confirm:id=>{state.queueConfirming=id;renderRunPodQueue();},
    cancel:id=>queueControl(`/api/runpod/queue/${encodeURIComponent(id)}/cancel`),
    pause:paused=>queueControl('/api/runpod/queue/'+(paused?'pause':'resume')),
  });
}

$('queueContinueCompose').addEventListener('click',()=>{
  if(selectedApp()?.provider!=='runpod') state.selectedAppId=state.queue?.pending?.[0]?.app_id||state.queue?.active?.[0]?.app_id||state.apps.find(a=>a.id==='runpod-noctq-v4-text-to-image')?.id||state.apps.find(a=>a.provider==='runpod')?.id;
  setView(state.selectedAppId?'compose':'create');
});

function managePolling() {
  const hasActive = state.view === "queue" || Boolean(state.queue?.active?.length || state.queue?.pending?.length) || state.tasks.some((task) => task.status === "queued" || task.status === "running");
  if (hasActive && !state.polling) state.polling = setInterval(loadData, 3500);
  if (!hasActive && state.polling) {
    clearInterval(state.polling);
    state.polling = null;
  }
}

function setNotice(message, kind = "info") {
  const notice = $("notice");
  notice.classList.toggle("hidden", !message);
  notice.dataset.kind = kind;
  notice.textContent = message || "";
}

function coverStyle(app) {
  return `background-image: url('${escapeAttr(appVisualUrl(app))}')`;
}

function appVisualUrl(app = {}) {
  if (app.provider === "runpod" && !app.icon_path && !app.cover_path) return "/runpod-qwen-icon.svg";
  return app.icon_thumb_url || app.icon_url || app.cover_thumb_url || app.cover_url || "/default-app-icon.png";
}

function previewUrl(item = {}) {
  return item.thumb_url || item.sample_thumb_url || item.input_thumb_url || item.url || item.sample_url || item.input_url || "";
}

function outputLabel(app) {
  return app.output_type === "zip" ? "相册" : "图片";
}

function isImageOutput(item) {
  return item?.type === "image" || ["png", "jpg", "jpeg", "webp"].includes(item?.type);
}

function isVisibleImageOutput(item) {
  return isImageOutput(item) && !item.deleted;
}

function shortStatus(status) {
  return { queued: "排队中", running: "处理中", success: "已完成", failed: "失败", cancelled: "已取消" }[status] || status;
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
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

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

function truthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").toLowerCase());
}

$("searchInput").addEventListener("input", (event) => {
  state.search = event.target.value;
  renderStyles();
});

document.querySelectorAll("[data-home-provider]").forEach((button) => {
  button.addEventListener("click", () => {
    state.homeProvider = button.dataset.homeProvider;
    state.category = "全部";
    render();
  });
});

$("promptDirectoryRetry").addEventListener("click", async () => {try {await loadData();}catch(error){showToast(error.message,"error");}});
$("managePromptFoldersButton").addEventListener("click", () => {
  HuashiPromptFolders.manage({api,value:state.promptFolderId,onMutate:loadData,toast:showToast});
});
window.matchMedia("(max-width:760px)").addEventListener("change", event => {
  if (!event.matches) $("promptDirectoryPanel").open = true;
});
$("promptSearchAll").addEventListener("change", event => {state.promptAllDirectories = event.target.checked;state.promptPage=0;state.promptSelected.clear();renderPrompts();});
$("promptSelectMode").addEventListener("click", () => {state.promptSelecting = !state.promptSelecting;state.promptSelected.clear();renderPrompts();});
$("promptSelectVisible").addEventListener("click", () => {state.promptSelected = new Set(filteredPrompts().map(prompt => prompt.id));renderPrompts();});
$("promptMoveSelected").addEventListener("click", () => movePromptIds([...state.promptSelected]));
$("promptSearchInput").addEventListener("input", (event) => {
  state.promptSearch = event.target.value;
  state.promptPage=0;
  state.promptSelected.clear();
  renderPrompts();
});

$("categorySelect").addEventListener("change", (event) => {
  state.category = event.target.value;
  render();
});

$("sortSelect")?.addEventListener("change", (event) => {
  state.homeSort = event.target.value;
  renderStyles();
});

$("createTaskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const app = selectedApp();
  if (!app || state.taskSubmitting) return;
  const formData = new FormData(event.currentTarget);
  formData.append("appId", app.id);
  state.taskSubmitting = true;
  updateGenerateState();
  setNotice(app.provider === "runpod" ? "正在保存到队列…" : "正在提交…");
  try {
    const { task } = await api("/api/tasks", { method: "POST", body: formData });
    state.selectedTaskId = task.id;
    if (app.provider === "runpod") {
      setNotice("已加入队列。图片与参数已独立保存，可以继续准备下一单。");
      showToast("已加入队列，可以继续创作。");
    } else {
      $("createTaskForm").reset();
      delete $("dynamicInputs").dataset.appId;
      setView("result");
    }
    await loadData().catch(()=>showToast("任务已保存，状态刷新失败，请打开队列核对。","error"));
  } catch (error) {
    setNotice(error.message + (app.provider === "runpod" ? "；若网络中断，请先查看队列核对是否已入队，再决定是否提交。" : ""), "error");
  } finally {
    state.taskSubmitting = false;
    renderCompose();
  }
});

$("newPromptButton").addEventListener("click", () => openPromptForm());
$("keepPromptDraftButton").addEventListener("click", () => $("promptDiscardDialog").close());
$("discardPromptDraftButton").addEventListener("click", () => {$("promptDiscardDialog").close();closePromptForm(true);});
$("cancelPromptButton").addEventListener("click", closePromptForm);
$("promptEditorDialog").addEventListener("cancel",event=>{event.preventDefault();closePromptForm();});
$("choosePromptSampleLibrary")?.addEventListener("click", () => openArtworkPicker("promptSample", "promptSample"));
$("promptSampleUploadInput")?.addEventListener("change", event => uploadPromptSample(event.currentTarget));
$("choosePromptSampleButton").addEventListener("click", () => openArtworkPicker("promptSample", "promptSample"));
$("clearPromptSampleButton").addEventListener("click", () => setPromptSample("", ""));

$("promptForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = $("promptIdInput").value;
  try {
    await api(id ? `/api/prompts/${id}` : "/api/prompts", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(promptFormPayload()),
    });
    closePromptForm(true);
    await loadData();
  } catch (error) {
    setNotice(error.message, "error");
  }
});

document.querySelectorAll("[data-close-prompt-picker]").forEach((item) => {
  item.addEventListener("click", closePromptPicker);
});

document.querySelectorAll("[data-close-artwork-picker]").forEach((item) => {
  item.addEventListener("click", closeArtworkPicker);
});

document.querySelectorAll("[data-close-rewrite]").forEach((item) => {
  item.addEventListener("click", closeRewriteDrawer);
});

$("rewriteButton").addEventListener("click", runPromptRewrite);

document.querySelectorAll("[data-close-agent]").forEach((item) => {
  item.addEventListener("click", closeAgentDrawer);
});

$("agentAnalyzeButton").addEventListener("click", runAgentAnalyze);
$("agentGenerateButton").addEventListener("click", runAgentGenerate);
$("portraitGenerateButton")?.addEventListener("click", generatePortraitPrompt);
$("portraitLoadMoreButton")?.addEventListener("click", loadMorePortraitMaterials);
$("portraitImportToggleButton")?.addEventListener("click", () => {
  state.portraitImportOpen = !state.portraitImportOpen;
  renderPortrait();
});
$("portraitImportPromptInput")?.addEventListener("input", syncPortraitImportPrompt);
$("portraitAnalyzePromptButton")?.addEventListener("click", analyzePortraitImportPrompt);
$("portraitClearImportButton")?.addEventListener("click", clearPortraitImport);
$("portraitOpenSlotsButton")?.addEventListener("click", () => {
  state.portraitDrawerOpen = true;
  renderPortrait();
});
$("portraitPrevStepButton")?.addEventListener("click", prevPortraitStep);
$("portraitNextStepButton")?.addEventListener("click", nextPortraitStep);
$("portraitGlobalIdeaInput")?.addEventListener("input", syncPortraitGlobalIdea);
$("portraitBasePromptInput")?.addEventListener("input", syncPortraitBasePrompt);
$("portraitChooseBasePromptButton")?.addEventListener("click", () => openPromptPicker("portraitBasePrompt"));
$("portraitSearchInput")?.addEventListener("input", (event) => {
  state.portraitQuery = event.currentTarget.value;
  reloadPortraitMaterials();
});
$("portraitMobileSearchInput")?.addEventListener("input", (event) => {
  state.portraitQuery = event.currentTarget.value;
  reloadPortraitMaterials();
});
document.querySelectorAll("[data-close-portrait-slots]").forEach((item) => {
  item.addEventListener("click", () => {
    state.portraitDrawerOpen = false;
    renderPortrait();
  });
});
document.querySelectorAll("[data-prompt-section]").forEach((button) => {
  button.addEventListener("click", () => setPromptSection(button.dataset.promptSection || ""));
});
$("newAlbumFolderButton")?.addEventListener("click", createAlbumFolder);
$("inboxUploadInput")?.addEventListener("change", event => uploadAlbumImage(event.currentTarget, true));
$("albumUploadInput")?.addEventListener("change", (event) => uploadAlbumImage(event.currentTarget));

document.querySelectorAll("[data-nav-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.navView));
});

document.querySelectorAll("[data-history-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-history-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.historyFilter = button.dataset.historyFilter;
    state.historyPage = 0;
    render();
  });
});

$("backButton").addEventListener("click", () => {
  if (state.view === 'inspiration') {
    const r=state.inspirationRoute || HuashiInspirationNav.parse('#inspiration');
    setView(r.entryId ? HuashiInspirationNav.format({...r,entryId:''}) : r.view==='home' ? 'home' : r.collection==='code' ? 'inspiration/animation' : 'inspiration');
  }
  else if (state.view === "prompts" && state.promptSection) {
    setView(state.promptSection === "portrait" ? "inspiration/prompts" : "inspiration");
  }
  else if (state.view === "compose") setView("create");
  else if (state.view === "result") setView("history");
  else setView("home");
});

$("clearPendingInspiration")?.addEventListener("click", () => { state.pendingComposePrompt = ""; render(); });
$("gridSizeInput")?.addEventListener("input", (event) => { state.galleryColumns = Number(event.currentTarget.value); renderGallery(); });
HuashiRooms.inspirationState.kind = initialRoute.kind || "";
window.addEventListener("hashchange", () => {
  const route = HuashiRooms.parseRoute(window.location.hash);
  if(route.kind)HuashiRooms.inspirationState.kind = route.kind;
  setView(window.location.hash.replace("#", ""), {historyMode:"none"});
});
document.addEventListener("error", (event) => {
  if (event.target instanceof HTMLImageElement && event.target.closest(".photo-tile, .artwork-choice, .room-search-image")) {
    event.target.classList.add("is-missing");
  }
}, true);
$("createTaskForm").addEventListener("invalid", (event) => {
  const advanced = event.target.closest(".room-advanced");
  if (advanced) advanced.open = true;
}, true);
document.addEventListener("keydown", (event) => {
  if (document.querySelector("dialog[open]")) return;
  if (!$('inspirationDetail').open) {
    const drawer=[$('promptPicker'),$('artworkPicker')].find(element=>!element.classList.contains('hidden'));
    if(drawer) {
      if(event.key==='Escape'){event.preventDefault();drawer.id==='promptPicker'?closePromptPicker():closeArtworkPicker();return;}
      if(event.key==='Tab'){
        const focusable=Array.from(drawer.querySelectorAll('button:not([disabled]),input:not([disabled]),a[href],select')).filter(element=>element.getClientRects().length);
        const first=focusable[0],last=focusable.at(-1);
        if(event.shiftKey && (document.activeElement===first || !drawer.contains(document.activeElement))){event.preventDefault();last?.focus();}
        else if(!event.shiftKey && (document.activeElement===last || !drawer.contains(document.activeElement))){event.preventDefault();first?.focus();}
      }
      return;
    }
  }
  if (state.view !== "gallery" || !state.galleryViewerOpen) return;
  if(event.key==='Tab') {
    const viewer=document.querySelector('.photo-viewer');
    const focusable=[...viewer.querySelectorAll('button:not([disabled]),select,summary')].filter(el=>el.getClientRects().length);
    const first=focusable[0],last=focusable.at(-1);
    if(event.shiftKey && (document.activeElement===first || !viewer.contains(document.activeElement))){event.preventDefault();last?.focus();}
    else if(!event.shiftKey && (document.activeElement===last || !viewer.contains(document.activeElement))){event.preventDefault();first?.focus();}
    return;
  }
  if(/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;
  if (event.key === "Escape") { state.galleryViewerOpen = false; renderGallery(); }
  else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    const count = artworkItems().length;
    if (!count) return;
    state.galleryIndex = (state.galleryIndex + (event.key === "ArrowLeft" ? -1 : 1) + count) % count;
    state.galleryZoom = 1;
    renderGallery();
  }
});
render();

loadData().catch((error) => setNotice(error.message, "error"));

function bindCreationImages(root) {
  root?.querySelectorAll('[data-send-image]').forEach(button => {
    button.onclick = () => {
      const image = {path:button.dataset.imagePath, name:button.dataset.imageName};
      const apps = state.apps.filter(app => appInputs(app).some(input => ['image','file'].includes(input.type)));
      const send = appId => {
        const app = apps.find(app => app.id === appId);
        const input = app && appInputs(app).find(input => ['image','file'].includes(input.type));
        if (!input) {showToast('暂时没有可用的对应编辑画布','error');return;}
        state.selectedAppId=app.id; setView('compose');
        const form=$('createTaskForm');
        const field=form.querySelector(`[data-artwork-input="${CSS.escape(input.id)}"]`);
        if (!field) {showToast('当前画布无法接收这张图片','error');return;}
        field.value=image.path;
        showInputPreview(input.id,button.dataset.imagePreview);
        form.querySelectorAll(`[data-file-input="${CSS.escape(input.id)}"]`).forEach(file => file.value='');
        const label=form.querySelector(`[data-file-label="${CSS.escape(input.id)}"]`);
        if(label)label.textContent=`陈列室：${image.name || image.path.split('/').pop()}`;
        updateGenerateState();
        showToast(button.dataset.sendImage==='double' ? '已带入第一张图片，请选择第二张' : '图片已带入创作画布','info');
      };
      if (['reference','choose'].includes(button.dataset.sendImage)) HuashiCreation.chooseCanvas(apps,send);
      else send(button.dataset.sendImage==='single' ? 'runpod-qwen21-single-image-edit' : 'runpod-qwen21-two-image-edit');
    };
  });
}

function showInputPreview(key, url) {
  const preview = $('createTaskForm').querySelector(`[data-input-preview="${CSS.escape(key)}"]`);
  if (!preview) return;
  const safe = typeof url === 'string' && url.startsWith('/') && !url.startsWith('//');
  preview.hidden = !safe;
  if (safe) preview.src=url; else preview.removeAttribute('src');
}
