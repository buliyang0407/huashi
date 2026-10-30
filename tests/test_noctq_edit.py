import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huashi.runpod import RunPodClient, make_payload
from huashi.runpod_workflows import RUNPOD_APPS
from tests import test_noctq
from tests.test_runpod import FakeRunPod, png_bytes

APP = 'runpod-noctq-v4-single-image-edit'


class NoctQEditTest(unittest.TestCase):
    def app(self):
        app = next((a for a in RUNPOD_APPS if a['id'] == APP), None)
        self.assertIsNotNone(app, '单图编辑画布尚未注册')
        return app

    def test_image_and_sampling_reach_exact_source_graph(self):
        app = self.app()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.jpg'; source.write_bytes(png_bytes())
            before = source.read_bytes()
            values = {i['id']: i.get('defaultValue', '') for i in app['inputs']}
            values.update(seed='0', cfg='3.25', denoise='0.85', negative_prompt='', resolution='512')
            body = json.loads(make_payload(app['workflow_key'], app['inputs'], values, {'image1': source}))['input']
            graph = body['workflow']
            self.assertEqual(set(graph), {'1','2','3','4','6','7','8','12'})
            self.assertEqual(graph['12']['inputs']['image'], body['images'][0]['name'])
            self.assertEqual(graph['4']['inputs']['images.image_1'], ['12', 0])
            self.assertEqual(graph['6']['inputs']['latent_image'], ['4', 2])
            self.assertEqual(graph['6']['inputs']['model'], ['1', 0])
            self.assertEqual((graph['6']['inputs']['seed'], graph['6']['inputs']['cfg'], graph['6']['inputs']['denoise']), (0,3.25,0.85))
            self.assertEqual(graph['4']['inputs']['negative_prompt'], '')
            self.assertEqual(graph['4']['inputs']['resolution'], 512)
            self.assertFalse({'width','height','batch_size','lora_name'} & {i['id'] for i in app['inputs']})
            self.assertEqual(source.read_bytes(), before)

    def test_invalid_input_does_not_leave_task_rows(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            service = test_noctq.NoctQTest().service(Path(tmp))
            valid = {'input_image1': {'filename':'input.png', 'content':png_bytes()}}
            cases = [({'input_prompt':'test'}, {}),
                     ({'input_prompt':'test','input_image1_artwork':'../outside.png'}, {}),
                     ({'input_prompt':'test'}, {'input_image1':{'filename':'bad.png','content':b'bad'}})]
            for key, value in [('cfg','nan'),('denoise','1.1'),('sampler','missing'),('prompt',''),('resolution','-1')]:
                cases.append(({'input_prompt':'test','input_'+key:value},valid))
            for fields, files in cases:
                with self.subTest(fields=fields), self.assertRaises(ValueError):
                    service.create_task_from_form(APP, fields, files, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])

    def test_upload_and_gallery_retry_preserve_original_and_values(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); service = test_noctq.NoctQTest().service(root)
            original=root/'cache'/'original.png';original.write_bytes(png_bytes())
            digest=hashlib.sha256(original.read_bytes()).hexdigest()
            for source in ['upload','artwork']:
                fields={'input_prompt':'change the shirt to red','input_cfg':'3.25', 'input_denoise':'0.85', 'input_seed':'0','input_negative_prompt':'','input_resolution':'512'}
                files={'input_image1':{'filename':'test.png','content':original.read_bytes()}} if source=='upload' else {}
                if source=='artwork':fields['input_image1_artwork']='cache/original.png'
                task=service.create_task_from_form(APP,fields,files,start_background=False)
                self.assertEqual(task['input_payload']['files']['image1']['source'],source)
                values=copy.deepcopy(task['input_payload']['values'])
                self.assertEqual((values['seed'],values['negative_prompt']),('0',''))
                retry=service.retry_task(task['id'],start_background=False)
                self.assertEqual(retry['input_payload']['values'],values)
                fake=FakeRunPod()
                with patch.object(RunPodClient,'from_workflow',return_value=fake):
                    result=service.process_task(retry['id'],poll_interval=0,timeout=1)
                self.assertEqual(result['status'],'success',result.get('error'))
                self.assertEqual(fake.payload['input']['workflow']['12']['inputs']['image'],'input_1.jpg')
                self.assertTrue(any(i['task_id']==retry['id'] for i in service.list_album_items('works')))
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),digest)
