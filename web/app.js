const state = {
  apps: [],
  tasks: [],
  prompts: [],
  albums: [],
  albumItems: [],
  selectedAlbumId: "works",
  galleryFolderOpen: false,
  posePath: "",
  poseData: null,
  promptModels: [],
  selectedAppId: null,
  selectedTaskId: null,
  selectedPromptField: "",
  selectedArtworkField: "",
  artworkPickerMode: "input",
  artworkPickerAlbumOpen: false,
  artworkPickerAlbumId: "",
  artworkPickerPosePath: "",
  artworkPickerItems: [],
  artworkPickerPoseData: null,
  rewritingPromptId: "",
  galleryIndex: 0,
  galleryViewerOpen: false,
  homeSort: "new",
  category: "全部",
  historyFilter: "all",
  search: "",
  promptSearch: "",
  pickerSearch: "",
  rewriteCandidates: [],
  rewriteTranslations: {},
  agentPromptId: "",
  agentAnalysis: null,
  agentResult: null,
  agentParentVariantId: "",
  agentRoundIndex: 0,
  agentSessionId: "",
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

function initialView() {
  const view = window.location.hash.replace("#", "");
  return ["home", "compose", "result", "history", "gallery", "prompts"].includes(view) ? view : "home";
}

async function loadData() {
  const [{ apps }, { tasks }, { prompts }, { models }, { folders }] = await Promise.all([
    api("/api/apps"),
    api("/api/tasks"),
    api("/api/prompts"),
    api("/api/prompt-models"),
    api("/api/albums"),
  ]);
  state.apps = apps;
  state.tasks = tasks;
  state.prompts = prompts;
  state.promptModels = models;
  state.albums = folders;
  if (!state.albums.some((folder) => folder.id === state.selectedAlbumId)) {
    state.selectedAlbumId = state.albums[0]?.id || "works";
  }
  await refreshAlbumItems();
  if (!state.selectedAppId && apps.length) state.selectedAppId = apps[0].id;
  render();
  managePolling();
}

async function refreshAlbums() {
  const { folders } = await api("/api/albums");
  state.albums = folders;
  if (!state.albums.some((folder) => folder.id === state.selectedAlbumId)) {
    state.selectedAlbumId = state.albums[0]?.id || "works";
  }
  await refreshAlbumItems();
}

async function refreshAlbumItems() {
  if (state.selectedAlbumId === "__pose__") {
    const data = await api(`/api/pose?path=${encodeURIComponent(state.posePath || "")}&limit=120`);
    state.poseData = data;
    state.albumItems = data.items || [];
    return;
  }
  const { items } = await api(`/api/albums/items?folder_id=${encodeURIComponent(state.selectedAlbumId || "works")}`);
  state.poseData = null;
  state.albumItems = items;
}

function selectedApp() {
  return state.apps.find((app) => app.id === state.selectedAppId) || state.apps[0];
}

function currentAlbum() {
  return state.albums.find((folder) => folder.id === state.selectedAlbumId) || state.albums[0];
}

function setView(view) {
  state.view = view;
  if (view === "gallery") {
    state.galleryFolderOpen = false;
    state.galleryViewerOpen = false;
  }
  if (window.location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
  render();
}

function render() {
  const shell = $("app");
  shell.dataset.view = state.view;
  document.querySelectorAll("[data-screen]").forEach((screen) => {
    screen.classList.toggle("active", screen.dataset.screen === state.view);
  });
  document.querySelectorAll("[data-nav-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.navView === state.view);
  });
  $("backButton").classList.toggle("visible", state.view !== "home");
  renderTitle();
  renderCategories();
  renderStyles();
  renderCompose();
  renderResult();
  renderHistory();
  renderGallery();
  renderPrompts();
  renderRewriteModels();
  renderAgentModels();
}

function renderTitle() {
  const titles = {
    home: ["画室", "样式广场"],
    compose: [selectedApp()?.name || "生成", "设置输入"],
    result: ["生成结果", resultHint()],
    history: ["生成记录", `${filteredTasks().length} 条记录`],
    gallery: ["画册", state.galleryFolderOpen ? `${currentAlbum()?.name || "文件夹"} · ${artworkItems().length} 张图片` : "选择文件夹"],
    prompts: ["提示词库", `${filteredPrompts().length} 条提示词`],
  };
  const [title, hint] = titles[state.view] || titles.home;
  $("pageTitle").textContent = title;
  $("pageHint").textContent = hint;
}

function resultHint() {
  const task = currentTask();
  return task ? `${task.app_name} · ${formatTime(task.created_at)}` : "暂无";
}

function renderCategories() {
  const categories = ["全部", ...new Set(state.apps.map((app) => app.category).filter(Boolean))];
  if (!categories.includes(state.category)) state.category = "全部";
  $("categorySelect").innerHTML = categories
    .map((name) => `<option value="${escapeAttr(name)}" ${state.category === name ? "selected" : ""}>${escapeHtml(name)}</option>`)
    .join("");
  if ($("sortSelect")) $("sortSelect").value = state.homeSort;
}

function renderStyles() {
  const query = state.search.trim().toLowerCase();
  let apps = state.apps.filter((app) => {
    const matchCategory = state.category === "全部" || app.category === state.category;
    const matchSearch = !query || `${app.name} ${app.category} ${app.description}`.toLowerCase().includes(query);
    return matchCategory && matchSearch;
  });
  apps = sortApps(apps);
  const favorites = apps.filter((app) => app.favorite);
  const otherApps = apps.filter((app) => !app.favorite);
  $("favoriteSection").hidden = favorites.length === 0;
  $("favoriteGrid").innerHTML = favorites.map(styleCard).join("");
  $("styleSectionTitle").textContent = state.category === "全部" ? "全部样式" : state.category;
  $("styleGrid").innerHTML = otherApps.length
    ? otherApps.map(styleCard).join("")
    : `<div class="empty-state">${favorites.length ? "下面暂无其他样式" : "没有匹配的样式"}</div>`;
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
  return `
    <button class="style-card" type="button" data-style-id="${app.id}">
      <span class="style-thumb ${app.cover_url ? "has-cover" : ""}" style="${coverStyle(app)}">
        ${app.cover_url ? `<img loading="lazy" src="${app.cover_url}" alt="">` : ""}
      </span>
      <span class="style-name">${escapeHtml(app.name)}</span>
      <span class="style-meta">
        <span>${escapeHtml(app.category)}</span>
        ${app.favorite ? "<b>常用</b>" : ""}
      </span>
    </button>
  `;
}

function renderCompose() {
  const app = selectedApp();
  if (!app) return;
  $("composeCover").style = coverStyle(app);
  $("composeCover").classList.toggle("has-cover", Boolean(app.cover_url));
  $("composeTitle").textContent = app.name;
  $("composeMeta").textContent = `${app.category} · ${outputLabel(app)}`;
  $("dynamicInputs").innerHTML = appInputs(app).map(inputControl).join("");
  bindDynamicInputs();
  updateGenerateState();
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
          <label class="upload-drop compact" for="${inputId}_gallery">
            <input id="${inputId}_gallery" name="${name}" type="file" accept="image/*" data-file-input="${escapeAttr(input.id)}" />
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M20 16.5V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.5" /></svg></span>
            <span>相册</span>
          </label>
          <button class="upload-drop compact" type="button" data-artwork-target="${escapeAttr(input.id)}">
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5Zm3 12 3.2-3.2 2.3 2.3L16 11l3 4.2M8.5 8.5h.01" /></svg></span>
            <span>作品库</span>
          </button>
        </div>
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
      ? `<button class="inline-tool" type="button" data-prompt-target="${escapeAttr(input.id)}">从提示词库选择</button>`
      : "";
    return `
      <div class="field-block ${input.role === "prompt" ? "prompt-field" : ""}">
        <span><label for="${inputId}">${label}</label>${promptButton}</span>
        <textarea id="${inputId}" name="${name}" rows="3" ${required}>${escapeHtml(input.defaultValue || "")}</textarea>
      </div>
    `;
  }
  return `
    <label class="field-block">
      <span>${label}</span>
      <input name="${name}" type="${input.type === "number" ? "number" : "text"}" value="${escapeAttr(input.defaultValue || "")}" ${required} />
    </label>
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
  $("dynamicInputs").querySelectorAll("[data-artwork-target]").forEach((button) => {
    button.addEventListener("click", () => openArtworkPicker(button.dataset.artworkTarget));
  });
  $("dynamicInputs").querySelectorAll("[data-clear-file-target]").forEach((button) => {
    button.addEventListener("click", () => clearImageInput(button.dataset.clearFileTarget));
  });
}

function clearImageInput(key) {
  if (!key) return;
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
  $("generateButton").disabled = !ok;
}

function renderHistory() {
  const tasks = filteredTasks();
  $("taskList").innerHTML = tasks.length ? tasks.map(recordRow).join("") : `<div class="empty-state">暂无记录</div>`;
  $("taskList").querySelectorAll("[data-task-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedTaskId = row.dataset.taskId;
      setView("result");
    });
  });
}

function artworkItems() {
  return (state.albumItems || [])
    .filter((item) => isVisibleImageOutput(item))
    .map((item, index) => ({ ...item, index }));
}

function renderGallery() {
  const target = $("artworkGallery");
  if (!target) return;
  renderAlbumFolders();
  if (!state.galleryFolderOpen) {
    target.className = "artwork-gallery album-landing";
    target.innerHTML = renderAlbumLanding();
    bindAlbumLanding(target);
    return;
  }
  if (state.selectedAlbumId === "__pose__") {
    renderPoseGallery(target);
    return;
  }
  const items = artworkItems();
  if (!items.length) {
    target.className = "artwork-gallery empty-state";
    target.innerHTML = "这个文件夹还没有图片";
    return;
  }
  state.galleryIndex = Math.min(Math.max(state.galleryIndex, 0), items.length - 1);
  const item = items[state.galleryIndex];
  target.className = "artwork-gallery photo-roll";
  target.innerHTML = `
    <div class="photo-grid">
      ${items.map((thumb, index) => `
        <button class="photo-tile" type="button" data-gallery-index="${index}" aria-label="打开图片 ${index + 1}">
          <img class="${thumb.blurred ? "is-blurred" : ""}" loading="lazy" src="${thumb.url}" alt="">
        </button>
      `).join("")}
    </div>
    ${state.galleryViewerOpen ? galleryViewer(item, items.length) : ""}
  `;
  bindGalleryActions(target, items);
}

function galleryViewer(item, total) {
  const folders = state.albums || [];
  const canBlur = item.task_id && item.output_path;
  const canManage = item.source_type !== "pose";
  return `
    <div class="photo-viewer" data-gallery-stage>
      <button class="viewer-close" type="button" data-gallery-close aria-label="关闭">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12" /></svg>
      </button>
      <img class="${item.blurred ? "is-blurred" : ""}" src="${item.url}" alt="作品">
      <div class="viewer-actions">
        ${canBlur ? `<button type="button" data-toggle-output-blur="${escapeAttr(item.task_id)}" data-output-path="${escapeAttr(item.output_path || item.path)}">
          ${item.blurred ? "还原" : "模糊"}
        </button>` : ""}
        ${canManage ? `
          <button type="button" data-reorder-album-item="${escapeAttr(item.id)}" data-direction="up">前移</button>
          <button type="button" data-reorder-album-item="${escapeAttr(item.id)}" data-direction="down">后移</button>
          <label class="viewer-move-select">
            <span>移到</span>
            <select data-move-album-item="${escapeAttr(item.id)}">
              ${folders.filter((folder) => !folder.virtual).map((folder) => `<option value="${escapeAttr(folder.id)}" ${folder.id === item.folder_id ? "selected" : ""}>${escapeHtml(folder.name)}</option>`).join("")}
            </select>
          </label>
          <button class="danger" type="button" data-delete-album-item="${escapeAttr(item.id)}">删除</button>
        ` : ""}
      </div>
      <div class="viewer-meta">
        <span>${state.galleryIndex + 1} / ${total}</span>
        <small>${escapeHtml(item.title || item.app_name || "图片")} · ${formatTime(item.created_at)}</small>
      </div>
    </div>
  `;
}

function renderAlbumFolders() {
  const target = $("albumFolderList");
  if (!target) return;
  if (!state.galleryFolderOpen) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = (state.albums || []).map((folder) => `
    <button class="album-folder ${folder.id === state.selectedAlbumId ? "active" : ""}" type="button" data-album-folder="${escapeAttr(folder.id)}">
      ${escapeHtml(folder.name)}
      <span>${Number(folder.item_count || 0)}</span>
    </button>
  `).join("");
  target.querySelectorAll("[data-album-folder]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedAlbumId = button.dataset.albumFolder || "works";
      state.posePath = "";
      state.galleryIndex = 0;
      state.galleryViewerOpen = false;
      state.galleryFolderOpen = true;
      await refreshAlbumItems();
      renderGallery();
      renderTitle();
    });
  });
}

function renderPoseGallery(target) {
  const data = state.poseData || { directories: [], items: [], breadcrumbs: [], next_offset: null, image_count: 0 };
  const items = artworkItems();
  state.galleryIndex = Math.min(Math.max(state.galleryIndex, 0), Math.max(items.length - 1, 0));
  const item = items[state.galleryIndex];
  target.className = "artwork-gallery pose-browser";
  target.innerHTML = `
    <div class="pose-path-bar">
      <button type="button" data-pose-path="">POSE</button>
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
            <img loading="lazy" src="${thumb.url}" alt="">
          </button>
        `).join("")}
      </div>
    ` : ""}
    ${data.next_offset !== null ? `<button class="secondary-button pose-more-button" type="button" data-pose-more="${Number(data.next_offset)}">加载更多（${items.length}/${Number(data.image_count || items.length)}）</button>` : ""}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个 POSE 文件夹没有图片</div>` : ""}
    ${state.galleryViewerOpen && item ? galleryViewer(item, items.length) : ""}
  `;
  bindPoseGalleryActions(target, items);
}

