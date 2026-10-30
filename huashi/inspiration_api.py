"""HTTP boundary for the v2 inspiration browser, separate from legacy canvas search."""
import json
import sqlite3
from urllib.parse import urlsplit,parse_qs
from .inspiration_catalog import InspirationCatalog
from .inspiration_state import InspirationState

class InspirationAPI:
    def __init__(self,library,store):
        self.library=library
        self.catalog=InspirationCatalog(library,store,library.root/'animation')
        self.state=InspirationState(library,store,library.root/'user-data/inspiration-state.sqlite3',self.catalog)

    def handle_get(self,h):
        path=urlsplit(h.path).path
        if not path.startswith('/api/inspiration/v2/'):return False
        q={k:v[0] for k,v in parse_qs(urlsplit(h.path).query,keep_blank_values=True).items()}
        try:
            if path=='/api/inspiration/v2/catalog':
                filters={k:q.get(k,'') for k in ('q','domain','collection','kind','category','source_id','tech')}
                filters.update(offset=int(q.get('offset') or 0),limit=int(q.get('limit') or 20),prompt_folder_id=q.get('prompt_folder_id') or None)
                h.json_response(self.catalog.search(**filters))
            elif path=='/api/inspiration/v2/entry':h.json_response(self.catalog.get_entry(q.get('id')))
            elif path=='/api/inspiration/v2/favorites':h.json_response(self.state.list_favorites())
            elif path=='/api/inspiration/v2/favorites/export':h.json_download_response(self.state.export_favorites(),'huashi-inspiration-favorites.json')
            else:h.error_response(404,'接口不存在')
        except KeyError as e:h.error_response(404,str(e))
        except (ValueError,TypeError) as e:h.error_response(400,str(e))
        except (OSError,sqlite3.Error) as e:h.error_response(503,'灵感资料暂不可用，请稍后重试')
        return True

    def handle_put(self,h):
        if urlsplit(h.path).path!='/api/inspiration/v2/favorites':return False
        origin=h.headers.get('Origin')
        if origin:
            u=urlsplit(origin);scheme='https' if getattr(h.server,'inspiration_https',False) else 'http'
            if u.scheme!=scheme or u.netloc!=h.headers.get('Host') or u.path or u.query or u.fragment:
                h.error_response(403,'请从本画室操作收藏');return True
        if h.headers.get('Content-Type','').split(';')[0].strip()!='application/json':h.error_response(415,'请求格式不正确');return True
        try:
            length=int(h.headers.get('Content-Length','0'))
            if not 0<length<4096 or h.headers.get('Transfer-Encoding'):raise ValueError('请求大小不正确')
            timeout=h.connection.gettimeout()
            try:h.connection.settimeout(2);body=json.loads(h.rfile.read(length))
            finally:h.connection.settimeout(timeout)
            if not isinstance(body,dict) or not isinstance(body.get('id'),str) or type(body.get('favorite')) is not bool:raise ValueError('收藏条目或状态不正确')
            h.json_response(self.state.set_favorite(body['id'],body['favorite']))
        except KeyError as e:h.error_response(404,str(e))
        except (ValueError,TypeError) as e:h.error_response(400,str(e))
        except (OSError,TimeoutError,sqlite3.Error):h.error_response(503,'收藏暂不可用，请检查状态库初始化')
        return True
