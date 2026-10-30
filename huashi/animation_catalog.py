"""Deterministic offline import of pinned upstream data; never execute source repositories."""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit, urlunsplit

SLUGS=('lemo-opuscar','awesome-opus5-5-videos','opus-video-prompts')
CATEGORIES={'motion':'动态图形','3d':'三维场景','explainer':'讲解动画','interactive':'交互作品'}

def encoded(value):
    return json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True).encode()+b'\n'

def sha(data):return hashlib.sha256(data).hexdigest()

def work_key(url):
    u=urlsplit(str(url));m=re.search(r'/status/(\d+)',u.path)
    if u.hostname in {'x.com','www.x.com','twitter.com','www.twitter.com','mobile.twitter.com'} and m:return 'x:'+m[1]
    m=re.search(r'/video/(BV[a-zA-Z0-9]+)',u.path)
    if u.hostname in {'www.bilibili.com','bilibili.com'} and m:return 'bilibili:'+m[1]
    return ''

def normalized_url(url):
    u=urlsplit(str(url));return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path.rstrip('/'),'',''))

def text_blocks(markdown):return re.findall(r'```(?:text|markdown|prompt)?[^\n]*\n(.*?)```',markdown,re.S)

def build_catalog(source_root,output_root,dry_run=False):
    source_root=Path(source_root).resolve();output=Path(output_root).absolute();sources={};files=[];payloads={}
    for slug in SLUGS:
        folder=source_root/slug;meta=json.loads((folder/'source.json').read_text());sources[slug]=meta
        for p in sorted((folder/'files').rglob('*')):
            if p.is_symlink():raise ValueError('Source symlinks are not allowed')
            if not p.is_file():continue
            rel='sources/'+slug+'/'+p.relative_to(folder/'files').as_posix();raw=p.read_bytes();payloads[rel]=raw;files.append({'path':rel,'bytes':len(raw),'sha256':sha(raw)})
        payloads['sources/'+slug+'/source.json']=encoded(meta)
    digest=sha(encoded({'files':files,'sources':sources}));snapshot='code-'+digest[:12];entries=[];assets={};aliases={};source_counts={};work_index={};anomalies=[]
    def srcpath(slug,path):return source_root/slug/'files'/path
    def load(slug,path):return json.loads(srcpath(slug,path).read_text())
    def source_link(slug,path):return 'https://github.com/'+sources[slug]['repository']+'/blob/'+sources[slug]['commit']+'/'+path
    def base(id,kind,title,slug,record,path,prompt='',status='description-only',category=''):
        return {'id':id,'domain':'animation','collection':'code','kind':kind,'title':title,'description':'','category':category,'tags':[],'source_id':sources[slug]['repository'],'source':slug,'source_ids':[sources[slug]['repository']],'source_urls':[source_link(slug,path)],'source_revision':sources[slug]['commit'],'source_file':path,'source_sha256':sha(srcpath(slug,path).read_bytes()),'source_license':'MIT repository; original works retain their authors rights' if srcpath(slug,'LICENSE').exists() else 'No explicit repository license found; retain attribution and source links','original':record,'prompts':{'original':prompt,'zh':'','en':''},'prompt_versions':[],'prompt_status':status,'thumbnail':'','thumbnail_url':'','media':[],'related_ids':[],'capabilities':{'copy_prompt':bool(prompt),'save_prompt':bool(prompt),'use_image_canvas':False}}
    def poster(e,slug,path=None,url=None):
        aid='poster-'+sha((slug+':'+str(path or url)).encode())[:18];url=url or 'https://raw.githubusercontent.com/'+sources[slug]['repository']+'/'+sources[slug]['commit']+'/'+path
        assets.setdefault(aid,{'id':aid,'type':'poster','source_url':url,'source_id':sources[slug]['repository'],'entries':[]});assets[aid]['entries'].append(e['id']);e['poster_asset_id']=aid
    lemo='lemo-opuscar';styles=load(lemo,'styleboard/catalog.json');films=load(lemo,'styleboard/opuscar98_styles.json');tree=json.loads((source_root/lemo/'tree.json').read_text())['tree'];paths={i['path'] for i in tree if i['type']=='blob'}
    releases=json.loads((source_root/lemo/'releases.json').read_text());web=[a for r in releases if r['tag_name']=='web' for a in r['assets'] if a['name'].endswith('.mp4')]
    for a in web:
        aid='lemo-'+Path(a['name']).stem;assets[aid]={'id':aid,'type':'video','source_url':a['browser_download_url'],'expected_bytes':a['size'],'source_id':sources[lemo]['repository'],'role':'demo','entries':[],'release_updated_at':a.get('updated_at'),'github_digest':a.get('digest')}
    for row in styles:
        slug=row.get('slug','')
        if not slug or slug=='_template':continue
        path='styles/'+slug+'/STYLE.md';p=srcpath(lemo,path)
        if not p.is_file():anomalies.append({'source':lemo,'id':slug,'reason':'missing style guide'});prompt=''
        else:prompt=p.read_text()
        e=base('animation:lemo:style:'+slug,'style',row.get('cn') or row.get('en') or slug,lemo,row,path if p.is_file() else 'styleboard/catalog.json',prompt,'style-guide' if prompt else 'description-only',row.get('cat',''))
        e.update(description=row.get('line_cn') or row.get('line',''),tags=row.get('uses',[]),duration_seconds=row.get('dur'),tech_tags=['Canvas / WebGL'],production_notes=prompt)
        if 'styleboard/img/'+slug+'_0.jpg' in paths:poster(e,lemo,'styleboard/img/'+slug+'_0.jpg')
        aid='lemo-'+slug;e['media']=[{'asset_id':aid,'role':'demo','availability':'external-link','external_url':'https://lemomo-ai.github.io/lemo-opuscar/','duration_seconds':row.get('dur')}]
        if aid in assets:assets[aid]['entries'].append(e['id'])
        entries.append(e)
    for row in films.get('films',[]):
        e=base('animation:lemo:opuscar98:'+str(row['no']),'style',str(row.get('no'))+' · '+str(row.get('zh') or row.get('title')),lemo,row,'styleboard/opuscar98_styles.json',row.get('prompt_en') or row.get('prompt_zh',''),'style-guide','电影风格片段')
        e.update(description=row.get('desc_zh') or row.get('desc_en',''),tags=row.get('blend_zh',[]),tech_tags=[row.get('render','')],shots=row.get('shots',[]),direction_zh=row.get('direction_zh',''),direction_en=row.get('direction_en',''),duration_seconds=row.get('dur'),number=row['no']);e['prompts'].update(zh=row.get('prompt_zh',''),en=row.get('prompt_en',''))
        path='styleboard/img/opuscar98/'+str(row['no']).zfill(2)+'.jpg'
        if path in paths:poster(e,lemo,path)
        e['source_urls'].append(films.get('film','https://lemomo-ai.github.io/lemo-opuscar/opuscar98/'));e['media']=[{'asset_id':'lemo-opuscar98','role':'demo','availability':'external-link','external_url':films.get('film',''),'start_seconds':row.get('t0',0),'end_seconds':row.get('t0',0)+row.get('dur',0),'duration_seconds':row.get('dur')}]
        if 'lemo-opuscar98' in assets:assets['lemo-opuscar98']['entries'].append(e['id'])
        entries.append(e)
    source_counts[lemo]={'styles':len(styles),'film_segments':len(films.get('films',[])),'raw':len(styles)+len(films.get('films',[]))}
    awesome='awesome-opus5-5-videos';videos=load(awesome,'data/videos.json')
    for row in videos:
        slug=row.get('slug') or sha(encoded(row))[:20];prompt=row.get('prompt') or '';status='partial' if row.get('prompt_partial') else 'curated' if prompt else 'description-only'
        e=base('animation:awesome:'+slug,'case',row.get('title') or CATEGORIES.get(row.get('category'),'代码动画')+' · @'+row.get('author',''),awesome,row,'data/videos.json',prompt,status,CATEGORIES.get(row.get('category'),'代码动画'))
        e.update(description=prompt[:180],author=row.get('author',''),tech_tags=row.get('tech_tags',[]),tags=[row.get('category',''),*row.get('tech_tags',[])],prompt_partial=row.get('prompt_partial'),has_remake=bool(row.get('has_remake')))
        e['source_urls']+=list(dict.fromkeys(u for u in [row.get('post_url'),row.get('skillry_url')] if u));e['media']=[{'role':'original','availability':'external-link','external_url':row.get('skillry_url') or row.get('post_url') or ''}]
        if row.get('has_remake'):e['media'].append({'role':'remake','availability':'external-link','external_url':row.get('skillry_url') or ''})
        if row.get('poster_url'):poster(e,awesome,url=row['poster_url'])
        key=work_key(row.get('post_url'));work_index[key]=e if key else work_index.get(key);entries.append(e)
    source_counts[awesome]={'raw':len(videos),'partial':sum(bool(v.get('prompt_partial')) for v in videos),'prompt_texts':len({v.get('prompt') for v in videos if v.get('prompt')})}
    joe='opus-video-prompts';cases=load(joe,'cases.json');joe_entries=[];linked=0
    for row in cases:
        title=row.get('title') or '代码动画参考';url=row.get('url','');id='animation:joe:case:'+sha((normalized_url(url)+'\n'+title).encode())[:20];key=work_key(url);target=work_index.get(key) if key else None
        if target:
            aliases[id]=target['id'];target['source_ids'].append(sources[joe]['repository']);target['source_urls']+=list(dict.fromkeys([source_link(joe,'cases.json'),url]));target.setdefault('additional_sources',[]).append({'source_id':sources[joe]['repository'],'record':row,'revision':sources[joe]['commit']});target['title']=title;linked+=1;e=target
        else:
            e=base(id,'case',title,joe,row,'cases.json',category=row.get('category',''));e.update(description=row.get('how') or '',author=row.get('author',''),production_notes='上游说明：'+str(row.get('how',''))+'\n上游成本自述（未独立核验）：'+str(row.get('cost','')));e['source_urls'].append(url);e['media']=[{'role':'original','availability':'external-link','external_url':url}];entries.append(e)
        joe_entries.append((row,e))
    # These are title associations within the pinned Chinese source, not inferred video identity.
    title_hints={'03':'中华五千年','05':'Transformer','06':'从房间','09':'大气环流','11':'奥斯特里茨','17':'像素巫师'}
    template_count=0;attached=0
    for p in sorted((srcpath(joe,'prompts')).glob('*.md')):
        markdown=p.read_text();title=markdown.splitlines()[0].lstrip('# ').strip();blocks=text_blocks(markdown);prompt='\n\n'.join(blocks);urls=list(dict.fromkeys(re.findall(r'https?://[^\s)<>]+',markdown)));key=next((work_key(u) for u in urls if work_key(u)),'');possible=[e for row,e in joe_entries if key and work_key(row.get('url'))==key];number=p.name.split('-')[0]
        if not possible:
            possible=[e for row,e in joe_entries if row.get('title')==title]
        if not possible and number in title_hints:possible=[e for row,e in joe_entries if title_hints[number] in row.get('title','')]
        target=possible[0] if len(possible)==1 else None
        version={'id':'animation:joe:template:'+p.stem,'title':title,'text':prompt,'source_url':source_link(joe,'prompts/'+p.name),'source_urls':urls,'source_file':'prompts/'+p.name,'source_sha256':sha(p.read_bytes()),'notes':markdown,'status':'curated' if '中文转述' in markdown else 'original'}
        if target:
            target['prompt_versions'].append(version);target['source_urls']=list(dict.fromkeys(target['source_urls']+[version['source_url'],*urls]));attached+=1
            if not target['prompts']['original'] and prompt:target['prompts']['original']=prompt;target['prompt_status']=version['status'];target['capabilities'].update(copy_prompt=True,save_prompt=True)
        else:
            e=base(version['id'],'template',title,joe,{'file':p.name},'prompts/'+p.name,prompt,version['status'],'可复用模板');e.update(description='独立提示词材料；来源及使用说明完整保留。',production_notes=markdown,prompt_versions=[version],source_urls=[version['source_url'],*urls]);entries.append(e);template_count+=1
    source_counts[joe]={'raw':len(cases),'linked_cases':linked,'prompt_files':attached+template_count,'attached_prompt_files':attached,'standalone_templates':template_count}
    groups=defaultdict(list)
    for e in entries:
        text=' '.join(e['prompts']['original'].split())
        if text:groups[sha(text.encode())].append(e['id'])
    same=[{'prompt_sha256':h,'entry_ids':ids} for h,ids in sorted(groups.items()) if len(ids)>1]
    for e in entries:
        e['source_urls']=list(dict.fromkeys(u for u in e['source_urls'] if urlsplit(u).scheme in {'http','https'}));e['source_ids']=list(dict.fromkeys(e['source_ids']));e['related_ids']=[id for g in same if e['id'] in g['entry_ids'] for id in g['entry_ids'] if id!=e['id']]
    # Deterministic proportional selection: 26 motion and 8 from each other category.
    selected=[]
    for category,count in [('motion',26),('explainer',8),('3d',8),('interactive',8)]:
        pool=sorted((v for v in videos if v.get('category')==category and v.get('prompt') and v.get('poster_url') and v.get('skillry_url')),key=lambda v:(bool(v.get('prompt_partial')),not bool(v.get('has_remake')),v['slug']))
        selected.extend(v['slug'] for v in pool[:count])
    catalog={'version':1,'snapshot_id':snapshot,'entries':entries,'aliases':aliases,'same_prompt_groups':same,'source_counts':source_counts,'selected_awesome_slugs':selected}
    manifest={'version':1,'snapshot_id':snapshot,'input_digest':digest,'sources':sources,'source_files':files,'resources':[],'planned_assets':list(assets.values()),'selected_awesome_slugs':selected,'license_note':'Personal local reference archive. Repository licenses do not settle third-party video rights.'}
    report={'snapshot_id':snapshot,'raw_candidates':sum(v['raw'] for v in source_counts.values()),'entries':len(entries),'counts':dict(Counter(e['kind'] for e in entries)),'linked_cases':linked,'source_counts':source_counts,'anomalies':anomalies,'same_prompt_groups':len(same),'selected_originals':len(selected)}
    payloads.update({'catalog.json':encoded(catalog),'manifest.json':encoded(manifest),'import-report.json':encoded(report)});report={**report,'planned_files':[{'path':k,'bytes':len(v)} for k,v in sorted(payloads.items())],'planned_bytes':sum(map(len,payloads.values()))}
    if dry_run:return report
    if output.exists():
        if not (output/'manifest.json').is_file() or json.loads((output/'manifest.json').read_text()).get('input_digest')!=digest:raise FileExistsError('Existing snapshot cannot be overwritten')
        if any(not (output/path).is_file() or (output/path).read_bytes()!=raw for path,raw in payloads.items()):raise FileExistsError('Existing snapshot contents differ; no files overwritten')
        return {**report,'unchanged':True}
    if any(p.is_symlink() for p in [output,*output.parents]):raise ValueError('Snapshot path cannot use symlinks')
    output.mkdir(parents=True)
    for path,raw in payloads.items():
        dest=output/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    return report


