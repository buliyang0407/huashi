import hashlib
import copy
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None

from huashi.runpod import RunPodClient, RunPodError, RunPodSubmissionUnknown, make_payload, prepare_image
from huashi.service import HuashiService
from huashi.server import make_handler
from huashi.storage import HuashiStore
from huashi.runpod_workflows import RUNPOD_APPS


APP_ID = "runpod-qwen21-two-image-edit"
T2I_APP_ID = "runpod-qwen21-text-to-image"
SINGLE_APP_ID = "runpod-qwen21-single-image-edit"


def png_bytes(size=(48, 48)):
    data = io.BytesIO()
    Image.new("RGB", size, "#aa66cc").save(data, "PNG")
    return data.getvalue()


class FakeRunPod:
    def __init__(self, *, preflight_error=False, submit_unknown=False):
        self.preflight_error = preflight_error
        self.submit_unknown = submit_unknown
        self.calls = []

    def check_connection(self):
        self.calls.append("check")
        if self.preflight_error:
            raise RunPodError("Mac Mini 代理不可用；任务尚未提交 RunPod，未启动远端 GPU")

    def submit(self, payload):
        self.calls.append("submit")
        self.payload = json.loads(payload)
        if self.submit_unknown:
            raise RunPodSubmissionUnknown("提交结果未知")
        return "job_123"

    def wait(self, job_id, on_status, poll_interval, timeout):
        self.calls.append("wait")
        on_status("IN_QUEUE")
        on_status("IN_PROGRESS")
        on_status("COMPLETED")
        import base64
        return {"output": {"images": [{"type": "base64", "data": base64.b64encode(png_bytes()).decode()}]}}


