"""Build a separate Lemo material snapshot from local pinned sources. No network or execution."""
import argparse,copy,hashlib,json,os,shutil
from pathlib import Path
COMMIT='b5e8ef93930b6d828f352055a689320f138237b1'
DESCRIPTIONS={'satellite-briefing':'以卫星影像与地图对照组织叙事，用有出处的真实地理材料呈现环境变化。','briefing-board':'把备选工程方案放在同一简报板上比较，让真实约束推动结论。','lidar-survey':'逐层呈现点云结构，从地表和空间测量中揭示不易察觉的细节。','white-model':'用白色建筑模型承接投影和数据，通过光影讲述空间的变化。','data-physical':'让数据变成有尺度的实体结构，用相同单位比较数量和时间变化。','teardown':'把产品逐层拆开再合拢，用镜头与尺寸标注讲清真实结构。','microscope':'由整体向微观连续深入，借助真实显微材料与测量解释差异。','archive-lighttable':'把档案放在灯台上逐件检视，用放大、对照和出处核对串起叙事。'}
LICENSE='Code and documents: MIT; official films and stills: CC BY 4.0 (LemoLab); third-party materials: see individual CREDITS.'
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(1024*1024):h.update(chunk)
 return h.hexdigest()
def update_snapshot(base,upstream,film,output):
 base,upstream,film,output=map(Path,(base,upstream,film,output))
 if output.exists():raise FileExistsError(output)
 if output.resolve().is_relative_to(base.resolve()):raise ValueError('Output overlaps base')
 data=json.loads((base/'catalog.json').read_text());manifest=json.loads((base/'manifest.json').read_text());old=data['snapshot_id'];new=output.name
 for row in manifest.get('resources',[])+manifest.get('source_files',[]):
  rel=Path(row['path']);p=base/rel
  if rel.is_absolute() or '..' in rel.parts or p.is_symlink() or not p.is_file() or p.stat().st_size!=row['bytes'] or digest(p)!=row['sha256']:raise ValueError('Invalid base resource: '+str(rel))
 if any(p.is_symlink() for p in base.rglob('*')):raise ValueError('Symlink in base')
 # Hard links reuse immutable media without another large storage allocation. Metadata is replaced atomically.
 def link_or_copy(a,b):
  try:os.link(a,b)
  except OSError:shutil.copy2(a,b)
 shutil.copytree(base,output,copy_function=link_or_copy)
 def write_json(name,value):
  p=output/name;tmp=p.with_suffix(p.suffix+'.new');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,p)
 def register(src,relative,resource=False,mime=None):
  target=output/relative;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():raise ValueError('New file collides: '+relative)
  shutil.copy2(src,target);row={'path':relative,'bytes':target.stat().st_size,'sha256':digest(target)}
  if mime:row.update(mime=mime,asset_id='studio-tea-20261021' if mime=='video/mp4' else Path(relative).stem,type='video' if mime=='video/mp4' else 'poster')
  manifest.setdefault('resources' if resource else 'source_files',[]).append(row)
  return '/inspiration-media/'+new+'/'+relative
 for e in data['entries']:
  for key in ('thumbnail','thumbnail_url'):
   if isinstance(e.get(key),str):e[key]=e[key].replace('/inspiration-media/'+old+'/', '/inspiration-media/'+new+'/')
  for m in e.get('media',[]):
   if m.get('url'):m['url']=m['url'].replace('/inspiration-media/'+old+'/', '/inspiration-media/'+new+'/')
 byid={e['id']:e for e in data['entries']}
 def update(id,title,path,kind='style',category='制作方法',description='',original=None):
  e=byid.get(id);curated={k:e[k] for k in ('title','description','features') if k in e} if e and id.startswith('animation:lemo:style:') else {}
  if e is None:
   e={'id':id,'domain':'animation','collection':'code','kind':kind,'media':[],'tags':[],'related_ids':[]};data['entries'].append(e);byid[id]=e
  text=(upstream/path).read_text();source='https://github.com/lemomo-ai/lemo-opuscar/blob/'+COMMIT+'/'+path
  e.update(title=title,category=category,description=description,source='lemo-opuscar',source_id='lemomo-ai/lemo-opuscar',source_ids=['lemomo-ai/lemo-opuscar'],source_revision=COMMIT,source_file=path,source_sha256=hashlib.sha256(text.encode()).hexdigest(),source_license=LICENSE,source_urls=[source],source_title=title,source_description=description,prompts={'original':text,'zh':'','en':''},production_notes=text,prompt_status='style-guide' if kind=='style' else 'original',capabilities={'copy_prompt':True,'save_prompt':True,'use_image_canvas':False})
  if original is not None:e['original']=original
  if curated:e.update(curated)
  e['editorial']={'basis':'pinned-source-text','label':'依据来源文字整理；未逐条实播复核','version':'20261021'}
  register(upstream/path,'sources/lemo-20261021/'+path)
  return e
 rows=json.loads((upstream/'styleboard/catalog.json').read_text());rows=[r for r in rows if r['slug']!='_template'];assert len(rows)==51
 for row in rows:
  slug=row['slug'];e=update('animation:lemo:style:'+slug,row.get('cn') or row['en'],'styles/'+slug+'/STYLE.md',category=row.get('cat',''),description=row.get('line_cn') or row.get('line',''),original=row)
  if slug in DESCRIPTIONS:e['description']=DESCRIPTIONS[slug]
  e.update(duration_seconds=row.get('dur'),tech_tags=['Canvas / WebGL'],tags=row.get('uses',[]))
  if not e.get('thumbnail'):
   poster=upstream/'styleboard/img'/ (slug+'_0.jpg')
   if not poster.exists():poster=upstream/'styles'/slug/'poster.jpg'
   if poster.exists():
    url=register(poster,'posters/lemo-20261021-'+slug+'.jpg',True,'image/jpeg');e.update(thumbnail=url,thumbnail_url=url,cover_status='original',poster_asset_id='lemo-20261021-'+slug)
   else:e['cover_status']='missing'
  if not e.get('features'):e['features']=[row.get('cat') or '风格参考',row.get('cn') or slug]
  if not e['media']:e['media']=[{'role':'demo','availability':'external-link','external_url':'https://lemomo-ai.github.io/lemo-opuscar/','duration_seconds':row.get('dur')}]
  e['viewing_links']=[{'url':'https://lemomo-ai.github.io/lemo-opuscar/','roles':['demo']}]
 films=json.loads((upstream/'styleboard/opuscar98_styles.json').read_text())
 register(upstream/'styleboard/opuscar98_styles.json','sources/lemo-20261021/styleboard/opuscar98_styles.json')
 register(upstream/'styleboard/catalog.json','sources/lemo-20261021/styleboard/catalog.json')
 for row in films.get('films',[]):
  e=byid.get('animation:lemo:opuscar98:'+str(row['no']))
  if e is None:raise ValueError('Unexpected new film segment')
  e.update(source_revision=COMMIT,source_license=LICENSE,original=row,source_urls=['https://github.com/lemomo-ai/lemo-opuscar/blob/'+COMMIT+'/styleboard/opuscar98_styles.json',films.get('film','https://lemomo-ai.github.io/lemo-opuscar/opuscar98/')],prompts={'original':row.get('prompt_en') or row.get('prompt_zh',''),'zh':row.get('prompt_zh',''),'en':row.get('prompt_en','')},direction_zh=row.get('direction_zh',''),direction_en=row.get('direction_en',''),shots=row.get('shots',[]),source_sha256=digest(upstream/'styleboard/opuscar98_styles.json'))
 for slug,title,path,description in [('director','导演指南：故事、镜头与声音','DIRECTOR.md','从故事、镜头、节奏到声音和审片，组织一支原创短片。'),('technique','制作指南：画面、配音与导出','TECHNIQUE.md','逐帧绘制、配音、配乐、字幕和成片导出的完整技术方法。'),('my-styles','自定义风格：改成自己的版本','MY-STYLES.md','基于原有风格调整视觉规则，保存个人版本并制作15至30秒试片。')]:
  e=update('animation:lemo:guide:'+slug,title,path,'template',description=description);e.update(features=['制作方法','完整指南'],tech_tags=['制作指南'])
 water=byid['animation:lemo:style:watercolor'];water['media']=[m for m in water['media'] if m.get('role')!='studio-test']
 url=register(film/'一叶入杯.mp4','previews/studio-tea-20261021.mp4',True,'video/mp4')
 water['media'].append({'asset_id':'studio-tea-20261021','role':'studio-test','label':'我们的试片《一叶入杯》','availability':'local','url':url,'duration_seconds':18,'file_duration_seconds':18,'mime':'video/mp4','bytes':(film/'一叶入杯.mp4').stat().st_size})
 water['production_notes']+='\n\n## 我们的适配试片《一叶入杯》\n18秒原创水彩试验，1080p，带合成音乐音效，无旁白。验证了水彩笔刷和导出链路；未验证完整自动制作、复杂人物、中文配音或其他风格。工程和研究说明已随固定版本资料归档NAS。'
 for p in film.iterdir():
  if p.is_file() and p.name in {'TREATMENT.md','CREDITS.md','验收记录.md'}:register(p,'sources/studio-tea-20261021/'+p.name)
 data.update(snapshot_id=new,parent_snapshot_id=old)
 data.setdefault('source_counts',{})['lemo-opuscar']={'styles':51,'film_segments':len(films.get('films',[])),'guides':3,'raw':51+len(films.get('films',[]))+3}
 manifest['snapshot_id']=new
 manifest.setdefault('sources',{})['lemo-20261021']={'repository':'lemomo-ai/lemo-opuscar','commit':COMMIT,'license':LICENSE}
 manifest['input_digest']=hashlib.sha256((manifest.get('input_digest','')+COMMIT).encode()).hexdigest()
 assert len(byid)==len(data['entries'])
 write_json('catalog.json',data);write_json('manifest.json',manifest)
 report={'snapshot_id':new,'parent_snapshot_id':old,'entries':len(data['entries']),'styles':51,'guides':3,'trial':'studio-tea-20261021','revision':COMMIT}
 write_json('lemo-update-report.json',report)
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ('base','upstream','film','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();print(json.dumps(update_snapshot(a.base,a.upstream,a.film,a.output),ensure_ascii=False))
