/* Real RunPod queue view. Task details, history and result actions remain in app.js. */
(function(root){
  'use strict';
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function model(data={}){
    const active=data.active||[],pending=data.pending||[],blocked=Boolean(data.blocked?.length);
    return {count:active.length+pending.length,blocked,action:data.paused?'继续队列':'暂停队列',state:blocked?'提交结果待核对，已停止派单':data.paused?(active.length?'当前完成后暂停':'已暂停，等待继续'):active.length?'依次生成中':pending.length?'等待开始':'队列空闲'};
  }
  function parameters(task){
    const v=task.input_payload?.values||{},items=[];
    if(v.width&&v.height)items.push(`${v.width} × ${v.height}`);else if(v.resolution!==undefined)items.push(`编码 ${v.resolution}`);
    if(v.steps!==undefined)items.push(`${v.steps}步`);if(v.cfg!==undefined)items.push(`CFG ${v.cfg}`);if(v.lora_strength!==undefined)items.push(`权重 ${v.lora_strength}`);
    return items.join(' · ');
  }
  const image=(task,done=false)=>{
    const out=done?(task.outputs||[]).find(o=>!o.deleted&&['image','png','jpg','jpeg','webp'].includes(o.type)):null;
    const src=done?(out?.thumb_url||out?.url):(task.input_thumb_url||task.input_url);
    return src?`<img loading="lazy" class="${out?.blurred?'queue-blurred':''}" src="${esc(src)}" alt="${done?'生成作品':'任务参考图片'}">`:'<span class="queue-image-empty">文生图</span>';
  };
  function render(target,data,ctx){
    const m=model(data),active=data.active||[],pending=data.pending||[],completed=data.completed||[];
    const detail=t=>`<button class="queue-text" type="button" data-queue-detail="${esc(t.id)}">查看设定 ↗</button>`;
    target.innerHTML=`<div class="queue-page-tabs"><span>正在进行 <b>${m.count}</b></span><button class="queue-text" data-queue-history type="button">全部记录 ↗</button></div>
      ${(data.blocked||[]).map(t=>`<div class="queue-blocked" role="status"><strong>这条任务需要维护核对</strong><p>RunPod 提交结果未知。后续任务和输入已保存，未再次提交；请联系维护核对远端后继续。</p>${detail(t)}</div>`).join('')}
      <div class="queue-page-grid"><section class="queue-working" aria-label="生成队列"><div class="queue-control"><span class="${data.paused||m.blocked?'queue-paused':'queue-running'}">${esc(m.state)}</span><button class="queue-text" type="button" data-queue-pause ${(!m.count&&!data.paused)||m.blocked?'disabled':''}>${m.action}</button></div>
      ${active.length?active.map(t=>`<article class="queue-active-card"><div class="queue-overline"><span>${esc(ctx.stage(t))}</span><span>#${esc(t.queue_sequence??t.id.slice(0,8))}</span></div><div class="queue-active-content">${image(t)}<div><h3>${esc(t.app_name)}</h3><p>${esc(t.prompt)}</p><div class="queue-task-meta">${esc(parameters(t))}</div></div></div><div class="queue-indeterminate" role="progressbar" aria-label="任务运行中，尚无完成百分比"></div><div class="queue-active-bottom"><span>${esc(ctx.elapsed(t.created_at))}${t.stage==='recovery_wait'?' · 等待恢复查询':''}</span>${detail(t)}</div></article>`).join(''):`<div class="queue-empty">${data.paused?'队列已暂停，继续后开始下一单。':'没有正在生成的任务，准备下一张吧。'}</div>`}
      <div class="queue-waiting-title"><span>接下来 · ${pending.length} 单</span><span>按提交顺序</span></div><div class="queue-waiting-list">${pending.map((t,i)=>`<article class="queue-waiting-row"><span class="queue-order">${String(i+1).padStart(2,'0')}</span>${image(t)}<div class="queue-waiting-copy"><h3>${esc(t.app_name)}</h3><p>${esc(t.prompt)}</p><div class="queue-task-meta">${esc(parameters(t))}</div><div class="queue-item-actions">${detail(t)}</div>${ctx.confirming===t.id?`<div class="queue-cancel-confirm">取消这条待生成任务？记录和图片会保留。<div><button type="button" class="queue-text" data-queue-confirm="${esc(t.id)}">确认取消</button><button class="queue-text" type="button" data-queue-keep>保留任务</button></div></div>`:''}</div><button class="queue-cancel" type="button" data-queue-cancel="${esc(t.id)}">取消</button></article>`).join('')||'<p class="queue-empty">下一份想法，准备好就加入。</p>'}</div></section>
      <aside class="queue-harvest"><div class="queue-finished-heading"><div><span>回来收图</span><h3>最近完成</h3></div><button class="queue-text" type="button" data-queue-success>查看记录 ↗</button></div><div class="queue-finished-grid">${completed.slice(0,6).map(t=>`<button type="button" class="queue-finished-item" data-queue-detail="${esc(t.id)}" aria-label="查看${esc(t.app_name)}生成作品">${image(t,true)}<span>✓ 已完成</span></button>`).join('')||'<p class="queue-empty">完成的作品会出现在这里。</p>'}</div><div class="queue-background-note"><strong>任务交给后台</strong><p>已加入的任务会在 NAS 依次执行。<br>可以关掉网页，稍后回来查看。</p></div><button class="secondary-button queue-all-results" type="button" data-queue-success>查看已完成记录 ↗</button></aside></div>`;
    target.querySelectorAll('[data-queue-detail]').forEach(el=>el.addEventListener('click',()=>ctx.detail(el.dataset.queueDetail)));
    target.querySelectorAll('[data-queue-cancel]').forEach(el=>el.addEventListener('click',()=>ctx.confirm(el.dataset.queueCancel)));
    target.querySelector('[data-queue-confirm]')?.addEventListener('click',e=>ctx.cancel(e.currentTarget.dataset.queueConfirm));
    target.querySelector('[data-queue-keep]')?.addEventListener('click',()=>ctx.confirm(null));
    target.querySelector('[data-queue-pause]')?.addEventListener('click',()=>ctx.pause(!data.paused));
    target.querySelectorAll('[data-queue-history]').forEach(el=>el.addEventListener('click',()=>ctx.history('all')));
    target.querySelectorAll('[data-queue-success]').forEach(el=>el.addEventListener('click',()=>ctx.history('success')));
  }
  const api={model,parameters,render};if(typeof module==='object'&&module.exports)module.exports=api;else root.HuashiTaskQueue=api;
})(typeof window==='undefined'?{}:window);