@unittest.skipIf(Image is None, "Pillow is not installed in this Python environment")
class RunPodTest(unittest.TestCase):
    def setUp(self):
        # Exercise the retained legacy transport in an isolated historical configuration.
        # Actual retirement and refusal of old submissions are covered by test_noctq.
        apps = copy.deepcopy(RUNPOD_APPS)
        for app in apps:
            if app["id"] in {APP_ID, T2I_APP_ID, SINGLE_APP_ID}:
                app["enabled"] = True
        legacy_config = patch("huashi.storage.RUNPOD_APPS", apps)
        legacy_config.start()
        self.addCleanup(legacy_config.stop)

    def make_service(self, root):
        store = HuashiStore(root / "db.sqlite")
        store.initialize()
        return HuashiService(root, store, object())

    def make_task(self, service):
        return service.create_task_from_form(
            APP_ID,
            {"input_prompt": "Combine <image1> and <image2>", "input_width": "512", "input_height": "512", "input_steps": "4", "input_seed": "42", "input_canvas": "custom"},
            {"input_image1": {"filename": "one.png", "content": png_bytes((2500, 1000))},
             "input_image2": {"filename": "two.png", "content": png_bytes()}},
            start_background=False,
        )

    def test_all_three_apps_persist_sampling_defaults_and_keep_history_on_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            single = service.store.get_app(SINGLE_APP_ID) if SINGLE_APP_ID in [a["id"] for a in service.store.list_apps()] else None
            self.assertIsNotNone(single, "单图编辑应用尚未接入")
            for app_id, expected_steps, scheduler in ((APP_ID, "25", "beta"), (T2I_APP_ID, "25", "simple"), (SINGLE_APP_ID, "30", "beta")):
                with self.subTest(app_id=app_id):
                    task = service.create_task_from_form(app_id, {"input_prompt": "test", "input_seed": "0"}, {}, start_background=False)
                    values = task["input_payload"]["values"]
                    self.assertEqual({k:values[k] for k in ("sampler", "scheduler", "steps", "seed")}, {"sampler":"euler", "scheduler":scheduler, "steps":expected_steps, "seed":"0"})
                    task_id = task["id"]
                    service.store.initialize()
                    self.assertEqual(service.store.get_task(task_id)["input_payload"]["values"], values)
                    retry = service.retry_task(task_id, start_background=False)
                    self.assertEqual(retry["input_payload"]["values"], values)

    def test_single_image_reference_and_custom_dimensions_preserve_original(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            self.assertIn(SINGLE_APP_ID, [a["id"] for a in service.store.list_apps()], "单图编辑应用尚未接入")
            original = png_bytes((2560, 1920))
            task = service.create_task_from_form(SINGLE_APP_ID, {"input_prompt":"Turn the chair blue", "input_seed":"0"}, {"input_image1":{"filename":"source.png", "content":original}}, start_background=False)
            app = service.store.get_app(SINGLE_APP_ID)
            fake = FakeRunPod()
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                completed = service.process_task(task["id"], poll_interval=0, timeout=1)
            self.assertEqual(completed["status"], "success")
            self.assertEqual((root/task["input_payload"]["files"]["image1"]["path"]).read_bytes(), original)
            body = fake.payload["input"]
            self.assertEqual(len(body["images"]), 1)
            workflow = body["workflow"]
            self.assertEqual(len(workflow), 11)
            self.assertFalse(workflow["459:468"]["inputs"]["switch"])
            self.assertEqual(workflow["459:468"]["inputs"]["on_false"], ["459:474", 2])
            self.assertEqual(workflow["459:474"]["inputs"]["resolution"], 0)
            self.assertEqual(workflow["459:474"]["inputs"]["prompt"], "Turn the chair blue")
            self.assertNotIn("images.image_2", workflow["459:474"]["inputs"])
            self.assertEqual(workflow["461"]["class_type"], "SaveImage")
            self.assertEqual(workflow["459:458"]["inputs"]["steps"], 30)
            self.assertEqual(workflow["459:458"]["inputs"]["cfg"], 1)
            self.assertEqual(workflow["459:458"]["inputs"]["denoise"], 1)
            self.assertEqual(service.list_album_items("works")[0]["task_id"], task["id"])
            self.assertEqual(list((root/"tmp").iterdir()), [])
            import base64
            with Image.open(io.BytesIO(base64.b64decode(body["images"][0]["image"]))) as prepared:
                self.assertEqual(prepared.size, (2048,1536))
            input_file = root/"small.jpg";input_file.write_bytes(png_bytes())
            values = {**task["input_payload"]["values"], "canvas":"自定义尺寸", "width":"512", "height":"768"}
            custom = json.loads(make_payload(app["workflow_key"], app["inputs"], values, {"image1":input_file}))["input"]["workflow"]
            self.assertTrue(custom["459:468"]["inputs"]["switch"])
            self.assertEqual(custom["459:456"]["inputs"]["width"], 512)
            self.assertEqual(custom["459:456"]["inputs"]["height"], 768)
            for node in workflow.values():
                for value in node["inputs"].values():
                    if isinstance(value,list): self.assertIn(value[0], workflow)

    def test_sampling_options_map_to_workflow_and_invalid_choices_fail_before_submission(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);service = self.make_service(root)
            source = root/"small.jpg";source.write_bytes(png_bytes())
            for app_id in (APP_ID,T2I_APP_ID):
                app = service.store.get_app(app_id)
                self.assertIn("sampler", [i["id"] for i in app["inputs"]], "采样器字段尚未接入")
            for app_id in (APP_ID,T2I_APP_ID,SINGLE_APP_ID):
                app = service.store.get_app(app_id)
                for sampler in ("euler","euler_ancestral","dpmpp_2m","dpmpp_2m_sde"):
                    for scheduler in ("beta","simple","normal","karras"):
                        body = json.loads(make_payload(app["workflow_key"], app["inputs"], {"prompt":"test","width":"512","height":"512","steps":"31","seed":"0","sampler":sampler,"scheduler":scheduler}, {"image1":source,"image2":source}))
                        sampling = body["input"]["workflow"]["459:458"]["inputs"]
                        self.assertEqual((sampling["sampler_name"],sampling["scheduler"],sampling["steps"],sampling["seed"]),(sampler,scheduler,31,0))
                for key in ("sampler","scheduler"):
                    task = service.create_task_from_form(app_id,{"input_prompt":"test", "input_seed":"0",f"input_{key}":"unsupported"}, {f"input_{k}":{"filename":"small.png","content":png_bytes()} for k in ("image1","image2")},start_background=False)
                    fake = FakeRunPod()
                    with patch.object(RunPodClient,"from_workflow",return_value=fake): failed=service.process_task(task["id"])
                    self.assertEqual(failed["status"],"failed")
                    self.assertEqual(failed["remote_submission_state"],"not_submitted")
                    self.assertEqual(fake.calls,[])

    def test_nondefault_sampling_history_matches_submitted_request_and_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            for app_id in (APP_ID,T2I_APP_ID,SINGLE_APP_ID):
                with self.subTest(app_id=app_id):
                    fields={"input_prompt":"test","input_seed":"0","input_steps":"31","input_sampler":"dpmpp_2m_sde","input_scheduler":"karras"}
                    files={f"input_{key}":{"filename":"source.png","content":png_bytes()} for key in ("image1","image2")}
                    task=service.create_task_from_form(app_id,fields,files,start_background=False)
                    fake=FakeRunPod()
                    with patch.object(RunPodClient,"from_workflow",return_value=fake): completed=service.process_task(task["id"],poll_interval=0,timeout=1)
                    self.assertEqual(completed["status"],"success")
                    history=service.store.get_task(task["id"])["input_payload"]["values"]
                    self.assertEqual({k:history[k] for k in ("sampler","scheduler","steps","seed")},{"sampler":"dpmpp_2m_sde","scheduler":"karras","steps":"31","seed":"0"})
                    sampling=fake.payload["input"]["workflow"]["459:458"]["inputs"]
                    self.assertEqual((sampling["sampler_name"],sampling["scheduler"],sampling["steps"],sampling["seed"]),("dpmpp_2m_sde","karras",31,0))
                    retry=service.retry_task(task["id"],start_background=False)
                    self.assertEqual(retry["input_payload"]["values"],history)

    def test_text_to_image_random_seed_is_persisted_and_retry_keeps_it(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            fields = {"input_prompt": "A red boat", "input_width": "512", "input_height": "512"}
            with patch("huashi.service.secrets.randbits", side_effect=[123456, 654321]) as random_seed:
                first = service.create_task_from_form(T2I_APP_ID, fields, {}, start_background=False)
                second = service.create_task_from_form(T2I_APP_ID, fields, {}, start_background=False)
                retry = service.retry_task(first["id"], start_background=False)
                self.assertEqual(random_seed.call_count, 2)
            self.assertEqual(first["input_payload"]["values"]["seed"], "123456")
            self.assertEqual(second["input_payload"]["values"]["seed"], "654321")
            self.assertEqual(retry["input_payload"]["values"]["seed"], "123456")
            self.assertEqual(first["input_payload"]["values"]["steps"], "25")
            self.assertNotIn("input_seed", fields)
            fake = FakeRunPod()
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                completed = service.process_task(first["id"], poll_interval=0, timeout=1)
            self.assertEqual(completed["status"], "success")
            self.assertEqual(fake.payload["input"]["images"], [])
            self.assertEqual(fake.payload["input"]["workflow"]["459:458"]["inputs"]["seed"], 123456)
            self.assertEqual(service.list_album_items("works")[0]["task_id"], first["id"])
            self.assertEqual(service.store.get_task(first["id"])["input_payload"]["values"]["seed"], "123456")

    def test_text_to_image_fixed_seed_and_editable_parameters(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            app = service.store.get_app(T2I_APP_ID)
            self.assertEqual([item["id"] for item in app["inputs"]], ["prompt", "width", "height", "steps", "seed", "sampler", "scheduler"])
            for seed in (0, 2**64 - 1):
                with self.subTest(seed=seed), patch("huashi.service.secrets.randbits") as random_seed:
                    task = service.create_task_from_form(T2I_APP_ID, {
                        "input_prompt": "A blue boat", "input_width": "512", "input_height": "768",
                        "input_steps": "37", "input_seed": str(seed),
                    }, {}, start_background=False)
                    random_seed.assert_not_called()
                    self.assertEqual(task["input_payload"]["values"]["seed"], str(seed))
                    workflow = json.loads(make_payload(app["workflow_key"], app["inputs"], task["input_payload"]["values"], {}))["input"]["workflow"]
                    self.assertEqual(workflow["459:452"]["inputs"]["prompt"], "A blue boat")
                    self.assertEqual(workflow["459:456"]["inputs"]["width"], 512)
                    self.assertEqual(workflow["459:456"]["inputs"]["height"], 768)
                    self.assertEqual(workflow["459:458"]["inputs"]["steps"], 37)
                    self.assertEqual(workflow["459:458"]["inputs"]["seed"], seed)
            self.assertEqual(len(workflow), 9)
            self.assertEqual(workflow["461"]["class_type"], "SaveImage")
            self.assertEqual(set(workflow["461"]["inputs"]), {"filename_prefix", "images"})
            self.assertEqual(workflow["459:458"]["inputs"]["cfg"], 1)
            self.assertEqual(workflow["459:458"]["inputs"]["sampler_name"], "euler")
            self.assertEqual(workflow["459:458"]["inputs"]["scheduler"], "simple")
            self.assertEqual(workflow["459:480"]["inputs"]["device"], "gpu")
            for node in workflow.values():
                for value in node["inputs"].values():
                    if isinstance(value, list):
                        self.assertIn(value[0], workflow)

    def test_text_to_image_rejects_invalid_seed_before_creating_task(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            for seed in ("-1", str(2**64), "1.5", "abc"):
                with self.subTest(seed=seed), self.assertRaises(ValueError):
                    service.create_task_from_form(T2I_APP_ID, {"input_prompt": "test", "input_seed": seed}, {}, start_background=False)
            self.assertEqual(service.store.list_tasks(), [])
            app = service.store.get_app(T2I_APP_ID)
            with self.assertRaisesRegex(ValueError, "尚未确定"):
                make_payload(app["workflow_key"], app["inputs"], {"prompt": "test"}, {})

    def test_shared_tasks_api_accepts_no_files_and_reports_invalid_seed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = self.make_service(root)
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service, root, root))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            opener = build_opener(ProxyHandler({}))
            def request(seed):
                fields = {"appId": T2I_APP_ID, "input_prompt": "A boat", "input_seed": seed}
                body = "".join(f'--huashi-test\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n' for key, value in fields.items()) + "--huashi-test--\r\n"
                return Request(f"http://127.0.0.1:{server.server_port}/api/tasks", data=body.encode(), headers={"Content-Type": "multipart/form-data; boundary=huashi-test"})
            try:
                with patch.object(service, "process_task"), patch("huashi.service.secrets.randbits", return_value=876543):
                    with self.assertRaises(HTTPError) as caught:
                        opener.open(request("-1"), timeout=5)
                    self.assertEqual(caught.exception.code, 400)
                    self.assertIn("随机种子", json.load(caught.exception)["error"])
                    self.assertEqual(service.store.list_tasks(), [])
                    with opener.open(request(""), timeout=5) as response:
                        self.assertEqual(response.status, 201)
                        task = json.load(response)["task"]
                    self.assertEqual(task["provider"], "runpod")
                    self.assertEqual(task["input_payload"]["files"], {})
                    self.assertEqual(task["input_payload"]["values"]["seed"], "876543")
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_preparation_preserves_original_and_maps_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.png"
            original.write_bytes(png_bytes((2500, 1000)))
            before = hashlib.sha256(original.read_bytes()).digest()
            prepared = prepare_image(original, root / "temporary.jpg")
            with Image.open(prepared) as image:
                self.assertEqual(max(image.size), 2048)
            self.assertEqual(hashlib.sha256(original.read_bytes()).digest(), before)
            service = self.make_service(root)
            app = service.store.get_app(APP_ID)
            payload = make_payload(app["workflow_key"], app["inputs"],
                                   {"prompt": "test", "width": "512", "height": "512", "steps": "4", "seed": "42", "canvas": "custom"},
                                   {"image1": prepared, "image2": prepared})
            import json
            body = json.loads(payload)
            workflow = body["input"]["workflow"]
            self.assertEqual(workflow["459:474"]["inputs"]["prompt"], "test")
            self.assertEqual(workflow["459:456"]["inputs"]["width"], 512)
            self.assertTrue(workflow["459:468"]["inputs"]["switch"])
            self.assertEqual(len(body["input"]["images"]), 2)

    def test_success_uses_shared_history_cache_and_album(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            task = self.make_task(service)
            fake = FakeRunPod()
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                completed = service.process_task(task["id"], poll_interval=0, timeout=1)
            self.assertEqual(completed["status"], "success")
            self.assertEqual(completed["provider"], "runpod")
            self.assertEqual(completed["runpod_job_id"], "job_123")
            self.assertEqual(completed["remote_status"], "COMPLETED")
            self.assertEqual(completed["remote_submission_state"], "submitted")
            self.assertTrue((Path(temp) / completed["outputs"][0]["path"]).exists())
            self.assertEqual(service.list_task_summaries()[0]["provider"], "runpod")
            self.assertEqual(service.list_album_items("works")[0]["task_id"], task["id"])
            self.assertEqual(list((Path(temp) / "tmp").iterdir()), [])
            self.assertEqual(fake.calls, ["check", "submit", "wait"])

    def test_preflight_failure_never_submits(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            task = self.make_task(service)
            fake = FakeRunPod(preflight_error=True)
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                failed = service.process_task(task["id"])
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["remote_submission_state"], "not_submitted")
            self.assertEqual(fake.calls, ["check"])

    def test_ambiguous_post_never_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            task = self.make_task(service)
            fake = FakeRunPod(submit_unknown=True)
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                failed = service.process_task(task["id"])
            self.assertEqual(failed["stage"], "submission_unknown")
            self.assertEqual(failed["remote_submission_state"], "unknown")
            self.assertEqual(fake.calls, ["check", "submit"])

    def test_restart_marks_ambiguous_submission_without_resubmitting(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            task = self.make_task(service)
            service.store.update_task(task["id"], status="running", stage="submitting", remote_submission_state="unknown")
            with patch.object(RunPodClient, "from_workflow") as client_factory:
                service.resume_runpod_tasks()
            recovered = service.store.get_task(task["id"])
            self.assertEqual(recovered["status"], "failed")
            self.assertEqual(recovered["stage"], "submission_unknown")
            self.assertEqual(recovered["remote_submission_state"], "unknown")
            client_factory.assert_not_called()

    def test_known_job_resumes_status_polling_without_new_post(self):
        with tempfile.TemporaryDirectory() as temp:
            service = self.make_service(Path(temp))
            task = self.make_task(service)
            service.store.update_task(task["id"], status="running", runpod_job_id="job_123", remote_submission_state="submitted")
            fake = FakeRunPod()
            with patch.object(RunPodClient, "from_workflow", return_value=fake):
                completed = service.process_task(task["id"], poll_interval=0, timeout=1)
            self.assertEqual(completed["status"], "success")
            self.assertEqual(fake.calls, ["wait"])


if __name__ == "__main__":
    unittest.main()
