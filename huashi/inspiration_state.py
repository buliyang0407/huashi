"""Bridge authoritative image favorites and explicitly initialized new inspiration state."""
from __future__ import annotations
import sqlite3
from pathlib import Path


def initialize_state(path):
    path=Path(path).absolute()
    if path.name!='inspiration-state.sqlite3' or any(p.is_symlink() for p in [path,*path.parents]):
        raise ValueError('只允许初始化独立的 inspiration-state.sqlite3，不能使用符号链接')
    path.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(path)
    try:
        with conn:
            conn.execute('CREATE TABLE IF NOT EXISTS favorites (entry_id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('CREATE TABLE IF NOT EXISTS aliases (alias_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            conn.execute("INSERT OR IGNORE INTO schema_meta VALUES ('version','1')")
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise sqlite3.DatabaseError('状态库校验失败')
    finally:conn.close()
    path.chmod(0o600)


class InspirationState:
    def __init__(self,image_library,prompt_store,state_db_path,catalog):
        self.library=image_library
        self.store=prompt_store
        self.path=Path(state_db_path).absolute()
        self.catalog=catalog

    def _connect(self,writable=False):
        if not self.path.is_file() or self.path.is_symlink():raise OSError('收藏状态尚未初始化')
        c=sqlite3.connect(self.path.as_uri()+('?mode=rw' if writable else '?mode=ro'),uri=True,timeout=1)
        try:
            columns=[r[1] for r in c.execute('PRAGMA table_info(favorites)')]
            if columns!=['entry_id','created_at']:raise sqlite3.DatabaseError('收藏状态结构不正确')
            return c
        except Exception:c.close();raise

    def list_favorites(self):
        sources={};records=[];common=[]
        try:
            records.extend({**r,'domain':'image','storage':'image'} for r in self.library.read_favorites())
            sources['image']={'available':True}
        except (OSError,sqlite3.Error,ValueError):sources['image']={'available':False,'message':'图像收藏暂不可用'}
        try:
            c=self._connect()
            try:records.extend({'id':r[0],'created_at':r[1],'storage':'additional'} for r in c.execute('SELECT entry_id,created_at FROM favorites ORDER BY created_at DESC,entry_id'))
            finally:c.close()
            sources['additional']={'available':True}
        except (OSError,sqlite3.Error):sources['additional']={'available':False,'message':'配色与动画收藏状态尚未初始化'}
        items=[]
        available,_=self.catalog._all()
        by_id={e['id']:e for e in available}
        for r in records:
            try:
                e=by_id[self.catalog.aliases.get(r['id'],r['id'])];row={k:e.get(k) for k in ('id','domain','collection','kind','title','description','category','thumbnail','source','prompt_status','capabilities','duration_seconds','tech_tags','playable','source_ids','features','viewing_links','cover_status','editorial','source_title')};row.update(created_at=r['created_at'],available=True)
            except (KeyError,OSError,ValueError,sqlite3.Error):row={**r,'title':r['id'],'available':False,'description':'来源暂不可用，收藏记录已保留','kind':'case','thumbnail':''}
            items.append(row)
        try:
            common=[{'id':'prompt:'+p['id'],'title':p['title'],'prompt_id':p['id'],'folder_path':p.get('folder_path') or ''} for p in self.store.list_prompts() if p.get('favorite')]
            sources['prompts']={'available':True}
        except (OSError,sqlite3.Error,ValueError):sources['prompts']={'available':False,'message':'常用提示词暂不可用'}
        unique={}
        for row in items:
            prior=unique.get(row['id'])
            if prior is None or (row.get('created_at') or '')<(prior.get('created_at') or ''):unique[row['id']]=row
        items=list(unique.values())
        items.sort(key=lambda e:(e.get('created_at') or '',e['id']),reverse=True)
        return {'items':items,'common_prompts':common,'sources':sources,'total':len(items)}

    def set_favorite(self,entry_id,favorite):
        if not isinstance(entry_id,str) or type(favorite) is not bool:raise ValueError('收藏条目或状态不正确')
        e=self.catalog.get_entry(entry_id)
        entry_id=e['id']
        if e['domain']=='prompt':raise ValueError('常用提示词请在原提示词管理中设置')
        if e['domain']=='image' and e['kind']!='palette':self.library.set_favorite(entry_id,favorite)
        else:
            c=self._connect(True)
            try:
                with c:
                    if favorite:c.execute('INSERT OR IGNORE INTO favorites (entry_id) VALUES (?)',(entry_id,))
                    else:
                        for id_ in [entry_id,*[a for a,v in self.catalog.aliases.items() if v==entry_id]]:c.execute('DELETE FROM favorites WHERE entry_id=?',(id_,))
            finally:c.close()
        return {'id':entry_id,'favorite':favorite,**self.list_favorites()}

    def export_favorites(self):
        return {'version':2,'library':'huashi-inspiration',**self.list_favorites()}
