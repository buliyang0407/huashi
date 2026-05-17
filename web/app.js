const state = {
  apps: [],
  tasks: [],
  selectedAppId: null,
  selectedTaskId: null,
  category: "全部",
  historyFilter: "all",
  search: "",
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
  return ["home", "compose", "result", "history"].includes(view) ? view : "home";
}

async function loadData() {
  const [{ apps }, { tasks }] = await Promise.all([api("/api/apps"), api("/api/tasks")]);
  state.apps = apps;
  state.tasks = tasks;
  if (!state.selectedAppId && apps.length) state.selectedAppId = apps[0].id;
  render();
  managePolling();
}

function selectedApp() {
  return state.apps.find((app) => app.id === state.selectedAppId) || state.apps[0];
}

function setView(view) {
  state.view = view;
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
}

function renderTitle() {
  const titles = {
    home: ["画室", "样式广场"],
    compose: [selectedApp()?.name || "生成", "设置输入"],
    result: ["生成结果", resultHint()],
    history: ["生成记录", `${filteredTasks().length} 条记录`],
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
}

function renderStyles() {
  const query = state.search.trim().toLowerCase();
  const apps = state.apps.filter((app) => {
    const matchCategory = state.category === "全部" || app.category === state.category;
    const matchSearch = !query || `${app.name} ${app.category} ${app.description}`.toLowerCase().includes(query);
    return matchCategory && matchSearch;
  });
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

function styleCard(app) {
  return `
    <button class="style-card" type="button" data-style-id="${app.id}">
      <span class="style-thumb ${app.cover_url ? "has-cover" : ""}" style="${coverStyle(app)}"></span>
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
    return `
      <div class="file-field" data-required="${input.required ? "1" : "0"}">
        <div class="field-title">${label}</div>
        <div class="picker-row">
          <label class="upload-drop compact" for="${inputId}_gallery">
            <input id="${inputId}_gallery" name="${name}" type="file" accept="image/*" data-file-input="${escapeAttr(input.id)}" />
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4M7 9l5-5 5 5M20 16.5V19a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-2.5" /></svg></span>
            <span>相册</span>
          </label>
          <label class="upload-drop compact" for="${inputId}_files">
            <input id="${inputId}_files" name="${name}" type="file" data-file-input="${escapeAttr(input.id)}" />
            <span class="upload-mark"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H10l2 2h5.5A2.5 2.5 0 0 1 20 8.5v8A2.5 2.5 0 0 1 17.5 19h-11A2.5 2.5 0 0 1 4 16.5Z" /></svg></span>
            <span>文件夹</span>
          </label>
        </div>
        <small class="file-name" data-file-label="${escapeAttr(input.id)}">未选择</small>
      </div>
    `;
  }
  if (input.type === "select") {
    const options = input.options || [];
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
    return `
      <label class="field-block">
        <span>${label}</span>
        <textarea name="${name}" rows="3" ${required}>${escapeHtml(input.defaultValue || "")}</textarea>
      </label>
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
      const label = document.querySelector(`[data-file-label="${CSS.escape(key)}"]`);
      if (label) label.textContent = file.name;
      updateGenerateState();
    });
  });
  $("dynamicInputs").querySelectorAll("input, textarea, select").forEach((input) => {
    input.addEventListener("input", updateGenerateState);
    input.addEventListener("change", updateGenerateState);
  });
}

function updateGenerateState() {
  const app = selectedApp();
  const inputs = app ? appInputs(app) : [];
  const form = $("createTaskForm");
  const ok = inputs.every((input) => {
    if (!input.required) return true;
    const name = `input_${input.id}`;
    if (input.type === "image" || input.type === "file") {
      return Array.from(form.querySelectorAll(`[name="${CSS.escape(name)}"]`)).some((item) => item.files && item.files.length);
    }
    const field = form.querySelector(`[name="${CSS.escape(name)}"]`);
    return field && String(field.value || "").trim();
  });
  $("generateButton").disabled = !ok;
}

function renderHistory() {
  const tasks = filteredTasks();
  $("taskList").innerHTML = tasks.length ? tasks.map(recordRow).join("") : `<div class="empty-state">暂无记录</div>`;
  document.querySelectorAll("[data-task-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedTaskId = row.dataset.taskId;
      setView("result");
    });
  });
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
    `;
    bindTaskActions();
    return;
  }
  const images = task.outputs.filter((item) => item.type === "image" || ["png", "jpg", "jpeg", "webp"].includes(item.type));
  const packages = task.outputs.filter((item) => item.type === "zip");
  $("resultView").className = "result-view";
  $("resultView").innerHTML = `
    <div class="result-gallery">
      ${images.length ? images.map((item) => `<a href="${item.url}" target="_blank"><img src="${item.url}" alt="生成结果"></a>`).join("") : `<div class="empty-state">暂无预览</div>`}
    </div>
    <div class="action-grid">
      <button class="primary-button" type="button" data-action="archive" data-task-id="${task.id}" ${task.saved ? "disabled" : ""}>${task.saved ? "已保存" : "保存"}</button>
      ${downloadButton(images, packages)}
      <button class="secondary-button" type="button" data-action="retry" data-task-id="${task.id}">重做</button>
      <button class="danger-button" type="button" data-action="delete" data-task-id="${task.id}">删除</button>
    </div>
  `;
  bindTaskActions();
}

function currentTask() {
  return state.tasks.find((task) => task.id === state.selectedTaskId) || state.tasks[0];
}

function downloadButton(images, packages) {
  const item = packages[0] || images[0];
  return item
    ? `<a class="secondary-button link-button" href="${item.url}" download>下载</a>`
    : `<button class="secondary-button" type="button" disabled>下载</button>`;
}

function taskThumb(task) {
  const image = task.outputs.find((item) => item.type === "image" || ["png", "jpg", "jpeg", "webp"].includes(item.type));
  if (image) return `<img class="record-thumb" src="${image.url}" alt="">`;
  if (task.input_url) return `<img class="record-thumb" src="${task.input_url}" alt="">`;
  return `<span class="record-thumb"></span>`;
}

function bindTaskActions() {
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
  if (app.cover_url) return `background-image: url('${app.cover_url}')`;
  return `background: linear-gradient(135deg, ${app.accent || "#6d5dfc"}, #f1f4ff)`;
}

function outputLabel(app) {
  return app.output_type === "zip" ? "相册" : "图片";
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

$("searchInput").addEventListener("input", (event) => {
  state.search = event.target.value;
  renderStyles();
});

$("categorySelect").addEventListener("change", (event) => {
  state.category = event.target.value;
  render();
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
  else setView("home");
});

window.addEventListener("hashchange", () => {
  state.view = initialView();
  render();
});

loadData().catch((error) => setNotice(error.message, "error"));
