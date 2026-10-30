import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from huashi.animation_ingest import prepare_media_plan, fetch_media


class AnimationCardsPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.snap = Path(self.tmp.name) / 'animation/snapshots/new'
        self.snap.mkdir(parents=True)
        self.manifest = {'snapshot_id': 'new', 'resources': [], 'source_files': [],
                         'planned_assets': [{'id': 'poster-one', 'type': 'poster', 'source_url': 'https://example.org/cover.jpg'},
                                            {'id': 'lemo-one', 'type': 'video', 'source_url': 'https://example.org/demo.mp4', 'expected_bytes': 10}]}
        (self.snap / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.snap / 'catalog.json').write_text(json.dumps({'entries': [], 'selected_awesome_slugs': ['one']}))

    def test_default_plan_never_contacts_video_or_source_pages(self):
        with patch('huashi.animation_ingest.MediaDownloader.request', side_effect=AssertionError('Unexpected network request')):
            plan = prepare_media_plan(self.snap)
        self.assertEqual([x['type'] for x in plan['assets']], ['poster'])
        self.assertEqual(plan['known_video_bytes'], 0)
        self.assertEqual(plan['video_policy'], 'external-links-only-preserve-existing')

    def test_old_video_plan_refused_before_network_or_manifest_changes(self):
        (self.snap / 'media-plan.json').write_text(json.dumps({'assets': self.manifest['planned_assets'], 'known_video_bytes': 10}))
        before = (self.snap / 'manifest.json').read_bytes()
        with patch('huashi.animation_ingest.MediaDownloader.request', side_effect=AssertionError('Unexpected network request')):
            with self.assertRaisesRegex(ValueError, 'Video downloads are disabled'):
                fetch_media(self.snap)
        self.assertEqual((self.snap / 'manifest.json').read_bytes(), before)

    def test_existing_video_manifest_and_original_text_survive_poster_only_maintenance(self):
        import hashlib
        video = self.snap / 'previews/old.mp4'
        video.parent.mkdir()
        video.write_bytes(b'preserved-video')
        resource = {'id': 'old', 'asset_id': 'old', 'type': 'video', 'role': 'original', 'path': 'previews/old.mp4',
                    'bytes': video.stat().st_size, 'sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                    'mime': 'video/mp4', 'duration_seconds': 3}
        self.manifest['resources'] = [resource]
        (self.snap / 'manifest.json').write_text(json.dumps(self.manifest))
        entry = {'id': 'animation:test:one', 'prompts': {'original': 'Full\noriginal text.'},
                 'media': [{'asset_id': 'old', 'availability': 'local', 'role': 'original', 'url': '/inspiration-media/new/previews/old.mp4'}]}
        (self.snap / 'catalog.json').write_text(json.dumps({'entries': [entry]}))
        (self.snap / 'media-plan.json').write_text(json.dumps({'assets': [], 'known_video_bytes': 0}))
        with patch('huashi.animation_ingest.MediaDownloader.request', side_effect=AssertionError('Unexpected network request')):
            result = fetch_media(self.snap)
        after = json.loads((self.snap / 'manifest.json').read_text())
        self.assertEqual(after['resources'], [resource])
        self.assertEqual(result['videos'], 1)
        self.assertEqual(video.read_bytes(), b'preserved-video')
        self.assertEqual(json.loads((self.snap / 'catalog.json').read_text())['entries'][0]['prompts'], entry['prompts'])
