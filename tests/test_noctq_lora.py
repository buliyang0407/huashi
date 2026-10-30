import copy
import json
import subprocess
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huashi.runpod import RunPodClient, make_payload
from huashi.runpod_workflows import RUNPOD_APPS
from tests import test_noctq
ROOT = test_noctq.ROOT
from tests.test_runpod import FakeRunPod

APP = 'runpod-noctq-v4-lora-text-to-image'


class NoctQLoraTest(unittest.TestCase):
    def app(self):
        app = next((a for a in RUNPOD_APPS if a['id'] == APP), None)
        self.assertIsNotNone(app, '独立 LoRA 画布尚未注册')
        return app

    def test_selectable_lora_and_fractional_strength_reach_model_node(self):
        app = self.app()
        inputs = copy.deepcopy(app['inputs'])
        selector = next(i for i in inputs if i['id'] == 'lora_name')
        selector['options'].append('future/new style.safetensors')
        values = {i['id']: i.get('defaultValue', '') for i in inputs}
        values.update(lora_name='future/new style.safetensors', lora_strength='0.75', seed='0', negative_prompt='')
        graph = json.loads(make_payload(app['workflow_key'], inputs, values, {}))['input']['workflow']
        self.assertEqual(graph['11']['inputs'], {'lora_name': values['lora_name'], 'strength_model': 0.75, 'model': ['1', 0]})
        self.assertEqual(graph['6']['inputs']['model'], ['11', 0])
        self.assertNotIn('strength_clip', graph['11']['inputs'])
        self.assertEqual(graph['4']['inputs']['negative_prompt'], '')
        self.assertTrue(next(a for a in RUNPOD_APPS if a['id'] == 'runpod-noctq-v4-text-to-image')['enabled'])

    def test_invalid_lora_and_strength_do_not_create_tasks(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            service = test_noctq.NoctQTest().service(Path(tmp))
            for key, value in [('lora_name', 'missing.safetensors'), ('lora_name', ''),
                               ('lora_strength', 'nan'), ('lora_strength', 'inf'),
                               ('lora_strength', '101'), ('lora_strength', '-101'), ('lora_strength', '')]:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    service.create_task_from_form(APP, {'input_prompt': 'test', 'input_' + key: value}, {}, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])

    def test_history_retry_and_generation_preserve_selected_lora_and_zero(self):
        app = self.app()
        name = next(i for i in app['inputs'] if i['id'] == 'lora_name')['defaultValue']
        with tempfile.TemporaryDirectory() as tmp:
            service = test_noctq.NoctQTest().service(Path(tmp))
            task = service.create_task_from_form(APP, {'input_prompt': 'a clothed adult fashion portrait',
                'input_lora_name': name, 'input_lora_strength': '0', 'input_negative_prompt': '',
                'input_seed': str(2**64 - 1)}, {}, start_background=False)
            values = task['input_payload']['values']
            self.assertEqual((values['lora_name'], values['lora_strength'], values['negative_prompt']), (name, '0', ''))
            service.store.initialize()
            retry = service.retry_task(task['id'], start_background=False)
            self.assertEqual(retry['input_payload']['values'], values)
            fake = FakeRunPod()
            with patch.object(RunPodClient, 'from_workflow', return_value=fake):
                result = service.process_task(retry['id'], poll_interval=0, timeout=1)
            self.assertEqual(result['status'], 'success')
            self.assertEqual(fake.payload['input']['workflow']['11']['inputs']['strength_model'], 0)
            self.assertEqual(fake.payload['input']['workflow']['6']['inputs']['seed'], 2**64 - 1)
            self.assertEqual(service.list_album_items('works')[0]['task_id'], retry['id'])

    def test_form_allows_decimal_lora_strength(self):
        script = """
const fs=require('fs'),vm=require('vm');const text=fs.readFileSync('web/app.js','utf8');
const block=text.slice(text.indexOf('function inputControl(input) {'),text.indexOf('function bindDynamicInputs()'));
const context={escapeAttr:String,escapeHtml:String};vm.createContext(context);vm.runInContext(block,context);
const html=context.inputControl({id:'lora_strength',type:'number',label:'LoRA 权重',defaultValue:'1'});
if(!/step="any"/.test(html))throw Error('LoRA weight does not accept decimals');
"""
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_future_catalog_file_updates_dropdown_without_new_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(ROOT / 'huashi/runpod_workflows.py', root / 'runpod_workflows.py')
            shutil.copytree(ROOT / 'huashi/workflows', root / 'workflows')
            catalog = root / 'workflows/noctq-v4-loras.json'
            data = json.loads(catalog.read_text())
            data['loras'].append('portraits/future model.safetensors')
            catalog.write_text(json.dumps(data))
            script = """
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('isolated_catalog',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
app=next(a for a in module.RUNPOD_APPS if a['id']=='runpod-noctq-v4-lora-text-to-image')
print(json.dumps(next(i for i in app['inputs'] if i['id']=='lora_name')['options']))
"""
            result = subprocess.run(['python3', '-B', '-c', script, str(root / 'runpod_workflows.py')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), data['loras'])
