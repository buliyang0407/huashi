import importlib.util
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile,threading,unittest

class AnimationDownloadTests(unittest.TestCase):
 def setUp(self):
  self.assertIsNotNone(importlib.util.find_spec('huashi.animation_ingest'),'Bounded media downloader is missing')
  from huashi.animation_ingest import MediaDownloader,inspect_asset
  self.Downloader=MediaDownloader;self.inspect=inspect_asset;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  class H(BaseHTTPRequestHandler):
   def do_HEAD(s):s.send_response(405);s.end_headers()
   def do_GET(s):
    raw=b'abcdefghijklmnopqrst';range_=s.headers.get('Range')
    s.send_response(206 if range_ else 200);s.send_header('Content-Type','video/mp4')
    if range_:s.send_header('Content-Range','bytes 0-0/20');raw=raw[:1]
    s.send_header('Content-Length',str(len(raw)));s.end_headers();s.wfile.write(raw)
   def log_message(s,*a):pass
  self.server=ThreadingHTTPServer(('127.0.0.1',0),H);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop);self.url='http://127.0.0.1:'+str(self.server.server_port)+'/actual.mp4'
 def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def test_head_failure_range_fallback_discovers_total(self):
  d=self.Downloader(self.root,100);m=d.metadata(self.url);self.assertEqual(m['bytes'],20);self.assertEqual(m['method'],'range')
 def test_atomic_download_length_hash_and_complete_resume(self):
  d=self.Downloader(self.root,100);p=self.root/'clip.mp4';r=d.fetch(self.url,p,expected=20);self.assertEqual(p.read_bytes(),b'abcdefghijklmnopqrst');self.assertFalse(Path(str(p)+'.part').exists());self.assertEqual(d.fetch(self.url,p,expected=20,known_sha=r['sha256'])['status'],'verified-existing')
 def test_budget_failure_leaves_no_published_file(self):
  d=self.Downloader(self.root,10);p=self.root/'clip.mp4'
  with self.assertRaises(ValueError):d.fetch(self.url,p,expected=20)
  self.assertFalse(p.exists());self.assertFalse(Path(str(p)+'.part').exists())
 def test_wrong_length_rejected_and_bad_image_never_published(self):
  d=self.Downloader(self.root,100);p=self.root/'clip.mp4'
  with self.assertRaises(ValueError):d.fetch(self.url,p,expected=21)
  bad=self.root/'bad.webp';bad.write_bytes(b'<html>error</html>')
  with self.assertRaises(ValueError):self.inspect(bad,'poster')

 def test_active_snapshot_cannot_be_modified_by_downloader(self):
  import json
  from huashi.animation_ingest import fetch_media
  animation=self.root/'animation';snap=animation/'snapshots/one';snap.mkdir(parents=True)
  (animation/'active.json').write_text(json.dumps({'snapshot_id':'one'}));(snap/'manifest.json').write_text(json.dumps({'snapshot_id':'one','resources':[],'source_files':[]}));(snap/'catalog.json').write_text(json.dumps({'entries':[]}));(snap/'media-plan.json').write_text(json.dumps({'assets':[],'known_video_bytes':0}))
  before=(snap/'manifest.json').read_bytes()
  with self.assertRaises(FileExistsError):fetch_media(snap)
  self.assertEqual(before,(snap/'manifest.json').read_bytes())
