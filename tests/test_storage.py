import tempfile
import unittest
from pathlib import Path

from huashi.storage import HuashiStore


class StorageTest(unittest.TestCase):
    def test_store_seeds_runninghub_apps_and_persists_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()

            apps = store.list_apps()
            self.assertEqual([app["id"] for app in apps], ["effect-png", "private-zip"])
            self.assertEqual(apps[0]["name"], "3D微缩模型转换器")
            self.assertEqual(store.get_app("private-zip")["output_type"], "zip")
            self.assertEqual(store.get_app("private-zip")["name"], "高级换装")
            self.assertEqual(store.get_app("effect-png")["source_url"], "https://www.runninghub.cn/ai-detail/2014608238859259906")

            task = store.create_task(
                app_id="private-zip",
                input_path="uploads/input.png",
                input_name="input.png",
                prompt="换一套蓝色西装",
            )
            store.update_task(
                task["id"],
                status="success",
                runninghub_task_id="rh-task",
                output_type="zip",
                cache_path="cache/task",
                outputs=[{"path": "cache/task/result.zip", "type": "zip"}],
            )

            saved = store.get_task(task["id"])
            self.assertEqual(saved["status"], "success")
            self.assertEqual(saved["runninghub_task_id"], "rh-task")
            self.assertEqual(saved["outputs"][0]["type"], "zip")
            self.assertEqual(saved["prompt"], "换一套蓝色西装")
            self.assertEqual(store.list_tasks()[0]["id"], task["id"])

    def test_store_can_add_and_disable_custom_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()

            app = store.save_app(
                {
                    "name": "真人照片卡通化",
                    "description": "卡通头像",
                    "webapp_id": "123",
                    "node_id": "9",
                    "field_name": "image",
                    "output_type": "png",
                    "category": "卡通化",
                    "favorite": "on",
                    "enabled": "on",
                    "cover_path": "covers/avatar/cover.png",
                    "prompt_node_id": "12",
                    "prompt_field_name": "prompt",
                    "default_prompt": "清新",
                }
            )

            self.assertEqual(app["name"], "真人照片卡通化")
            self.assertEqual(app["cover_url"], "/files/covers/avatar/cover.png")
            self.assertTrue(app["favorite"])
            self.assertEqual([item["type"] for item in app["inputs"]], ["image", "textarea"])

            disabled = store.disable_app(app["id"])
            self.assertFalse(disabled["enabled"])
            self.assertNotIn(app["id"], [item["id"] for item in store.list_apps()])

    def test_store_can_save_text_only_style_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()

            app = store.save_app(
                {
                    "name": "地名生成",
                    "description": "输入地名",
                    "webapp_id": "2012800641969688578",
                    "output_type": "png",
                    "category": "文字生成",
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
                        }
                    ],
                }
            )

            self.assertEqual(app["inputs"][0]["type"], "textarea")
            self.assertEqual(app["node_id"], "")


if __name__ == "__main__":
    unittest.main()
