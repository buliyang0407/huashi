/* Integrated inspiration browser. Personal editors and portrait tools stay in the original app. */
(()=>{
 const nav=window.HuashiInspirationNav, esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const names={case:'效果案例',style:'画风',layout:'排版',palette:'配色',prompt:'提示词',template:'模板'},paths={case:'cases',style:'styles',layout:'layouts',palette:'palettes',all:'all'};
 const choices=new Map(),positions=new Map();
 const statuses={original:'原始提示词',partial:'提示词片段',curated:'整理收录', 'style-guide':'风格指南','description-only':'仅有说明'};
 const repositories=[['lemomo-ai/lemo-opuscar','Lemo · 风格与样片'],['yihui-dev/awesome-opus5-5-videos','Awesome · 视频案例'],['joeseesun/opus-video-prompts','中文案例与模板']];
 const duration=n=>Number.isFinite(Number(n))&&Number(n)>0?Math.floor(n/60)+':'+String(Math.floor(n%60)).padStart(2,'0'):'';
 const image=u=>typeof u==='string'&&u.startsWith('/')&&!u.startsWith('//')?u:'';
 const safeLink=u=>typeof u==='string'&&/^https?:\/\//.test(u)?u:'';
 const icon=path=>`<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg>`;
 const searchIcon=icon('M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM16 16l6 6');
 const button=(text,action,primary=false)=>`<button type="button" class="button${primary?' primary':''}" data-action="${action}">${text}</button>`;
 function searchForm(value,placeholder='搜索当前分类的名称、标签或提示词'){return `<form class="search" data-search-form>${searchIcon}<input name="q" type="search" value="${esc(value)}" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}"><button type="submit" hidden>搜索</button></form>`}
 function head(title,subtitle,actions='',eyebrow='灵感屋'){return `<div class="heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${actions}</div></div>`}
 function crumbs(last,parent){return `<div class="breadcrumbs"><a href="#inspiration">灵感屋</a><span>›</span>${parent?`<a href="${parent.href}">${esc(parent.name)}</a><span>›</span>`:''}<span>${esc(last)}</span></div>`}
 function watchLinks(e){const result=new Map();for(const x of e.viewing_links||((e.media||[]).map(m=>({url:m.external_url,roles:[m.role]})))){if(!safeLink(x.url))continue;const old=result.get(x.url)||{url:x.url,roles:[]};for(const role of x.roles||[])if(!old.roles.includes(role))old.roles.push(role);result.set(x.url,old)}return [...result.values()]}
 function watchLabel(link){return link.roles.includes('original')&&link.roles.includes('remake')?'观看原片 / 复刻':link.roles.includes('remake')?'观看复刻':link.roles.includes('demo')?'观看样片':link.roles.includes('original')?'观看原片':link.roles.includes('reference')?'查看资料来源':'打开原帖'}
 function mount(target,context,initialRoute){
  const fullImages=window.HuashiInspirationImages.create({loadEntry:(id,options)=>context.api('/api/inspiration/v2/entry?id='+encodeURIComponent(id),options),imageURL:image});
  target.classList.add('inspiration-browser');
  const dialog=document.getElementById('inspirationDetail');dialog.classList.add('inspiration-dialog');
  let route=null,baseKey='',disposed=false,serial=0,controller=null,favorites={items:[],sources:{}},data=null,detailReturn=null;
  const navigate=hash=>context.navigate(hash.replace(/^#/,''));
  const url=(r,changes={})=>nav.format({...r,...changes});
  const toast=text=>context.toast(text,'info');
  const favoriteIds=()=>new Set(favorites.items.map(e=>e.id));
  function pages(total){const max=Math.max(1,Math.ceil(total/route.pageSize));return `<div class="pagination"><label>每页显示 <select data-page-size aria-label="每页显示数量">${[20,50,100].map(n=>`<option value="${n}"${n===route.pageSize?' selected':''}>${n}</option>`).join('')}</select></label><span>共 ${total} 条 · ${route.page+1} / ${max} 页</span><button data-page="${route.page-1}" ${!route.page?'disabled':''}>上一页</button><button data-page="${route.page+1}" ${route.page+1>=max?'disabled':''}>下一页</button></div>`}
 function home(data){
  const items=data.items,dataset={counts:{images:data.counts.image,active_prompts:data.counts.personal_main ?? context.getPrompts().length}};
  const safe=items.filter(i=>i.kind==='case'&&/旅行|咖啡|地图|徽章|建筑/.test(i.title));const covers=(safe.length>=2?safe:items.filter(i=>i.kind==='case')).slice(0,2);
  return head('灵感屋','找一份参考，留下一种表达。','<a class="button" href="#inspiration/favorites">♡ 我的收藏</a>','EXPLORE · 灵感屋')+`<div class="home-search">${searchForm('','搜索全部灵感，例如：水墨、海报、动画')}<small>从目录慢慢逛，也可以直接找。</small></div><div class="entrances"><a class="entrance" data-entrance="portrait" href="#inspiration/portrait"><div class="entrance-visual prompt-visual"><div class="prompt-paper"><small>PORTRAIT STUDIO</small><strong>挑喜欢的素材，<br>装进素材袋。</strong></div></div><div class="entrance-content"><div class="entrance-title"><h2>人像工坊</h2><span>↗</span></div><p>发型、服装、姿势与场景，<br>图片和参考词一起带去创作。</p><div class="entrance-bottom"><span>你的素材库</span><b>打开人像工坊</b></div></div></a>
  <a class="entrance" data-entrance="prompts" href="#inspiration/prompts"><div class="entrance-visual prompt-visual"><div class="prompt-paper"><small>MY PROMPTS</small><strong>把好用的表达<br>留给下一次创作。</strong><div class="paper-line"></div><div class="paper-line"></div><div class="paper-line"></div></div></div><div class="entrance-content"><div class="entrance-title"><h2>提示词</h2><span>↗</span></div><p>整理自己的提示词，<br>从人物、服饰到完整表达。</p><div class="entrance-bottom"><span>${dataset.counts.active_prompts} 条个人内容</span><b>我的提示词</b></div></div></a>
  <a class="entrance" data-entrance="animation" href="#inspiration/animation/code"><div class="entrance-visual animation-visual"><div class="film-frame"><div class="film-scene"><span class="moon"></span><span class="mountain"></span><span class="mountain second"></span></div><span class="film-caption">A STORY IN MOTION</span></div></div><div class="entrance-content"><div class="entrance-title"><h2>动画</h2><span>↗</span></div><p>看画面怎样动起来，<br>收集样片、风格与制作方法。</p><div class="entrance-bottom"><span>代码类 · ${data.counts.animation||0} 份资料</span><b>进入代码类</b></div></div></a>
  <a class="entrance" data-entrance="image" href="#inspiration/image"><div class="entrance-visual image-visual">${covers.map(i=>`<img src="${esc(image(i.thumbnail))}" alt="${esc(i.title)}" loading="lazy">`).join('')}</div><div class="entrance-content"><div class="entrance-title"><h2>图像</h2><span>↗</span></div><p>挑一个效果，再找一套画风，<br>把它们组合成自己的主题。</p><div class="entrance-bottom"><span>${dataset.counts.images} 份图像参考</span><b>案例 · 画风 · 排版 · 配色</b></div></div></a></div>
  <div class="home-footnote"><span>图像承接原「完整灵感库」，提示词保留已有目录。</span><a class="subtle-link" href="#inspiration/image/styles">先逛逛画风 →</a></div><div class="home-explainer"><span>从参考到自己的表达</span><span>图像与动画保存作品和原始资料；想反复使用的表达，再存进自己的提示词。</span></div>`;
 }
 function entryCard(e){return HuashiInspirationPresentation.card(e,{attributes:`data-entry="${esc(e.id)}"`})}
 function topLine(active,filters=''){return `<div class="reference-topline">${HuashiInspirationPresentation.navigation(active)}${searchForm(route.query,'搜索标题、标签或提示词')}${filters}<a class="button reference-favorites" href="#inspiration/favorites">我的收藏</a></div>`}

 function imagePage(){return topLine('image')+`<div class="reference-filterline"><nav class="category-tabs" aria-label="图像分类">${Object.entries(paths).map(([kind,path])=>`<a href="#inspiration/image/${path}" class="${route.kind===kind?'active':''}">${names[kind]||'全部'}<small>${(kind==='all'?data.counts.image:data.counts[kind])??''}</small></a>`).join('')}</nav><select data-category aria-label="类别"><option value="">全部类别</option>${data.categories.map(c=>`<option${c===route.category?' selected':''}>${esc(c)}</option>`).join('')}</select><span class="reference-count">${data.total} 份参考</span>${button('组合参考','compose')}</div>`+listView(data.items,data.total)}

 function listView(items,total){return (items.length?`<div class="image-grid inspiration-card-grid">${items.map(entryCard).join('')}</div>`:'<div class="empty"><h2>暂时没有相关内容</h2><p>试试其他关键词或分类。</p></div>')+pages(total)}
 function favoritesPage(){const list=favorites.items,start=route.page*route.pageSize;const common=(favorites.common_prompts||[]).length?`<section class="common-prompts"><h2>常用提示词</h2><p>沿用个人提示词中的常用标记。</p><div class="inspiration-card-grid">${favorites.common_prompts.map(entryCard).join('')}</div></section>`:'';return topLine('')+`<div class="reference-filterline"><strong>我的收藏</strong><a class="button" href="/api/inspiration/v2/favorites/export" download>导出全部收藏</a><a class="subtle-link" href="/inspiration/api/favorites/export" download>原图像收藏导出</a></div>`+`<div class="category-tabs"><span>参考收藏 ${list.length}</span><a href="#inspiration/prompts">常用提示词 ${favorites.common_prompts?.length||0} →</a></div>`+(list.length?listView(list.slice(start,start+route.pageSize),list.length):'<div class="empty"><h2>还没有收藏的参考</h2><p>打开喜欢的图像、画风、排版或配色，点一下收藏。</p><a class="button" href="#inspiration/image">去逛逛图像</a></div>')+common}
 function animationPage(){
  const count=data.counts.animation||0,available=data.sources.animation?.available,unavailable=data.sources.animation?.status==='unavailable';
  if(!route.collection)return crumbs('动画')+head('动画','收集样片、风格与制作方法。')+`<a class="entrance animation-category" href="#inspiration/animation/code"><div class="entrance-visual animation-visual"><div class="film-frame"><div class="film-scene"><span class="moon"></span><span class="mountain"></span><span class="mountain second"></span></div><span class="film-caption">A STORY IN MOTION</span></div></div><div class="entrance-content"><div class="entrance-title"><h2>代码类</h2><span>↗</span></div><p>用代码绘制每一帧，收集动态图形、讲解动画和三维场景。</p><div class="entrance-bottom"><span>${available?count+' 份资料':unavailable?'归档暂不可用':'尚未收录'}</span><b>进入代码类 →</b></div></div></a>`;
  return topLine('animation',button('整理短片创作请求','film-request'))+(available?`<div class="reference-filterline"><nav class="category-tabs" aria-label="动画资料类型">${[['','全部'],['case','案例'],['style','风格'],['template','模板']].map(([k,label])=>`<button type="button" data-animation-kind="${k}" class="${route.kind===k?'active':''}">${label}<small>${data.counts[k||'animation']||0}</small></button>`).join('')}</nav><div class="animation-toolbar"><select data-animation-source aria-label="动画来源"><option value="">全部来源</option>${repositories.map(([id,title])=>`<option value="${id}"${route.sourceId===id?' selected':''}>${title}</option>`).join('')}</select><select data-animation-tech aria-label="技术路线"><option value="">全部技术</option>${(data.techniques||[]).map(t=>`<option${route.tech===t?' selected':''}>${esc(t)}</option>`).join('')}</select><select data-category aria-label="用途分类"><option value="">全部用途与分类</option>${data.categories.map(c=>`<option${route.category===c?' selected':''}>${esc(c)}</option>`).join('')}</select></div></div>`+listView(data.items,data.total):`<div class="empty"><h2>${unavailable?'动画资料暂不可用':'动画资料尚未收录'}</h2><p>${unavailable?'原收藏记录已保留，请稍后重试。':'这里将收集代码动画的样片、风格与制作资料。'}</p></div>`);
 }
 function searchPage(){const sources=[['gpt-image2','图像案例'],['handdraw','手绘参考'],['personal','我的提示词'],...repositories];const filters=`<select class="reference-global-filter" data-animation-source aria-label="全部来源"><option value="">全部来源</option>${sources.map(([id,title])=>`<option value="${esc(id)}"${route.sourceId===id?' selected':''}>${esc(title)}</option>`).join('')}</select><select class="reference-global-filter" data-animation-tech aria-label="制作方式"><option value="">全部制作方式</option>${(data.techniques||[]).map(t=>`<option${route.tech===t?' selected':''}>${esc(t)}</option>`).join('')}</select><select class="reference-global-filter" data-category aria-label="用途分类"><option value="">全部用途</option>${data.categories.map(c=>`<option${route.category===c?' selected':''}>${esc(c)}</option>`).join('')}</select>`;return topLine('',filters)+listView(data.items,data.total)}

 function selectionBar(){if(!choices.size)return '';return `<div class="selection-bar"><span>这次的参考</span><div class="selection-items">${[...choices.values()].map(e=>`<button type="button" class="selection-chip" data-remove-choice="${esc(e.kind)}" title="移除${esc(e.title)}">${names[e.kind]} · ${esc(e.title)} ×</button>`).join('')}</div>${button('清空','clear')}${button('换成我的主题','compose',true)}</div>`}
 function draw(){if(disposed||!data)return;const renderers={home:()=>home(data),image:imagePage,animation:animationPage,favorites:favoritesPage,search:searchPage};target.innerHTML=(renderers[route.view]||renderers.home)()+selectionBar();const unavailable=Object.entries(route.view==='favorites'?favorites.sources||{}:data.sources||{}).filter(([k,v])=>!(k==='animation'&&v.status==='not-collected')&&!v.available);if(unavailable.length)target.insertAdjacentHTML('afterbegin',`<div class="section-note error">${unavailable.map(([k,v])=>esc(v.message||k+'暂不可用')).join('；')}</div>`);bind();}
 function releaseMedia(){dialog.querySelectorAll('video').forEach(v=>{v.pause();v.removeAttribute('src');v.querySelectorAll('source').forEach(x=>x.removeAttribute('src'));v.load()})}
 function closeDetail(){releaseMedia();dialog.close();navigate(url(route,{entryId:''}));detailReturn?.focus?.({preventScroll:true})}
 async function toggleFavorite(id){const current=favoriteIds().has(id);try{favorites=await context.api('/api/inspiration/v2/favorites',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,favorite:!current})});draw();if(dialog.open&&route.entryId===id)await detail(id);toast(current?'已取消收藏':'已收藏，留给下次')}catch(e){toast(e.message)}}
 async function detail(id){
  fullImages.hidePreview();const ticket=serial;let e;
  try{e=await context.api('/api/inspiration/v2/entry?id='+encodeURIComponent(id),{signal:controller?.signal})}catch(error){if(!disposed&&error.name!=='AbortError')toast(error.message);return}
  if(disposed||ticket!==serial||route.entryId!==id)return;
  if(!dialog.open)detailReturn=document.activeElement;
  HuashiInspirationDetail.show(dialog,e,{
    images:fullImages,copy:context.copy,toast,close:closeDetail,
    favorite:e.domain==='prompt'?e.favorite:favoriteIds().has(e.id),
    toggleFavorite:e.domain==='prompt'?()=>context.favoritePrompt(e.prompt_id):async()=>{const next=!favoriteIds().has(e.id);favorites=await context.api('/api/inspiration/v2/favorites',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:e.id,favorite:next})});draw();return next},
    chosen:choices.get(e.kind)?.id===e.id,
    toggleChoice:e.domain==='image'?()=>{if(choices.get(e.kind)?.id===e.id)choices.delete(e.kind);else choices.set(e.kind,e);draw();detail(e.id)}:null,
    savePrompt:e.domain!=='prompt'?(text,entry)=>{closeDetail();context.savePrompt(text,{title:entry.title,note:'来源条目：'+entry.id+'\n'+(entry.source_urls||[]).join('\n')})}:null,
    usePrompt:e.capabilities?.use_image_canvas?text=>{closeDetail();context.usePrompt(text)}:null,
    managePrompt:e.domain==='prompt'?()=>{closeDetail();context.managePrompt(e.prompt_id)}:null,
    primaryHTML:e.domain==='animation'?'<button type="button" class="button" data-film-request>整理短片创作请求</button>':'',
    bindExtra:node=>node.querySelector('[data-film-request]')?.addEventListener('click',()=>filmRequest(e)),
  });
 }

 function filmRequest(entry){HuashiAnimationRequest.open({dialog,entry,api:context.api,copy:context.copy,toast,release:releaseMedia,close:()=>{if(route.entryId)navigate(url(route,{entryId:''}))}})}
 function composer(){
  if(![...choices.values()].some(e=>e.kind!=='palette')){toast('先在详情中选一个案例、画风或排版，加入组合参考。');return}
  if(dialog.open){releaseMedia();dialog.close()}const palette=choices.get('palette');
  dialog.innerHTML=`<div class="detail-header"><span>把灵感换成自己的主题</span><button type="button" data-close-compose aria-label="关闭组合">×</button></div><form class="compose-form"><h2>这次，你想做什么？</h2><p>选中的参考会整理成一段创作请求，复制给 Codex 继续创作。</p><label>主题与要求<textarea name="theme" required rows="3" placeholder="例如：做一张杭州周末旅行海报"></textarea></label><label>主题色<select name="palette"><option value="">让 Codex 帮我选</option></select></label><label>画面比例<select name="ratio"><option value="">按内容决定</option>${['3:4','1:1','16:9','9:16'].map(x=>`<option>${x}</option>`).join('')}</select></label><p role="alert" class="compose-error"></p><button class="button primary" type="submit">整理成一段请求</button><div class="compose-output" hidden><h3>可以这样对 Codex 说</h3><pre class="compose-result"></pre><button type="button" class="button" data-copy-composition>复制给 Codex</button></div></form>`;
  dialog.querySelector('[data-close-compose]').onclick=()=>dialog.close();dialog.oncancel=null;dialog.onclick=null;dialog.showModal();const form=dialog.querySelector('form');let palettes=[];
  context.api('/api/inspiration/v2/catalog?domain=image&kind=palette&limit=100').then(r=>{if(disposed||!form.isConnected)return;palettes=r.items;form.elements.palette.insertAdjacentHTML('beforeend',palettes.map(p=>`<option value="${esc(p.id)}"${palette?.id===p.id?' selected':''}>${esc(p.title)}</option>`).join(''))}).catch(e=>toast(e.message));
  form.onsubmit=async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;try{const id=form.elements.palette.value,pal=id?await context.api('/api/inspiration/v2/entry?id='+encodeURIComponent(id)):null;const entries=[...choices.values()].filter(e=>e.kind!=='palette');const map=Object.fromEntries(entries.map(e=>[e.kind,e.id]));const text=HuashiInspirationCompose.buildRequest({entries,choices:map,theme:form.elements.theme.value,palette:pal,ratio:form.elements.ratio.value,origin:location.origin});form.querySelector('.compose-result').textContent=text;form.querySelector('.compose-output').hidden=false;form.querySelector('[data-copy-composition]').onclick=e=>context.copy(text,e.currentTarget);form.querySelector('.compose-error').textContent=''}catch(e){form.querySelector('.compose-error').textContent=e.message}finally{submit.disabled=false}};
 }
 function bind(){
  fullImages.bind(target);
  target.querySelectorAll('a[href^="#"]').forEach(a=>a.onclick=event=>{if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();navigate(a.getAttribute('href'))});
  target.querySelectorAll('[data-entry]').forEach(b=>b.onclick=()=>navigate(url(route,{entryId:b.dataset.entry})));
  target.querySelectorAll('[data-favorite]').forEach(b=>b.onclick=()=>toggleFavorite(b.dataset.favorite));
  target.querySelectorAll('[data-manage-prompt]').forEach(b=>b.onclick=()=>context.managePrompt(b.dataset.managePrompt));
  target.querySelectorAll('[data-remove-choice]').forEach(b=>b.onclick=()=>{choices.delete(b.dataset.removeChoice);draw()});
  target.querySelectorAll('[data-animation-kind]').forEach(b=>b.onclick=()=>navigate(url(route,{kind:b.dataset.animationKind,page:0,entryId:''})));
  for(const [selector,key] of [['[data-animation-source]','sourceId'],['[data-animation-tech]','tech']])target.querySelector(selector)?.addEventListener('change',e=>navigate(url(route,{[key]:e.target.value,page:0,entryId:''})));
  target.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{if(b.dataset.action==='film-request')filmRequest();else if(b.dataset.action==='compose')composer();else if(b.dataset.action==='clear'){choices.clear();draw()}});
  target.querySelectorAll('[data-search-form]').forEach(f=>f.onsubmit=e=>{e.preventDefault();const q=new FormData(f).get('q').trim();navigate(route.view==='home'?'#inspiration/search?q='+encodeURIComponent(q):url(route,{query:q,page:0,entryId:''}))});
  target.querySelector('[data-category]')?.addEventListener('change',e=>navigate(url(route,{category:e.target.value,page:0,entryId:''})));
  target.querySelector('[data-page-size]')?.addEventListener('change',e=>navigate(url(route,{pageSize:Number(e.target.value),page:0,entryId:''})));
  target.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>navigate(url(route,{page:Number(b.dataset.page),entryId:''})));
 }
 async function updateRoute(next){
  fullImages.close();
  const old=route,key=url(next,{entryId:''});if(old)positions.set(baseKey,scrollY);route=next;
  if(key===baseKey&&data){if(route.entryId)detail(route.entryId);else if(dialog.open){releaseMedia();dialog.close()}return}
  baseKey=key;controller?.abort();controller=new AbortController();const ticket=++serial;
  if(dialog.open){releaseMedia();dialog.close()}target.innerHTML='<p class="loading">正在打开灵感资料…</p>';
  try{
   const filters=new URLSearchParams({q:route.query||'',domain:['image','animation'].includes(route.domain)?route.domain:'',collection:route.domain==='animation'?'code':'',kind:['image','animation'].includes(route.domain)?route.kind:'',source_id:route.sourceId||'',tech:route.tech||'',offset:String(route.page*route.pageSize),limit:String(route.view==='home'?8:route.pageSize),category:route.category||''});
   const [r,f]=await Promise.all([context.api('/api/inspiration/v2/catalog?'+filters,{signal:controller.signal}),context.api('/api/inspiration/v2/favorites',{signal:controller.signal})]);
   if(disposed||ticket!==serial)return;data=r;favorites=f;
   const total=route.view==='favorites'?f.total:r.total,maxPage=Math.max(0,Math.ceil(total/route.pageSize)-1);
   if(route.view!=='home'&&!(route.view==='animation'&&!route.collection)&&route.page>maxPage){navigate(url(route,{page:maxPage}));return}
   draw();requestAnimationFrame(()=>scrollTo(0,positions.get(baseKey)||0));if(route.entryId)detail(route.entryId);if(route.notice)toast(route.notice);
  }catch(e){if(!disposed&&e.name!=='AbortError')target.innerHTML=`<div class="empty"><h2>暂时无法读取资料</h2><p>${esc(e.message)}</p><a href="#inspiration">返回灵感屋</a></div>`}
 }
 updateRoute(initialRoute);
 return {updateRoute,destroy(){fullImages.destroy();disposed=true;serial++;controller?.abort();positions.set(baseKey,scrollY);releaseMedia();if(dialog.open)dialog.close();dialog.oncancel=null;dialog.onclick=null;dialog.classList.remove('inspiration-dialog','reference-detail');target.classList.remove('inspiration-browser')}};
 }
 window.HuashiInspirationBrowser={mount};
})();
