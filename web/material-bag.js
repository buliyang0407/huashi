/* Shared material bag and existing multipart image-input bridge. */
(() => {
  let catalogPromise, picker=null, frame=null, targetKey=null, focusReturn=null;
function loadMaterialCatalog(){const plain=()=>fetch('/portrait-materials.json?v=20261030-speed-1').then(r=>{if(!r.ok)throw Error('素材目录读取失败');return r.json()});if(typeof DecompressionStream!=='function')return plain();return fetch('/portrait-materials.json.gz?v=20261030-speed-1').then(r=>{if(!r.ok||!r.body)throw Error('compressed catalog unavailable');return new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json()}).catch(plain)}
  const load=()=>catalogPromise ||= loadMaterialCatalog().catch(e=>{catalogPromise=null;throw e});
  let thumbnailMapPromise;
  const urlKey=url=>{try{const u=new URL(url,location.origin);return u.origin===location.origin?decodeURIComponent(u.pathname):''}catch(e){return ''}};
  async function withDirectoryThumbnails(items){
    if(!items?.length)return items||[];
    try{
      const map=await (thumbnailMapPromise ||= load().then(rows=>new Map(rows.filter(m=>m.thumbnail).map(m=>[urlKey(m.image),m.thumbnail]))).catch(e=>{thumbnailMapPromise=null;throw e}));
      return items.map(item=>{const thumb=map.get(urlKey(item.url));return thumb?{...item,thumb_url:thumb}:item});
    }catch(e){return items}
  }
  function count(){let n=0;try{n=JSON.parse(localStorage.getItem('huashi-material-bag-v1')||'[]').length}catch(e){}document.querySelectorAll('[data-material-bag-count]').forEach(x=>x.textContent=n)}
  function mount(){const screen=document.querySelector('[data-screen="portrait"]');if(!screen)return;if(!screen.querySelector('.portrait-studio-frame')){screen.insertAdjacentHTML('afterbegin','<iframe class="portrait-studio-frame" title="人像工坊" allow="clipboard-write" src="/portrait-studio.html?v=20261030-speed-1"></iframe>');screen.classList.add('portrait-v2')}}
  function close(){picker?.remove();picker=null;frame=null;targetKey=null;document.body.style.overflow='';focusReturn?.focus();count()}
  function open(key=null){close();focusReturn=document.activeElement;targetKey=key;picker=document.createElement('div');picker.className='material-bag-overlay';picker.innerHTML='<iframe title="素材袋" allow="clipboard-write" src="/portrait-studio.html?mode=bag'+(key?'&pick='+encodeURIComponent(key):'')+'&v=20261030-speed-1"></iframe>';document.body.append(picker);frame=picker.firstElementChild;document.body.style.overflow='hidden';frame.focus()}
  async function select(id,key){
    if(!targetKey||key!==targetKey)return;
    showToast('正在读取原图…');const currentKey=targetKey;const m=(await load()).find(x=>x.id===id);if(!m)throw Error('素材已不可用，请重新选择');
    const response=await fetch(m.image);if(!response.ok)throw Error('素材图片读取失败');const blob=await response.blob();
    if(!blob.type.startsWith('image/'))throw Error('图片格式不可用');
    if(currentKey!==targetKey)return;
    const inputs=[...document.querySelectorAll('[data-file-input]')].filter(x=>x.dataset.fileInput===currentKey);if(!inputs.length)throw Error('当前上传位置已改变，请重新选择');
    const transfer=new DataTransfer();transfer.items.add(new File([blob],m.filename,{type:blob.type}));inputs[0].files=transfer.files;
    const artwork=document.querySelector(`[data-artwork-input="${CSS.escape(currentKey)}"]`);if(artwork)artwork.value='';
    inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
    // Reuse the existing preview and validation functions in the host application.
    showInputPreview(currentKey,m.thumbnail||m.image);updateGenerateState();close();showToast('已选入：'+m.title);
  }
  window.addEventListener('message',e=>{if(e.origin!==location.origin)return;const studio=document.querySelector('.portrait-studio-frame');if(e.source!==frame?.contentWindow&&e.source!==studio?.contentWindow)return;const d=e.data||{};if(d.type==='portrait-close')close();if(d.type==='portrait-navigate'&&['create','inspiration'].includes(d.view)){close();document.querySelector(`[data-nav-view="${d.view}"]`)?.click()}if(d.type==='portrait-select'&&e.source===frame?.contentWindow)select(d.id,d.key).catch(error=>showToast(error.message,'error'));count()});
  document.addEventListener('click',e=>{const b=e.target.closest('[data-material-bag]');if(b)open(b.dataset.materialBag||null)});
  window.addEventListener('storage',count);document.addEventListener('keydown',e=>{if(e.key==='Escape'&&picker)close()});
  window.HuashiMaterialBag={mount,open,count,withDirectoryThumbnails};count();
})();
