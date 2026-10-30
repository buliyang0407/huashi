/* Navigation and legacy-link contract for the integrated inspiration rooms. */
(() => {
  const kinds={cases:'case',styles:'style',layouts:'layout',palettes:'palette',all:'all'};
  function parse(hash){
    const text=String(hash||'#inspiration').replace(/^#/,''), [raw,query='']=text.split('?');
    const p=new URLSearchParams(query), parts=raw.split('/'), page=Number(p.get('page')||0), size=Number(p.get('size')||50);
    const r={domain:'',collection:'',kind:'',query:p.get('q')||'',category:p.get('category')||'',folderId:p.get('folder')||'',sourceId:p.get('source')||'',tech:p.get('tech')||'',page:Number.isInteger(page)&&page>=0?page:0,pageSize:[20,50,100].includes(size)?size:50,entryId:p.get('entry')||'',view:'home',notice:''};
    if(raw==='inspiration')return r;
    if(raw==='inspiration/portrait')return {...r,domain:'prompt',collection:'personal',kind:'prompt',view:'portrait'};
    if(parts[0]!=='inspiration')return {...r,notice:'这个地址暂不可用，已返回灵感屋。'};
    if(raw==='inspiration/favorites')return {...r,view:'favorites'};
    if(raw==='inspiration/search')return {...r,view:'search'};
    if(parts[1]==='prompts'&&parts.length<=3&&(!parts[2]||parts[2]==='portrait'))return {...r,domain:'prompt',collection:'personal',kind:'prompt',view:parts[2]==='portrait'?'portrait':'prompts'};
    if(parts[1]==='image'&&parts.length<=3&&(!parts[2]||kinds[parts[2]]))return {...r,domain:'image',collection:'reference',kind:kinds[parts[2]]||'case',view:'image'};
    if(parts[1]==='animation'&&parts.length<=3&&(!parts[2]||parts[2]==='code'))return {...r,domain:'animation',collection:parts[2]||'',kind:p.get('kind')||'',view:'animation'};
    return {...r,entryId:'',view:'home',notice:'这个分类暂未开放，已返回灵感屋。'};
  }
  function format(r){
    let base='#inspiration';
    if(r.view==='favorites'||r.view==='search')base+='/'+r.view;
    else if(r.domain==='prompt')base+=r.view==='portrait'?'/portrait':'/prompts';
    else if(r.domain==='image')base+='/image/'+(Object.keys(kinds).find(k=>kinds[k]===r.kind)||'cases');
    else if(r.domain==='animation')base+='/animation'+(r.collection?'/'+r.collection:'');
    const p=new URLSearchParams();
    for(const [key,value] of Object.entries({q:r.query,category:r.category,folder:r.folderId,page:r.page||'',size:r.pageSize!==50?r.pageSize:'',entry:r.entryId,source:r.sourceId,tech:r.tech,kind:r.domain==='animation'?r.kind:''}))if(value!==undefined&&value!==null&&String(value)!=='')p.set(key,String(value));
    return base+(p.size?'?'+p:'');
  }
  function legacy(value){
    const u=new URL(value,'http://preview.local'), hash=u.hash;
    const simple={'#prompts':'#inspiration/prompts','#portrait':'#inspiration/prompts/portrait','#rewrite':'#inspiration/prompts','#translate':'#inspiration/prompts','#inspiration-case':'#inspiration/image/cases','#inspiration-style':'#inspiration/image/styles','#inspiration-layout':'#inspiration/image/layouts'};
    if(simple[hash])return simple[hash];
    if(u.pathname==='/inspiration/'&&hash.startsWith('#/')){
      const [old,q='']=hash.slice(2).split('?');
      const map={cases:'#inspiration/image/cases',styles:'#inspiration/image/styles',layouts:'#inspiration/image/layouts',favorites:'#inspiration/favorites',all:'#inspiration/image/all'};
      if(map[old])return map[old]+(q?'?'+new URLSearchParams(q).toString():'');
    }
    return null;
  }
  window.HuashiInspirationNav={parse,format,legacy};
})();
