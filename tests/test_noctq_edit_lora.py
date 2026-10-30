import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huashi.runpod import RunPodClient, make_payload
from huashi.runpod_workflows import RUNPOD_APPS
from tests import test_noctq
from tests.test_runpod import FakeRunPod, png_bytes

APP = 'runpod-noctq-v4-lora-single-image-edit'


class NoctQEditLoraTest(unittest.TestCase):
    def app(self):
        app = next((a for a in RUNPOD_APPS if a['id'] == APP), None)
        self.assertIsNotNone(app, 'LoRA单图编辑画布尚未注册')
        return app

    def test_selected_lora_and_image_use_exact_nine_node_graph(self):
        app=self.app(); inputs=copy.deepcopy(app['inputs'])
        selector=next(i for i in inputs if i['id']=='lora_name')
        selector['options'].append('portraits/future.safetensors')
        values={i['id']:i.get('defaultValue','') for i in inputs}
        values.update(lora_name='portraits/future.safetensors',lora_strength='0.85',seed='0',cfg='3.25',negative_prompt='',resolution='512')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.png';source.write_bytes(png_bytes())
            graph=json.loads(make_payload(app['workflow_key'],inputs,values,{'image1':source}))['input']['workflow']
            self.assertEqual(set(graph),{'1','2','3','4','6','7','8','11','12'})
            self.assertEqual(graph['11']['inputs'],{'model':['1',0],'lora_name':values['lora_name'],'strength_model':0.85})
            self.assertEqual(graph['6']['inputs']['model'],['11',0])
            self.assertEqual(graph['6']['inputs']['latent_image'],['4',2])
            self.assertEqual(graph['4']['inputs']['images.image_1'],['12',0])
            self.assertEqual(graph['12']['inputs']['image'],'input_1.jpg')
            self.assertEqual((graph['4']['inputs']['negative_prompt'],graph['6']['inputs']['seed']),('',0))
            self.assertNotIn('strength_clip',graph['11']['inputs'])
            self.assertFalse({'width','height','batch_size'} & {i['id'] for i in inputs})

    def test_invalid_selection_and_weight_leave_no_task_rows(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            service=test_noctq.NoctQTest().service(Path(tmp))
            files={'input_image1':{'filename':'source.png','content':png_bytes()}}
            for key,value in [('lora_name','missing.safetensors'),('lora_name',''),('lora_strength','nan'),('lora_strength','inf'),('lora_strength','101'),('lora_strength','-101'),('lora_strength','')]:
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                    service.create_task_from_form(APP,{'input_prompt':'change the shirt to red','input_'+key:value},files,start_background=False)
            with self.assertRaises(ValueError):
                service.create_task_from_form(APP,{'input_prompt':'test'},{},start_background=False)
            self.assertEqual(service.store.list_tasks(),[])

    def test_gallery_history_retry_preserve_zero_weight_and_original(self):
        app=self.app();name=next(i for i in app['inputs'] if i['id']=='lora_name')['defaultValue']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);service=test_noctq.NoctQTest().service(root)
            original=root/'cache'/'original.png';original.write_bytes(png_bytes());digest=hashlib.sha256(original.read_bytes()).hexdigest()
            task=service.create_task_from_form(APP,{'input_prompt':'a red evening dress','input_image1_artwork':'cache/original.png','input_lora_name':name,'input_lora_strength':'0','input_negative_prompt':'','input_seed':str(2**64-1)}, {},start_background=False)
            values=task['input_payload']['values'];self.assertEqual((values['lora_strength'],values['negative_prompt']),('0',''))
            service.store.initialize();retry=service.retry_task(task['id'],start_background=False)
            self.assertEqual(retry['input_payload']['values'],values)
            fake=FakeRunPod()
            with patch.object(RunPodClient,'from_workflow',return_value=fake):result=service.process_task(retry['id'],poll_interval=0,timeout=1)
            self.assertEqual(result['status'],'success',result.get('error'))
            self.assertEqual(fake.payload['input']['workflow']['11']['inputs']['strength_model'],0)
            self.assertEqual(fake.payload['input']['workflow']['6']['inputs']['seed'],2**64-1)
            self.assertTrue(any(i['task_id']==retry['id'] for i in service.list_album_items('works')))
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),digest)

    def test_shared_catalog_updates_both_lora_dropdowns(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);shutil.copy2(test_noctq.ROOT/'huashi/runpod_workflows.py',root/'runpod_workflows.py');shutil.copytree(test_noctq.ROOT/'huashi/workflows',root/'workflows')
            catalog=root/'workflows/noctq-v4-loras.json';data=json.loads(catalog.read_text());data['loras'].append('future/edit style.safetensors');catalog.write_text(json.dumps(data))
            script="""
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('isolated',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
print(json.dumps({a['id']:next(i for i in a['inputs'] if i['id']=='lora_name')['options'] for a in m.RUNPOD_APPS if a['id'] in ['runpod-noctq-v4-lora-text-to-image','runpod-noctq-v4-lora-single-image-edit']}))
"""
            result=subprocess.run(['python3','-B','-c',script,str(root/'runpod_workflows.py')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            options=json.loads(result.stdout);self.assertEqual(len(options),2)
            self.assertTrue(all(v==data['loras'] for v in options.values()))
