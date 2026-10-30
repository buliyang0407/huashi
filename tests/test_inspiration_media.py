import importlib.util,http.client,json,tempfile,threading,unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

class InspirationMediaTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('huashi.inspiration_media'),'Streaming animation service is missing')
  from huashi.inspiration_media import InspirationMedia
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);snap=self.root/'snapshots/test-snapshot';(snap/'previews').mkdir(parents=True);(snap/'posters').mkdir();(snap/'previews/clip.mp4').write_bytes(b'0123456789');(snap/'previews/empty.mp4').write_bytes(b'');(snap/'posters/cover.webp').write_bytes(b'cover')
  (snap/'manifest.json').write_text(json.dumps({'snapshot_id':'test-snapshot','resources':[{'path':'previews/clip.mp4','bytes':10,'mime':'video/mp4'},{'path':'previews/empty.mp4','bytes':0,'mime':'video/mp4'},{'path':'posters/cover.webp','bytes':5,'mime':'image/webp'}]}));self.service=InspirationMedia(self.root)
  class H(BaseHTTPRequestHandler):
   def do_GET(s):self.service.handle(s)
   def do_HEAD(s):self.service.handle(s)
   def log_message(s,*args):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),H);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
 def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def get(self,path='previews/clip.mp4',range_=None,method='GET'):
  c=http.client.HTTPConnection(*self.server.server_address,timeout=4);c.request(method,'/inspiration-media/test-snapshot/'+path,headers={'Range':range_} if range_ else {});r=c.getresponse();res=(r.status,r.read(),dict(r.getheaders()));c.close();return res
 def test_full_get_and_head(self):
  r=self.get();self.assertEqual(r[:2],(200,b'0123456789'));self.assertEqual(r[2]['Accept-Ranges'],'bytes');self.assertEqual(self.get(method='HEAD')[:2],(200,b''));self.assertEqual(self.get('posters/cover.webp')[:2],(200,b'cover'))
 def test_single_ranges_suffix_open_and_head(self):
  for header,body,content in [('bytes=0-2',b'012','bytes 0-2/10'),('bytes=-3',b'789','bytes 7-9/10'),('bytes=6-',b'6789','bytes 6-9/10')]:
   r=self.get(range_=header);self.assertEqual(r[:2],(206,body));self.assertEqual(r[2]['Content-Range'],content)
  self.assertEqual(self.get(range_='bytes=0-2',method='HEAD')[:2],(206,b''))
 def test_invalid_and_multiple_ranges_are_consistent(self):
  for header in ['bytes=20-','bytes=8-2','bytes=-0','bytes=bad']:
   r=self.get(range_=header);self.assertEqual(r[0],416);self.assertEqual(r[2]['Content-Range'],'bytes */10')
  self.assertEqual(self.get(range_='bytes=0-1,5-6')[:2],(200,b'0123456789'))
 def test_empty_and_private_paths(self):
  self.assertEqual(self.get('previews/empty.mp4')[:2],(200,b''));self.assertEqual(self.get('previews/empty.mp4',range_='bytes=0-')[0],416)
  for path in ['../manifest.json','manifest.json','sources/a.md','previews/unknown.mp4','previews/%252e%252e/x','previews/%2e%2e/manifest.json','previews/clip.mp4/extra']:
   self.assertEqual(self.get(path)[0],404,path)
 def test_symlink_and_size_mismatch_refused(self):
  p=self.root/'snapshots/test-snapshot/previews/clip.mp4';p.unlink();p.symlink_to(self.root/'snapshots/test-snapshot/posters/cover.webp');self.assertEqual(self.get()[0],404);p.unlink();p.write_bytes(b'wrong length');self.assertEqual(self.get()[0],404)
