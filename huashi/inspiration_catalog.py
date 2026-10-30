"""Read-only normalized inspiration catalog. Source archives remain authoritative."""
from __future__ import annotations
import copy
import json
import sqlite3
import re
from pathlib import Path
from urllib.parse import urlsplit
from .inspiration_search import InspirationSearch, _asset

KINDS=('case','style','layout','palette','template','prompt')
DOMAINS=('image','animation','prompt')
SUMMARY=('id','domain','collection','kind','title','description','category','tags','source','source_id','source_url','thumbnail','thumbnail_url','capabilities','number','folder_id','folder_path','prompt_id','variant_id','favorite','prompt_status','duration_seconds','tech_tags','playable','source_ids','prompt_partial','features','viewing_links','cover_status','editorial','source_title')
LABELS={'Poster':'海报','Photography':'摄影','Realistic':'写实','Illustration':'插画','Infographic':'信息图','Charts':'图表','Character':'角色','Characters':'人物','Product':'产品','Products':'产品','Commerce':'商业','Education':'教育','Travel':'旅行','Food':'美食','Social':'社交','Story':'故事','Tech':'科技','Creative':'创意','Classical':'古典','3D':'三维','Architecture':'建筑','Brand':'品牌','Documents':'文档','Scenes':'场景','History':'历史','UI':'界面'}

