/* Image previews are transient UI. Originals load only after an explicit click. */
(() => {
  function create({loadEntry, imageURL}) {
    const peek = document.createElement('div');
    peek.className = 'inspiration-image-peek'; peek.hidden = true;
    peek.innerHTML = '<img alt=""><div><strong></strong><span>完整构图 · 点击看原图</span></div>';
    peek.setAttribute('aria-hidden', 'true');
    const dialog = document.createElement('dialog');
    dialog.className = 'inspiration-full-image'; dialog.setAttribute('aria-label', '查看完整图片');
    dialog.innerHTML = '<header class="image-viewer-toolbar"><strong class="image-viewer-title"></strong><div><button type="button" data-image-fit aria-pressed="true">适应窗口</button><button type="button" data-image-actual aria-pressed="false">原始大小</button><a target="_blank" rel="noopener noreferrer" data-image-original hidden>单独打开原图 ↗</a><button type="button" data-image-close aria-label="关闭全图">关闭 ×</button></div></header><div class="image-viewer-stage"><img class="image-viewer-picture" alt="" hidden><p class="image-viewer-status" role="status">正在读取原图…</p></div><footer>先看完整构图，再用「原始大小」滚动查看细节。</footer>';
    document.body.append(peek, dialog);
    const picture = dialog.querySelector('img'), stage = dialog.querySelector('.image-viewer-stage');
    const status = dialog.querySelector('.image-viewer-status'), original = dialog.querySelector('[data-image-original]');
    const bound = new WeakSet(), cache = new Map();
    let timer, ticket = 0, controller, returnTo, restoringFocus = false, destroyed = false;
    function hidePreview() { clearTimeout(timer); peek.hidden = true; }
    function close() {
      hidePreview(); ticket++; controller?.abort(); picture.onload = picture.onerror = null;
      picture.removeAttribute('src'); picture.hidden = true;
      if (dialog.open) {
        restoringFocus = true; dialog.close();
        if (returnTo?.isConnected) returnTo.focus({preventScroll:true});
        restoringFocus = false;
      }
    }
    function fit(actual = false) {
      stage.classList.toggle('is-actual', actual);
      dialog.querySelector('[data-image-fit]').setAttribute('aria-pressed', String(!actual));
      dialog.querySelector('[data-image-actual]').setAttribute('aria-pressed', String(actual));
      stage.scrollTo(0, 0);
    }
    async function open(button) {
      hidePreview(); controller?.abort(); controller = new AbortController();
      const current = ++ticket, id = button.dataset.fullImage;
      returnTo = button; fit(); picture.hidden = true; picture.removeAttribute('src');
      original.hidden = true; status.hidden = false; status.textContent = '正在读取原图…';
      const title = button.dataset.fullTitle || '完整图片';
      dialog.querySelector('.image-viewer-title').textContent = title; picture.alt = title;
      if (!dialog.open) dialog.showModal();
      try {
        let src = imageURL(button.dataset.fullSrc);
        if (!src) {
          let entry = cache.get(id);
          if (!entry) {
            entry = await loadEntry(id, {signal:controller.signal});
            if (destroyed || current !== ticket) return;
            cache.set(id, entry); if (cache.size > 80) cache.delete(cache.keys().next().value);
          }
          src = imageURL(entry.image || entry.thumbnail);
        }
        if (!src || destroyed || current !== ticket) throw new Error('原图暂不可用');
        original.href = src; original.hidden = false;
        picture.onload = () => { if (current === ticket) { status.hidden = true; picture.hidden = false; } };
        picture.onerror = () => { if (current === ticket) { picture.hidden = true; status.hidden = false; status.textContent = '图片暂时无法显示，可以单独打开原图重试。'; } };
        picture.src = src;
      } catch (error) {
        if (!destroyed && current === ticket && error.name !== 'AbortError') status.textContent = error.message || '原图暂不可用，请稍后重试。';
      }
    }
    function preview(button) {
      hidePreview();
      if (restoringFocus || dialog.open || button.closest('dialog') || !matchMedia('(hover:hover) and (pointer:fine)').matches) return;
      const src = imageURL(button.dataset.fullThumb); if (!src) return;
      timer = setTimeout(() => {
        if (destroyed || !button.isConnected) return;
        const rect = button.getBoundingClientRect(), width = Math.min(420, innerWidth - 32);
        const right = rect.right + 14, left = rect.left - width - 14;
        peek.style.width = width + 'px';
        peek.style.left = Math.max(12, Math.min(innerWidth - width - 12, right + width <= innerWidth - 12 ? right : left)) + 'px';
        peek.style.top = Math.max(12, Math.min(rect.top, innerHeight - Math.min(620, innerHeight * .72) - 12)) + 'px';
        peek.querySelector('strong').textContent = button.dataset.fullTitle || '完整图片';
        peek.querySelector('span').textContent = button.dataset.previewCaption || '完整构图 · 点击看原图';
        peek.querySelector('img').src = src; peek.hidden = false;
      }, 550);
    }
    function bind(root) {
      root.querySelectorAll('[data-full-image],[data-preview-image]').forEach(button => {
        if (bound.has(button)) return; bound.add(button);
        if (button.hasAttribute('data-full-image')) button.addEventListener('click', () => open(button));
        button.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') preview(button); });
        button.addEventListener('pointerleave', hidePreview);
        button.addEventListener('focus', () => { if (button.matches(':focus-visible')) preview(button); });
        button.addEventListener('blur', hidePreview);
      });
    }
    dialog.querySelector('[data-image-close]').onclick = close;
    dialog.querySelector('[data-image-fit]').onclick = () => fit();
    dialog.querySelector('[data-image-actual]').onclick = () => fit(true);
    dialog.oncancel = event => { event.preventDefault(); close(); };
    dialog.onclick = event => {
      if (event.target !== dialog) return;
      const r = dialog.getBoundingClientRect();
      if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) close();
    };
    const onKey = event => { if (event.key === 'Escape') hidePreview(); };
    window.addEventListener('scroll', hidePreview, true); window.addEventListener('resize', hidePreview); window.addEventListener('keydown', onKey);
    return {bind, close, hidePreview, destroy() { destroyed = true; close(); window.removeEventListener('scroll', hidePreview, true); window.removeEventListener('resize', hidePreview); window.removeEventListener('keydown', onKey); peek.remove(); dialog.remove(); cache.clear(); }};
  }
  window.HuashiInspirationImages = {create};
})();
