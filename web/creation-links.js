/* Cross-room actions reuse existing image paths and the prompt library API. */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function mergePrompt(current, incoming, mode, separator = "\n\n") {
    return mode === 'append' && current ? `${current}${separator}${incoming}` : incoming;
  }
  function promptPayload(title, content, folderId, tags, note = "") {
    const list = String(tags || '').split(/[,，\n]/).map(t => t.trim()).filter(Boolean);
    return {title:title.trim(), content:content.trim(), folder_id:String(folderId || ''), note:String(note || ''), tags:[...new Set(list)], app_ids:[]};
  }
  function imageActions(path, name = '', preview = '') {
    if (!path) return '';
    return `<div class="creation-image-actions"><button class="tiny-button" type="button" data-send-image="choose" data-image-path="${esc(path)}" data-image-name="${esc(name || path.split('/').pop())}" data-image-preview="${esc(preview)}">送去创作间</button></div>`;
  }
  function chooseCanvas(apps, choose) {
    const dialog = document.getElementById('creationTargetDialog');
    dialog.innerHTML = `<div class="room-dialog-heading"><h3>送去创作间</h3><button class="tiny-button" type="button" data-close-target>取消</button></div><p class="room-muted">选择画布，图片会自动带入；双图编辑会先填入第一张。</p><div class="creation-canvas-list">${apps.map(app => `<button class="secondary-button" type="button" data-reference-app="${esc(app.id)}"><strong>${esc(app.name)}</strong><small>${app.provider === 'runpod' ? 'RunPod' : 'RunningHub'}</small></button>`).join('')}</div>`;
    dialog.querySelector('[data-close-target]').onclick = () => dialog.close();
    dialog.querySelectorAll('[data-reference-app]').forEach(button => button.onclick = () => {dialog.close();choose(button.dataset.referenceApp);});
    dialog.showModal();
  }
  function savePrompt(content, prompts, context) {
    if (!content.trim()) {context.toast('先写一些提示词再保存','info');return;}
    const dialog = document.getElementById('canvasPromptDialog');
    dialog.innerHTML = `<form class="creation-save-form"><div class="room-dialog-heading"><h3>保存到提示词库</h3><button class="tiny-button" type="button" data-cancel-save>取消</button></div><p class="room-muted">保存为一条新提示词，方便下次继续使用。</p><label class="field-block"><span>名称</span><input name="title" required maxlength="200" placeholder="给这条提示词起个名字"></label><div data-save-prompt-folder></div><label class="field-block"><span>标签（可选）</span><input name="tags" placeholder="多个标签用逗号分隔"></label><label class="field-block"><span>提示词内容</span><textarea name="content" rows="7" required>${esc(content)}</textarea></label><p class="creation-save-error" role="alert"></p><div class="room-dialog-actions"><button class="primary-button" type="submit">保存新提示词</button></div></form>`;
    const form = dialog.querySelector('form');
    form.elements.title.value = context.title || '';
    form.elements.tags.value = context.tags || '';
    const submitButton = form.querySelector('[type="submit"]'); submitButton.disabled = true;
    const selector = HuashiPromptFolders.mountSelector(form.querySelector('[data-save-prompt-folder]'), {api:context.api,value:context.folderId,onReady:id => {submitButton.disabled = !id;}});
    dialog.querySelector('[data-cancel-save]').onclick = () => dialog.close();
    form.onsubmit = async event => {
      event.preventDefault();
      const submit = form.querySelector('[type="submit"]');
      const data = new FormData(form);
      const payload = promptPayload(data.get('title'),data.get('content'),selector.value,data.get('tags'),context.note);
      const error = dialog.querySelector('[role="alert"]');
      if (!payload.folder_id) {error.textContent='请先选择可用的保存目录';return;}
      if (!payload.title || !payload.content) {error.textContent='请填写名称和提示词内容';return;}
      submit.disabled=true; form.querySelector('[data-cancel-save]').disabled=true; error.textContent='';
      try {
        const saved = await context.api('/api/prompts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        // Update the library without rerendering or resetting the current canvas draft.
        context.saved(saved.prompt); dialog.close(); context.toast('已保存新提示词，可在灵感屋搜索','info');
      } catch (e) {error.textContent=e.message;} finally {submit.disabled=!selector.value;form.querySelector('[data-cancel-save]').disabled=false;}
    };
    dialog.oncancel = event => {if(form.querySelector('[data-cancel-save]').disabled) event.preventDefault();};
    dialog.showModal(); form.elements.title.focus();
  }
  window.HuashiCreation = {mergePrompt, promptPayload, imageActions, chooseCanvas, savePrompt};
})();
