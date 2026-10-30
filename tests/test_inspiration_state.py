import importlib.util
import sqlite3
import unittest
import test_inspiration_catalog as fixtures

class InspirationStateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('huashi.inspiration_state'),'Stage B favorites adapter is missing')
        fixtures.InspirationCatalogTests.setUp(self)
        from huashi.inspiration_state import InspirationState,initialize_state
        self.initialize=initialize_state;self.state_path=self.root/'inspiration/user-data/inspiration-state.sqlite3';self.library.db.parent.mkdir(parents=True)
        with sqlite3.connect(self.library.db) as c:c.execute('CREATE TABLE favorites (id TEXT PRIMARY KEY,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)');c.execute("INSERT INTO favorites VALUES ('case:1','2026-01-01 01:02:03')")
        self.state=InspirationState(self.library,self.store,self.state_path,self.catalog)
    def test_image_uses_same_database_and_keeps_original_timestamp(self):
        self.state.set_favorite('case:1',True);records=self.state.list_favorites()['items'];self.assertEqual(next(x for x in records if x['id']=='case:1')['created_at'],'2026-01-01 01:02:03')
        self.state.set_favorite('style:1',True)
        with sqlite3.connect(self.library.db) as c:self.assertIsNotNone(c.execute("SELECT id FROM favorites WHERE id='style:1'").fetchone())
        self.state.set_favorite('case:1',False);self.assertNotIn('case:1',{x['id'] for x in self.state.list_favorites()['items']})
    def test_missing_new_state_does_not_get_created_on_read(self):
        r=self.state.list_favorites();self.assertFalse(self.state_path.exists());self.assertFalse(r['sources']['additional']['available']);self.assertTrue(r['sources']['image']['available'])
        with self.assertRaises(OSError):self.state.set_favorite('image:palette:C-01',True)
    def test_palette_persistence_idempotent_init_and_independent_export(self):
        self.initialize(self.state_path);self.state.set_favorite('image:palette:C-01',True);first=self.state.list_favorites();self.initialize(self.state_path);self.state.set_favorite('image:palette:C-01',True);self.assertEqual(first,self.state.list_favorites());self.assertEqual(self.state.export_favorites()['version'],2)
        self.assertEqual(self.library.read_favorites()[0]['id'],'case:1')
    def test_unknown_ids_and_non_boolean_rejected(self):
        for id_,flag in [('bad',True),('case:1',1),('case:1','yes')]:
            with self.assertRaises((ValueError,KeyError)):self.state.set_favorite(id_,flag)
    def test_common_prompts_remain_distinct_from_favorites(self):
        p=self.store.get_prompt(self.prompt['id']);self.store.save_prompt({**p,'favorite':True},p['id']);r=self.state.list_favorites();self.assertEqual(len(r['common_prompts']),1);self.assertNotIn('prompt:'+p['id'],{x['id'] for x in r['items']})
        with self.assertRaises(ValueError):self.state.set_favorite('prompt:'+p['id'],True)
    def test_initializer_rejects_authoritative_or_symlink_database(self):
        for p in [self.library.db,self.store.db_path]:
            with self.assertRaises(ValueError):self.initialize(p)
        self.state_path.symlink_to(self.library.db)
        with self.assertRaises(ValueError):self.initialize(self.state_path)