class InspirationCatalog:
    def __init__(self,image_library,prompt_store,animation_root=None):
        self.library=image_library
        self.store=prompt_store
        self.animation_root=Path(animation_root) if animation_root else None
        self.old_search=InspirationSearch(image_library,prompt_store)
        self._stamp=None
        self._images=[]
        self._animation_cache=None
        self.aliases={}

    @staticmethod
    def _normalize(raw,domain,kind):
        e=copy.deepcopy(raw)
        e.update(domain=domain,collection='personal' if domain=='prompt' else 'reference',kind=kind)
        e.setdefault('title',e.get('name') or e['id'])
        e.setdefault('description','')
        e.setdefault('tags',[])
        e.setdefault('category','')
        original=next((e.get(k) for k in ('prompt','content','prompt_en','promptEn','promptHintEn') if isinstance(e.get(k),str) and e[k].strip()),'')
        e['prompts']={'original':original,'zh':e.get('prompt_zh') or (e.get('prompt','') if kind in {'layout','palette'} else ''),'en':e.get('promptEn') or e.get('prompt_en') or ''}
        e['prompt']=original
        e['source_id']=str(e.get('source') or ('personal' if domain=='prompt' else 'archive'))
        e['source_url']=e.get('source_url') or e.get('githubUrl') or e.get('sourceUrl') or ''
        e['source_urls']=list(dict.fromkeys(u for u in [e.get('githubUrl'),e.get('sourceUrl'),e['source_url']] if isinstance(u,str) and urlsplit(u).scheme in {'http','https'}))
        for field in ('thumbnail','image','referenceImage'):
            value=e.get(field) or ''
            e[field]=_asset(value) if domain=='image' else value
        e['thumbnail_url']=e['thumbnail']
        e['prompt_status']='original' if kind in {'case','prompt','layout'} and original else 'style-guide' if original else 'description-only'
        e['capabilities']={'copy_prompt':bool(original),'save_prompt':bool(original),'use_image_canvas':bool(original) and domain in {'image','prompt'}}
        e['_search']=' '.join(str(e.get(k) or '') for k in ('title','description','category','tags','traits','prompt','promptEn','folder_path'))+' '+json.dumps(e['prompts'],ensure_ascii=False)+' '+' '.join(LABELS.get(t,'') for t in e.get('tags',[]) if isinstance(t,str))
        return e

    def _read_images(self):
        raw,catalog=self.library._catalog()
        if id(raw)!=self._stamp:
            data=[]
            sources={s.get('id'):s for s in catalog.get('sources',[]) if isinstance(s,dict)}
            def normalized(raw,kind):
                e=self._normalize(raw,'image',kind)
                source=sources.get('gpt-image2' if kind=='case' else 'handdraw',{})
                e['source_id']=source.get('id') or e['source_id']
                e['source_revision']=source.get('commit') or source.get('snapshot') or ''
                e['source_license']=source.get('license') or ''
                repository=source.get('repository') or ''
                if repository and repository not in e['source_urls']:e['source_urls'].append(repository)
                if not e['source_url']:e['source_url']=repository
                return e
            for r in catalog.get('entries',[]):
                if isinstance(r,dict) and isinstance(r.get('id'),str) and r.get('kind') in {'case','style','layout'}:
                    data.append(normalized(r,r['kind']))
            for c in catalog.get('colors',[]):
                raw_color={**c,'id':'image:palette:'+str(c['id']),'number':c['id'],'title':str(c.get('name_zh') or c['id'])+' · '+str(c.get('name_en') or ''),'category':c.get('category_zh') or c.get('category') or '', 'description':c.get('quote_zh') or '', 'source':'yang0 / handraw-style','prompt':c.get('prompt_zh') or '', 'thumbnail':c.get('image') or ''}
                data.append(normalized(raw_color,'palette'))
            self._images=data
            self._stamp=id(raw)
        return self._images

    def _read_prompts(self):
        items=self.old_search._prompts()
        by_id={p['id']:p for p in self.store.list_prompts()}
        result=[]
        for e in items:
            e=dict(e)
            p=by_id.get(e.get('prompt_id'),{})
            e['favorite']=bool(p.get('favorite'))
            e['created_at']=p.get('created_at')
            e['category']=e.get('folder_path') or ''
            e['source']='personal'
            result.append(self._normalize(e,'prompt','prompt'))
        return result

    def _read_animation(self):
        if self.animation_root is None:raise FileNotFoundError('Animation not collected')
        pointer=self.animation_root/'active.json'
        if any(p.is_symlink() for p in [pointer,*pointer.parents]):raise ValueError('Unsafe animation pointer')
        active=json.loads(pointer.read_text());snapshot=active.get('snapshot_id','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',snapshot):raise ValueError('Invalid snapshot ID')
        path=self.animation_root/'snapshots'/snapshot/'catalog.json'
        if any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('Unsafe animation catalog')
        stamp=(snapshot,path.stat().st_mtime_ns,path.stat().st_size)
        if self._animation_cache is None or self._animation_cache[0]!=stamp:
            data=json.loads(path.read_text());items=[];ids={e['id'] for e in data['entries']};aliases=data.get('aliases',{})
            if any(not a.startswith('animation:') or a in ids or v not in ids or v in aliases for a,v in aliases.items()):raise ValueError('Alias map must be flat and non-conflicting')
            for raw in data['entries']:
                e=copy.deepcopy(raw)
                if not e['id'].startswith('animation:') or e.get('domain')!='animation' or e.get('collection')!='code' or e.get('kind') not in KINDS:raise ValueError('Invalid animation entry')
                e['prompt']=e.get('prompts',{}).get('original','');e.setdefault('thumbnail','');e.setdefault('thumbnail_url',e['thumbnail']);e.setdefault('tags',[]);e.setdefault('description','');e.setdefault('playable',any(m.get('availability')=='local' for m in e.get('media',[])));e['capabilities']={'copy_prompt':bool(e['prompt']),'save_prompt':bool(e['prompt']),'use_image_canvas':False}
                e['_search']=json.dumps({k:e.get(k) for k in ('title','source_title','description','features','category','tags','tech_tags','prompts','prompt_versions','author','direction_zh','direction_en')},ensure_ascii=False)
                items.append(e)
            self._animation_cache=(stamp,items,aliases,data.get('source_counts',{}))
        self.aliases=self._animation_cache[2]
        return self._animation_cache[1]

    def _all(self):
        sources={};items=[]
        for domain,read in [('image',self._read_images),('prompt',self._read_prompts)]:
            try:
                part=read();items.extend(part);sources[domain]={'available':True,'total':len(part)}
            except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as e:
                sources[domain]={'available':False,'total':0,'message':'图像归档暂不可用' if domain=='image' else '提示词库暂不可用'}
        try:
            part=self._read_animation();items.extend(part);sources['animation']={'available':True,'total':len(part),'repositories':self._animation_cache[3]}
        except FileNotFoundError:
            missing_active=self.animation_root is None or not (self.animation_root/'active.json').exists()
            self.aliases={};sources['animation']={'available':False,'total':0,'status':'not-collected' if missing_active else 'unavailable','message':'动画资料尚未收录' if missing_active else '动画归档暂不可用，收藏记录保留'}
        except (OSError,ValueError,KeyError,TypeError):
            self.aliases={};sources['animation']={'available':False,'total':0,'status':'unavailable','message':'动画归档暂不可用，收藏记录保留'}
        return items,sources

    def get_entry(self,entry_id):
        if not isinstance(entry_id,str) or len(entry_id)>400:raise KeyError('条目不存在')
        items,_=self._all()
        canonical=self.aliases.get(entry_id,entry_id)
        for e in items:
            if e['id']==canonical:
                result={k:copy.deepcopy(v) for k,v in e.items() if k!='_search'}
                if entry_id!=canonical:result.update(canonical_id=canonical,alias_id=entry_id)
                return result
        raise KeyError('条目不存在')

    def search(self,q='',domain='',collection='',kind='',category='',source_id='',offset=0,limit=20,prompt_folder_id=None,tech=''):
        q=str(q or '').strip()
        if len(q)>256 or domain not in ('','all',*DOMAINS) or kind not in ('','all',*KINDS) or collection not in ('','reference','personal','code','film') or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError('分类、长度或分页范围不正确')
        items,sources=self._all();words=q.casefold().split()
        matched=[e for e in items if all(w in e['_search'].casefold() for w in words) and (not source_id or source_id in e.get('source_ids',[e['source_id']])) and (not prompt_folder_id or e.get('folder_id')==prompt_folder_id)]
        categories=sorted({e.get('category') for e in matched if e.get('category') and domain in ('','all',e['domain']) and (not collection or e['collection']==collection)})
        techniques=sorted({t for e in matched if domain in ('','all',e['domain']) for t in e.get('tech_tags',[]) if t})
        if tech:matched=[e for e in matched if tech.casefold() in [t.casefold() for t in e.get('tech_tags',[])]]
        if category:matched=[e for e in matched if e.get('category')==category]
        counts={d:sum(e['domain']==d for e in matched) for d in DOMAINS}
        selected=[e for e in matched if domain in ('','all',e['domain']) and (not collection or e['collection']==collection)]
        counts.update({k:sum(e['kind']==k for e in selected) for k in KINDS});counts['all']=len(matched);counts['personal_main']=sum(e['id'].startswith('prompt:') for e in matched)
        selected=[e for e in selected if kind in ('','all',e['kind'])]
        if q:selected.sort(key=lambda e:(-sum(w in e['title'].casefold() for w in words),e['id']))
        total=len(selected)
        visible=[]
        for e in selected[offset:offset+limit]:
            row={k:copy.deepcopy(e[k]) for k in SUMMARY if k in e};row['prompt_excerpt']=e['prompt'][:120];visible.append(row)
        return {'items':visible,'total':total,'counts':counts,'categories':categories,'techniques':techniques,'sources':sources,'next_offset':offset+limit if offset+limit<total else None}
