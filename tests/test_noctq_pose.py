import base64
import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from huashi.runpod import RunPodClient, make_payload
from huashi.runpod_workflows import RUNPOD_APPS, WORKFLOWS
from tests import test_noctq
from tests.test_runpod import FakeRunPod

APP = 'runpod-noctq-v4-lora-pose-transfer'
KEY = 'noctq-v4-lora-pose-transfer'
SOURCE_SHA256 = '70b64edd32008bb176f2c1b2aa1083fea0ae03345d3b9ffa3d7257c4339ec055'


def image_bytes(size, color):
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, 'PNG')
    return buffer.getvalue()


class NoctQPoseTest(unittest.TestCase):
    def app(self):
        app = next((item for item in RUNPOD_APPS if item['id'] == APP), None)
        self.assertIsNotNone(app, '双图姿势迁移画布尚未注册')
        return app

    def test_source_graph_and_every_scalar_default_remain_exact(self):
        app = self.app()
        source = WORKFLOWS[KEY]['workflow_path'].read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), SOURCE_SHA256)
        graph = json.loads(source)
        self.assertEqual(len(graph), 10)
        self.assertEqual(app['workflow_key'], KEY)
        self.assertTrue(app['enabled'])
        self.assertEqual(WORKFLOWS[KEY]['max_input_edge'], 2048)
        inputs = app['inputs']
        self.assertEqual([(i['id'], i['nodeId'], i['label'], i['required']) for i in inputs if i['type'] == 'image'],
                         [('image1', '12', '人物原图', True), ('image2', '13', '姿势参考图', True)])
        self.assertFalse({'width', 'height', 'batch_size'} & {i['id'] for i in inputs})
        for item in inputs:
            if item['type'] != 'image':
                self.assertEqual(item['defaultValue'], str(graph[item['nodeId']]['inputs'][item['fieldName']]), item['id'])
        self.assertEqual(next(i['defaultValue'] for i in inputs if i['id'] == 'seed'), '134688284425031')
        old_ids = [test_noctq.APP, 'runpod-noctq-v4-lora-text-to-image', 'runpod-noctq-v4-single-image-edit', 'runpod-noctq-v4-lora-single-image-edit']
        self.assertTrue(all(next(a for a in RUNPOD_APPS if a['id'] == key)['enabled'] for key in old_ids))
        self.assertTrue(all(not next(a for a in RUNPOD_APPS if a['id'] == key)['enabled'] for key in test_noctq.LEGACY))

    def test_distinct_images_and_lora_scalars_reach_correct_ten_nodes(self):
        app = self.app()
        inputs = copy.deepcopy(app['inputs'])
        next(i for i in inputs if i['id'] == 'lora_name')['options'].append('future/pose.safetensors')
        values = {i['id']: i.get('defaultValue', '') for i in inputs}
        values.update(lora_name='future/pose.safetensors', lora_strength='0.85', seed='0', cfg='3.25', negative_prompt='', resolution='512')
        with tempfile.TemporaryDirectory() as tmp:
            sources = {key: Path(tmp) / (key + '.png') for key in ['image1', 'image2']}
            sources['image1'].write_bytes(image_bytes((80, 64), 'red'))
            sources['image2'].write_bytes(image_bytes((64, 96), 'blue'))
            originals = {key: path.read_bytes() for key, path in sources.items()}
            body = json.loads(make_payload(KEY, inputs, values, sources))['input']
            graph = body['workflow']
            self.assertEqual(set(graph), {'1', '2', '3', '4', '6', '7', '8', '11', '12', '13'})
            self.assertEqual(graph['4']['inputs']['images.image_1'], ['12', 0])
            self.assertEqual(graph['4']['inputs']['images.image_2'], ['13', 0])
            self.assertEqual(graph['6']['inputs']['latent_image'], ['4', 2])
            self.assertEqual(graph['6']['inputs']['model'], ['11', 0])
            self.assertEqual(graph['11']['inputs'], {'model': ['1', 0], 'lora_name': values['lora_name'], 'strength_model': 0.85})
            self.assertEqual((graph['4']['inputs']['negative_prompt'], graph['6']['inputs']['seed'], graph['6']['inputs']['cfg']), ('', 0, 3.25))
            for index, key in enumerate(['image1', 'image2']):
                self.assertEqual(graph[str(12 + index)]['inputs']['image'], body['images'][index]['name'])
                self.assertEqual(base64.b64decode(body['images'][index]['image']), originals[key])
                self.assertEqual(sources[key].read_bytes(), originals[key])
            self.assertNotEqual(body['images'][0]['image'], body['images'][1]['image'])

    def test_missing_or_invalid_images_leave_no_task_or_uploads(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = test_noctq.NoctQTest().service(root)
            valid = {f'input_{key}': {'filename': key + '.png', 'content': image_bytes((64, 64), color)}
                     for key, color in [('image1', 'red'), ('image2', 'blue')]}
            cases = [({}, {}), ({}, {'input_image1': valid['input_image1']}), ({}, {'input_image2': valid['input_image2']})]
            for key in ['image1', 'image2']:
                bad = copy.deepcopy(valid)
                bad[f'input_{key}']['content'] = b'not an image'
                cases.append(({}, bad))
                other = 'image2' if key == 'image1' else 'image1'
                cases.append(({f'input_{key}_artwork': '../outside.png'}, {f'input_{other}': valid[f'input_{other}']}))
            for fields, files in cases:
                with self.subTest(fields=fields, files=list(files)), self.assertRaises(ValueError):
                    service.create_task_from_form(APP, fields, files, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])
            self.assertEqual(list((root / 'uploads').rglob('*')), [])

    def test_invalid_scalars_leave_no_task_or_uploads(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = test_noctq.NoctQTest().service(root)
            valid = {f'input_{key}': {'filename': key + '.png', 'content': image_bytes((64, 64), color)}
                     for key, color in [('image1', 'red'), ('image2', 'blue')]}
            cases = [('lora_name', 'missing.safetensors'), ('lora_name', ''), ('lora_strength', 'nan'),
                     ('lora_strength', 'inf'), ('lora_strength', '101'), ('lora_strength', '-101'), ('lora_strength', ''),
                     ('cfg', 'nan'), ('cfg', '-1'), ('denoise', '1.1'), ('resolution', '-1'), ('steps', '0'),
                     ('sampler', 'missing'), ('scheduler', 'missing'), ('seed', str(2**64)), ('seed', '1.5'), ('prompt', '')]
            for key, value in cases:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    service.create_task_from_form(APP, {'input_' + key: value}, valid, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])
            self.assertEqual(list((root / 'uploads').rglob('*')), [])

    def test_gallery_retry_dual_inputs_zero_values_and_disposable_jpegs(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = test_noctq.NoctQTest().service(root)
            originals = {key: root / 'cache' / (key + '.png') for key in ['image1', 'image2']}
            originals['image1'].write_bytes(image_bytes((2600, 900), 'red'))
            originals['image2'].write_bytes(image_bytes((800, 2400), 'blue'))
            digests = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in originals.items()}
            for gallery_key in ['image1', 'image2']:
                upload_key = 'image2' if gallery_key == 'image1' else 'image1'
                fields = {f'input_{gallery_key}_artwork': 'cache/' + gallery_key + '.png', 'input_lora_strength': '0',
                          'input_seed': '0', 'input_cfg': '0', 'input_denoise': '0', 'input_resolution': '0', 'input_negative_prompt': ''}
                files = {f'input_{upload_key}': {'filename': upload_key + '.png', 'content': originals[upload_key].read_bytes()}}
                task = service.create_task_from_form(APP, fields, files, start_background=False)
                payload = copy.deepcopy(task['input_payload'])
                self.assertEqual(set(payload['files']), {'image1', 'image2'})
                self.assertEqual(payload['files'][gallery_key]['source'], 'artwork')
                self.assertEqual(payload['files'][upload_key]['source'], 'upload')
                self.assertEqual([payload['values'][key] for key in ['lora_strength', 'seed', 'cfg', 'denoise', 'resolution', 'negative_prompt']], ['0', '0', '0', '0', '0', ''])
                service.store.initialize()
                self.assertEqual(service.store.get_task(task['id'])['input_payload'], payload)
                retry = service.retry_task(task['id'], start_background=False)
                self.assertEqual(retry['input_payload']['values'], payload['values'])
                self.assertEqual(set(retry['input_payload']['files']), {'image1', 'image2'})
                for key in originals:
                    retry_file = retry['input_payload']['files'][key]
                    self.assertEqual(retry_file['name'], payload['files'][key]['name'])
                    self.assertEqual(hashlib.sha256((root / retry_file['path']).read_bytes()).hexdigest(), digests[key])
                fake = FakeRunPod()
                with patch.object(RunPodClient, 'from_workflow', return_value=fake):
                    result = service.process_task(retry['id'], poll_interval=0, timeout=1)
                self.assertEqual(result['status'], 'success', result.get('error'))
                graph = fake.payload['input']['workflow']
                self.assertEqual(graph['11']['inputs']['strength_model'], 0)
                self.assertEqual(graph['6']['inputs']['seed'], 0)
                self.assertEqual(graph['4']['inputs']['negative_prompt'], '')
                for index, key in enumerate(['image1', 'image2']):
                    self.assertEqual(graph[str(12 + index)]['inputs']['image'], f'input_{index + 1}.jpg')
                    data = base64.b64decode(fake.payload['input']['images'][index]['image'])
                    with Image.open(io.BytesIO(data)) as prepared:
                        self.assertEqual(prepared.format, 'JPEG')
                        self.assertEqual(max(prepared.size), 2048)
                        pixel = prepared.getpixel((0, 0))
                        self.assertGreater(pixel[0 if key == 'image1' else 2], 240)
                    self.assertEqual(hashlib.sha256((root / payload['files'][key]['path']).read_bytes()).hexdigest(), digests[key])
                    self.assertEqual(hashlib.sha256(originals[key].read_bytes()).hexdigest(), digests[key])
                self.assertEqual(list((root / 'tmp').iterdir()), [])
                self.assertTrue(any(i['task_id'] == retry['id'] for i in service.list_album_items('works')))

    def test_shared_catalog_extends_all_three_lora_dropdowns(self):
        self.app()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy2(test_noctq.ROOT / 'huashi/runpod_workflows.py', root / 'runpod_workflows.py')
            shutil.copytree(test_noctq.ROOT / 'huashi/workflows', root / 'workflows')
            catalog = root / 'workflows/noctq-v4-loras.json'
            data = json.loads(catalog.read_text())
            data['loras'].append('future/pose style.safetensors')
            catalog.write_text(json.dumps(data))
            script = '''
import importlib.util,json,sys
spec=importlib.util.spec_from_file_location('isolated',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
print(json.dumps({a['id']:next(i for i in a['inputs'] if i['id']=='lora_name')['options'] for a in m.RUNPOD_APPS if a['enabled'] and any(i['id']=='lora_name' for i in a['inputs'])}))
'''
            result = subprocess.run([sys.executable, '-B', '-c', script, str(root / 'runpod_workflows.py')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            options = json.loads(result.stdout)
            self.assertEqual(set(options), {'runpod-noctq-v4-lora-text-to-image', 'runpod-noctq-v4-lora-single-image-edit', APP})
            self.assertTrue(all(names == data['loras'] for names in options.values()))
