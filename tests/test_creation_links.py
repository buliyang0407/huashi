"""Phase 3 contracts on temporary databases and browser-independent helpers."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from huashi.storage import HuashiStore
from huashi.service import HuashiService
from huashi.server import MissingRunningHubClient

ROOT = Path(__file__).resolve().parents[1]

class CreationLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = HuashiStore(self.root / 'db.sqlite'); self.store.initialize()
        self.service = HuashiService(self.root, self.store, MissingRunningHubClient())

    def test_unspecified_upload_goes_to_inbox_and_reuses_it(self):
        a = self.service.save_album_upload('', 'a.png', b'image')
        b = self.service.save_album_upload('', 'b.png', b'image')
        self.assertEqual(a['folder_id'], b['folder_id'])
        self.assertEqual(self.store.get_album_folder(a['folder_id'])['name'], '待整理')

    def test_renamed_inbox_is_not_overwritten(self):
        self.store.ensure_album_folder('__inbox__','用户改名的分类')
        item = self.service.save_album_upload('', 'a.png', b'image')
        self.assertNotEqual(item['folder_id'], '__inbox__')
        self.assertEqual(self.store.get_album_folder('__inbox__')['name'], '用户改名的分类')
        self.assertEqual(self.store.get_album_folder(item['folder_id'])['name'],'待整理')

    def test_named_existing_inbox_is_reused(self):
        folder = self.store.create_album_folder('待整理')
        item = self.service.save_album_upload('', 'a.png', b'image')
        self.assertEqual(item['folder_id'], folder['id'])

    def test_explicit_destination_stays_and_invalid_one_writes_no_file(self):
        item = self.service.save_album_upload('works', 'a.png', b'image')
        self.assertEqual(item['folder_id'], 'works')
        before = set(self.root.rglob('*.png'))
        with self.assertRaises((KeyError, ValueError)):
            self.service.save_album_upload('missing', 'bad.png', b'image')
        self.assertEqual(before, set(self.root.rglob('*.png')))

    def test_parallel_default_uploads_create_only_one_inbox(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            items=list(pool.map(lambda i:self.service.save_album_upload('', f'{i}.png', b'image'),range(6)))
        self.assertEqual(len({i['folder_id'] for i in items}),1)
        self.assertEqual(len([f for f in self.store.list_album_folders() if f['name']=='待整理']),1)

    def test_inbox_display_uses_name_after_reserved_folder_is_renamed(self):
        script="""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');global.window={};
vm.runInThisContext(fs.readFileSync('web/rooms.js','utf8'));
const folders=window.HuashiRooms.displayFolders([{id:'__inbox__',name:'改名分类'},{id:'new-inbox',name:'待整理'}]);
assert.equal(folders.find(f=>f.displayName==='待整理').id,'new-inbox');
assert.equal(folders.find(f=>f.id==='__inbox__').displayName,'改名分类');
"""
        result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_prompt_merge_preserves_subject_and_save_uses_directory(self):
        script = """
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');global.window={};window.HuashiPromptFoldersDefault='__TEST_DEFAULT__';
vm.runInThisContext(fs.readFileSync('web/creation-links.js','utf8'));
const c=window.HuashiCreation;
assert.equal(c.mergePrompt('主体  \\n', '油画风格','append'),'主体  \\n\\n\\n油画风格');
assert.equal(c.mergePrompt('主体','礼服','replace'),'礼服');
assert.equal(c.mergePrompt('', '礼服','append'),'礼服');
assert.equal(c.mergePrompt('主体','风格','append',' '),'主体 风格');
const payload=c.promptPayload('另存','礼服主体',window.HuashiPromptFoldersDefault,'分类:人像,礼服,测试');
assert.equal(payload.id,undefined);assert.equal(payload.folder_id,'__TEST_DEFAULT__');assert.deepEqual(payload.tags,['分类:人像','礼服','测试']);
console.log(JSON.stringify(payload));
"""
        result = subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        data=json.loads(result.stdout)
        data['folder_id']=next(folder['id'] for folder in self.store.list_prompt_folders() if folder['level']==2)
        original=self.store.save_prompt({'title':'原稿','content':'原始礼服'})
        saved=self.store.save_prompt(data)
        self.assertNotEqual(saved['id'],original['id'])
        self.assertEqual(self.store.get_prompt(original['id'])['content'],'原始礼服')
        self.assertIn('分类:人像',saved['tags'])