function bindPoseGalleryActions(root, items) {
  root.querySelectorAll("[data-pose-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.posePath = button.dataset.posePath || "";
      state.galleryIndex = 0;
      state.galleryViewerOpen = false;
      await refreshAlbumItems();
      renderGallery();
      renderTitle();
    });
  });
  root.querySelector("[data-pose-more]")?.addEventListener("click", async (event) => {
    const offset = Number(event.currentTarget.dataset.poseMore || 0);
    const data = await api(`/api/pose?path=${encodeURIComponent(state.posePath || "")}&offset=${offset}&limit=120`);
    state.poseData = { ...data, items: [...(state.poseData?.items || []), ...(data.items || [])] };
    state.albumItems = state.poseData.items;
    renderGallery();
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
  const folders = state.albums || [];
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
  state.selectedArtworkField = inputId;
  state.artworkPickerMode = mode;
  state.artworkPickerAlbumOpen = false;
  state.artworkPickerAlbumId = "";
  state.artworkPickerPosePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPoseData = null;
  $("artworkPicker").classList.remove("hidden");
  $("artworkPicker").setAttribute("aria-hidden", "false");
  renderArtworkPicker();
}

function closeArtworkPicker() {
  $("artworkPicker").classList.add("hidden");
  $("artworkPicker").setAttribute("aria-hidden", "true");
  state.selectedArtworkField = "";
  state.artworkPickerAlbumOpen = false;
  state.artworkPickerAlbumId = "";
  state.artworkPickerPosePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPoseData = null;
}

function renderArtworkPicker() {
  const target = $("artworkPickerList");
  if (!state.artworkPickerAlbumOpen) {
    target.className = "artwork-picker-folders album-folder-grid";
    target.innerHTML = (state.albums || []).map((folder) => `
      <button class="album-folder-card" type="button" data-picker-folder="${escapeAttr(folder.id)}">
        <span class="folder-shape" aria-hidden="true"></span>
        <strong>${escapeHtml(folder.name)}</strong>
        <small>${folder.virtual ? `${Number(folder.directory_count || 0)} 个文件夹` : `${Number(folder.item_count || 0)} 张图片`}</small>
      </button>
    `).join("");
    target.querySelectorAll("[data-picker-folder]").forEach((button) => {
      button.addEventListener("click", () => openArtworkPickerFolder(button.dataset.pickerFolder || "works"));
    });
    return;
  }
  if (state.artworkPickerAlbumId === "__pose__") {
    renderArtworkPosePicker(target);
    return;
  }
  const items = state.artworkPickerItems || [];
  target.className = "artwork-picker-grid";
  target.innerHTML = items.length ? artworkPickerImageButtons(items) : `<div class="empty-state">这个文件夹还没有可复用图片</div>`;
  target.querySelectorAll("[data-use-artwork]").forEach((button) => {
    button.addEventListener("click", () => useArtwork(Number(button.dataset.useArtwork || 0)));
  });
}

async function openArtworkPickerFolder(folderId) {
  state.artworkPickerAlbumOpen = true;
  state.artworkPickerAlbumId = folderId;
  state.artworkPickerPosePath = "";
  state.artworkPickerItems = [];
  state.artworkPickerPoseData = null;
  if (folderId === "__pose__") {
    await refreshArtworkPickerPose("");
  } else {
    const { items } = await api(`/api/albums/items?folder_id=${encodeURIComponent(folderId || "works")}`);
    state.artworkPickerItems = (items || []).filter((item) => isVisibleImageOutput(item));
  }
  renderArtworkPicker();
}

function artworkPickerImageButtons(items) {
  return items.map((item, index) => `
    <button class="artwork-choice" type="button" data-use-artwork="${index}">
      <img class="${item.blurred ? "is-blurred" : ""}" src="${item.url}" alt="">
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
      <button type="button" data-picker-pose-path="">POSE</button>
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
    ${data.next_offset !== null ? `<button class="secondary-button pose-more-button" type="button" data-picker-pose-more="${Number(data.next_offset)}">加载更多（${items.length}/${Number(data.image_count || items.length)}）</button>` : ""}
    ${!(data.directories || []).length && !items.length ? `<div class="empty-state">这个 POSE 文件夹没有图片</div>` : ""}
  `;
  target.querySelectorAll("[data-picker-pose-path]").forEach((button) => {
    button.addEventListener("click", () => refreshArtworkPickerPose(button.dataset.pickerPosePath || "").then(renderArtworkPicker));
  });
  target.querySelector("[data-picker-pose-more]")?.addEventListener("click", async (event) => {
    const offset = Number(event.currentTarget.dataset.pickerPoseMore || 0);
    const data = await api(`/api/pose?path=${encodeURIComponent(state.artworkPickerPosePath || "")}&offset=${offset}&limit=120`);
    state.artworkPickerPoseData = { ...data, items: [...(state.artworkPickerPoseData?.items || []), ...(data.items || [])] };
    state.artworkPickerItems = state.artworkPickerPoseData.items || [];
    renderArtworkPicker();
  });
  target.querySelectorAll("[data-use-artwork]").forEach((button) => {
    button.addEventListener("click", () => useArtwork(Number(button.dataset.useArtwork || 0)));
  });
}

async function refreshArtworkPickerPose(path) {
  state.artworkPickerPosePath = path || "";
  const data = await api(`/api/pose?path=${encodeURIComponent(state.artworkPickerPosePath)}&limit=120`);
  state.artworkPickerPoseData = data;
  state.artworkPickerItems = data.items || [];
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
  form.querySelectorAll(`[data-file-input="${CSS.escape(key)}"]`).forEach((input) => {
    input.value = "";
  });
  const label = document.querySelector(`[data-file-label="${CSS.escape(key)}"]`);
  if (label) label.textContent = `作品库：${item.download_name || item.path?.split("/").pop() || "作品"}`;
  closeArtworkPicker();
  updateGenerateState();
}

function renderPrompts() {
  const target = $("promptList");
  if (!target) return;
  const prompts = filteredPrompts();
  target.innerHTML = prompts.length
    ? prompts.map((prompt) => promptCard(prompt, { mode: "manage" })).join("")
    : `<div class="empty-state">还没有保存提示词</div>`;
  bindPromptListActions(target);
}

function filteredPrompts(source = state.prompts, query = state.promptSearch) {
  const text = String(query || "").trim().toLowerCase();
  return source.filter((prompt) => {
    if (!text) return true;
    const variantText = (prompt.variants || []).map((variant) => `${variant.title} ${variant.content} ${variant.translation} ${variant.edit_idea}`).join(" ");
    const haystack = `${prompt.title} ${prompt.content} ${variantText} ${(prompt.tags || []).join(" ")} ${(prompt.apps || []).map((app) => app.name).join(" ")}`.toLowerCase();
    return haystack.includes(text);
  });
}

function promptCard(prompt, options = {}) {
  const tags = (prompt.tags || []).slice(0, 4).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("");
  const variants = prompt.variants || [];
  const sample = prompt.sample_url
    ? `<button class="prompt-sample" type="button" data-agent-prompt="${prompt.id}"><img loading="lazy" src="${prompt.sample_url}" alt=""></button>`
    : `<button class="prompt-sample empty" type="button" data-agent-prompt="${prompt.id}">提示词</button>`;
  const pickButton = options.mode === "picker"
    ? `<button class="tiny-button" type="button" data-use-prompt="${prompt.id}">使用</button>`
    : "";
  const manageButtons = options.mode === "manage"
    ? `
      <button class="tiny-button" type="button" data-agent-prompt="${prompt.id}">智能拆解</button>
      <button class="tiny-button" type="button" data-edit-prompt="${prompt.id}">编辑</button>
      <button class="tiny-button danger" type="button" data-delete-prompt="${prompt.id}">删除</button>
    `
    : "";
  return `
    <article class="prompt-card">
      ${sample}
      <div class="prompt-card-main">
        <strong>${escapeHtml(prompt.title)}</strong>
        <p>${escapeHtml(prompt.content)}</p>
        <small>使用 ${Number(prompt.use_count || 0)} 次${variants.length ? ` · ${variants.length} 个衍生` : ""}</small>
        ${tags ? `<div class="tag-row">${tags}</div>` : ""}
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
      <div class="prompt-card-actions">
        ${prompt.favorite ? `<span class="star-mark">常用</span>` : ""}
        ${pickButton}
        ${manageButtons}
      </div>
    </article>
  `;
}

function bindPromptListActions(root) {
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
  root.querySelectorAll("[data-copy-variant]").forEach((button) => {
    button.addEventListener("click", async () => {
      const variant = findPromptVariant(button.dataset.copyVariant)?.variant;
      await navigator.clipboard.writeText(variant?.content || "");
      button.textContent = "已复制";
    });
  });
  root.querySelectorAll("[data-delete-variant]").forEach((button) => {
    button.addEventListener("click", () => deletePromptVariant(button.dataset.deleteVariant));
  });
  root.querySelectorAll("[data-agent-prompt]").forEach((button) => {
    button.addEventListener("click", () => openAgentDrawer(button.dataset.agentPrompt));
  });
}

function openPromptForm(prompt = null) {
  $("promptForm").classList.remove("hidden");
  $("promptIdInput").value = prompt?.id || "";
  $("promptTitleInput").value = prompt?.title || "";
  $("promptContentInput").value = prompt?.content || "";
  $("promptTagsInput").value = (prompt?.tags || []).join(", ");
  $("promptFavoriteInput").checked = Boolean(prompt?.favorite);
  $("promptNoteInput").value = prompt?.note || "";
  setPromptSample(prompt?.sample_path || "", prompt?.sample_url || "");
  $("promptContentInput").focus();
}

function closePromptForm() {
  $("promptForm").classList.add("hidden");
  $("promptForm").reset();
  $("promptIdInput").value = "";
  setPromptSample("", "");
}

function editPrompt(promptId) {
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
  return {
    title: $("promptTitleInput").value.trim(),
    content: $("promptContentInput").value.trim(),
    tags: $("promptTagsInput").value.trim(),
    favorite: $("promptFavoriteInput").checked,
    note: $("promptNoteInput").value.trim(),
    sample_path: $("promptSamplePathInput").value.trim(),
    app_ids: [],
  };
}

function setPromptSample(path, url = "") {
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
  $("pickerSearchInput").value = "";
  $("promptPicker").classList.remove("hidden");
  $("promptPicker").setAttribute("aria-hidden", "false");
  renderPromptPicker();
}

function closePromptPicker() {
  $("promptPicker").classList.add("hidden");
  $("promptPicker").setAttribute("aria-hidden", "true");
  state.selectedPromptField = "";
}

function renderPromptPicker() {
  const ordered = [...state.prompts].sort((a, b) => {
    if (Boolean(b.favorite) !== Boolean(a.favorite)) return Number(b.favorite) - Number(a.favorite);
    return String(b.last_used_at || b.updated_at || "").localeCompare(String(a.last_used_at || a.updated_at || ""));
  });
  const prompts = filteredPrompts(ordered, state.pickerSearch);
  $("pickerPromptList").innerHTML = prompts.length
    ? prompts.map((prompt) => promptCard(prompt, { mode: "picker" })).join("")
    : `<div class="empty-state">没有匹配的提示词</div>`;
  bindPromptListActions($("pickerPromptList"));
}

async function usePrompt(promptId) {
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (!prompt || !state.selectedPromptField) return;
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
    if (!$("promptPicker").classList.contains("hidden")) renderPromptPicker();
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
  const hasAvailableGrok = state.promptModels.some((item) => item.id === "aihubmix-grok" && item.available);
  input.innerHTML = state.promptModels
    .map((model) => {
      const selected = (hasAvailableGrok && model.id === "aihubmix-grok") || (!hasAvailableGrok && model.default);
      return `
        <option value="${escapeAttr(model.id)}" ${selected ? "selected" : ""} ${model.available ? "" : "disabled"}>
          ${escapeHtml(model.label)}${model.available ? "" : "（未配置）"}
        </option>
      `;
    })
    .join("");
}

function openRewriteDrawer(promptId) {
  const prompt = state.prompts.find((item) => item.id === promptId);
  if (!prompt) return;
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
      await navigator.clipboard.writeText(text);
      button.textContent = "已复制";
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
  state.agentResult = null;
  state.agentParentVariantId = "";
  state.agentRoundIndex = 0;
  state.agentSessionId = newSessionId();
  $("agentPromptTitle").textContent = prompt.title || "提示词";
  $("agentPromptPreview").textContent = prompt.content || "";
  $("agentInstructionInput").value = "";
  $("agentInstructionLabel").textContent = "修改要求";
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
  setAgentStatus("正在拆解提示词结构...");
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
    renderAgentAnalysis();
    setAgentStatus("拆解完成，可以写修改要求了。", "info");
    $("agentInstructionInput").focus();
  } catch (error) {
    setAgentStatus(error.message, "error");
  } finally {
    $("agentAnalyzeButton").disabled = false;
  }
}

async function runAgentGenerate() {
  const prompt = state.prompts.find((item) => item.id === state.agentPromptId);
  const instruction = $("agentInstructionInput").value.trim();
  if (!prompt) return;
  if (!state.agentAnalysis) {
    setAgentStatus("先点一次“开始拆解”，让 AI 看懂原提示词。", "error");
    return;
  }
  if (!instruction) {
    setAgentStatus("先写一下你想修改什么。", "error");
    return;
  }
  const isRefine = Boolean(state.agentResult?.prompt_en);
  $("agentGenerateButton").disabled = true;
  $("agentResult").innerHTML = "";
  setAgentStatus(isRefine ? "正在基于当前结果继续微调..." : "正在生成 1 条完整提示词...");
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
    $("agentInstructionInput").value = "";
    $("agentInstructionLabel").textContent = "继续修改";
    setAgentStatus("已生成，可以复制、保存，或继续基于这条微调。", "info");
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
      <div class="analysis-kicker">${escapeHtml(analysis.prompt_type || "其他")}</div>
      <strong>${escapeHtml(analysis.core_image || "")}</strong>
      ${analysisPointSection("核心不变点", analysis.core_points)}
      ${analysisPointSection("可修改点", analysis.editable_points, true)}
      ${analysisTextSection("建议保留", analysis.keep_points)}
      ${analysisTextSection("不建议轻易改", analysis.avoid_changes)}
      <p class="agent-guide">${escapeHtml(analysis.guide || "")}</p>
    </section>
  `;
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
    await navigator.clipboard.writeText(state.agentResult?.prompt_en || "");
    event.currentTarget.textContent = "已复制";
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
        <small>${formatTime(task.created_at)}</small>
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
  if (task.status === "queued" || task.status === "running") {
    $("resultView").className = "result-view";
    $("resultView").innerHTML = `
      <div class="progress-card">
        <div class="compare-strip">
          ${task.input_url ? `<img src="${task.input_url}" alt="原图">` : "<span></span>"}
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
          <span class="pending-preview">生成中</span>
        </div>
        <p>正在调用 NAS 接口</p>
        <div class="progress-line"><span></span></div>
      </div>
    `;
    return;
  }
  if (task.status === "failed") {
    $("resultView").className = "result-view";
    $("resultView").innerHTML = `
      <div class="notice">${escapeHtml(task.error || "任务失败")}</div>
      <div class="action-grid">
        <button class="secondary-button" type="button" data-action="retry" data-task-id="${task.id}">重试</button>
        <button class="danger-button" type="button" data-action="delete" data-task-id="${task.id}">删除</button>
      </div>
      ${taskSettingsCard(task)}
    `;
    bindTaskActions();
    return;
  }
  const images = task.outputs.filter((item) => isVisibleImageOutput(item));
  const packages = task.outputs.filter((item) => !item.deleted && item.type === "zip");
  $("resultView").className = "result-view";
  $("resultView").innerHTML = `
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
    const label = input.role === "prompt" ? "提示词" : (input.label || input.fieldName || input.id);
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
  const image = task.outputs.find((item) => isVisibleImageOutput(item));
  if (image) return `<img class="record-thumb ${image.blurred ? "is-blurred" : ""}" src="${image.url}" alt="">`;
  if (task.input_url) return `<img class="record-thumb" src="${task.input_url}" alt="">`;
  return `<span class="record-thumb"></span>`;
}

function bindTaskActions() {
  document.querySelectorAll("[data-copy-task-prompt]").forEach((button) => {
    button.addEventListener("click", async () => {
      const task = state.tasks.find((item) => item.id === button.dataset.copyTaskPrompt);
      await navigator.clipboard.writeText(task?.prompt || "");
      button.textContent = "已复制";
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
          const { task } = await api(`/api/tasks/${taskId}/retry`, { method: "POST" });
          state.selectedTaskId = task.id;
          setView("result");
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
    await refreshAlbumItems();
    renderResult();
    renderGallery();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function createAlbumFolder() {
  const name = prompt("新文件夹名称");
  if (!name || !name.trim()) return;
  try {
    const { folder } = await api("/api/albums", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    state.selectedAlbumId = folder.id;
    await refreshAlbums();
    render();
  } catch (error) {
    setNotice(error.message, "error");
  }
}

async function uploadAlbumImage(input) {
  const file = input.files?.[0];
  if (!file) return;
  if (state.selectedAlbumId === "__pose__") {
    input.value = "";
    setNotice("POSE 文件夹是只读模板库，不能上传到这里。", "error");
    return;
  }
  const formData = new FormData();
  formData.append("folder_id", state.selectedAlbumId || "works");
  formData.append("image", file);
  try {
    await api("/api/albums/upload", { method: "POST", body: formData });
    input.value = "";
    await refreshAlbums();
    render();
  } catch (error) {
    input.value = "";
    setNotice(error.message, "error");
  }
}

async function moveAlbumItem(select) {
  const itemId = select.dataset.moveAlbumItem;
  const folderId = select.value;
  if (!itemId || !folderId) return;
  try {
    await api(`/api/albums/items/${itemId}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_id: folderId }),
    });
    state.galleryViewerOpen = false;
    await refreshAlbums();
    render();
  } catch (error) {
    setNotice(error.message, "error");
  }
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

async function deleteAlbumItem(button) {
  const itemId = button.dataset.deleteAlbumItem;
  if (!itemId) return;
  if (!confirm("从画册移除这张图片？")) return;
  try {
    await api(`/api/albums/items/${itemId}/delete`, { method: "POST" });
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

function managePolling() {
  const hasActive = state.tasks.some((task) => task.status === "queued" || task.status === "running");
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
  if (app.cover_url) return `background-image: url('${escapeAttr(app.cover_url)}')`;
  return "background-image: url('/default-app-icon.png')";
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
  return { queued: "处理中", running: "处理中", success: "已完成", failed: "失败" }[status] || status;
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

$("promptSearchInput").addEventListener("input", (event) => {
  state.promptSearch = event.target.value;
  renderPrompts();
});

$("pickerSearchInput").addEventListener("input", (event) => {
  state.pickerSearch = event.target.value;
  renderPromptPicker();
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
  if (!app) return;
  const formData = new FormData(event.currentTarget);
  formData.append("appId", app.id);
  $("generateButton").disabled = true;
  setNotice("已提交。");
  try {
    const { task } = await api("/api/tasks", { method: "POST", body: formData });
    state.selectedTaskId = task.id;
    $("createTaskForm").reset();
    setView("result");
    await loadData();
  } catch (error) {
    setNotice(error.message, "error");
  } finally {
    renderCompose();
  }
});

$("newPromptButton").addEventListener("click", () => openPromptForm());
$("cancelPromptButton").addEventListener("click", closePromptForm);
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
    closePromptForm();
    await loadData();
    setView("prompts");
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
$("newAlbumFolderButton")?.addEventListener("click", createAlbumFolder);
$("albumUploadInput")?.addEventListener("change", (event) => uploadAlbumImage(event.currentTarget));

document.querySelectorAll("[data-nav-view]").forEach((button) => {
  button.addEventListener("click", () => setView(button.dataset.navView));
});

document.querySelectorAll("[data-history-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("[data-history-filter]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.historyFilter = button.dataset.historyFilter;
    render();
  });
});

$("backButton").addEventListener("click", () => {
  if (state.view === "compose") setView("home");
  else if (state.view === "result") setView("history");
  else if (state.view === "gallery" && state.galleryFolderOpen) {
    state.galleryFolderOpen = false;
    state.galleryViewerOpen = false;
    render();
  }
  else setView("home");
});

window.addEventListener("hashchange", () => {
  state.view = initialView();
  render();
});

loadData().catch((error) => setNotice(error.message, "error"));
