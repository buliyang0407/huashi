import http.client
from contextlib import closing
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from huashi.inspiration import InspirationLibrary


class InspirationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        site = self.root / 'library/site'
        site.mkdir(parents=True)
        fixture = {
            'index.html': '<div class="header-right"><a href="/api/favorites/export">导出</a></div><script src="/app.js"></script><a href="https://github.com/source">来源</a>',
            'app.js': "fetch(path,{cache:'no-store'});esc(e.thumbnail);esc(e.referenceImage);esc(c.image);const image=e.image;makeRequest({origin:location.origin});",
            'model.mjs': 'export const kindNames = {};',
            'styles.css': 'body {color: black}', 'favicon.svg': '<svg/>',
        }
        for name, text in fixture.items():
            (site / name).write_text(text)
        self.raw = b'{ "entries": [{"id":"case:1"}], "colors": [], "sources": [] }\n'
        for path, data in {'library/site/library/catalog.json':self.raw, 'library/site/thumbs/a.webp':b'thumb', 'library/resources/handraw-style/2026-10-02-c16664cb/source/images/a.webp':b'hand', 'library/resources/handraw-style/2026-10-02-c16664cb/source/images/colors/C-01.webp':b'color', 'library/resources/handraw-style/2026-10-02-c16664cb/source/images/layouts/ip/IP-013.webp':b'layout', 'library/resources/handraw-style/2026-10-02-c16664cb/source/images/styles/ref.webp':b'reference', 'library/resources/gpt-image2/new/source/data/images/a.jpg':b'new', 'snapshots/gpt-image2/2026-08-11-76fcd0e6/source/data/images/a.jpg':b'old', 'snapshots/gpt-image2/2026-08-11-76fcd0e6/source/data/cases.json':b'[]'}.items():
            p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.db=self.root/'user-data/favorites.sqlite3';self.db.parent.mkdir()
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('CREATE TABLE favorites (id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)');c.commit()
        self.source_db=self.root/'source.sqlite3';shutil.copyfile(self.db,self.source_db);self.source_bytes=self.source_db.read_bytes()
        self.start()

    def start(self):
        library=InspirationLibrary(self.root)
        class Handler(BaseHTTPRequestHandler):
            def do_GET(s): library.handle_get(s)
            def do_HEAD(s): library.handle_get(s)
            def do_PUT(s): library.handle_put(s)
            def log_message(s,*args): pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def tearDown(self): self.stop();self.tmp.cleanup()

    def req(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.request(method,path,body,headers or {});r=c.getresponse();result=(r.status,r.read(),dict(r.getheaders()));c.close();return result

    def test_resources_and_adapter(self):
        for path,data in {'/api/library':self.raw,'/library/catalog.json':self.raw,'/thumbs/a.webp':b'thumb','/handdraw/images/a.webp':b'hand','/handdraw/images/colors/C-01.webp':b'color','/handdraw/images/layouts/ip/IP-013.webp':b'layout','/handdraw/images/styles/ref.webp':b'reference','/gpt-image2/new/source/data/images/a.jpg':b'new','/gpt-image2/2026-08-11-76fcd0e6/source/data/images/a.jpg':b'old','/images/a.jpg':b'old','/data/cases.json':b'[]'}.items():
            self.assertEqual(self.req('/inspiration'+path)[:2],(200,data))
            self.assertEqual(self.req('/inspiration'+path,'HEAD')[:2],(200,b''))
        self.assertEqual(self.req('/inspiration')[2]['Location'],'/inspiration/')
        html=self.req('/inspiration/')[1].decode();self.assertIn('href="/"',html);self.assertIn('/inspiration/app.js',html);self.assertIn('https://github.com/',html)
        js=self.req('/inspiration/app.js')[1].decode()
        for expr in ['e.thumbnail','e.referenceImage','c.image']:
            self.assertIn('asset('+expr+')',js)
        self.assertIn("origin:location.origin+'/inspiration'",js)
        self.assertIn('asset(path)',js)
        self.assertEqual(self.req('/inspiration/model.mjs')[0],200)
        self.assertEqual(self.req('/inspiration/styles.css')[0],200)
        self.assertEqual(self.req('/inspiration/favicon.svg')[0],200)

    def test_lifecycle_restart_export_source_unchanged(self):
        for chosen in [True,True]:
            r=self.req('/inspiration/api/favorites','PUT',json.dumps({'id':'case:1','favorite':chosen}),{'Content-Type':'application/json'})
            self.assertEqual(r[0],200);self.assertEqual(json.loads(r[1])['favorites'],['case:1'])
        self.stop();self.start()
        self.assertEqual(json.loads(self.req('/inspiration/api/favorites/export')[1]),{'version':1,'library':'image-inspiration','favorites':['case:1'],'sources':[]})
        self.assertEqual(self.source_db.read_bytes(),self.source_bytes)
        self.assertEqual(self.req('/inspiration/api/favorites','PUT',json.dumps({'id':'case:1','favorite':False}),{'Content-Type':'application/json'})[0],200)
        self.assertEqual(json.loads(self.req('/inspiration/api/favorites')[1]),{'favorites':[]})

    def test_invalid_and_private_paths(self):
        for value in [[],{}, {'id':[], 'favorite':True},{'id':'unknown','favorite':True},{'id':'case:1','favorite':1}]:
            self.assertEqual(self.req('/inspiration/api/favorites','PUT',json.dumps(value),{'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.req('/inspiration/api/favorites','PUT','{}',{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.req('/inspiration/api/favorites','PUT','{}',{'Content-Type':'application/json','Origin':'https://foreign.test'})[0],403)
        self.assertEqual(self.req('/inspiration/api/favorites','PUT','x'*4096,{'Content-Type':'application/json'})[0],400)
        for path in ['/../user-data/favorites.sqlite3','/%2e%2e/server.py','/handdraw/.git/config','/gpt-image2/new/source/server.py','/thumbs/','/server.py','/library/config.json','/api/nope']:
            self.assertEqual(self.req('/inspiration'+path)[0],404,path)
        (self.root/'library/site/thumbs/leak.webp').symlink_to(self.source_db)
        self.assertEqual(self.req('/inspiration/thumbs/leak.webp')[0],404)

    def test_fail_closed_missing_or_bad_database(self):
        self.db.unlink()
        self.assertEqual(self.req('/inspiration/api/favorites')[0],503)
        self.assertFalse(self.db.exists())
        self.assertEqual(self.req('/inspiration/')[0],503)
        with closing(sqlite3.connect(self.db)) as c:c.execute('CREATE TABLE wrong (id TEXT)');c.commit()
        self.assertEqual(self.req('/inspiration/api/favorites')[0],503)

    def test_busy_database_clean_error(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('BEGIN EXCLUSIVE')
            self.assertEqual(self.req('/inspiration/api/favorites')[0],503)

    def test_static_cache_does_not_read_favorites_when_locked(self):
        self.assertEqual(self.req('/inspiration/thumbs/a.webp')[0],200)
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('BEGIN EXCLUSIVE')
            self.assertEqual(self.req('/inspiration/thumbs/a.webp')[:2],(200,b'thumb'))

    def test_missing_library_does_not_break_huashi(self):
        from huashi.server import make_handler
        web=self.root/'huashi/web';web.mkdir(parents=True);(web/'index.html').write_text('Huashi remains available')
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(object(),web,self.root/'data'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            c=http.client.HTTPConnection(*server.server_address)
            c.request('GET','/');r=c.getresponse();self.assertEqual(r.status,200);self.assertIn(b'Huashi',r.read())
            c.request('GET','/inspiration/');r=c.getresponse();self.assertEqual(r.status,503);r.read();c.close()
        finally:
            server.shutdown();server.server_close();thread.join()