def activate_snapshot(animation_root,snapshot_id,state_path,dry_run=False):
    """Validate immutable files before atomically changing the active pointer; never restore data."""
    import os,sqlite3,time
    root=Path(animation_root).absolute()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',snapshot_id):raise ValueError('Invalid snapshot ID')
    snap=root/'snapshots'/snapshot_id
    if any(p.is_symlink() for p in [snap,*snap.parents]):raise ValueError('Unsafe snapshot path')
    catalog=json.loads((snap/'catalog.json').read_text());manifest=json.loads((snap/'manifest.json').read_text())
    if catalog['snapshot_id']!=snapshot_id or manifest['snapshot_id']!=snapshot_id:raise ValueError('Snapshot identifiers differ')
    approved={}
    for row in manifest.get('resources',[])+manifest.get('source_files',[]):
        rel=row['path'];p=snap/rel
        if Path(rel).is_absolute() or '..' in Path(rel).parts or any(a.is_symlink() for a in [p,*p.parents]) or not p.is_file():raise ValueError('Unsafe or missing file: '+rel)
        if p.stat().st_size!=row['bytes'] or sha(p.read_bytes())!=row['sha256']:raise ValueError('Hash verification failed: '+rel)
        approved[rel]=row
    ids={e['id'] for e in catalog['entries']};aliases=catalog.get('aliases',{})
    if any(a in ids or v not in ids or v in aliases or not a.startswith('animation:') for a,v in aliases.items()):raise ValueError('Invalid alias map')
    for entry in catalog['entries']:
        for media in entry.get('media',[]):
            if media.get('availability')=='local':
                prefix='/inspiration-media/'+snapshot_id+'/'
                if not media.get('url','').startswith(prefix) or media['url'][len(prefix):] not in approved:raise ValueError('Catalog refers to unpublished media')
    report={'snapshot_id':snapshot_id,'entries':len(ids),'files_verified':len(approved),'resource_bytes':sum(r['bytes'] for r in manifest.get('resources',[])),'catalog_sha256':sha((snap/'catalog.json').read_bytes()),'manifest_sha256':sha((snap/'manifest.json').read_bytes())}
    if dry_run:return report
    state=Path(state_path).absolute()
    if state.name!='inspiration-state.sqlite3' or not state.is_file() or any(p.is_symlink() for p in [state,*state.parents]):raise ValueError('An explicitly initialized independent state is required')
    conn=sqlite3.connect(state.as_uri()+'?mode=rw',uri=True)
    try:
        with conn:
            for alias,canonical in aliases.items():
                old=conn.execute('SELECT canonical_id FROM aliases WHERE alias_id=?',(alias,)).fetchone()
                if old and old[0]!=canonical:raise ValueError('Existing alias cannot be silently redirected')
                conn.execute('INSERT OR IGNORE INTO aliases VALUES (?,?)',(alias,canonical))
    finally:conn.close()
    active=root/'active.json'
    if active.is_symlink():raise ValueError('Active pointer cannot be a symlink')
    if active.exists():
        previous=root/('active.previous.'+str(time.time_ns())+'.json');previous.write_bytes(active.read_bytes())
    temp=root/('active.'+str(time.time_ns())+'.tmp');temp.write_bytes(encoded(report));os.replace(temp,active)
    return report
