/* Shared presentation only: no data store, requests or task ownership. */
(() => {
  const sizes = [20, 50, 100];
  const sizeOf = value => sizes.includes(Number(value)) ? Number(value) : 20;
  function windowFor(total, page = 0, size = 20) {
    size = sizeOf(size); total = Math.max(0, Number(total) || 0);
    const pages = Math.max(1, Math.ceil(total / size));
    page = Math.min(pages - 1, Math.max(0, Number(page) || 0));
    return {page, size, total, pages, start:page * size, end:(page + 1) * size};
  }
  function sizeControl(size = 20) {
    return `<label class="page-size-control">每页显示<select data-page-size aria-label="每页显示数量">${sizes.map(n=>`<option value="${n}" ${n===sizeOf(size)?'selected':''}>${n}</option>`).join('')}</select></label>`;
  }
  function markup(total, page = 0, size = 20) {
    const w = windowFor(total, page, size);
    return `<div class="huashi-pagination">${sizeControl(w.size)}<span>共 ${w.total} 条 · ${w.page+1} / ${w.pages} 页</span><button type="button" class="tiny-button" data-page-nav="${w.page-1}" ${!w.page?'disabled':''}>上一页</button><button type="button" class="tiny-button" data-page-nav="${w.page+1}" ${w.page+1>=w.pages?'disabled':''}>下一页</button></div>`;
  }
  function bind(root, change) {
    const select=root.querySelector('[data-page-size]');
    if(select)select.onchange=()=>change({page:0,size:sizeOf(select.value)});
    root.querySelectorAll('[data-page-nav]').forEach(button=>button.onclick=()=>change({page:Number(button.dataset.pageNav),size:sizeOf(select?.value)}));
  }
  window.HuashiPages = {sizes, sizeOf, windowFor, sizeControl, markup, bind};
})();
