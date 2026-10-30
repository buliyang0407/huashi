/* Display-only language and compact cards. Original entries and prompt text stay untouched. */
(() => {
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={image:'图像',animation:'动画',prompt:'提示词',portrait:'人像素材'};
  const tags={Poster:'海报',Photography:'摄影',Realistic:'写实',Illustration:'插画',Infographic:'信息图',Charts:'图表',Character:'角色',Characters:'人物',Product:'产品',Products:'产品',Commerce:'商业',Education:'教育',Travel:'旅行',Food:'美食',Social:'社交',Story:'叙事',Tech:'科技',Creative:'创意',Classical:'古典',Architecture:'建筑',Brand:'品牌',Documents:'文档',Scenes:'场景',History:'历史',UI:'界面',Handdrawn:'手绘','3D':'三维'};
  const captions={'case:544':'实物拆解与词汇标注，适合幼儿认知','case:543':'山川风景与珐琅徽章质感结合','case:542':'高对比黑白与大字排版结合','case:541':'照片与纸张拼贴，记录日常回忆','case:540':'奇幻城市景观与编辑海报结合','case:539':'粗粝手绘笔触与搭档肖像结合','case:538':'橡皮章质感，呈现旅行见闻','case:537':'暗调空间与档案馆纵深光影','case:536':'春日樱花与电影感回眸人像','case:535':'同一张脸，比较十二种发型','case:534':'红色光线叠加实验肖像排版','case:533':'手绘线条与时尚人物涂鸦','case:532':'六宫格呈现柠檬饮料微缩场景','case:531':'水晶边框与国家旅行风景结合','case:530':'保留实拍背景，替换涂鸦人物','case:529':'云朵气球与山脊旅行人像','case:528':'圣诞实景与可爱比例人物结合','case:527':'旅行票据与纸雕立体层次','case:525':'酒红背景与棚拍男士肖像'};
  const clean=value=>String(value??'').replace(/\s+/g,' ').trim();
  function excerpt(value,max=26){const text=clean(value).replace(/^```[\w-]*\s*/, '');return Array.from(text).length>max?Array.from(text).slice(0,max).join('').replace(/[，、；：\s]+$/,'')+'…':text;}
  function summary(e){
    if(captions[e.id])return captions[e.id];
    let original=e.domain==='prompt'?(e.content||e.prompts?.original||''):'';
    try{const parsed=JSON.parse(original);original=typeof parsed.prompt==='string'?parsed.prompt:''}catch{/* Display plain text without modifying its source. */}
    const text=clean(e.description||e.note||e.prompt_hint_cn||original);
    if(/[\u3400-\u9fff]/.test(text)&&!text.startsWith('{'))return excerpt(text.split(/[。！？\n]/)[0]);
    if(e.domain==='animation'&&e.features?.length)return excerpt(e.features.slice(0,3).join(' · '));
    const readable=(e.tags||[]).map(t=>tags[t]||(/[\u3400-\u9fff]/.test(t)?t.replace(/^分类:/,''):null)).filter(Boolean);
    if(readable.length)return excerpt([...new Set(readable)].slice(0,3).join(' · '));
    if(e.kind==='palette')return '查看完整配色与中英文搭配说明';
    if(e.kind==='style')return '参考画面笔触、材质与用色方式';
    if(e.kind==='layout')return '参考信息层级、图文关系与留白';
    if(e.domain==='prompt')return e.variants?.length?'保留原文，附有可继续使用的衍生':'个人保存的完整提示词';
    return e.category?excerpt(e.category+' · '+(e.domain==='animation'?'制作资料与演示':'图像参考')):'查看完整作品与制作资料';
  }
  function navigation(active){return `<nav class="reference-domains" aria-label="灵感类型">${[['','全部','#inspiration/search'],['prompt','提示词','#inspiration/prompts'],['animation','动画','#inspiration/animation/code'],['image','图像','#inspiration/image/cases']].map(([key,title,href])=>`<a href="${href}" class="${key===active?'active':''}"${key===active?' aria-current="page"':''}>${title}</a>`).join('')}</nav>`;}
  function card(e,{attributes='',selection='',extraClass=''}={}){
    const thumb=typeof e.thumbnail==='string'&&e.thumbnail.startsWith('/')&&!e.thumbnail.startsWith('//')?e.thumbnail:'',label=labels[e.domain]||'灵感',caption=summary(e);
    const preview=thumb?`data-preview-image data-full-title="${esc(e.title)}" data-full-thumb="${esc(thumb)}" data-preview-caption="完整构图 · 点击查看详情"`:'';
    return `<article class="entry-card inspiration-card reference-card ${esc(extraClass)}${e.domain==='animation'?' animation-card':e.domain==='image'?' image-entry-card':''}" data-entry-card="${esc(e.id)}">
      <button class="entry-cover inspiration-card-cover reference-cover" type="button" ${attributes} ${preview} aria-label="查看${esc(label)}：${esc(e.title)}">
        ${thumb?`<img src="${esc(thumb)}" alt="${esc(e.title)}" loading="lazy" decoding="async">`:`<span class="reference-text-cover"><small>文字资料</small><strong>${esc(label)}</strong><span>点击查看完整内容</span></span>`}
        <small class="reference-type">${esc(label)}${e.domain==='animation'&&e.playable?' · 已保存':''}</small>
      </button>
      <div class="entry-copy inspiration-card-body reference-card-copy"><h3 class="inspiration-card-title" title="${esc(e.title)}"><button type="button" ${attributes}>${esc(e.title)}</button></h3><p class="inspiration-card-summary" title="${esc(caption)}">${esc(caption)}</p></div>
      ${selection}
    </article>`;
  }
  window.HuashiInspirationPresentation={esc,excerpt,summary,navigation,card,labels};
})();
