import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from huashi.storage import HuashiStore
from huashi.service import HuashiService
from huashi.server import make_handler

class QueueApiTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);store=HuashiStore(self.root/'db.sqlite');store.initialize()
        self.service=HuashiService(self.root,store,object());self.service.task_queue.set_paused(True)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service,Path('web').resolve(),self.root))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.service.task_queue.stop();self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,method='GET'):
        with urlopen(Request(self.base+path,method=method),timeout=3) as f:return json.load(f)
    def test_cancel_preserves_task_and_unknown_retry_returns_conflict(self):
        a=self.service.create_task_from_form('runpod-noctq-v4-text-to-image',{'input_prompt':'retained'}, {},start_background=False)
        snapshot=self.request('/api/runpod/queue');self.assertTrue(snapshot['paused']);self.assertEqual(snapshot['pending'][0]['id'],a['id'])
        after=self.request('/api/runpod/queue/'+a['id']+'/cancel','POST');self.assertEqual(after['pending'],[])
        self.assertEqual(self.request('/api/tasks/'+a['id'])['task']['status'],'cancelled')
        self.service.store.update_task(a['id'],status='failed',remote_submission_state='unknown')
        with self.assertRaises(HTTPError) as caught:self.request('/api/tasks/'+a['id']+'/retry','POST')
        self.assertEqual(caught.exception.code,409);self.assertEqual(len(self.service.store.list_tasks()),1)
    def test_invalid_cancel_and_delete_active_are_conflicts(self):
        a=self.service.create_task_from_form('runpod-noctq-v4-text-to-image',{'input_prompt':'pending'}, {},start_background=False)
        with self.assertRaises(HTTPError) as caught:self.request('/api/tasks/'+a['id'],'DELETE')
        self.assertEqual(caught.exception.code,409)
        with self.assertRaises(HTTPError) as caught:self.request('/api/runpod/queue/missing/cancel','POST')
        self.assertEqual(caught.exception.code,409)
    def test_pause_endpoint_persists(self):
        self.assertTrue(self.request('/api/runpod/queue/pause','POST')['paused'])
        with self.service.store.connect() as c:self.assertEqual(c.execute('select paused from runpod_queue_control').fetchone()[0],1)
