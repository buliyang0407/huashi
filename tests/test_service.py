import tempfile
import unittest
import zipfile
from pathlib import Path

from huashi.service import HuashiService
from huashi.runninghub import RunningHubError
from huashi.storage import HuashiStore


class FakeRunningHubClient:
    def __init__(self, output_path):
        self.output_path = Path(output_path)
        self.node_info_list = []

    def upload_media(self, file_path):
        return "runninghub/uploaded/input.png"

    def run_app(self, webapp_id, node_id, field_name, field_value, extra_nodes=None):
        self.extra_nodes = extra_nodes or []
        self.node_info_list = [{"nodeId": node_id, "fieldName": field_name, "fieldValue": field_value}, *self.extra_nodes]
        return {"taskId": "rh-task-1", "taskStatus": "RUNNING"}

    def run_app_nodes(self, webapp_id, node_info_list):
        self.node_info_list = node_info_list
        self.extra_nodes = node_info_list[1:]
        return {"taskId": "rh-task-1", "taskStatus": "RUNNING"}

    def wait_for_success(self, task_id, poll_interval=5, timeout=600):
        return "SUCCESS"

    def get_outputs(self, task_id):
        return [{"fileType": "zip", "nodeId": "206", "fileUrl": "fake://result.zip"}]

    def download_file(self, url, destination):
        destination.write_bytes(self.output_path.read_bytes())


class MissingKeyClient:
    api_key = ""

    def upload_media(self, file_path):
        raise RunningHubError("RUNNINGHUB_API_KEY is not configured.")


class ServiceTest(unittest.TestCase):
    def test_service_processes_zip_task_into_gallery_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")
                archive.writestr("nested/two.jpg", b"two")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            service = HuashiService(root, store, FakeRunningHubClient(zip_path))

            task = service.create_task_from_upload(
                app_id="private-zip",
                filename="input.png",
                content=b"input-image",
                start_background=False,
            )
            completed = service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(completed["status"], "success")
            self.assertEqual(completed["output_type"], "zip")
            self.assertTrue((root / completed["cache_path"] / "original.zip").exists())
            extracted = [item["path"] for item in completed["outputs"] if item["type"] == "image"]
            self.assertIn(str(Path(completed["cache_path"]) / "extracted" / "one.png"), extracted)
            self.assertIn(str(Path(completed["cache_path"]) / "extracted" / "nested" / "two.jpg"), extracted)

    def test_service_passes_optional_prompt_node_to_runninghub(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.get_app("private-zip")
            store.save_app(
                {
                    **app,
                    "prompt_node_id": "88",
                    "prompt_field_name": "prompt",
                },
                app_id=app["id"],
            )
            client = FakeRunningHubClient(zip_path)
            service = HuashiService(root, store, client)

            task = service.create_task_from_upload(
                app_id="private-zip",
                filename="input.png",
                content=b"input-image",
                prompt="赛博朋克风",
                start_background=False,
            )
            service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(
                client.extra_nodes,
                [{"nodeId": "88", "fieldName": "prompt", "fieldValue": "赛博朋克风"}],
            )

    def test_service_runs_dynamic_text_and_select_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "地标模型",
                    "description": "输入地名生成",
                    "webapp_id": "2012800641969688578",
                    "output_type": "png",
                    "category": "3D化",
                    "enabled": "on",
                    "inputs": [
                        {
                            "id": "field_1",
                            "nodeId": "20",
                            "fieldName": "default_value",
                            "type": "textarea",
                            "label": "国家/城市名",
                            "required": True,
                            "defaultValue": "杭州",
                            "options": [],
                        },
                        {
                            "id": "field_2",
                            "nodeId": "2",
                            "fieldName": "aspectRatio",
                            "type": "select",
                            "label": "图像比例",
                            "required": True,
                            "defaultValue": "4:3",
                            "options": ["1:1", "4:3"],
                        },
                    ],
                }
            )
            client = FakeRunningHubClient(zip_path)
            service = HuashiService(root, store, client)

            task = service.create_task_from_form(
                app_id=app["id"],
                fields={"input_field_1": "宁波", "input_field_2": "1:1"},
                files={},
                start_background=False,
            )
            service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(
                client.node_info_list,
                [
                    {"nodeId": "20", "fieldName": "default_value", "fieldValue": "宁波"},
                    {"nodeId": "2", "fieldName": "aspectRatio", "fieldValue": "1:1"},
                ],
            )

    def test_service_keeps_missing_api_key_error_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            service = HuashiService(root, store, MissingKeyClient())

            task = service.create_task_from_upload(
                app_id="effect-png",
                filename="input.png",
                content=b"input-image",
                start_background=False,
            )
            failed = service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["error"], "RUNNINGHUB_API_KEY is not configured.")

    def test_service_exports_and_imports_style_backups(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as target_tmp:
            source_root = Path(source_tmp)
            source_store = HuashiStore(source_root / "db.sqlite")
            source_store.initialize()
            source_service = HuashiService(source_root, source_store, MissingKeyClient())
            custom = source_store.save_app(
                {
                    "id": "custom-text-style",
                    "name": "文字生成城市",
                    "description": "输入地名",
                    "webapp_id": "2012800641969688578",
                    "output_type": "png",
                    "category": "文字生成",
                    "favorite": "1",
                    "enabled": "1",
                    "inputs": [
                        {
                            "id": "field_1",
                            "nodeId": "20",
                            "fieldName": "default_value",
                            "type": "textarea",
                            "label": "地名",
                            "required": True,
                            "defaultValue": "杭州",
                            "options": [],
                        }
                    ],
                },
                app_id="custom-text-style",
            )

            backup_path = source_service.write_apps_backup("test")
            bundle = source_service.export_apps_bundle()

            target_root = Path(target_tmp)
            target_store = HuashiStore(target_root / "db.sqlite")
            target_store.initialize()
            target_service = HuashiService(target_root, target_store, MissingKeyClient())
            result = target_service.import_apps_bundle(bundle)
            imported = target_store.get_app(custom["id"])

            self.assertTrue(backup_path.exists())
            self.assertEqual(result["count"], len(bundle["apps"]))
            self.assertEqual(imported["name"], "文字生成城市")
            self.assertTrue(imported["favorite"])
            self.assertEqual(imported["inputs"][0]["type"], "textarea")
            self.assertTrue((target_root / result["before_backup"]).exists())
            self.assertTrue((target_root / result["after_backup"]).exists())


if __name__ == "__main__":
    unittest.main()
