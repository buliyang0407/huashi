import tempfile
import unittest
import zipfile
from pathlib import Path

from huashi.service import HuashiService
from huashi.runninghub import RunningHubError
from huashi.runninghub import quote_url
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
    def test_quote_url_encodes_chinese_output_paths(self):
        self.assertEqual(
            quote_url("https://example.com/output/魔法书生_00001.png?x=1"),
            "https://example.com/output/%E9%AD%94%E6%B3%95%E4%B9%A6%E7%94%9F_00001.png?x=1",
        )

    def test_service_lists_pose_directory_lazily(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            pose = root / "pose"
            (pose / "SFWPose" / "standing").mkdir(parents=True)
            for index in range(22):
                (pose / "SFWPose" / "standing" / f"{index:02d}.png").write_bytes(b"png")
            store = HuashiStore(data / "db.sqlite")
            store.initialize()
            service = HuashiService(data, store, FakeRunningHubClient(root / "result.zip"))

            summary = service.pose_summary()
            self.assertEqual(summary["name"], "POSE")
            self.assertEqual(summary["directory_count"], 1)
            root_listing = service.list_pose_directory("")
            self.assertEqual(root_listing["directories"][0]["name"], "SFWPose")
            listing = service.list_pose_directory("SFWPose/standing", limit=1)
            self.assertEqual(len(listing["items"]), 20)
            self.assertEqual(listing["next_offset"], 20)
            self.assertTrue(listing["items"][0]["path"].startswith("pose:"))

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
            self.assertEqual(len(extracted), 2)
            self.assertTrue(all((root / path).exists() for path in extracted))
            self.assertTrue(all("高级换装" in Path(path).name for path in extracted))

    def test_service_saves_unique_cover_paths_and_album_uploads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            service = HuashiService(root, store, FakeRunningHubClient(root / "missing.zip"))

            first = service.save_cover("app-1", "cover.png", b"one")
            second = service.save_cover("app-1", "cover.png", b"two")
            self.assertNotEqual(first, second)
            self.assertTrue((root / first).exists())
            self.assertTrue((root / second).exists())

            folder = store.create_album_folder("参考")
            item = service.save_album_upload(folder["id"], "ref.jpg", b"jpg")
            self.assertEqual(item["folder_id"], folder["id"])
            self.assertTrue((root / item["path"]).exists())

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

    def test_service_clears_missing_optional_image_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "多图编辑",
                    "description": "可选参考图",
                    "webapp_id": "2046794946094571522",
                    "output_type": "png",
                    "category": "官方",
                    "enabled": "on",
                    "inputs": [
                        {"id": "field_1", "nodeId": "3", "fieldName": "image", "type": "image", "label": "上传图像1", "required": True},
                        {
                            "id": "field_2",
                            "nodeId": "2",
                            "fieldName": "image",
                            "type": "image",
                            "label": "上传图像2",
                            "required": False,
                            "defaultValue": "runninghub-default-demo.png",
                        },
                        {"id": "field_3", "nodeId": "4", "fieldName": "prompt", "type": "textarea", "label": "输入文本", "required": True},
                    ],
                }
            )
            client = FakeRunningHubClient(zip_path)
            service = HuashiService(root, store, client)

            task = service.create_task_from_form(
                app_id=app["id"],
                fields={"input_field_3": "换背景"},
                files={"input_field_1": {"filename": "one.png", "content": b"one"}},
                start_background=False,
            )
            service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(
                client.node_info_list,
                    [
                        {"nodeId": "3", "fieldName": "image", "fieldValue": "runninghub/uploaded/input.png"},
                        {"nodeId": "2", "fieldName": "image", "fieldValue": ""},
                        {"nodeId": "4", "fieldName": "prompt", "fieldValue": "换背景"},
                    ],
                )

    def test_service_resolves_output_type_from_selected_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "高级洗图",
                    "description": "去 AI 感",
                    "webapp_id": "2030207491971227650",
                    "output_type": "png",
                    "auto_unzip": True,
                    "category": "修图",
                    "enabled": "on",
                    "inputs": [
                        {"id": "field_1", "nodeId": "12", "fieldName": "image", "type": "image", "label": "图片", "required": True},
                        {"id": "field_3", "nodeId": "114", "fieldName": "select", "type": "hidden", "label": "加密方式", "required": True, "defaultValue": "2", "outputTypeMap": {"2": "zip"}},
                    ],
                }
            )
            client = FakeRunningHubClient(zip_path)
            service = HuashiService(root, store, client)

            task = service.create_task_from_form(
                app_id=app["id"],
                fields={"input_field_3": "2"},
                files={"input_field_1": {"filename": "one.png", "content": b"one"}},
                start_background=False,
            )
            completed = service.process_task(task["id"], poll_interval=0, timeout=1)

            self.assertEqual(completed["output_type"], "zip")
            self.assertTrue(any(item["type"] == "image" for item in completed["outputs"]))

    def test_service_can_reuse_artwork_as_new_image_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artwork = root / "cache" / "old-task" / "高级洗图-old-task-1.png"
            artwork.parent.mkdir(parents=True)
            artwork.write_bytes(b"old-artwork")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "图生图",
                    "description": "继续编辑作品",
                    "webapp_id": "2046794946094571522",
                    "output_type": "png",
                    "category": "官方",
                    "enabled": "on",
                    "inputs": [
                        {"id": "field_1", "nodeId": "3", "fieldName": "image", "type": "image", "label": "上传图像", "required": True},
                    ],
                }
            )
            service = HuashiService(root, store, MissingKeyClient())

            task = service.create_task_from_form(
                app_id=app["id"],
                fields={"input_field_1_artwork": "cache/old-task/高级洗图-old-task-1.png"},
                files={},
                start_background=False,
            )

            copied = root / task["input_path"]
            self.assertTrue(copied.exists())
            self.assertEqual(copied.read_bytes(), b"old-artwork")
            self.assertIn("高级洗图-old-task-1.png", task["input_name"])
            self.assertEqual(task["input_payload"]["files"]["field_1"]["source"], "artwork")

    def test_service_uses_unique_output_names_for_direct_and_extracted_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zip_path = root / "fake-result.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.png", b"one")

            store = HuashiStore(root / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "高级洗图",
                    "description": "去 AI 感",
                    "webapp_id": "2030207491971227650",
                    "output_type": "zip",
                    "auto_unzip": True,
                    "category": "修图",
                    "enabled": "on",
                    "inputs": [
                        {"id": "field_1", "nodeId": "12", "fieldName": "image", "type": "image", "label": "图片", "required": True},
                    ],
                }
            )
            service = HuashiService(root, store, FakeRunningHubClient(zip_path))
            task = service.create_task_from_form(
                app_id=app["id"],
                fields={},
                files={"input_field_1": {"filename": "one.png", "content": b"input"}},
                start_background=False,
            )
            completed = service.process_task(task["id"], poll_interval=0, timeout=1)

            image_outputs = [item for item in completed["outputs"] if item["type"] == "image"]
            self.assertEqual(len(image_outputs), 1)
            self.assertIn("高级洗图", Path(image_outputs[0]["path"]).name)
            self.assertIn(task["id"][:8], Path(image_outputs[0]["path"]).name)
            self.assertNotEqual(Path(image_outputs[0]["path"]).name, "one.png")

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
            self.assertEqual(bundle["kind"], "huashi-backup")
            self.assertEqual(result["count"], len(bundle["apps"]))
            self.assertEqual(result["prompt_count"], 0)
            self.assertEqual(imported["name"], "文字生成城市")
            self.assertTrue(imported["favorite"])
            self.assertEqual(imported["inputs"][0]["type"], "textarea")
            self.assertTrue((target_root / result["before_backup"]).exists())
            self.assertTrue((target_root / result["after_backup"]).exists())

    def test_service_exports_and_imports_prompt_library_with_app_links(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as target_tmp:
            source_root = Path(source_tmp)
            source_store = HuashiStore(source_root / "db.sqlite")
            source_store.initialize()
            source_service = HuashiService(source_root, source_store, MissingKeyClient())
            app = source_store.get_app("effect-png")
            prompt = source_store.save_prompt(
                {
                    "id": "poster-prompt",
                    "title": "电影感海报",
                    "content": "强烈电影光影，胶片颗粒",
                    "tags": ["海报", "电影感"],
                    "app_ids": [app["id"]],
                },
                prompt_id="poster-prompt",
            )
            source_store.save_prompt_variant(
                prompt["id"],
                {"id": "poster-blue", "title": "蓝色版", "content": "蓝色电影海报", "edit_idea": "蓝色为主"},
                variant_id="poster-blue",
            )
            bundle = source_service.export_apps_bundle()

            target_root = Path(target_tmp)
            target_store = HuashiStore(target_root / "db.sqlite")
            target_store.initialize()
            target_service = HuashiService(target_root, target_store, MissingKeyClient())
            result = target_service.import_apps_bundle(bundle)
            imported = target_store.get_prompt(prompt["id"])

            self.assertEqual(result["prompt_count"], 1)
            self.assertEqual(imported["title"], "电影感海报")
            self.assertEqual(imported["tags"], ["海报", "电影感"])
            self.assertEqual(imported["app_ids"], [app["id"]])
            self.assertEqual(imported["variants"][0]["id"], "poster-blue")
            self.assertEqual(imported["variants"][0]["content"], "蓝色电影海报")


if __name__ == "__main__":
    unittest.main()
