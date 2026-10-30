import json,sqlite3,tempfile,unittest
from pathlib import Path
from huashi.inspiration import InspirationLibrary
from huashi.inspiration_catalog import InspirationCatalog
from huashi.inspiration_state import InspirationState,initialize_state
from huashi.storage import HuashiStore

class AnimationIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.store=HuashiStore(self.root/'data/db.sqlite');self.store.initialize();self.lib=InspirationLibrary(self.root/'inspiration');self.anim=self.root/'inspiration/animation';self.snap=self.anim/'snapshots/snap-one';self.snap.mkdir(parents=True);self.lib.db.parent.mkdir(exist_ok=True)
  with sqlite3.connect(self.lib.db) as c:c.execute('CREATE TABLE favorites(id TEXT PRIMARY KEY,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
  self.entry={'id':'animation:test:1','domain':'animation','collection':'code','kind':'style','title':'动画水墨','category':'绘画','tech_tags':['Canvas'],'source_id':'test/source','source_ids':['test/source','test/other'],'source_urls':['https://example.org/work'],'prompt_status':'style-guide','prompts':{'original':'full animation guide','zh':'中文完整提示词','en':''},'thumbnail':'','media':[{'availability':'local','url':'/inspiration-media/snap-one/previews/test.mp4','role':'demo'}],'capabilities':{'save_prompt':True,'copy_prompt':True,'use_image_canvas':False},'prompt_versions':[{'title':'另一版本','text':'version search marker'}]}
  self.data={'snapshot_id':'snap-one','entries':[self.entry],'aliases':{'animation:old:1':'animation:test:1'},'source_counts':{'repo':{'raw':1}}};(self.snap/'catalog.json').write_text(json.dumps(self.data));(self.anim/'active.json').write_text(json.dumps({'snapshot_id':'snap-one'}));self.cat=InspirationCatalog(self.lib,self.store,self.anim)
 def test_animation_filter_versions_and_lightweight_list(self):
  r=self.cat.search(domain='animation',collection='code',source_id='test/other');self.assertEqual(r['total'],1);self.assertTrue(r['sources']['animation']['available']);self.assertNotIn('media',r['items'][0]);self.assertNotIn('prompts',r['items'][0]);self.assertEqual(self.cat.search(q='version search marker')['total'],1);self.assertFalse(self.cat.get_entry(self.entry['id'])['capabilities']['use_image_canvas'])
 def test_alias_detail_and_canonical_favorites_preserve_timestamp(self):
  e=self.cat.get_entry('animation:old:1');self.assertEqual(e['canonical_id'],self.entry['id']);path=self.lib.root/'user-data/inspiration-state.sqlite3';initialize_state(path);s=InspirationState(self.lib,self.store,path,self.cat);s.set_favorite('animation:old:1',True);first=s.list_favorites();self.assertEqual(first['items'][0]['id'],self.entry['id']);s.set_favorite(self.entry['id'],True);self.assertEqual(first,s.list_favorites())
 def test_unsafe_pointer_and_alias_cycle_fail_only_animation(self):
  (self.anim/'active.json').write_text(json.dumps({'snapshot_id':'../../elsewhere'}));r=self.cat.search();self.assertFalse(r['sources']['animation']['available']);self.assertFalse((self.root/'elsewhere').exists())
  (self.anim/'active.json').write_text(json.dumps({'snapshot_id':'snap-one'}));self.data['aliases']={'animation:a':'animation:b','animation:b':'animation:a'};(self.snap/'catalog.json').write_text(json.dumps(self.data));self.assertFalse(self.cat.search()['sources']['animation']['available'])
  (self.snap/'catalog.json').unlink();self.assertEqual(self.cat.search()['sources']['animation']['status'],'unavailable')
 def test_tech_filter_and_original_search_unchanged(self):
  self.assertEqual(self.cat.search(domain='animation',tech='Canvas')['total'],1);self.assertEqual(self.cat.search(domain='animation',tech='Blender')['total'],0);self.assertEqual(self.cat.old_search.search(kind='all')['total'],0)

 def test_activation_verifies_every_file_and_preserves_old_pointer_on_failure(self):
  import huashi.animation_catalog as module
  self.assertTrue(hasattr(module,'activate_snapshot'),'Verified atomic activation is missing')
  import hashlib
  media=self.snap/'previews/test.mp4';media.parent.mkdir();media.write_bytes(b'clip')
  (self.snap/'manifest.json').write_text(json.dumps({'snapshot_id':'snap-one','resources':[{'path':'previews/test.mp4','bytes':4,'sha256':hashlib.sha256(b'clip').hexdigest(),'mime':'video/mp4'}],'source_files':[]}))
  state=self.lib.root/'user-data/inspiration-state.sqlite3';initialize_state(state);module.activate_snapshot(self.anim,'snap-one',state)
  before=(self.anim/'active.json').read_bytes();self.assertIn('catalog_sha256',json.loads(before));media.write_bytes(b'corrupt')
  with self.assertRaises(ValueError):module.activate_snapshot(self.anim,'snap-one',state)
  self.assertEqual(before,(self.anim/'active.json').read_bytes())
