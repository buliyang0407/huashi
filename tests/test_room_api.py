"""HTTP acceptance on temporary data only; never calls either provider."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from huashi.server import make_handler, MissingRunningHubClient
from huashi.service import HuashiService
from huashi.storage import HuashiStore


class RoomApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = HuashiStore(self.root / 'data/db.sqlite')
        self.store.initialize()
        self.store.save_prompt({'title':'礼服', 'content':'a dress'})
        site = self.root / 'inspiration/library/site/library'
        site.mkdir(parents=True)
        (site/'catalog.json').write_text(json.dumps({'entries':[{'id':'case:1','kind':'case','title':'礼服案例','prompt':'dress case'}]}))
        base = make_handler(HuashiService(self.root/'data', self.store, MissingRunningHubClient()), self.root/'web', self.root/'data')
        class Handler(base):
            def log_message(self, *_): pass
        self.server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def req(self, path, method='GET', data=None):
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        conn.request(method,path,None if data is None else json.dumps(data),{'Content-Type':'application/json'})
        response=conn.getresponse();body=json.loads(response.read());status=response.status;conn.close()
        return status,body

    def test_search_counts_and_invalid_filters_over_http(self):
        before=self.store.db_path.read_bytes()
        status, result=self.req('/api/inspiration/search?q=%E7%A4%BC%E6%9C%8D')
        self.assertEqual(status,200);self.assertEqual(result['counts']['all'],2)
        self.assertEqual(before,self.store.db_path.read_bytes())
        for query in ['kind=bad','offset=-1','limit=1000','offset=oops']:
            self.assertEqual(self.req('/api/inspiration/search?'+query)[0],400)

    def test_batch_preview_commit_and_stale_repeat_over_http(self):
        status, body=self.req('/api/albums','POST',{'name':'待整理'})
        self.assertEqual(status,201)
        item=self.store.save_album_upload('works','albums/test.png','测试素材')
        moves=[{'item_id':item['id'],'from_folder_id':'works','to_folder_id':body['folder']['id']}]
        self.assertEqual(self.req('/api/albums/moves/preview','POST',{'moves':moves})[0],200)
        self.assertEqual(self.store.get_album_item(item['id'])['folder_id'],'works')
        status, result=self.req('/api/albums/moves/apply','POST',{'moves':moves})
        self.assertEqual(status,200)
        self.assertTrue((self.root/'data/backups'/result['receipt']).exists())
        self.assertEqual(self.req('/api/albums/moves/apply','POST',{'moves':moves})[0],400)

    def test_receipt_write_failure_returns_error_without_moving(self):
        from unittest.mock import patch
        folder=self.store.create_album_folder('待整理')
        item=self.store.save_album_upload('works','albums/test.png','测试素材')
        moves=[{'item_id':item['id'],'from_folder_id':'works','to_folder_id':folder['id']}]
        with patch('huashi.album_organizer.AlbumOrganizer._write',side_effect=OSError('disk full')):
            self.assertEqual(self.req('/api/albums/moves/apply','POST',{'moves':moves})[0],503)
        self.assertEqual(self.store.get_album_item(item['id'])['folder_id'],'works')

    def test_invalid_json_shape_is_a_client_error(self):
        for payload in [[], {'moves':[]}, {'moves':[{}]}]:
            self.assertEqual(self.req('/api/albums/moves/apply','POST',payload)[0],400)

    def upload(self, folder_id=None):
        boundary='huashi-upload-test'
        chunks=[]
        if folder_id is not None:
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="folder_id"\r\n\r\n{folder_id}\r\n'.encode())
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="sample.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+b'local-test-image'+f'\r\n--{boundary}--\r\n'.encode())
        conn=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        conn.request('POST','/api/albums/upload',b''.join(chunks),{'Content-Type':f'multipart/form-data; boundary={boundary}'})
        response=conn.getresponse();body=json.loads(response.read());status=response.status;conn.close()
        return status,body

    def test_upload_without_category_uses_inbox_but_explicit_works_stays(self):
        status,body=self.upload()
        self.assertEqual(status,201)
        self.assertEqual(self.store.get_album_folder(body['item']['folder_id'])['name'],'待整理')
        status,body=self.upload('works')
        self.assertEqual(status,201);self.assertEqual(body['item']['folder_id'],'works')

    def test_bad_upload_destination_is_a_client_error_without_orphan(self):
        before=set((self.root/'data').rglob('*.png'))
        self.assertEqual(self.upload('missing')[0],400)
        self.assertEqual(before,set((self.root/'data').rglob('*.png')))

    def test_retired_rewrite_and_translation_never_dispatch_to_models(self):
        from unittest.mock import patch
        for endpoint, method in [('rewrite', 'rewrite_prompt_stream'), ('translate', 'translate_prompt_stream')]:
            with self.subTest(endpoint=endpoint), patch.object(HuashiService, method, side_effect=AssertionError('Retired feature called a model')):
                status, body = self.req('/api/prompts/'+endpoint, 'POST', {})
                self.assertEqual(status, 410)
                self.assertIn('下线', body['error'])
