import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from huashi.server import make_handler,MissingRunningHubClient
from huashi.storage import HuashiStore
from huashi.service import HuashiService

class InspirationV2ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=HuashiStore(self.root/'data/db.sqlite');self.store.initialize()
        site=self.root/'inspiration/library/site/library';site.mkdir(parents=True);(site/'catalog.json').write_text(json.dumps({'entries':[{'id':'case:1','kind':'case','title':'测试','prompt':'original'}],'colors':[],'sources':[]}))
        db=self.root/'inspiration/user-data/favorites.sqlite3';db.parent.mkdir()
        with sqlite3.connect(db) as c:c.execute('CREATE TABLE favorites(id TEXT PRIMARY KEY,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        base=make_handler(HuashiService(self.root/'data',self.store,MissingRunningHubClient()),self.root/'web',self.root/'data')
        class Handler(base):
            def log_message(self,*args):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,path,method='GET',payload=None,headers=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5);c.request(method,path,json.dumps(payload) if payload is not None else None,headers or {'Content-Type':'application/json'});r=c.getresponse();body=r.read();status=r.status;c.close();return status,json.loads(body)
    def test_list_detail_validation_and_read_only(self):
        before=self.store.db_path.read_bytes();s,r=self.request('/api/inspiration/v2/catalog?domain=image');self.assertEqual(s,200);self.assertEqual(r['total'],1);self.assertNotIn('prompts',r['items'][0]);self.assertEqual(self.request('/api/inspiration/v2/entry?id=case%3A1')[1]['prompts']['original'],'original');self.assertEqual(before,self.store.db_path.read_bytes())
        for q in ['limit=101','offset=-1','domain=bad','offset=nope']:self.assertEqual(self.request('/api/inspiration/v2/catalog?'+q)[0],400)
        self.assertEqual(self.request('/api/inspiration/v2/entry?id=missing')[0],404)
    def test_shared_favorites_old_export_and_new_export(self):
        self.assertEqual(self.request('/api/inspiration/v2/favorites','PUT',{'id':'case:1','favorite':True})[0],200)
        self.assertEqual(self.request('/inspiration/api/favorites')[1]['favorites'],['case:1'])
        self.assertEqual(self.request('/inspiration/api/favorites/export')[1]['version'],1)
        self.assertEqual(self.request('/api/inspiration/v2/favorites/export')[1]['version'],2)
    def test_rejects_invalid_body_and_foreign_origin(self):
        for body in [[],{}, {'id':'case:1','favorite':1}]:self.assertEqual(self.request('/api/inspiration/v2/favorites','PUT',body)[0],400)
        self.assertEqual(self.request('/api/inspiration/v2/favorites','PUT',{'id':'case:1','favorite':True},{'Content-Type':'application/json','Origin':'https://foreign.example'})[0],403)
