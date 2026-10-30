/* Shared two-level prompt directories. Prompts belong only to leaf directories. */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let data = null, pending = null, serial = 0;
  const isLeaf = folder => Number(folder.level) === 2 && Boolean(folder.parent_id);
  const leaves = value => (value?.folders || []).filter(isLeaf);
  function resolveLeaf(value, remembered) {
    return leaves(value).find(folder => folder.id === remembered)?.id || leaves(value).find(folder => folder.id === value?.default_folder_id)?.id || '';
  }
  function filterPrompts(prompts, folderId, allDirectories = false) {
    return allDirectories ? prompts : prompts.filter(prompt => Boolean(folderId) && prompt.folder_id === folderId);
  }
  function remembered(key = 'huashiPromptFolder') { try { return localStorage.getItem(key) || ''; } catch (_) { return ''; } }
  function remember(id, key = 'huashiPromptFolder') { try { localStorage.setItem(key, id); } catch (_) {} }
  async function refresh(api) {
    const request = ++serial;
    const promise = api('/api/prompt-folders').then(next => {
      if (!Array.isArray(next.folders)) throw new Error('目录数据不完整，请重试');
      if (request === serial) data = next;
      return next;
    }).catch(error => { if (request === serial) data = null; throw error; }).finally(() => { if (request === serial) pending = null; });
    pending = promise;
    return promise;
  }
  function ensure(api) { return data ? Promise.resolve(data) : pending || refresh(api); }
  function options(value, selected, empty = false) {
    const folders = value?.folders || [];
    return `${empty ? '<option value="">请选择二级目录</option>' : ''}${folders.filter(folder => !folder.parent_id).map(parent => `<optgroup label="${esc(parent.name)}">${leaves(value).filter(folder => folder.parent_id === parent.id).map(folder => `<option value="${esc(folder.id)}" ${folder.id === selected ? 'selected' : ''}>${esc(folder.path || `${parent.name} / ${folder.name}`)}</option>`).join('')}</optgroup>`).join('')}`;
  }
  function mountSelector(target, context) {
    const token = {}; target.promptFolderToken = token;
    let selected = '', control;
    const alive = () => target.promptFolderToken === token;
    async function draw() {
      target.innerHTML = '<p class="room-muted" role="status">正在读取目录…</p>';
      try {
        const value = await ensure(context.api); if (!alive()) return '';
        selected = resolveLeaf(value, context.value);
        target.innerHTML = `<label class="field-block prompt-directory-select"><span>${esc(context.label || '保存目录')}</span><select name="folder_id" required ${leaves(value).length ? '' : 'disabled'}>${options(value, selected, !selected)}</select></label>${selected ? '' : '<p class="creation-save-error" role="alert">没有可用的默认二级目录，请先管理目录。</p>'}`;
        const select = target.querySelector('select');
        select.onchange = () => {selected = select.value; context.value = selected; context.onChange?.(selected);};
        context.onReady?.(selected); return selected;
      } catch (error) {
        if (!alive()) return '';
        selected = ''; target.innerHTML = `<p class="creation-save-error" role="alert">目录读取失败：${esc(error.message)}</p><button type="button" class="tiny-button">重试目录</button>`;
        target.querySelector('button').onclick = () => { control.ready = draw(); };
        context.onReady?.(''); return '';
      }
    }
    control = {get value() {return selected;}, ready:null, destroy() {if(alive())target.promptFolderToken = null;}};
    control.ready = draw(); return control;
  }
  function dialog(title) {
    const element = document.createElement('dialog'); element.className = 'room-organize-dialog prompt-folder-dialog';
    element.setAttribute('aria-label', title); document.body.append(element);
    element.addEventListener('close', () => element.remove(), {once:true}); return element;
  }
  async function manage(context) {
    let value;
    try { value = await ensure(context.api); } catch(error) {context.toast?.(error.message,'error');return;}
    const element = dialog('管理提示词目录');
    element.innerHTML = `<form class="creation-save-form"><div class="room-dialog-heading"><h3>管理目录</h3><button type="button" class="tiny-button" data-cancel>关闭</button></div><label class="field-block"><span>操作</span><select name="action"><option value="edit">修改现有目录</option><option value="root">新建一级目录</option><option value="leaf">新建二级目录</option></select></label><label class="field-block" data-existing><span>选择目录</span><select name="existing">${value.folders.map(folder => `<option value="${esc(folder.id)}">${esc(folder.path || folder.name)}</option>`).join('')}</select></label><label class="field-block"><span>目录名称</span><input name="name" required maxlength="100"></label><label class="field-block" data-parent><span>所属一级目录</span><select name="parent">${value.folders.filter(folder => !folder.parent_id).map(folder => `<option value="${esc(folder.id)}">${esc(folder.name)}</option>`).join('')}</select></label><label class="field-block"><span>排列顺序（数值小的在前）</span><input name="order" type="number" step="1" value="0"></label><p class="room-muted">一级目录用于组织二级目录。只有空目录可以删除；默认二级目录保留，可改名。</p><p role="alert" class="creation-save-error"></p><div class="room-dialog-actions"><button type="submit" class="primary-button">保存目录</button><button type="button" class="secondary-button danger" data-delete>删除空目录</button></div></form>`;
    const form = element.querySelector('form'), fields = form.elements, error = element.querySelector('[role="alert"]');
    const deleteConfirmation = document.createElement('div');
    deleteConfirmation.hidden = true;
    deleteConfirmation.innerHTML = '<p class="room-muted" data-delete-message></p><button type="button" class="secondary-button danger" data-confirm-delete>确认删除空目录</button> <button type="button" class="tiny-button" data-cancel-delete>取消删除</button>';
    form.append(deleteConfirmation);
    deleteConfirmation.querySelector('[data-cancel-delete]').onclick = () => {deleteConfirmation.hidden = true;};
    fields.existing.value = context.value || value.default_folder_id || value.folders[0]?.id || '';
    function update(reset = true) {
      if(reset)deleteConfirmation.hidden = true;
      const existing = value.folders.find(folder => folder.id === fields.existing.value), editing = fields.action.value === 'edit';
      element.querySelector('[data-existing]').hidden = !editing;
      element.querySelector('[data-parent]').hidden = fields.action.value === 'root' || (editing && !existing?.parent_id);
      element.querySelector('[data-delete]').hidden = !editing;
      element.querySelector('[data-delete]').disabled = !existing || existing.id === value.default_folder_id || Number(existing.count) > 0 || value.folders.some(folder => folder.parent_id === existing.id);
      if (reset) {
        fields.name.value = editing ? existing?.name || '' : '';
        fields.order.value = editing ? existing?.sort_order || 0 : 0;
        if(existing?.parent_id)fields.parent.value = existing.parent_id;
      }
    }
    fields.action.onchange = update; fields.existing.onchange = update; update();
    let busy = false;
    element.querySelector('[data-cancel]').onclick = () => {if(!busy)element.close();};
    element.oncancel = event => {if(busy)event.preventDefault();};
    async function mutate(removing = false) {
      if(busy)return;
      const editing = fields.action.value === 'edit', existing = value.folders.find(folder => folder.id === fields.existing.value);
      if (!removing && !fields.name.value.trim()) {error.textContent = '请填写目录名称';return;}
      busy = true; error.textContent = ''; Array.from(fields).forEach(field => field.disabled = true);
      const parent = fields.action.value === 'leaf' || (editing && existing?.parent_id) ? fields.parent.value : null;
      try {
        await context.api(`/api/prompt-folders${editing ? `/${encodeURIComponent(existing.id)}` : ''}`,{method:removing ? 'DELETE' : editing ? 'PUT' : 'POST',headers:{'Content-Type':'application/json'},...(!removing ? {body:JSON.stringify({name:fields.name.value.trim(),parent_id:parent,sort_order:Number(fields.order.value)})} : {})});
        await refresh(context.api); element.close(); await context.onMutate?.(); context.toast?.(removing ? '空目录已删除' : '目录已保存','info');
      } catch(e) {error.textContent = e.message;} finally {busy = false;Array.from(fields).forEach(field => field.disabled = false);update(false);}
    }
    form.onsubmit = event => {event.preventDefault();mutate();};
    element.querySelector('[data-delete]').onclick = () => {
      const existing = value.folders.find(folder => folder.id === fields.existing.value);
      deleteConfirmation.querySelector('[data-delete-message]').textContent = `删除空目录「${existing?.path || existing?.name}」？之后可在下方恢复。`;
      deleteConfirmation.hidden = false;
    };
    deleteConfirmation.querySelector('[data-confirm-delete]').onclick = () => mutate(true);
    element.showModal();
    const recovery = document.createElement('div'); recovery.className = 'prompt-folder-recovery'; element.append(recovery);
    recovery.innerHTML = '<details><summary>恢复已删除的空目录</summary><div data-recovery-list><p class="room-muted">正在读取…</p></div></details>';
    const recoveryList = recovery.querySelector('[data-recovery-list]');
    async function readRecovery() {
      try {
        const archived = await context.api('/api/prompt-folders?include_deleted=1'); if(!element.isConnected)return;
        const removed = archived.folders.filter(folder => folder.deleted_at);
        recoveryList.innerHTML = removed.length ? removed.map(folder => `<button type="button" class="tiny-button" data-restore="${esc(folder.id)}">恢复 ${esc(folder.path || folder.name)}</button>`).join('') : '<p class="room-muted">没有已删除的空目录。</p>';
        recoveryList.querySelectorAll('[data-restore]').forEach(button => button.onclick = async () => {
          if(busy)return;busy = true;button.disabled = true;error.textContent = '';
          try {await context.api(`/api/prompt-folders/${encodeURIComponent(button.dataset.restore)}/restore`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});await refresh(context.api);element.close();await context.onMutate?.();context.toast?.('目录已恢复','info');}
          catch(e) {error.textContent = e.message;}
          finally {busy = false;button.disabled = false;}
        });
      } catch(e) {if(element.isConnected){recoveryList.innerHTML = `<p class="creation-save-error">读取失败：${esc(e.message)}</p><button type="button" class="tiny-button">重试</button>`;recoveryList.querySelector('button').onclick = readRecovery;}}
    }
    readRecovery();
  }
  function mountTree(target, context) {
    const value = data;
    if(!value) {target.innerHTML='<p class="room-muted">目录暂不可用</p>';return;}
    const current = leaves(value).find(folder => folder.id === context.value);
    target.innerHTML = `<div class="prompt-directory-heading"><strong>提示词目录</strong><button class="tiny-button" type="button" data-manage>管理</button></div><div class="prompt-directory-tree">${value.folders.filter(folder => !folder.parent_id).map(parent => `<details ${parent.id === current?.parent_id ? 'open' : ''}><summary>${esc(parent.name)}<small>${Number(parent.count || 0)}</small></summary>${leaves(value).filter(folder => folder.parent_id === parent.id).map(folder => `<button type="button" class="${folder.id === context.value ? 'active' : ''}" data-leaf="${esc(folder.id)}" ${folder.id === context.value ? 'aria-current="true"' : ''}><span>${esc(folder.name)}</span><small>${Number(folder.count || 0)}</small></button>`).join('')}</details>`).join('')}</div>`;
    target.querySelector('[data-manage]').onclick = () => manage(context);
    target.querySelectorAll('[data-leaf]').forEach(button => button.onclick = () => context.onChange(button.dataset.leaf));
  }
  function move(ids, context) {
    if(!ids.length)return;
    const element = dialog('移动提示词');
    element.innerHTML = `<form class="creation-save-form"><div class="room-dialog-heading"><h3>移动 ${ids.length} 条提示词</h3><button type="button" class="tiny-button" data-cancel>取消</button></div><p class="room-muted">只修改目录归属，原内容、配图及 AI 衍生一起保留。</p><div data-folder></div><p role="alert" class="creation-save-error"></p><div class="room-dialog-actions"><button type="submit" class="primary-button" disabled>移动到此目录</button></div></form>`;
    const form = element.querySelector('form'), submit = form.querySelector('[type="submit"]'); let busy = false;
    const selector = mountSelector(element.querySelector('[data-folder]'),{api:context.api,value:context.value,label:'目标完整路径',onReady:id => {submit.disabled = !id;}});
    element.querySelector('[data-cancel]').onclick = () => {if(!busy)element.close();}; element.oncancel = event => {if(busy)event.preventDefault();};
    form.onsubmit = async event => {
      event.preventDefault();if(busy || !selector.value)return;busy = true;submit.disabled = true;
      try {await context.api('/api/prompts/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt_ids:ids,folder_id:selector.value})});await refresh(context.api);element.close();await context.onMoved?.();context.toast?.(`已移动 ${ids.length} 条提示词`,'info');}
      catch(error) {element.querySelector('[role="alert"]').textContent = error.message;}
      finally {busy = false;submit.disabled = !selector.value;}
    };element.showModal();
  }
  window.HuashiPromptFolders = {refresh,snapshot:()=>data,resolveLeaf,filterPrompts,mountSelector,mountTree,move,manage,remembered,remember};
})();
