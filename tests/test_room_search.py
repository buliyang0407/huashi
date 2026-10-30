import json
import tempfile
import unittest
from pathlib import Path

from huashi.inspiration import InspirationLibrary
from huashi.storage import HuashiStore


class RoomSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = HuashiStore(self.root / 'data/db.sqlite')
        self.store.initialize()
        self.library = InspirationLibrary(self.root / 'inspiration')
        self.path = self.library.site / 'library/catalog.json'
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({'entries': [
            {'id': 'case:1', 'kind': 'case', 'title': '礼服摄影', 'promptEn': 'a formal dress portrait', 'thumbnail': '/thumbs/a.webp'},
            {'id': 'style:1', 'kind': 'style', 'title': '油画', 'tags': ['礼服'], 'promptHintEn': 'oil painting'},
            {'id': 'layout:1', 'kind': 'layout', 'title': '礼服海报', 'description': '标题与留白'},
        ]}), encoding='utf-8')
        self.prompt = self.store.save_prompt({'title': '礼服提示词', 'content': 'evening dress', 'tags': ['人像']})

    def search(self, **kwargs):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('huashi.inspiration_search'), 'Unified search adapter is not implemented')
        from huashi.inspiration_search import InspirationSearch
        return InspirationSearch(self.library, self.store).search(**kwargs)

    def test_unified_search_has_four_kinds_and_explicit_prompt_text(self):
        result = self.search(query='礼服')
        self.assertEqual(result['total'], 4)
        self.assertEqual(result['counts'], {'all': 4, 'case': 1, 'style': 1, 'layout': 1, 'prompt': 1})
        items = {i['kind']: i for i in result['items']}
        self.assertEqual(items['case']['prompt'], 'a formal dress portrait')
        self.assertEqual(items['layout']['prompt'], '')  # Descriptions are not executable prompts.
        self.assertEqual(items['case']['thumbnail'], '/inspiration/thumbs/a.webp')
        self.assertTrue(items['prompt']['id'].startswith('prompt:'))

    def test_filters_counts_pagination_and_repeated_query_are_stable(self):
        result = self.search(query='礼服', kind='style', limit=1)
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['counts']['all'], 4)
        first = self.search(query='礼服', limit=2)
        second = self.search(query='礼服', offset=2, limit=2)
        self.assertFalse(set(i['id'] for i in first['items']) & set(i['id'] for i in second['items']))
        self.assertEqual(first['items'], self.search(query='礼服', limit=2)['items'])

    def test_missing_archive_does_not_hide_prompts_or_create_favorites(self):
        self.path.unlink()
        result = self.search(query='礼服')
        self.assertEqual(result['total'], 1)
        self.assertFalse(result['sources']['archive']['available'])
        self.assertFalse(self.library.db.exists())

    def test_variants_and_unicode_tokens_are_searchable_and_deleted_prompts_hidden(self):
        self.store.save_prompt_variant(self.prompt['id'], {'title': '婚礼变体', 'content': 'Wedding DRESS', 'translation': '白色礼服'})
        self.assertEqual(self.search(query='wedding dress')['total'], 1)
        self.assertEqual(self.search(query='白色 礼服')['total'], 1)
        self.store.soft_delete_prompt(self.prompt['id'])
        self.assertEqual(self.search(query='wedding')['total'], 0)

    def test_all_results_include_other_matching_kinds_on_first_page(self):
        catalog = json.loads(self.path.read_text())
        catalog['entries'].extend({'id': f'case:{i}', 'kind': 'case', 'title': '礼服案例', 'prompt': 'dress'} for i in range(2,40))
        self.path.write_text(json.dumps(catalog))
        page = self.search(query='礼服', limit=4)
        self.assertEqual({i['kind'] for i in page['items']}, {'case','style','layout','prompt'})

    def test_prompt_sample_uses_existing_webp_thumbnail_protocol(self):
        from PIL import Image
        sample=self.store.db_path.parent/'albums/example dress.png'
        sample.parent.mkdir(parents=True)
        Image.new('RGB',(2,2)).save(sample)
        self.store.save_prompt({**self.prompt, 'sample_path':'albums/example dress.png'}, prompt_id=self.prompt['id'])
        item=self.search(kind='prompt')['items'][0]
        self.assertTrue(item['thumbnail'].startswith('/thumbs/480/albums%2Fexample%20dress.png?v='))
        self.assertEqual(item['image'],'/files/albums/example dress.png')
        self.assertFalse((self.store.db_path.parent/'thumbnails').exists())

    def test_search_is_read_only_and_bounded(self):
        before = self.store.db_path.read_bytes()
        self.search(query='礼服')
        self.assertEqual(before, self.store.db_path.read_bytes())
        for options in [{'kind': 'bad'}, {'offset': -1}, {'limit': 0}, {'limit': 101}, {'query': 'a' * 257}]:
            with self.assertRaises(ValueError):
                self.search(**options)

    def test_hundred_results_and_following_page_do_not_overlap(self):
        catalog = json.loads(self.path.read_text())
        catalog['entries'].extend({'id': f'case:page-{i}', 'kind': 'case', 'title': '分页案例', 'prompt': 'a case'} for i in range(125))
        self.path.write_text(json.dumps(catalog))
        first = self.search(query='分页', kind='case', limit=100)
        second = self.search(query='分页', kind='case', offset=100, limit=100)
        self.assertEqual(len(first['items']), 100)
        self.assertEqual(len(second['items']), 25)
        self.assertFalse({x['id'] for x in first['items']} & {x['id'] for x in second['items']})
        self.assertIsNone(second['next_offset'])


if __name__ == '__main__':
    unittest.main()
