/* Shared search adapter for the inspiration room and canvas drawer. */
(() => {
  const names = {all:'全部',case:'案例',style:'画风',layout:'排版',prompt:'提示词'};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeImage = value => typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : '';
  function codexText(item, origin = location.origin) {
    const image=safeImage(item.image || item.thumbnail);
    return `请参考画室灵感屋的${names[item.kind] || '灵感'}「${item.title}」，在保留我提供的主题与内容的前提下，模仿其视觉风格、构图和排版。先查看参考图片，再根据下面的信息完成设计。\n\n类型：${names[item.kind] || item.kind}\n编号：${item.id}\n来源：${item.source || '我的提示词库'}${item.source_url ? `\n来源链接：${item.source_url}` : ''}${image ? `\n参考图片：${new URL(image,origin).href}` : ''}\n\n参考提示词或说明：\n${item.prompt || item.description || '请以参考图片为准。'}`;
  }
  function detail(item, context) {
    const dialog = document.getElementById('inspirationDetail');
    const image = safeImage(item.image || item.thumbnail);
    dialog.innerHTML = `<div class="room-dialog-heading"><h3>${esc(item.title)}</h3></div><p class="room-muted">${esc(names[item.kind])} · ${esc(item.source || '')}${item.folder_path && item.folder_path !== item.source ? ` · ${esc(item.folder_path)}` : ''}</p>${image ? `<img class="room-detail-image" src="${esc(image)}" alt="${esc(item.title)}">` : ''}<p>${esc(item.description)}</p><pre class="room-entry-prompt">${esc(item.prompt || '此条目暂无可填入的提示词。')}</pre><div class="room-dialog-actions"><button class="secondary-button" type="button" data-copy-entry ${item.prompt ? '' : 'disabled'}>复制提示词</button><button class="primary-button" type="button" data-use-entry ${item.prompt ? '' : 'disabled'}>${context.picker ? (item.kind === 'prompt' ? '替换当前提示词' : '追加到当前提示词') : '用于创作'}</button>${context.picker ? `<button class="secondary-button" type="button" data-use-entry-other ${item.prompt ? '' : 'disabled'}>${item.kind === 'prompt' ? '追加到当前提示词' : '替换当前提示词'}</button>` : ''}<button class="secondary-button" type="button" data-copy-codex>复制给 Codex</button></div>`;
    dialog.onclick=event=>{if(event.target!==dialog)return;const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left || event.clientX>rect.right || event.clientY<rect.top || event.clientY>rect.bottom)dialog.close();};
    dialog.querySelector('[data-copy-entry]').onclick = event => context.copy(item.prompt,event.currentTarget);
    dialog.querySelector('[data-copy-codex]').onclick = event => context.copy(codexText(item),event.currentTarget);
    dialog.querySelector('[data-use-entry]').onclick = () => { dialog.close(); context.usePrompt(item.prompt, {mode:context.picker && item.kind !== 'prompt' ? 'append' : 'replace', item}); };
    dialog.querySelector('[data-use-entry-other]')?.addEventListener('click', () => {dialog.close();context.usePrompt(item.prompt,{mode:item.kind === 'prompt' ? 'append' : 'replace',item});});
    dialog.showModal();
  }
  function folderFilter(model, picker = false) {
    return (picker || model.kind === 'prompt') && !model.allDirectories ? model.promptFolderId || '' : '';
  }
  function mount(target, context, model = {query:'',kind:'all',offset:0}) {
    target.roomSearch?.destroy();
    model.pageSize=HuashiPages.sizeOf(model.pageSize);
    let disposed = false, serial = 0, timer = null, controller = null, data = null;
    const inputId = context.picker ? 'pickerSearchInput' : 'inspirationSearch';
    target.innerHTML = `<div class="room-search-bar"><label class="search-box"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z"/></svg><input id="${inputId}" type="search" value="${esc(model.query)}" placeholder="搜索案例、画风、排版和提示词，例如：礼服" aria-label="灵感搜索"></label></div><div class="room-search-filters">${Object.entries(names).map(([kind,name])=>`<button type="button" data-room-search-kind="${kind}" class="${model.kind===kind?'active':''}">${name}<small data-search-count="${kind}"></small></button>`).join('')}</div><div class="room-prompt-directory"><div data-search-prompt-folder></div><label class="check-line"><input type="checkbox" data-search-all-folders ${model.allDirectories ? 'checked' : ''}>搜索全部目录</label></div>${context.picker ? '<p class="room-muted room-picker-note">选择替换或追加；案例、画风和排版优先追加，保留你的主体描述。</p>' : ''}<div class="room-search-status" aria-live="polite"></div><div class="room-search-results"></div><div class="room-pagination room-search-pages"></div>`;
    const results = target.querySelector('.room-search-results'), status = target.querySelector('.room-search-status'), pages = target.querySelector('.room-search-pages');
    function filter(kind) { model.kind=kind; model.offset=0; update(); search(); }
    function update() {
      target.querySelectorAll('[data-room-search-kind]').forEach(button=>button.classList.toggle('active',button.dataset.roomSearchKind===model.kind));
      target.querySelector('.room-prompt-directory').hidden = !context.picker && model.kind !== 'prompt';
    }
    const folderKey = context.picker ? 'huashiPromptPickerFolder' : 'huashiPromptSearchFolder';
    const folderSelector = HuashiPromptFolders.mountSelector(target.querySelector('[data-search-prompt-folder]'), {
      api:context.api,value:model.promptFolderId || HuashiPromptFolders.remembered(folderKey),label:'提示词目录',
      onReady:id => {model.promptFolderId = id;},
      onChange:id => {model.promptFolderId = id;model.offset = 0;HuashiPromptFolders.remember(id,folderKey);search();}
    });
    target.querySelector('[data-search-all-folders]').onchange = event => {model.allDirectories = event.target.checked;model.offset = 0;search();};
    update();
    function draw() {
      if (!data) return;
      for (const [kind,count] of Object.entries(data.counts)) { const label=target.querySelector(`[data-search-count="${kind}"]`); if(label) label.textContent=String(count); }
      status.textContent = `${data.total} 条${model.query.trim() ? `与“${model.query.trim()}”相关的灵感` : '灵感'}${data.sources.archive.available ? '' : ' · 归档暂不可用，仍可搜索提示词'}`;
      results.classList.toggle('room-prompt-results', model.kind==='prompt');
      results.innerHTML = data.items.length ? `<div class="room-search-grid">${data.items.map((item,index)=>`<article class="room-search-card" data-room-result-id="${esc(item.id)}" data-room-result-kind="${esc(item.kind)}">${safeImage(item.thumbnail) ? `<button type="button" class="room-search-image" data-room-result-view="${index}" aria-label="查看${esc(item.title)}"><img src="${esc(safeImage(item.thumbnail))}" loading="lazy" alt=""></button>` : `<button type="button" class="room-search-image room-search-text" data-room-result-view="${index}" aria-label="查看${esc(item.title)}"><span>${esc((item.prompt || item.description || item.title).slice(0,130))}</span></button>`}<div class="room-search-card-body" title="${esc(item.prompt || item.description || item.title)}"><small>${esc(names[item.kind])} · ${esc(item.source || '个人收藏')}${item.folder_path && item.folder_path !== item.source ? ` · ${esc(item.folder_path)}` : ''}</small><h3>${esc(item.title)}</h3><p>${esc((item.description || item.prompt || '').slice(0,100))}</p><div class="room-search-actions"><button class="tiny-button" type="button" data-room-result-view="${index}">查看</button><button class="tiny-button" type="button" data-room-result-copy="${index}" ${item.prompt?'':'disabled'}>复制</button><button class="tiny-button room-search-use" type="button" data-room-result-use="${index}" ${item.prompt?'':'disabled'}>${context.picker ? (item.kind === 'prompt' ? '替换' : '追加') : '用于创作'}</button>${context.picker ? `<button class="tiny-button" type="button" data-room-result-other="${index}" ${item.prompt ? '' : 'disabled'}>${item.kind === 'prompt' ? '追加' : '替换'}</button>` : ''}</div></div></article>`).join('')}</div>` : '<div class="room-empty">没有找到相关内容，换个词或分类试试。</div>';
      results.querySelectorAll('[data-room-result-view]').forEach(button=>button.onclick=()=>detail(data.items[Number(button.dataset.roomResultView)],context));
      results.querySelectorAll('[data-room-result-copy]').forEach(button=>button.onclick=()=>context.copy(data.items[Number(button.dataset.roomResultCopy)].prompt,button));
      results.querySelectorAll('[data-room-result-use]').forEach(button=>button.onclick=()=>{const item=data.items[Number(button.dataset.roomResultUse)]; context.usePrompt(item.prompt,{mode:context.picker && item.kind !== 'prompt' ? 'append' : 'replace',item});});
      results.querySelectorAll('[data-room-result-other]').forEach(button=>button.onclick=()=>{const item=data.items[Number(button.dataset.roomResultOther)];context.usePrompt(item.prompt,{mode:item.kind === 'prompt' ? 'append' : 'replace',item});});
      pages.innerHTML = `${HuashiPages.sizeControl(model.pageSize)}<button class="secondary-button" type="button" data-search-prev ${!model.offset?'disabled':''}>上一页</button><span>第 ${Math.floor(model.offset/model.pageSize)+1} / ${Math.max(1,Math.ceil(data.total/model.pageSize))} 页</span><button class="secondary-button" type="button" data-search-next ${data.next_offset===null?'disabled':''}>下一页</button>`;
      pages.querySelector('[data-page-size]').onchange=event=>{model.pageSize=HuashiPages.sizeOf(event.target.value);model.offset=0;search();};
      pages.querySelector('[data-search-prev]').onclick=()=>{model.offset=Math.max(0,model.offset-model.pageSize);search();};
      pages.querySelector('[data-search-next]').onclick=()=>{model.offset=data.next_offset;search();};
    }
    function pending() {
      results.setAttribute('aria-busy','true');
      results.querySelectorAll('button').forEach(button=>button.disabled=true);
      pages.querySelectorAll('button').forEach(button=>button.disabled=true);
    }
    async function search() {
      const request=++serial; controller?.abort(); controller=new AbortController();
      status.textContent='正在查找…'; pending();
      try {
        if (context.picker || model.kind === 'prompt') {
          await folderSelector.ready;
          if (disposed || request !== serial) return;
          if (!folderSelector.value) throw new Error('提示词目录尚未就绪，请重试目录');
        }
        const folderId = folderFilter(model, context.picker);
        const next=await context.api(`/api/inspiration/search?q=${encodeURIComponent(model.query)}&kind=${model.kind}&offset=${model.offset}&limit=${model.pageSize}${folderId ? `&prompt_folder_id=${encodeURIComponent(folderId)}` : ''}`,{signal:controller.signal}); if(disposed||request!==serial)return;data=next;draw(); }
      catch(error) { if(disposed||request!==serial||error.name==='AbortError')return; status.textContent=`读取失败：${error.message}`;results.innerHTML='<button type="button" class="secondary-button" data-search-retry>重试</button>';results.querySelector('[data-search-retry]').onclick=search;pages.innerHTML=''; }
      finally { if(request===serial)results.removeAttribute('aria-busy'); }
    }
    target.querySelector(`#${inputId}`).oninput=event=>{model.query=event.target.value;model.offset=0;pending();status.textContent='正在查找…';clearTimeout(timer);++serial;controller?.abort();timer=setTimeout(search,180);};
    target.querySelectorAll('[data-room-search-kind]').forEach(button=>button.onclick=()=>filter(button.dataset.roomSearchKind));
    const controls={destroy(){disposed=true;clearTimeout(timer);controller?.abort();folderSelector.destroy();},filter,refresh:search,model}; target.roomSearch=controls;search();return controls;
  }
  window.HuashiSearch={mount,detail,codexText,folderFilter};
})();
