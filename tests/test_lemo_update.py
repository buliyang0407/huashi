import importlib.util,json,tempfile,unittest,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class LemoUpdateTests(unittest.TestCase):
 def test_update_preserves_ids_aliases_media_and_original_snapshot(self):
  spec=importlib.util.spec_from_file_location('lemo_update',ROOT/'scripts/update_lemo_materials.py')
  self.assertIsNotNone(spec)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as td:
   source=Path(td)/'upstream';(source/'styleboard').mkdir(parents=True);film=Path(td)/'film';film.mkdir();(film/'一叶入杯.mp4').write_bytes(b'our-film')
   rows=[]
   for slug in ['watercolor']+['style-'+str(i) for i in range(50)]:
    folder=source/'styles'/slug;folder.mkdir(parents=True);(folder/'STYLE.md').write_text('complete style '+slug);rows.append({'slug':slug,'cn':slug,'cat':'test','line_cn':'description'})
   (source/'styleboard/catalog.json').write_text(json.dumps(rows));(source/'styleboard/opuscar98_styles.json').write_text('{"films":[]}')
   for name in ['DIRECTOR.md','TECHNIQUE.md','MY-STYLES.md']:(source/name).write_text('complete guide '+name)
   base=Path(td)/'base';base.mkdir();(base/'previews').mkdir();(base/'previews/old.mp4').write_bytes(b'old-video')
   entry={'id':'animation:lemo:style:watercolor','domain':'animation','kind':'style','media':[{'availability':'local','url':'/inspiration-media/base/previews/old.mp4','role':'demo'}]}
   other={'id':'animation:other:keep','domain':'animation','kind':'case','prompts':{'original':'KEEP FULL ORIGINAL'},'media':[]}
   (base/'catalog.json').write_text(json.dumps({'snapshot_id':'base','entries':[entry,other],'aliases':{'animation:alias:keep':other['id']},'source_counts':{}}))
   (base/'manifest.json').write_text(json.dumps({'snapshot_id':'base','resources':[{'path':'previews/old.mp4','bytes':9,'sha256':hashlib.sha256(b'old-video').hexdigest(),'mime':'video/mp4'}],'source_files':[]}))
   before=(base/'catalog.json').read_bytes();out=Path(td)/'new'
   module.update_snapshot(base,source,film,out)
   data=json.loads((out/'catalog.json').read_text());items={e['id']:e for e in data['entries']}
   self.assertEqual(items[other['id']],other);self.assertEqual(data['aliases'],{'animation:alias:keep':other['id']})
   self.assertEqual((base/'catalog.json').read_bytes(),before)
   self.assertEqual((out/'previews/old.mp4').read_bytes(),b'old-video')
   self.assertEqual(len([i for i in items if i.startswith('animation:lemo:style:')]),51)
   self.assertEqual(items[entry['id']]['media'][0]['url'],'/inspiration-media/new/previews/old.mp4')
   self.assertEqual(items[entry['id']]['media'][-1]['role'],'studio-test')
   self.assertIn('animation:lemo:guide:director',items)
   with self.assertRaises(FileExistsError):module.update_snapshot(base,source,film,out)
