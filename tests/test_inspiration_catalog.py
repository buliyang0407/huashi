import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from huashi.inspiration import InspirationLibrary
from huashi.storage import HuashiStore

class InspirationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('huashi.inspiration_catalog'),'Stage B catalog adapter is missing')
        from huashi.inspiration_catalog import InspirationCatalog
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=HuashiStore(self.root/'data/db.sqlite');self.store.initialize()
        self.library=InspirationLibrary(self.root/'inspiration');self.path=self.library.site/'library/catalog.json';self.path.parent.mkdir(parents=True)
        self.source={'entries':[{'id':'case:1','kind':'case','title':'海报参考','prompt':'original <text>','category':'海报','tags':['Poster'],'image':'/images/a.jpg','githubUrl':'https://github.com/example/source'}, {'id':'style:1','kind':'style','title':'水墨','prompt':'ink style','traits':'wet brush 留白','referenceImage':'/handdraw/ink.webp'}, {'id':'layout:1','kind':'layout','title':'双语排版','prompt':'中文原文','promptEn':'English original'}, {'id':'case:2','kind':'case','title':'只有描述','description':'NOT A PROMPT'}],'colors':[{'id':'C-01','name_zh':'克莱因蓝','name_en':'Klein Blue','category_zh':'经典蓝系','prompt_zh':'主题色：克莱因蓝','prompt_en':'Klein Blue theme','image':'/handdraw/color.webp'}],'sources':[]}
        self.path.write_text(json.dumps(self.source,ensure_ascii=False))
        self.prompt=self.store.save_prompt({'title':'个人内容','content':'my prompt','tags':['水墨']})
        self.catalog=InspirationCatalog(self.library,self.store,self.root/'inspiration/animation')
    def test_full_detail_keeps_source_fields_and_original_ids(self):
        e=self.catalog.get_entry('style:1');self.assertEqual(e['traits'],'wet brush 留白');self.assertEqual(e['referenceImage'],'/inspiration/handdraw/ink.webp');self.assertEqual(e['id'],'style:1');self.assertEqual(e['prompts']['original'],'ink style')
        l=self.catalog.get_entry('layout:1');self.assertEqual(l['prompts']['zh'],'中文原文');self.assertEqual(l['prompts']['en'],'English original')
    def test_palette_is_independent_and_searchable_in_both_languages(self):
        e=self.catalog.get_entry('image:palette:C-01');self.assertEqual(e['prompts']['en'],'Klein Blue theme');self.assertEqual(self.catalog.search(domain='image',kind='palette')['total'],1);self.assertEqual(self.catalog.search(q='Klein Blue')['total'],1)
    def test_list_is_lightweight_and_descriptions_are_not_prompts(self):
        items=self.catalog.search(domain='image')['items'];self.assertTrue(all('prompts' not in i and 'prompt' not in i and 'traits' not in i for i in items))
        e=self.catalog.get_entry('case:2');self.assertEqual(e['prompts']['original'],'');self.assertFalse(e['capabilities']['copy_prompt'])
    def test_soft_deleted_parent_and_variants_stay_hidden(self):
        self.store.save_prompt_variant(self.prompt['id'],{'title':'变体','content':'variant text'});self.assertEqual(self.catalog.search(domain='prompt')['total'],2)
        self.store.soft_delete_prompt(self.prompt['id']);self.assertEqual(self.catalog.search(domain='prompt')['total'],0)
    def test_missing_image_archive_does_not_hide_prompts_or_create_state(self):
        self.path.unlink();r=self.catalog.search();self.assertEqual(r['total'],1);self.assertFalse(r['sources']['image']['available']);self.assertFalse(self.library.db.exists());self.assertFalse((self.root/'inspiration/animation').exists())
    def test_queries_are_read_only_and_do_not_modify_original_catalog(self):
        before=self.store.db_path.read_bytes();raw=self.path.read_bytes();self.catalog.search(q='水墨');self.catalog.get_entry('style:1');self.assertEqual(before,self.store.db_path.read_bytes());self.assertEqual(raw,self.path.read_bytes())
    def test_stable_pagination_and_domain_counts(self):
        a=self.catalog.search(limit=2);b=self.catalog.search(offset=2,limit=2);self.assertFalse({x['id'] for x in a['items']}&{x['id'] for x in b['items']});self.assertEqual(a['items'],self.catalog.search(limit=2)['items']);self.assertEqual(a['counts']['image'],5)
    def test_invalid_filters_and_unknown_id(self):
        for data in [{'domain':'bad'},{'kind':'bad'},{'limit':101},{'offset':-1},{'q':'a'*257}]:
            with self.assertRaises(ValueError):self.catalog.search(**data)
        with self.assertRaises(KeyError):self.catalog.get_entry('unknown')

    def test_palette_retains_archive_source_and_revision(self):
        source={'id':'handdraw','repository':'https://github.com/yang0/handraw-style','commit':'abc123','license':'MIT with attribution requirement'}
        self.source['sources']=[source];self.path.write_text(json.dumps(self.source));e=self.catalog.get_entry('image:palette:C-01')
        self.assertIn(source['repository'],e['source_urls']);self.assertEqual(e['source_revision'],'abc123');self.assertEqual(e['source_license'],source['license'])
    def test_legacy_html_navigation_script_is_not_archive_prefixed(self):
        raw=b'<head></head><script src="/app.js"></script>'
        html=InspirationLibrary._adapt('index.html',raw).decode()
        self.assertIn('src="/inspiration-nav.js?',html);self.assertNotIn('/inspiration/inspiration-nav.js',html)
