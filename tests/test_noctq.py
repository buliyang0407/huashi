import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huashi.runpod import RunPodClient, make_payload
from huashi.runpod_workflows import RUNPOD_APPS
from huashi.service import HuashiService
from huashi.storage import HuashiStore
from tests.test_runpod import FakeRunPod, png_bytes

ROOT = Path(__file__).resolve().parents[1]
APP = 'runpod-noctq-v4-text-to-image'
LEGACY = ['runpod-qwen21-text-to-image', 'runpod-qwen21-single-image-edit', 'runpod-qwen21-two-image-edit']


class NoctQTest(unittest.TestCase):
    def app(self):
        app = next((a for a in RUNPOD_APPS if a['id'] == APP), None)
        self.assertIsNotNone(app, 'NoctQ V4 画布尚未注册')
        return app

    def service(self, root):
        store = HuashiStore(root / 'db.sqlite')
        store.initialize()
        return HuashiService(root, store, object())

    def test_decimal_sampling_and_all_inputs_reach_original_nodes(self):
        app = self.app()
        values = dict(prompt='A ceramic cup on a cafe table', negative_prompt='', width='768', height='512',
                      batch_size='2', resolution='1024', steps='29', seed='0', cfg='3.25', denoise='0.85',
                      sampler='dpmpp_2m', scheduler='karras')
        body = json.loads(make_payload(app['workflow_key'], app['inputs'], values, {}))
        w = body['input']['workflow']
        self.assertEqual(set(w), set(map(str, range(1, 9))))
        self.assertEqual(w['1']['inputs']['unet_name'], 'noctQUncensoredRealismBuiltOn_v40Base_3260131.safetensors')
        self.assertEqual(w['2']['inputs']['clip_name'], 'qwen3vl_8b_int8_convrot.safetensors')
        self.assertEqual(w['4']['inputs']['prompt'], values['prompt'])
        self.assertEqual(w['4']['inputs']['negative_prompt'], '')
        self.assertEqual(w['4']['inputs']['resolution'], 1024)
        self.assertEqual(w['5']['inputs'], {'width':768, 'height':512, 'batch_size':2})
        self.assertEqual({k:w['6']['inputs'][k] for k in ['steps','seed','cfg','denoise','sampler_name','scheduler']},
                         dict(steps=29, seed=0, cfg=3.25, denoise=0.85, sampler_name='dpmpp_2m', scheduler='karras'))
        self.assertEqual(body['input']['images'], [])
        self.assertFalse(any('lora' in n['class_type'].lower() for n in w.values()))

    def test_invalid_numbers_are_rejected_before_task_creation(self):
        self.app()
        with tempfile.TemporaryDirectory() as temp:
            service = self.service(Path(temp))
            for key, value in [('cfg','nan'),('cfg','inf'),('cfg','-1'),('denoise','1.1'),('denoise','-0.1'),
                               ('batch_size','0'),('batch_size','1.5'),('batch_size','100'),
                               ('resolution','-1'),('steps','0'),('width','513'),('seed',str(2**64)),('prompt','')]:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    service.create_task_from_form(APP, {'input_prompt':'test', 'input_'+key:value}, {}, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])

    def test_history_preserves_decimal_zero_and_uint64_seed(self):
        self.app()
        with tempfile.TemporaryDirectory() as temp:
            service = self.service(Path(temp))
            for seed in ['0', str(2**64 - 1)]:
                task = service.create_task_from_form(APP, {'input_prompt':'test', 'input_negative_prompt':'',
                    'input_seed':seed, 'input_cfg':'3.25', 'input_denoise':'0'}, {}, start_background=False)
                values = task['input_payload']['values']
                self.assertEqual((values['seed'],values['cfg'],values['denoise'],values['negative_prompt']), (seed,'3.25','0',''))
                service.store.initialize()
                self.assertEqual(service.store.get_task(task['id'])['input_payload']['values'], values)
                retry = service.retry_task(task['id'], start_background=False)
                self.assertEqual(retry['input_payload']['values'], values)
            with patch('huashi.service.secrets.randbits', return_value=12345):
                task = service.create_task_from_form(APP, {'input_prompt':'test'}, {}, start_background=False)
            fake = FakeRunPod()
            with patch.object(RunPodClient, 'from_workflow', return_value=fake):
                result = service.process_task(task['id'], poll_interval=0, timeout=1)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(fake.payload['input']['workflow']['6']['inputs']['seed'],12345)
            self.assertEqual(service.list_album_items('works')[0]['task_id'], task['id'])

    def test_retirement_keeps_old_history_and_artwork_but_blocks_new_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            legacy = [copy.deepcopy(a) for a in RUNPOD_APPS if a['id'] in LEGACY]
            for a in legacy:a['enabled']=True
            with patch('huashi.storage.RUNPOD_APPS', legacy):
                service = self.service(root)
                old = service.store.create_task(LEGACY[0], '','old task', input_payload={'values':{'prompt':'old','seed':'0'}})
                dest = root/'cache'/'old.png';dest.write_bytes(png_bytes())
                service.store.update_task(old['id'],status='success',outputs=[{'path':'cache/old.png','type':'png'}])
                service.list_album_items('works')
            before = service.store.get_task(old['id'])
            items_before = service.list_album_items('works')
            service.store.initialize()
            self.assertEqual([a['id'] for a in service.store.list_apps() if a['provider']=='runpod'],[APP, 'runpod-noctq-v4-lora-text-to-image', 'runpod-noctq-v4-single-image-edit', 'runpod-noctq-v4-lora-single-image-edit', 'runpod-noctq-v4-lora-pose-transfer'])
            self.assertEqual(service.store.get_task(old['id']),before)
            self.assertEqual(service.list_album_items('works'),items_before)
            self.assertEqual(dest.read_bytes(),png_bytes())
            for id in LEGACY:
                self.assertFalse(service.store.get_app(id)['enabled'])
                with self.assertRaisesRegex(ValueError,'下架'):
                    service.create_task_from_form(id,{'input_prompt':'test'}, {}, start_background=False)
            with self.assertRaisesRegex(ValueError,'下架'):
                service.retry_task(old['id'],start_background=False)

    def test_form_accepts_fractional_cfg_and_denoise(self):
        script = """
const fs=require('fs'),vm=require('vm');
const text=fs.readFileSync('web/app.js','utf8');
const block=text.slice(text.indexOf('function inputControl(input) {'),text.indexOf('function bindDynamicInputs()'));
const context={escapeAttr:String,escapeHtml:String};vm.createContext(context);vm.runInContext(block,context);
for(const id of ['cfg','denoise']) {
 const html=context.inputControl({id,type:'number',label:id,defaultValue:'0.85'});
 if(!/step="any"/.test(html))throw Error(id+' does not accept decimals');
}
"""
        result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_history_names_negative_prompt_separately(self):
        script = """
const fs=require('fs'),vm=require('vm');const text=fs.readFileSync('web/app.js','utf8');
const block=text.slice(text.indexOf('function taskSettingRows(task) {'),text.indexOf('function taskSettingsText(task)'));
const context={state:{apps:[{id:'noctq',inputs:[{id:'negative_prompt',role:'prompt',label:'负向提示词（可清空）'}]}]},appInputs:a=>a.inputs};
vm.createContext(context);vm.runInContext(block,context);
const rows=context.taskSettingRows({app_id:'noctq',prompt:'coffee',input_payload:{values:{negative_prompt:'blurry'}}});
if(rows[0].label!=='负向提示词（可清空）')throw Error('Negative prompt is mislabeled');
"""
        result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
