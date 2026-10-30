/* Product navigation and room views. No task execution or database ownership. */
(() => {
  const rooms = [
    { id: "create", name: "创作间", en: "Create", description: "选择画布，让想法成为图片", icon: "m4 20 4-1 11-11-3-3L5 16l-1 4ZM14 7l3 3" },
    { id: "inspiration", name: "灵感屋", en: "Explore", description: "找案例、画风和好用的提示词", icon: "M9 18h6M10 21h4M8 13a6 6 0 1 1 8 0l-1 3H9l-1-3Z" },
    { id: "gallery", name: "陈列室", en: "Collect", description: "收藏作品，整理每一份素材", icon: "M4 5h16v15H4V5ZM4 15l5-5 5 5 3-3 3 3M8 8h.01" },
  ];
  const inspirationKinds = [
    { id: "case", name: "案例", description: "从完整作品中寻找创作方向", icon: "M4 4h7v7H4V4ZM14 4h6v7h-6V4ZM4 14h7v6H4v-6ZM14 14h6v6h-6v-6Z" },
    { id: "style", name: "画风", description: "摄影、绘画与不同的视觉语言", icon: "M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 0-4h-1a2 2 0 0 1 0-4h4a4 4 0 0 0 4-4c0-3-4-6-9-6ZM7 9h.01M10 6h.01M16 7h.01" },
    { id: "layout", name: "排版", description: "海报、卡片与画面结构的参考", icon: "M4 4h16v16H4V4ZM4 10h16M10 10v10" },
  ];
  const galleryCategories = [
    { id: "works", name: "我的作品", match: "作品" },
    { id: "__faces__", name: "人像库", virtual: true },
    { id: "__pose__", name: "姿势 / POSE", virtual: true },
    { id: "__costumes__", name: "服装库", virtual: true },
    { id: "icons", name: "图标库", match: "图标库" },
    { id: "__other__", name: "其他素材", match: "其他素材" },
    { id: "__inbox__", name: "待整理", match: "待整理" },
  ];
  const advancedIds = new Set(["sampler", "scheduler", "steps", "seed", "cfg", "denoise", "batch_size", "resolution"]);
  const icon = (path) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const asset = (path) => typeof path === "string" && path.startsWith("/") && !path.startsWith("//") ? `/inspiration${path}` : "";
  const roomForView = (view) => ["create", "compose", "history", "result", "queue"].includes(view) ? "create" : ["inspiration", "prompts", "portrait"].includes(view) ? "inspiration" : view === "gallery" ? "gallery" : "";
  const parseRoute = (hash) => {
    const value = String(hash || "").replace(/^#/, "");
    const old = window.HuashiInspirationNav?.legacy('/#'+value);
    if (window.HuashiInspirationNav && (value === 'inspiration' || value.startsWith('inspiration/') || old)) {
      const browserRoute = HuashiInspirationNav.parse(old || '#'+value);
      const canonicalHash = HuashiInspirationNav.format(browserRoute).slice(1);
      if (browserRoute.domain === 'prompt') return {view:'prompts', promptSection:browserRoute.view === 'portrait' ? 'portrait' : 'library', promptTool:'', canonicalHash};
      return {view:'inspiration', inspirationRoute:browserRoute, canonicalHash};
    }
    if (value === "portrait") return { view: "prompts", promptSection: "portrait" };
    if (["prompts", "rewrite", "translate"].includes(value)) return { view: "prompts", promptSection: "library", promptTool: "" };
    if (value.startsWith("inspiration-")) return { view: "inspiration", kind: inspirationKinds.some((k) => k.id === value.slice(12)) ? value.slice(12) : "" };
    return { view: ["home", "create", "compose", "result", "history", "queue", "gallery", "inspiration", "settings"].includes(value) ? value : "home", promptSection: "" };
  };
  const directoryLibraries = {
    __pose__: { root: "", label: "POSE" },
    __costumes__: { root: ".costume-library", label: "服装库" },
  };
  const costumeCategoryOrder = ["春装", "夏装", "秋装", "冬装", "内衣", "派对装", "泳装", "性感穿搭"];
  const directoryLibrary = id => directoryLibraries[id] || null;
  const directoryPath = (id, path = "") => {
    const library = directoryLibrary(id);
    if (!library) throw new Error("未知素材库");
    if (typeof path !== "string" || path.startsWith("/") || path.includes("\\") || path.split("/").some(part => part === "." || part === "..")) throw new Error("无效素材路径");
    return [library.root, path].filter(Boolean).join("/");
  };
  const directoryData = (id, data) => {
    const library = directoryLibrary(id);
    if (!library?.root) return data;
    const relative = path => {
      if (path === library.root) return "";
      if (!path.startsWith(library.root + "/")) throw new Error("素材目录超出当前库");
      return path.slice(library.root.length + 1);
    };
    const path = relative(data.path);
    const directories = (data.directories || []).map(folder => ({ ...folder, path: relative(folder.path) }));
    if (!path) directories.sort((a, b) => {
      const ai = costumeCategoryOrder.indexOf(a.name), bi = costumeCategoryOrder.indexOf(b.name);
      return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
    });
    return { ...data, path, name: path ? data.name : library.label,
      breadcrumbs: (data.breadcrumbs || []).filter(crumb => crumb.path !== library.root).map(crumb => ({ ...crumb, path: relative(crumb.path) })),
      directories,
    };
  };
  const displayFolders = (folders) => {
    if (folders.some(folder => folder.id === "__pose__") && !folders.some(folder => folder.id === "__costumes__")) {
      // The backend counts our hidden physical root; its separate entry owns it.
      folders = [...folders.map(folder => folder.id === "__pose__" ? { ...folder, directory_count: Math.max(0, Number(folder.directory_count || 0) - 1) } : folder),
        { id: "__costumes__", name: "服装库", virtual: true, directory_count: 8 }];
    }
    const used = new Set();
    const categories = galleryCategories.map((category) => {
      const actual = folders.find((folder) => (category.id === "__inbox__" ? folder.name === category.match : folder.id === category.id || (category.match && folder.name === category.match)));
      if (actual) used.add(actual.id);
      return actual ? { ...actual, displayName: category.name } : { ...category, displayName: category.name, placeholder: true, item_count: 0 };
    });
    return [...categories, ...folders.filter((folder) => !used.has(folder.id)).map((folder) => ({ ...folder, displayName: folder.name }))];
  };
  const splitInputs = (inputs) => ({ main: inputs.filter((input) => !advancedIds.has(input.id)), advanced: inputs.filter((input) => advancedIds.has(input.id)) });
  const inspirationState = { catalog: null, loading: null, unavailable: false, kind: "", query: "", offset: 0, page: 0, pageSize: 20 };

  function renderHome(target, navigate) {
    target.innerHTML = `<div class="moon-home"><section class="moon-home-copy"><span class="moon-eyebrow">HUASHI · PERSONAL STUDIO</span><h2>画室</h2><p class="moon-home-lead">在日常的光影里，<br>收藏灵感，创作自己的视觉世界。</p><div class="room-entrances">${rooms.map((room) => `<button class="room-entrance room-entrance-${room.id}" type="button" data-enter-room="${room.id}"><span class="room-entrance-body"><strong>${room.name}</strong><span>${room.description}</span></span><span class="room-enter-arrow" aria-hidden="true">进入 →</span></button>`).join("")}</div><p class="room-home-footer">从一份参考，走向自己的表达。</p></section><figure class="moon-home-art"><img src="/studio-iris.png" alt="紫色鸢尾与粗陶花瓶，月白墙面上的自然窗光" fetchpriority="high"><figcaption><span>月白 · 茄紫</span><span>静物习作 / 视觉示例</span></figcaption></figure></div>`;
    target.querySelectorAll("[data-enter-room]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.enterRoom)));
  }

  function renderInspiration(target, context) {
    const route = context.route || HuashiInspirationNav.parse('#inspiration');
    if (target.inspirationController) { target.inspirationController.updateRoute(route); return; }
    target.inspirationController = HuashiInspirationBrowser.mount(target, context, route);
  }

  function entryPrompt(entry) {
    return [entry.prompt, entry.prompt_en, entry.promptEn, entry.promptHintEn].find((value) => typeof value === "string" && value.trim()) || "";
  }
  function showEntry(entry, { copy, usePrompt }) {
    const dialog = document.getElementById("inspirationDetail");
    const prompt = entryPrompt(entry);
    dialog.innerHTML = `<div class="room-dialog-heading"><h3>${esc(entry.title || entry.name || entry.id)}</h3><button class="tiny-button" type="button" data-close-entry>关闭</button></div>${asset(entry.image || entry.referenceImage || entry.thumbnail) ? `<img class="room-detail-image" src="${esc(asset(entry.image || entry.referenceImage || entry.thumbnail))}" alt="${esc(entry.title || "参考图片")}">` : ""}<pre class="room-entry-prompt">${esc(prompt || "此条目暂无提示词，可打开完整灵感库查看参考信息。")}</pre><div class="room-dialog-actions"><button class="secondary-button" type="button" data-copy-entry ${prompt ? "" : "disabled"}>复制提示词</button><button class="primary-button" type="button" data-use-entry ${prompt ? "" : "disabled"}>用于创作</button><button class="secondary-button" type="button" data-copy-codex>复制给 Codex</button><a class="secondary-button" href="/inspiration/">完整灵感库 ↗</a></div>`;
    dialog.querySelector("[data-close-entry]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-copy-entry]").addEventListener("click", (event) => copy(prompt, event.currentTarget));
    dialog.querySelector("[data-copy-codex]").addEventListener("click", (event) => copy(`参考：${entry.title || entry.name || entry.id}\n类型：${entry.kind || entry.type}\n目录 ID：${entry.id}\n${prompt}`, event.currentTarget));
    dialog.querySelector("[data-use-entry]").addEventListener("click", () => { dialog.close(); usePrompt(prompt); });
    dialog.showModal();
  }

  function renderSettings(target, { apps, tasks, promptModels: models = [] }) {
    target.innerHTML = `<div class="room-heading"><div><h2>设置</h2><p>查看系统，保留重要配置。</p></div></div><div class="room-settings-grid"><section class="room-settings-panel"><h3>工作台状态</h3><dl><div><dt>应用</dt><dd>${apps.length} 个</dd></div><div><dt>处理中</dt><dd>${tasks.filter((task) => ["running", "queued"].includes(task.status)).length} 个</dd></div><div><dt>最近记录</dt><dd>${tasks.length} 条</dd></div></dl><p>最近记录为已加载摘要，不代表全部历史。</p></section><section class="room-settings-panel"><h3>提示词模型</h3><div class="room-model-status">${models.map((model) => `<span>${esc(model.label || model.name || model.id)}<small>${model.available ? "配置可选用" : "未配置"}</small></span>`).join("") || "暂无模型信息"}</div><p>配置状态不代表远端服务实时可用。</p></section><section class="room-settings-panel"><h3>配置备份</h3><p>导出 RunningHub 与提示词配置；RunPod 画布保存在代码中，作品和素材需要另行完整备份。</p><a class="secondary-button" href="/api/admin/backup">下载配置备份</a></section><section class="room-settings-panel"><h3>维护与管理</h3><p>创作画布由 Codex 维护。原有应用配置与备份工具继续保留。</p><a class="secondary-button" href="/admin">打开原管理工具 ↗</a><p class="room-muted">完整存储统计将在后续阶段接入。</p></section></div>`;
  }
  window.HuashiRooms = { rooms, inspirationKinds, galleryCategories, roomForView, parseRoute, displayFolders, directoryLibrary, directoryPath, directoryData, splitInputs, renderHome, renderInspiration, renderSettings, inspirationState, entryPrompt, icon };
})();
