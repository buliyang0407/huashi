import io,json,tarfile,tempfile,unittest
from pathlib import Path
from PIL import Image

class MaterialBuildToolsTests(unittest.TestCase):
 def test_empty_source_has_no_dependency_on_private_costume_catalog(self):
  from scripts.build_portrait_bag_catalog import build_catalog
  with tempfile.TemporaryDirectory() as tmp:self.assertEqual(build_catalog(Path(tmp)),[])
 def test_library_index_and_thumbnails_preserve_originals(self):
  from scripts.build_portrait_bag_catalog import build_catalog
  from scripts.build_portrait_bag_thumbnails import write_bundle
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'pose'/'站姿'/'示例.png';p.parent.mkdir(parents=True);Image.new('RGB',(900,1200),'white').save(p);original=p.read_bytes()
   rows=build_catalog(root);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['id'],'pose:站姿/示例.png')
   (root/'web').mkdir();(root/'web/portrait-materials.json').write_text(json.dumps(rows))
   output=io.BytesIO();report=write_bundle(root,output);self.assertEqual(report['count'],1)
   with tarfile.open(fileobj=io.BytesIO(output.getvalue())) as tar:
    saved=json.load(tar.extractfile('portrait-materials.json'));self.assertEqual(saved[0]['image'],rows[0]['image']);self.assertTrue(saved[0]['thumbnail'].startswith('/portrait-thumbs/'))
    with Image.open(tar.extractfile(saved[0]['thumbnail'].lstrip('/'))) as im:self.assertLessEqual(max(im.size),480)
   self.assertEqual(p.read_bytes(),original)
