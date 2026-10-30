"""Serve an independent, migrated inspiration archive; never create its database."""
import json
import mimetypes
import re
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlsplit


class InspirationLibrary:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.site = self.root / 'library/site'
        self.db = self.root / 'user-data/favorites.sqlite3'
        self._catalog_cache = None
        self._schema_verified = False

    @staticmethod
    def matches(path):
        path = urlsplit(path).path
        return path == '/inspiration' or path.startswith('/inspiration/')

    def _send(self, h, body, status=200, mime='application/json; charset=utf-8', attachment=False):
        h.send_response(status)
        h.send_header('Content-Type', mime)
        h.send_header('Content-Length', str(len(body)))
        h.send_header('Cache-Control', 'no-store')
        h.send_header('X-Content-Type-Options', 'nosniff')
        if attachment:
            h.send_header('Content-Disposition', 'attachment; filename="image-inspiration-favorites.json"')
        h.end_headers()
        if h.command != 'HEAD':
            h.wfile.write(body)

    def _json(self, h, value, status=200, attachment=False):
        self._send(h, json.dumps(value, ensure_ascii=False).encode(), status, attachment=attachment)

    def _connect(self, writable=False):
        conn = sqlite3.connect(self.db.as_uri() + ('?mode=rw' if writable else '?mode=ro'), uri=True, timeout=0.3)
        try:
            columns = conn.execute('PRAGMA table_info(favorites)').fetchall()
            if [(c[1], c[2].upper(), c[3], c[5]) for c in columns] != [('id', 'TEXT', 0, 1), ('created_at', 'TEXT', 1, 0)]:
                raise sqlite3.DatabaseError('Favorites migration required')
            return conn
        except Exception:
            conn.close()
            raise

    def _catalog(self):
        path = self.site / 'library/catalog.json'
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._catalog_cache
        if cached is None or cached[0] != stamp:
            raw = path.read_bytes()
            cached = (stamp, raw, json.loads(raw))
            self._catalog_cache = cached
        return cached[1], cached[2]

    def _ready(self, read_favorites=True):
        raw, catalog = self._catalog()
        # Production is immutable after migration. Check existence every time,
        # schema once for static files; API operations always recheck schema.
        if not self.db.is_file():
            raise OSError('Favorites migration required')
        favorites = []
        if read_favorites or not self._schema_verified:
            conn = self._connect()
            try:
                if read_favorites:
                    favorites = [r[0] for r in conn.execute('SELECT id FROM favorites ORDER BY created_at DESC, id')]
                self._schema_verified = True
            finally:
                conn.close()
        return raw, catalog, favorites

    @staticmethod
    def _adapt(name, raw):
        value = raw.decode('utf-8')
        if name == 'index.html':
            # Keep archived bytes immutable; preserve legacy fragment parameters client-side.
            compatibility = '<script src="/inspiration-nav.js?v=20261015-inspiration-c-1"></script><script>if(window.HuashiInspirationNav){const target=HuashiInspirationNav.legacy(location.href);location.replace("/"+(target||"#inspiration/image"));}</script>'
            value = re.sub(r'(href|src)="/(?!/)', r'\1="/inspiration/', value)
            value = value.replace('</head>', compatibility + '</head>')
            value = value.replace('<div class="header-right">', '<div class="header-right"><a href="/">返回画室</a>')
            value = value.replace('</head>', '<style>#libraryPages{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:20px 0;font-size:13px}#libraryPages label{margin-right:auto}#libraryPages select,#libraryPages button{padding:7px 10px;border:1px solid #d7dce1;border-radius:6px;background:white;color:#263c49}</style></head>')
        elif name == 'app.js':
            value = "const asset = path => typeof path === 'string' && path.startsWith('/') && !path.startsWith('//') ? '/inspiration' + path : path;\n" + value
            value = value.replace('fetch(path,', 'fetch(asset(path),')
            for expr in ['e.thumbnail', 'e.referenceImage', 'c.image']:
                value = value.replace('esc('+expr+')', 'esc(asset('+expr+'))')
            value = value.replace('const image=e.image;', 'const image=asset(e.image);')
            value = value.replace('origin:location.origin}', "origin:location.origin+'/inspiration'}")
            value = InspirationLibrary._paginate_archive(value)
        return value.encode()

    @staticmethod
    def _paginate_archive(value):
        """Adapt the served legacy UI; the archived source/assets remain immutable."""
        value = value.replace('limit:48,', 'page:0,pageSize:20,')
        value = value.replace('items.slice(0,state.limit)', 'items.slice(state.page*state.pageSize,(state.page+1)*state.pageSize)')
        value = value.replace('const items=filtered(state.entries,state.route,state.favorites);', 'const items=filtered(state.entries,state.route,state.favorites);state.page=Math.min(state.page,Math.max(0,Math.ceil(items.length/state.pageSize)-1));')
        value = value.replace("$('more').hidden=items.length<=state.limit;", "$('more').hidden=true;")
        value = value.replace('renderBasket();}', 'renderBasket();renderLibraryPages(items.length);}', 1)
        value = value.replace('state.limit=48;', 'state.page=0;')
        value = value.replace("$('more').addEventListener('click',()=>{state.limit+=48;render();});", '')
        # Detail opening/closing must not reset the current result page.
        value = value.replace('function navigate(){state.route=parseRoute(location.hash);state.page=0;', 'function navigate(){const old=state.route;state.route=parseRoute(location.hash);if(old.view!==state.route.view||old.query!==state.route.query||old.category!==state.route.category)state.page=0;')
        return value + """
function renderLibraryPages(total){
 let target=$('libraryPages');if(!target){target=document.createElement('div');target.id='libraryPages';$('more').insertAdjacentElement('afterend',target);}
 const pages=Math.max(1,Math.ceil(total/state.pageSize));
 target.innerHTML=`<label>每页显示 <select data-page-size aria-label="每页显示数量">${[20,50,100].map(n=>`<option value="${n}" ${n===state.pageSize?'selected':''}>${n}</option>`).join('')}</select></label><span>共 ${total} 条 · ${state.page+1} / ${pages} 页</span><button data-library-prev ${!state.page?'disabled':''}>上一页</button><button data-library-next ${state.page+1>=pages?'disabled':''}>下一页</button>`;
 target.querySelector('select').onchange=e=>{state.pageSize=Number(e.target.value);state.page=0;render();};
 target.querySelector('[data-library-prev]').onclick=()=>{state.page--;render();};
 target.querySelector('[data-library-next]').onclick=()=>{state.page++;render();};
}
"""

    def _file(self, path):
        parts = path.split('/')
        if any(p in {'.', '..'} or p.startswith('.') for p in parts if p):
            return None
        if '\\' in path or '\x00' in path:
            return None
        legacy = self.root / 'snapshots/gpt-image2/2026-08-11-76fcd0e6/source/data'
        roots = []
        if path in {'/', '/index.html', '/app.js', '/model.mjs', '/styles.css', '/favicon.svg', '/library/catalog.json'}:
            roots = [(self.site, 'index.html' if path == '/' else path[1:])]
        elif path.startswith('/thumbs/'):
            roots = [(self.site / 'thumbs', path[8:])]
        elif path.startswith('/handdraw/'):
            roots = [(self.root/'library/resources/handraw-style/2026-10-02-c16664cb/source', path[10:])]
        elif path.startswith('/gpt-image2/'):
            roots = [(self.root/'library/resources/gpt-image2', path[12:]), (self.root/'snapshots/gpt-image2', path[12:])]
        elif path.startswith('/images/'):
            roots = [(legacy/'images', path[8:])]
        elif path.startswith('/data/'):
            roots = [(legacy, path[6:])]
        allowed = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.svg', '.avif'}
        for root, relative in roots:
            target = root / relative
            if path not in {'/', '/index.html', '/app.js', '/model.mjs', '/styles.css', '/favicon.svg', '/library/catalog.json'}:
                if target.suffix.lower() not in allowed and not (path.startswith('/data/') and relative == 'cases.json'):
                    continue
            if any(p.is_symlink() for p in [root, target, *target.parents] if p.is_relative_to(self.root)):
                continue
            resolved = target.resolve()
            if resolved.is_relative_to(root.resolve()) and resolved.is_file():
                return resolved
        return None

    def handle_get(self, h):
        if not self.matches(h.path):
            return False
        if urlsplit(h.path).path == '/inspiration':
            h.send_response(308)
            h.send_header('Location', '/inspiration/')
            h.send_header('Content-Length', '0')
            h.end_headers()
            return True
        path = unquote(urlsplit(h.path).path)[len('/inspiration'):] or '/'
        target = self._file(path)
        if path not in {'/api/library', '/api/favorites', '/api/favorites/export'} and target is None and path not in {'/', '/index.html', '/app.js', '/model.mjs', '/styles.css', '/favicon.svg', '/library/catalog.json'}:
            self._json(h, {'error': '资源不存在'}, 404)
            return True
        try:
            raw, catalog, favorites = self._ready(read_favorites=path.startswith('/api/favorites'))
            if path == '/api/library':
                self._send(h, raw)
            elif path == '/api/favorites':
                self._json(h, {'favorites': favorites})
            elif path == '/api/favorites/export':
                self._json(h, {'version': 1, 'library': 'image-inspiration', 'favorites': favorites, 'sources': catalog['sources']}, attachment=True)
            else:
                if target is None:
                    raise OSError('Library migration required')
                payload = target.read_bytes()
                if path in {'/', '/index.html', '/app.js'}:
                    payload = self._adapt(target.name, payload)
                mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                self._send(h, payload, mime=mime)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            self._json(h, {'error': '灵感库尚未完成迁移或暂时不可用'}, 503)
        return True

    def read_favorites(self):
        conn = self._connect()
        try:
            return [{'id': r[0], 'created_at': r[1]} for r in conn.execute('SELECT id, created_at FROM favorites ORDER BY created_at DESC, id')]
        finally:
            conn.close()

    def set_favorite(self, entry_id, favorite):
        if not isinstance(entry_id, str) or type(favorite) is not bool:
            raise ValueError('收藏条目或状态不正确')
        _, catalog = self._catalog()
        if entry_id not in {e['id'] for e in catalog['entries']}:
            raise ValueError('收藏条目不存在')
        conn = self._connect(writable=True)
        try:
            with conn:
                if favorite:
                    conn.execute('INSERT OR IGNORE INTO favorites (id) VALUES (?)', (entry_id,))
                else:
                    conn.execute('DELETE FROM favorites WHERE id=?', (entry_id,))
            return [r[0] for r in conn.execute('SELECT id FROM favorites ORDER BY created_at DESC, id')]
        finally:
            conn.close()

    def handle_put(self, h):
        if not self.matches(h.path):
            return False
        if urlsplit(h.path).path != '/inspiration/api/favorites':
            self._json(h, {'error': '接口不存在'}, 404)
            return True
        origin = h.headers.get('Origin')
        if origin:
            parsed = urlsplit(origin)
            expected_scheme = 'https' if getattr(h.server, 'inspiration_https', False) else 'http'
            if parsed.scheme != expected_scheme or parsed.netloc != h.headers.get('Host') or parsed.path or parsed.query or parsed.fragment:
                self._json(h, {'error': '请从本图库操作收藏'}, 403)
                return True
        if h.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            self._json(h, {'error': '请求格式不正确'}, 415)
            return True
        try:
            length = int(h.headers.get('Content-Length', '0'))
            if not 0 < length < 4096 or h.headers.get('Transfer-Encoding'):
                raise ValueError()
            previous_timeout = h.connection.gettimeout()
            try:
                h.connection.settimeout(2)
                body = json.loads(h.rfile.read(length))
            finally:
                h.connection.settimeout(previous_timeout)
            if not isinstance(body, dict) or not isinstance(body.get('id'), str) or not isinstance(body.get('favorite'), bool):
                raise ValueError()
        except (ValueError, TypeError, TimeoutError, OSError):
            self._json(h, {'error': '收藏条目或状态不正确'}, 400)
            return True
        try:
            _, catalog, _ = self._ready()
            if body['id'] not in {e['id'] for e in catalog['entries']}:
                self._json(h, {'error': '收藏条目不存在'}, 400)
                return True
            favorites = self.set_favorite(body['id'], body['favorite'])
            self._json(h, {'id': body['id'], 'favorite': body['favorite'], 'favorites': favorites})
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            self._json(h, {'error': '收藏暂时不可用，请稍后重试'}, 503)
        return True
