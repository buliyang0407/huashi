import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class AnimationCardSnapshotTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('huashi.animation_cards'), 'Offline card snapshot preparation is missing')

    def test_new_snapshot_preserves_source_video_text_and_stable_ids(self):
        from huashi.animation_cards import prepare_cards
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / 'base'
            (base / 'previews').mkdir(parents=True)
            (base / 'previews/one.mp4').write_bytes(b'archived movie')
            e = {'id': 'animation:awesome:one', 'title': '动态图形 · @author', 'domain': 'animation', 'collection': 'code',
                 'kind': 'case', 'category': '动态图形', 'source': 'awesome-opus5-5-videos', 'source_ids': ['repo/name'],
                 'source_urls': ['https://example.org/post'], 'original': {'post_url': 'https://example.org/post'},
                 'prompts': {'original': 'Full original\nDo not truncate.'}, 'prompt_status': 'partial',
                 'media': [{'asset_id': 'one', 'availability': 'local', 'role': 'original', 'url': '/inspiration-media/base/previews/one.mp4', 'external_url': 'https://example.org/watch'}],
                 'thumbnail': '', 'thumbnail_url': '', 'tech_tags': ['canvas']}
            (base / 'catalog.json').write_text(json.dumps({'snapshot_id': 'base', 'entries': [e], 'aliases': {'animation:old': e['id']}}))
            (base / 'manifest.json').write_text(json.dumps({'snapshot_id': 'base', 'resources': [{'asset_id': 'one', 'type': 'video', 'path': 'previews/one.mp4', 'bytes': 14, 'sha256': hashlib.sha256(b'archived movie').hexdigest()}], 'source_files': [], 'planned_assets': []}))
            before = (base / 'catalog.json').read_bytes()
            notes = {'version': 1, 'entries': {e['id']: {'title': '产品界面连续变形', 'description': '通过同一图形连续变换界面状态，突出产品使用流程。', 'feature_tags': ['界面变形']}}}
            out = root / 'new'
            report = prepare_cards(base, out, notes)
            new = json.loads((out / 'catalog.json').read_text())
            self.assertEqual((base / 'catalog.json').read_bytes(), before)
            self.assertNotEqual(report['snapshot_id'], 'base')
            self.assertEqual(new['entries'][0]['prompts'], e['prompts'])
            self.assertEqual(new['aliases'], {'animation:old': e['id']})
            self.assertEqual(new['entries'][0]['source_title'], e['title'])
            self.assertEqual(new['entries'][0]['prompt_status'], 'partial')
            self.assertEqual((out / 'previews/one.mp4').read_bytes(), b'archived movie')
            self.assertTrue(new['entries'][0]['viewing_links'])
            self.assertIn('features', new['entries'][0])
            self.assertIn('text', new['entries'][0]['cover_status'])
            with self.assertRaises(FileExistsError):
                prepare_cards(base, out, notes)

    def test_untrusted_curation_cannot_replace_originals_or_inject_unsafe_viewing_links(self):
        from huashi.animation_cards import viewing_links
        e = {'media': [{'availability': 'external-link', 'role': 'original', 'external_url': 'javascript:alert(1)'},
                       {'role': 'original', 'external_url': 'https://example.org/watch'},
                       {'role': 'remake', 'external_url': 'https://example.org/watch'}],
             'original': {}, 'source_urls': ['https://example.org/watch']}
        links = viewing_links(e)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['url'], 'https://example.org/watch')
        self.assertEqual(links[0]['roles'], ['original', 'remake'])
