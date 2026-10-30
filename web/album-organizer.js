/* Classification UI only. The adapter validates and commits an entire move plan. */
(() => {
  const $=id=>document.getElementById(id);
  const escapeHtml=value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const escapeAttr=escapeHtml;
function createFolder(context) {
  const {api,folders,onCreated,toast}=context;
  const dialog=$('albumFolderDialog');
  dialog.innerHTML=`<form><div class="room-dialog-heading"><h3>新建分类 / 文件夹</h3><button class="tiny-button" type="button" data-cancel-folder>取消</button></div><label class="field-block"><span>分类名称</span><input id="albumFolderName" required maxlength="80" autocomplete="off" placeholder="例如：礼服参考"></label><p class="room-muted">为作品和素材建立一个容易找到的位置。</p><p data-folder-error role="alert"></p><div class="room-dialog-actions"><button class="primary-button" type="submit">创建分类</button></div></form>`;
  dialog.querySelector('[data-cancel-folder]').onclick=()=>dialog.close();
  dialog.querySelector('form').onsubmit=async event=>{
    event.preventDefault();const button=dialog.querySelector('button[type="submit"]');button.disabled=true;
    const name=$('albumFolderName').value.trim();
    try {
      if(!name)throw new Error('请填写分类名称');
      if(folders.some(folder=>folder.name===name))throw new Error('这个分类已经存在');
      const {folder}=await api('/api/albums',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
      await onCreated(folder);dialog.close();toast('分类已创建','info');
    } catch(error) {dialog.querySelector('[data-folder-error]').textContent=error.message;}
    finally {button.disabled=false;}
  };
  dialog.showModal();
}

function move(context, items, initialTarget='') {
  const {api,onMoved,toast}=context;
  const albums=context.folders;
  if(!items.length)return;
  const dialog=$('albumMoveDialog'), folders=albums.filter(folder=>!folder.virtual && !items.every(item=>item.folder_id===folder.id));
  let plan=null, applying=false;
  dialog.innerHTML=`<div class="room-dialog-heading"><h3>移动 ${items.length} 张图片</h3><button class="tiny-button" type="button" data-cancel-move>取消</button></div><label class="field-block"><span>目标分类</span><select id="albumMoveTarget"><option value="">选择一个分类</option>${folders.map(folder=>`<option value="${escapeAttr(folder.id)}" ${folder.id===initialTarget?'selected':''}>${escapeHtml(folder.id==='works'?'我的作品':folder.name)}</option>`).join('')}</select></label><p class="room-muted">仅调整分类，保留原图、生成记录和素材路径。</p><div id="albumMovePreview" class="room-move-preview" aria-live="polite">先选择目标，再查看移动清单。</div><p data-move-error role="alert"></p><div class="room-dialog-actions"><button class="secondary-button" type="button" id="previewAlbumMove">查看移动清单</button><button class="primary-button" type="button" id="confirmAlbumMove" disabled>确认移动</button></div>`;
  dialog.querySelector('[data-cancel-move]').onclick=()=>{if(!applying)dialog.close();};
  dialog.oncancel=event=>{if(applying)event.preventDefault();};
  $('albumMoveTarget').onchange=()=>{plan=null;$('confirmAlbumMove').disabled=true;$('albumMovePreview').textContent='分类已调整，请重新查看移动清单。';};
  $('previewAlbumMove').onclick=async()=>{
    const target=$('albumMoveTarget').value;
    if(!target){dialog.querySelector('[data-move-error]').textContent='请选择目标分类';return;}
    const previewButton=$('previewAlbumMove');previewButton.disabled=true;plan=null;$('confirmAlbumMove').disabled=true;
    try {
      const requestedTarget=target;
      const moves=items.map(item=>({item_id:item.id,from_folder_id:item.folder_id,to_folder_id:target,expected_file_path:item.path}));
      const result=await api('/api/albums/moves/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({moves})});
      if(!dialog.open || $('albumMoveTarget').value!==requestedTarget)return;
      plan=moves;dialog.querySelector('[data-move-error]').textContent='';
      const folderName=id=>albums.find(folder=>folder.id===id)?.name || id;
      $('albumMovePreview').innerHTML=`<strong>将移动 ${result.count} 张图片</strong><ul>${result.moves.map(move=>`<li><span>${escapeHtml(move.title || move.item_id)}</span><small>${escapeHtml(folderName(move.from_folder_id))} → ${escapeHtml(folderName(move.to_folder_id))}</small></li>`).join('')}</ul><p>可按本次记录移回原分类。</p>`;
      $('confirmAlbumMove').disabled=false;
    } catch(error){dialog.querySelector('[data-move-error]').textContent=error.message;}
    finally{previewButton.disabled=false;}
  };
  $('confirmAlbumMove').onclick=async()=>{
    if(!plan || applying)return;applying=true;
    dialog.querySelectorAll('button,select').forEach(control=>control.disabled=true);
    try {
      const result=await api('/api/albums/moves/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({moves:plan})});
      await onMoved(result);dialog.close();toast(`已移动 ${result.moved} 张图片，移回记录已保存`,'info');
    } catch(error){plan=null;dialog.querySelector('[data-move-error]').textContent=`${error.message}。请刷新分类核对后，再操作。`;}
    finally{applying=false;dialog.querySelectorAll('button,select').forEach(control=>control.disabled=false);$('confirmAlbumMove').disabled=true;}
  };
  dialog.showModal();
}

  window.HuashiAlbums={createFolder,move};
})();
