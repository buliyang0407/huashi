import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

class AnimationCatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('huashi.animation_catalog'),'Animation importer is missing')
        from huashi.animation_catalog import build_catalog
        self.build=build_catalog;self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.sources=self.root/'sources';self.dest=self.root/'snapshot'
        def put(slug,path,data):
            p=self.sources/slug/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data) if not isinstance(data,str) else data)
        self.put=put
        for slug in ['lemo-opuscar','awesome-opus5-5-videos','opus-video-prompts']:
            put(slug,'source.json',{'repository':'test/'+slug,'commit':'a'*40,'fetched_at':'2026-10-15T00:00:00Z'})
            put(slug,'files/README.md','Source attribution');put(slug,'tree.json',{'tree':[]});put(slug,'releases.json',[])
        put('lemo-opuscar','files/styleboard/catalog.json',[{'slug':'ink','cn':'水墨','cat':'绘画','dur':12}]);put('lemo-opuscar','files/styles/ink/STYLE.md','# Guide\n'+('original long text\n'*100));put('lemo-opuscar','files/styles/_template/STYLE.md','not a real style')
        put('lemo-opuscar','files/styleboard/opuscar98_styles.json',{'film':'https://example.org/movie','films':[{'no':1,'zh':'片段一','prompt_zh':'中文','prompt_en':'English','t0':2,'dur':3,'shots':[{'zh':'镜头原文'}]},{'no':2,'zh':'片段二','prompt_zh':'二','t0':6,'dur':2}]})
        put('awesome-opus5-5-videos','files/data/videos.json',[{'slug':'one','author':'A','post_url':'https://x.com/a/status/123','prompt':'same prompt','category':'motion','prompt_partial':True},{'slug':'two','author':'B','post_url':'https://x.com/b/status/456','prompt':'same prompt','category':'3d','prompt_partial':False},{'slug':'missing','author':'C','post_url':'https://example.org/list','category':'interactive'}])
        put('opus-video-prompts','files/cases.json',[{'title':'中文案例','url':'https://twitter.com/a/status/123?x=1','how':'保留说明'},{'title':'聚合作品一','url':'https://example.org/collection'},{'title':'聚合作品二','url':'https://example.org/collection'}])
        put('opus-video-prompts','files/prompts/01-example.md','# 中文案例\n- 来源：https://x.com/a/status/123\n## 提示词（原文）\n```text\ncomplete original\nsecond line\n```\n## 怎么测\n说明')
    def test_counts_template_exclusion_and_shared_movie(self):
        r=self.build(self.sources,self.dest);c=json.loads((self.dest/'catalog.json').read_text());e=c['entries'];self.assertEqual(r['raw_candidates'],9);self.assertEqual(len(e),8);self.assertFalse(any('_template' in x['id'] for x in e));films=[x for x in e if ':opuscar98:' in x['id']];self.assertEqual(films[0]['media'][0]['asset_id'],films[1]['media'][0]['asset_id']);self.assertEqual(films[0]['media'][0]['start_seconds'],2);self.assertEqual(films[0]['shots'][0]['zh'],'镜头原文')
    def test_text_does_not_merge_different_works_and_aggregate_stays_distinct(self):
        self.build(self.sources,self.dest);c=json.loads((self.dest/'catalog.json').read_text());e=c['entries'];self.assertTrue(any(x['id']=='animation:awesome:one' for x in e));self.assertTrue(any(x['id']=='animation:awesome:two' for x in e));self.assertEqual(len([x for x in e if x['title'].startswith('聚合作品')]),2);self.assertTrue(c['same_prompt_groups'])
    def test_cross_source_versions_partial_and_missing_prompt(self):
        self.build(self.sources,self.dest);c=json.loads((self.dest/'catalog.json').read_text());one=next(x for x in c['entries'] if x['id']=='animation:awesome:one');self.assertEqual(one['prompt_status'],'partial');self.assertEqual(one['prompts']['original'],'same prompt');self.assertIn('complete original\nsecond line\n',[x['text'] for x in one['prompt_versions']]);self.assertIn('保留说明',str(one));self.assertTrue(c['aliases']);self.assertEqual(next(x for x in c['entries'] if x['id']=='animation:awesome:missing')['prompt_status'],'description-only')
    def test_dry_run_stable_bytes_and_no_overwrite(self):
        r=self.build(self.sources,self.dest,dry_run=True);self.assertFalse(self.dest.exists());self.assertTrue(r['planned_files']);self.build(self.sources,self.dest);other=self.root/'other';self.build(self.sources,other);self.assertEqual((self.dest/'catalog.json').read_bytes(),(other/'catalog.json').read_bytes());before=(self.dest/'manifest.json').read_bytes();self.build(self.sources,self.dest);self.assertEqual(before,(self.dest/'manifest.json').read_bytes());self.put('awesome-opus5-5-videos','files/README.md','changed');
        with self.assertRaises(FileExistsError):self.build(self.sources,self.dest)
    def test_original_file_hashes_and_full_style_preserved(self):
        self.build(self.sources,self.dest);c=json.loads((self.dest/'catalog.json').read_text());style=next(x for x in c['entries'] if x['id']=='animation:lemo:style:ink');self.assertEqual(style['prompts']['original'],'# Guide\n'+('original long text\n'*100));m=json.loads((self.dest/'manifest.json').read_text());self.assertTrue(m['source_files']);self.assertTrue(all(x['sha256'] for x in m['source_files']));self.assertFalse(style['capabilities']['use_image_canvas'])

    def test_shared_posters_retain_all_entry_links_and_modified_output_refused(self):
        rows=json.loads((self.sources/'awesome-opus5-5-videos/files/data/videos.json').read_text());rows[0]['poster_url']='https://example.org/shared.webp';rows[1]['poster_url']=rows[0]['poster_url'];self.put('awesome-opus5-5-videos','files/data/videos.json',rows)
        self.build(self.sources,self.dest);manifest=json.loads((self.dest/'manifest.json').read_text());poster=next(a for a in manifest['planned_assets'] if a['type']=='poster');self.assertEqual(len(poster['entries']),2)
        (self.dest/'catalog.json').write_text('{}')
        with self.assertRaises(FileExistsError):self.build(self.sources,self.dest)
