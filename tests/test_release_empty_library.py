import gzip,json,tempfile,threading,unittest,http.client
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from huashi.server import create_service,make_handler

class EmptyLibraryTests(unittest.TestCase):
 def test_clean_start_and_missing_material_index_return_empty_library(self):
  with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{},clear=True):
   root=Path(tmp);web=root/'web';web.mkdir();(web/'index.html').write_text('<html>studio</html>')
   service=create_service(root/'data');server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(service,web,root/'data',inspiration_root=root/'inspiration'))
   thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   try:
    for url in ['/portrait-materials.json','/portrait-materials.json.gz']:
     c=http.client.HTTPConnection(*server.server_address,timeout=3);c.request('GET',url);r=c.getresponse();body=r.read();self.assertEqual(r.status,200)
     if url.endswith('.gz'):body=gzip.decompress(body)
     self.assertEqual(json.loads(body),[]);c.close()
    self.assertFalse((web/'portrait-materials.json').exists())
   finally:server.shutdown();server.server_close();thread.join()
