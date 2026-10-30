import copy
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from huashi.server import make_handler, MissingRunningHubClient
from huashi.service import HuashiService
from huashi.storage import HuashiStore


class PromptFolderAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = HuashiStore(self.root / 'data/db.sqlite')
        self.store.initialize()
        self.service = HuashiService(self.root / 'data', self.store, MissingRunningHubClient())
        web = self.root / 'web'; web.mkdir(); (web/'index.html').write_text('temporary fixture')
        handler = make_handler(self.service, web, self.root / 'data')
        handler.log_message = lambda *_: None
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def req(self, path, method='GET', data=None, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        conn.request(method, path, json.dumps(data) if data is not None else None,
                     headers or {'Content-Type': 'application/json'})
        r = conn.getresponse(); raw = r.read(); status = r.status; conn.close()
        try: result = json.loads(raw)
        except (ValueError, UnicodeDecodeError): result = {'raw': raw.decode(errors='replace')}
        return status, result

    def folder(self, name, parent_id=None):
        status, data = self.req('/api/prompt-folders', 'POST', {'name': name, 'parent_id': parent_id})
        self.assertEqual(status, 201, data)
        return data['folder']

    def test_list_default_folder_and_depth_rules_over_http(self):
        status, data = self.req('/api/prompt-folders')
        self.assertEqual(status, 200, data)
        leaf = next(f for f in data['folders'] if f['id'] == data['default_folder_id'])
        self.assertEqual(leaf['path'], '我的提示词 / 未分类')
        parent = self.folder('人物')
        child = self.folder('室内', parent['id'])
        self.assertEqual(child['level'], 2)
        self.assertEqual(self.req('/api/prompt-folders', 'POST', {'name': '第三层', 'parent_id': child['id']})[0], 400)
        self.assertEqual(self.req('/api/prompt-folders', 'POST', {'name': '室内', 'parent_id': parent['id']})[0], 400)

    def test_create_move_atomic_and_nonempty_delete(self):
        parent = self.folder('用户分类'); leaf = self.folder('动作', parent['id'])
        status, data = self.req('/api/prompts', 'POST', {'title':'第一条', 'content':'standing', 'folder_id':leaf['id']})
        self.assertEqual(status, 201, data); prompt = data['prompt']
        before = self.store.get_prompt(prompt['id'])
        self.assertEqual(self.req('/api/prompts/move', 'POST', {'prompt_ids':[prompt['id'], 'missing'], 'folder_id':self.store.default_prompt_folder_id()})[0], 400)
        self.assertEqual(self.store.get_prompt(prompt['id']), before)
        self.assertEqual(self.req('/api/prompt-folders/'+leaf['id'], 'DELETE')[0], 400)
        status, result = self.req('/api/prompts/move', 'POST', {'prompt_ids':[prompt['id']], 'folder_id':self.store.default_prompt_folder_id()})
        self.assertEqual(status, 200, result); self.assertEqual(result['moved'], 1)
        self.assertEqual(self.req('/api/prompt-folders/'+leaf['id'], 'DELETE')[0], 200)
        self.assertEqual(self.req('/api/prompt-folders/'+leaf['id']+'/restore','POST', {})[0], 200)

    def test_invalid_folder_rejects_update_and_omission_preserves_location(self):
        parent = self.folder('照片'); leaf = self.folder('侧面', parent['id'])
        prompt = self.store.save_prompt({'title':'原题', 'content':'profile', 'folder_id':leaf['id']})
        self.assertEqual(self.req('/api/prompts/'+prompt['id'], 'PUT', {'content':'wrong', 'folder_id':'missing'})[0], 400)
        self.assertEqual(self.store.get_prompt(prompt['id'])['content'], 'profile')
        status, data = self.req('/api/prompts/'+prompt['id'], 'PUT', {'title':'改名', 'content':'profile revised'})
        self.assertEqual(status, 200, data); self.assertEqual(data['prompt']['folder_id'], leaf['id'])
        status, data = self.req('/api/prompts?folder_id='+leaf['id'])
        self.assertEqual(status, 200); self.assertEqual([x['id'] for x in data['prompts']], [prompt['id']])
        self.assertEqual(self.req('/api/prompts?folder_id=missing')[0], 400)

    def test_search_filter_retains_variant_folder_path(self):
        parent=self.folder('人物'); leaf=self.folder('侧面',parent['id'])
        prompt=self.store.save_prompt({'content':'standing', 'folder_id':leaf['id']})
        variant=self.store.save_prompt_variant(prompt['id'], {'title':'变体','content':'walking'})
        self.store.save_prompt({'content':'unclassified'})
        status,result=self.req('/api/inspiration/search?kind=prompt&prompt_folder_id='+leaf['id'])
        self.assertEqual(status,200,result); self.assertEqual(result['total'],2)
        self.assertTrue(all(x['folder_path']=='人物 / 侧面' and x['folder_id']==leaf['id'] for x in result['items']))
        self.assertEqual(self.req('/api/inspiration/search?kind=prompt&prompt_folder_id=missing')[0],400)

    def test_v4_backup_roundtrip_and_v3_preserves_existing_folder(self):
        self.assertEqual(self.service.export_apps_bundle()['version'],4)
        parent=self.folder('我的测试'); leaf=self.folder('保存',parent['id'])
        prompt=self.store.save_prompt({'title':'原稿','content':'saved','folder_id':leaf['id']})
        bundle=self.service.export_apps_bundle()
        self.assertIn('prompt_folders',bundle);self.assertIn('prompt_folder_links',bundle)
        other=HuashiStore(self.root/'other/db.sqlite');other.initialize()
        service=HuashiService(other.db_path.parent,other,MissingRunningHubClient())
        service.import_apps_bundle(bundle)
        self.assertEqual(other.get_prompt(prompt['id'])['folder_path'],'我的测试 / 保存')
        legacy=copy.deepcopy(bundle);legacy['version']=3
        legacy.pop('prompt_folders');legacy.pop('prompt_folder_links')
        for p in legacy['prompts']:p.pop('folder_id',None);p.pop('folder_path',None)
        self.service.import_apps_bundle(legacy)
        self.assertEqual(self.store.get_prompt(prompt['id'])['folder_id'],leaf['id'])

    def test_invalid_backup_is_rejected_before_any_original_row_changes(self):
        self.assertEqual(self.service.export_apps_bundle()['version'],4)
        prompt=self.store.save_prompt({'title':'保留','content':'original'})
        bundle=self.service.export_apps_bundle()
        bundle['prompts'][0]['content']='must not be saved'
        root=next(x for x in bundle['prompt_folders'] if x['parent_id'] is None)
        root['parent_id']=root['id']
        before=self.store.get_prompt(prompt['id'])
        with self.assertRaises(ValueError):self.service.import_apps_bundle(bundle)
        self.assertEqual(self.store.get_prompt(prompt['id']),before)

    def test_backup_restores_move_and_archives_occupied_source_with_reused_name(self):
        parent = self.folder('恢复测试')
        source = self.folder('动作', parent['id'])
        target = self.folder('新目录', parent['id'])
        prompt = self.store.save_prompt({'title':'原稿', 'content':'standing', 'folder_id':source['id']})
        bundle = self.service.export_apps_bundle()
        for folder in bundle['prompt_folders']:
            if folder['id'] == source['id']: folder['deleted_at'] = '2026-10-13T00:00:00Z'
            if folder['id'] == target['id']: folder['name'] = '动作'
        for link in bundle['prompt_folder_links']:
            if link['prompt_id'] == prompt['id']: link['folder_id'] = target['id']
        for item in bundle['prompts']:
            if item['id'] == prompt['id']: item['folder_id'] = target['id']
        self.service.import_apps_bundle(bundle)
        self.assertEqual(self.store.get_prompt(prompt['id'])['folder_path'], '恢复测试 / 动作')
        self.assertTrue(self.store.get_prompt_folder(source['id'], include_deleted=True)['deleted_at'])

    def test_new_mutations_require_json_and_reject_cross_origin(self):
        self.assertEqual(self.req('/api/prompt-folders','POST',{'name':'reject'}, {'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.req('/api/prompt-folders','POST',{'name':'reject'}, {'Content-Type':'application/json','Origin':'https://foreign.example'})[0],403)

    def raw_tables(self):
        with self.store.connect() as conn:
            names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            return {name: [tuple(row) for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY rowid')] for name in names}

    def failure_bundle(self):
        parent = self.folder('回滚父目录')
        source = self.folder('动作', parent['id'])
        target = self.folder('备用目录', parent['id'])
        prompt = self.store.save_prompt({'id':'rollback-prompt','content':'原文','folder_id':source['id']})
        self.store.save_prompt_variant(prompt['id'], {'id':'rollback-variant','content':'原衍生'})
        bundle = self.service.export_apps_bundle()
        bundle['apps'][0]['name'] = '导入应用新名'
        for folder in bundle['prompt_folders']:
            if folder['id'] == parent['id']: folder['name'] = '导入父目录新名'
            if folder['id'] == source['id']: folder['deleted_at'] = 'archived'
            if folder['id'] == target['id']: folder['name'] = '动作'
        for link in bundle['prompt_folder_links']:
            if link['prompt_id'] == prompt['id']: link['folder_id'] = target['id']
        for item in bundle['prompts']:
            if item['id'] == prompt['id']:
                item.update(content='导入新文', folder_id=target['id'])
                item['variants'][0]['content'] = '导入新衍生'
        return bundle

    def test_failed_prompt_import_rolls_back_all_tables_and_prepared_names(self):
        bundle = self.failure_bundle()
        bundle['prompts'][0]['content'] = ''
        before = self.raw_tables()
        with self.assertRaises(ValueError): self.service.import_apps_bundle(bundle)
        self.assertEqual(self.raw_tables(), before)

    def test_late_invalid_variant_rolls_back_app_prompt_variant_and_directories(self):
        bundle = self.failure_bundle()
        bundle['prompts'][0]['variants'].append({'id':'bad-late-variant','content':''})
        before = self.raw_tables()
        with self.assertRaises(ValueError): self.service.import_apps_bundle(bundle)
        self.assertEqual(self.raw_tables(), before)

    def test_invalid_later_app_provider_rolls_back_earlier_app_and_prepared_names(self):
        bundle = self.failure_bundle()
        bundle['apps'][1]['provider'] = 'invalid'
        before = self.raw_tables()
        with self.assertRaises(ValueError): self.service.import_apps_bundle(bundle)
        self.assertEqual(self.raw_tables(), before)


if __name__=='__main__': unittest.main()
