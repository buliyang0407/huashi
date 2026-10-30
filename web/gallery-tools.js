/* Gallery presentation and confirmed soft removal; originals remain untouched. */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function viewer(item, context) {
    const canManage = !['pose','face'].includes(item.source_type);
    return `<div class="photo-viewer viewer-immersive ${context.quiet ? 'viewer-quiet' : ''}" data-gallery-stage role="dialog" aria-modal="true" aria-label="图片浏览" tabindex="-1">
      <div class="room-viewer-image"><img class="${item.blurred ? 'is-blurred' : ''}" src="${esc(item.url)}" alt="${esc(item.title || '作品')}" style="transform:scale(${context.zoom})"></div>
      <div class="room-viewer-heading"><span>${esc(item.title || item.app_name || '图片')} <small>${context.index+1} / ${context.total}</small></span><button type="button" data-gallery-close aria-label="关闭图片" title="关闭 · Esc">×</button></div>
      <div class="viewer-edge-arrows"><button type="button" data-room-image-prev aria-label="上一张" title="上一张 · ←">‹</button><button type="button" data-room-image-next aria-label="下一张" title="下一张 · →">›</button></div>
      <div class="room-viewer-toolbar"><button type="button" data-room-zoom="-0.25" aria-label="缩小图片">−</button><button type="button" data-room-zoom-reset title="适合屏幕">${Math.round(context.zoom*100)}%</button><button type="button" data-room-zoom="0.25" aria-label="放大图片">＋</button>${context.creationActions}
        <details class="viewer-extra"><summary>更多</summary><div class="viewer-extra-panel">
          ${item.task_id ? `<button type="button" data-gallery-task="${esc(item.task_id)}">生成记录</button>` : ''}
          ${item.task_id && item.output_path ? `<button type="button" data-toggle-output-blur="${esc(item.task_id)}" data-output-path="${esc(item.output_path)}">${item.blurred?'还原图片':'模糊图片'}</button>` : ''}
          ${canManage ? `<label>移动到分类<select data-move-album-item="${esc(item.id)}">${context.folders.filter(f=>!f.virtual).map(f=>`<option value="${esc(f.id)}" ${f.id===item.folder_id?'selected':''}>${esc(f.id==='works'?'我的作品':f.name)}</option>`).join('')}</select></label><div class="viewer-order"><button type="button" data-reorder-album-item="${esc(item.id)}" data-direction="up">前移</button><button type="button" data-reorder-album-item="${esc(item.id)}" data-direction="down">后移</button></div><button class="danger" type="button" data-delete-album-item="${esc(item.id)}">删除</button>` : ''}
          <small>${esc(context.time)}<br>${esc(item.path || '')}</small>
        </div></details>
      </div><button class="viewer-quiet-toggle" type="button" data-viewer-quiet>${context.quiet?'显示工具':'纯看图'}</button>
    </div>`;
  }
  function remove(items, context) {
    if(!items.length)return;
    const dialog=document.getElementById('albumDeleteDialog');
    const entries=items.map(item=>{
      const source=item.thumb_url || item.url || '';
      const thumbnail=source.startsWith('/') && !source.startsWith('//') ? `<img class="${item.blurred?'is-blurred':''}" src="${esc(source)}" alt="">` : '<span class="gallery-delete-placeholder">图片</span>';
      const date=item.created_at ? new Date(item.created_at).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}) : '';
      return `<li>${thumbnail}<span><strong>${esc(item.title || '图片')}</strong><small>${esc(date)}${item.blurred?' · 已模糊':''}</small></span></li>`;
    }).join('');
    dialog.innerHTML=`<form method="dialog"><div class="room-dialog-heading"><h3>删除 ${items.length} 张图片？</h3></div><p class="room-muted">请核对下面全部图片。从陈列室移除，保留原文件和生成记录。</p><ul class="gallery-delete-list">${entries}</ul><p role="alert"></p><div class="room-dialog-actions"><button type="button" data-cancel-delete autofocus>取消</button><button type="button" class="danger" data-confirm-delete>删除</button></div></form>`;
    const confirm=dialog.querySelector('[data-confirm-delete]'),cancel=dialog.querySelector('[data-cancel-delete]');
    cancel.onclick=()=>dialog.close();
    dialog.oncancel=event=>{if(confirm.disabled)event.preventDefault()};
    confirm.onclick=async()=>{
      confirm.disabled=true;cancel.disabled=true;const done=[];let error=null;
      for(const item of items){
        try{await context.api(`/api/albums/items/${encodeURIComponent(item.id)}/delete`,{method:'POST'});done.push(item.id);confirm.textContent=`已删除 ${done.length} / ${items.length}`;}
        catch(e){error=e;break;}
      }
      try { await context.onDeleted(done); }
      catch(e) { error=error || e; }
      if(error){dialog.querySelector('[role="alert"]').textContent=`已删除 ${done.length} 张，其余尚未完成：${error.message}。请关闭后核对。`;confirm.hidden=true;cancel.disabled=false;cancel.textContent='关闭';}
      else{dialog.close();context.toast(`已从陈列室删除 ${done.length} 张图片`,'info');}
    };
    dialog.showModal();
  }
  window.HuashiGallery={viewer,remove};
})();
