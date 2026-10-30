"""Build a private material index from mounted libraries; originals are read-only."""
from pathlib import Path
import argparse,json,sys
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from huashi.portrait_studio import PortraitStudio

def build_catalog(app_root):
    app_root=Path(app_root)
    rows=[]
    cats={'01_发型':'发型','02_发饰':'发饰','03_服饰':'服装','04_表情':'表情','05_肢体动作姿态':'姿势','06_镜头语言':'镜头','07_光影':'光影','08_人物气质身份':'人物','09_场景空间':'场景','10_环境细节道具':'细节'}
    for m in PortraitStudio(app_root/'promptscreation').scan_materials():
     rows.append(dict(id='portrait:'+m['id'],category=cats.get(m['raw_category'],'其他'),title=m['title_cn'],words='\n'.join(dict.fromkeys(filter(None,[m['prompt_hint_cn'],m['prompt_hint_en']]))),source='原有素材描述',image=m['image_url'],folder='原有工坊素材',filename=Path(m['rel_path']).name))
    cost=app_root/'pose/.costume-library'; meta=json.loads((cost/'.metadata/catalog.json').read_text()) if (cost/'.metadata/catalog.json').exists() else {'entries':[]}; known={e['media']['local_relative_path']:e for e in meta['entries']}
    for root,cat,prefix in [(app_root/'pose','姿势','/pose-files/'),(app_root/'data/faces','人物','/face-files/')]:
     for p in sorted(root.rglob('*')):
      if not p.is_file() or not p.resolve().is_relative_to(root.resolve()) or p.suffix.lower() not in {'.png','.jpg','.jpeg','.webp','.gif','.bmp'} or p.name.startswith('._'):continue
      rel=p.relative_to(root).as_posix()
      if any(part.startswith('.') for part in p.relative_to(root).parts) and not rel.startswith('.costume-library/'):continue
      e=known.get(rel.removeprefix('.costume-library/')) if rel.startswith('.costume-library/') else None
      if rel.startswith('.costume-library/.'):continue
      if e:title=e['category_zh']+' · '+e['source_item_id'];words='、'.join(e['keywords_zh'])+'\n\n'+e['keywords_original'];category='服装';folder=e['category_zh'];source='来源参考词 · 未逐图复审';id=e['id']
      else:title=p.stem;words=p.stem;category=cat;folder=p.parent.relative_to(root).as_posix();source='素材名称与目录';id=('pose:' if cat=='姿势' else 'face:')+rel
      rows.append(dict(id=id,category=category,title=title,words=words,source=source,image=prefix+quote(rel),folder=folder,filename=p.name))
    assert len({r['id'] for r in rows})==len(rows)
    return rows

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--app-root",type=Path,default=Path("/app"));args=parser.parse_args();print(json.dumps(build_catalog(args.app_root),ensure_ascii=False))
