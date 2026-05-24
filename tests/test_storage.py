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

    def test_store_can_toggle_task_output_blur(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            task = store.create_task(
                app_id="effect-png",
                input_path="uploads/input.png",
                input_name="input.png",
            )
            store.update_task(
                task["id"],
                status="success",
                outputs=[
                    {"path": "cache/task/a.png", "url": "/files/cache/task/a.png", "type": "image"},
                    {"path": "cache/task/b.png", "url": "/files/cache/task/b.png", "type": "image"},
                ],
            )

            blurred = store.set_task_output_blurred(task["id"], "cache/task/a.png", True)
            self.assertTrue(blurred["outputs"][0]["blurred"])
            self.assertNotIn("blurred", blurred["outputs"][1])
            album_by_path = {item["path"]: item for item in store.list_album_items("works")}
            self.assertTrue(album_by_path["cache/task/a.png"]["blurred"])

            restored = store.set_task_output_blurred(task["id"], "cache/task/a.png", False)
            self.assertFalse(restored["outputs"][0]["blurred"])
            album_by_path = {item["path"]: item for item in store.list_album_items("works")}
            self.assertFalse(album_by_path["cache/task/a.png"]["blurred"])

    def test_store_can_add_and_delete_custom_style_without_losing_task_history(self):
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

            task = store.create_task(app_id=app["id"], input_path="uploads/input.png", input_name="input.png")
            store.update_task(task["id"], status="success", outputs=[{"path": "cache/task/a.png", "type": "image"}])
            deleted = store.delete_app(app["id"])
            self.assertEqual(deleted["id"], app["id"])
            self.assertNotIn(app["id"], [item["id"] for item in store.list_apps()])
            self.assertEqual(store.list_tasks()[0]["app_name"], "已删除应用")

    def test_store_uses_default_app_cover_when_cover_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            app = store.save_app(
                {
                    "name": "无封面应用",
                    "description": "默认图标",
                    "webapp_id": "321",
                    "node_id": "9",
                    "field_name": "image",
                    "output_type": "png",
                    "category": "其他",
                    "enabled": "on",
                }
            )

            self.assertEqual(app["cover_url"], "/default-app-icon.png")

    def test_store_can_soft_delete_task_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            task = store.create_task(
                app_id="effect-png",
                input_path="uploads/input.png",
                input_name="input.png",
            )
            store.update_task(
                task["id"],
                status="success",
                outputs=[
                    {"path": "cache/task/a.png", "url": "/files/cache/task/a.png", "type": "image"},
                    {"path": "cache/task/b.png", "url": "/files/cache/task/b.png", "type": "image"},
                ],
            )

            updated = store.set_task_output_deleted(task["id"], "cache/task/a.png", True)
            self.assertTrue(updated["outputs"][0]["deleted"])
            self.assertNotIn("deleted", updated["outputs"][1])

    def test_store_syncs_generated_outputs_into_album_and_reorders(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            task = store.create_task(
                app_id="effect-png",
                input_path="uploads/input.png",
                input_name="input.png",
            )
            store.update_task(
                task["id"],
                status="success",
                outputs=[
                    {"path": "cache/task/a.png", "url": "/files/cache/task/a.png", "type": "image"},
                    {"path": "cache/task/b.png", "url": "/files/cache/task/b.png", "type": "image"},
                ],
            )

            items = store.list_album_items("works")
            self.assertEqual([item["path"] for item in items], ["cache/task/b.png", "cache/task/a.png"])
            store.reorder_album_item(items[1]["id"], "up")
            reordered = store.list_album_items("works")
            self.assertEqual([item["path"] for item in reordered], ["cache/task/a.png", "cache/task/b.png"])
            store.position_album_item(reordered[0]["id"], 1)
            positioned = store.list_album_items("works")
            self.assertEqual([item["path"] for item in positioned], ["cache/task/b.png", "cache/task/a.png"])

    def test_store_can_create_folder_upload_move_and_delete_album_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            folder = store.create_album_folder("参考图")
            item = store.save_album_upload(folder["id"], "albums/uploads/ref.png", "ref.png")
            self.assertEqual(item["folder_id"], folder["id"])
            self.assertEqual(store.list_album_folders()[1]["name"], "参考图")

            moved = store.move_album_item(item["id"], "works")
            self.assertEqual(moved["folder_id"], "works")
            store.soft_delete_album_item(item["id"])
            self.assertEqual(store.list_album_items("works"), [])

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

    def test_store_preserves_input_output_type_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()

            app = store.save_app(
                {
                    "name": "高级洗图",
                    "description": "去 AI 感",
                    "webapp_id": "2030207491971227650",
                    "output_type": "png",
                    "category": "修图",
                    "enabled": "on",
                    "inputs": [
                        {
                            "id": "field_3",
                            "nodeId": "114",
                            "fieldName": "select",
                            "type": "hidden",
                            "label": "加密方式",
                            "defaultValue": "2",
                            "options": ["2"],
                            "outputTypeMap": {"2": "zip", "bad": "exe"},
                        }
                    ],
                }
            )

            self.assertEqual(app["inputs"][0]["type"], "hidden")
            self.assertEqual(app["inputs"][0]["outputTypeMap"], {"2": "zip"})

    def test_store_marks_prompt_inputs_and_saves_prompt_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()

            app = store.save_app(
                {
                    "name": "GPT 图生图",
                    "description": "图像编辑",
                    "webapp_id": "2046794946094571522",
                    "output_type": "png",
                    "category": "官方",
                    "enabled": "on",
                    "inputs": [
                        {
                            "id": "field_1",
                            "nodeId": "3",
                            "fieldName": "image",
                            "type": "image",
                            "label": "上传图像",
                            "required": True,
                        },
                        {
                            "id": "field_2",
                            "nodeId": "4",
                            "fieldName": "prompt",
                            "type": "textarea",
                            "label": "输入文本",
                            "required": True,
                            "defaultValue": "变成海报",
                        },
                    ],
                }
            )

            self.assertEqual(app["prompt_node_id"], "4")
            self.assertEqual(app["prompt_field_name"], "prompt")
            self.assertEqual(app["inputs"][1]["role"], "prompt")

            prompt = store.save_prompt(
                {
                    "title": "电影海报",
                    "content": "复古电影海报风格",
                    "tags": "海报, 复古",
                    "favorite": "1",
                    "app_ids": [app["id"]],
                }
            )
            store.mark_prompt_used(prompt["id"])
            saved = store.get_prompt(prompt["id"])

            self.assertTrue(saved["favorite"])
            self.assertEqual(saved["tags"], ["海报", "复古"])
            self.assertEqual(saved["use_count"], 1)
            self.assertEqual(saved["app_ids"], [app["id"]])
            self.assertEqual(store.list_prompts(app_id=app["id"])[0]["id"], prompt["id"])

    def test_store_saves_prompt_variants_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            prompt = store.save_prompt({"title": "原提示词", "content": "红色卡片", "tags": "卡片"})

            updated = store.save_prompt_variant(
                prompt["id"],
                {
                    "title": "AI 衍生 1",
                    "content": "蓝色科技卡片",
                    "translation": "Blue tech card",
                    "edit_idea": "改成蓝色科技感",
                    "model_id": "ollama-qwen-vl",
                },
            )

            self.assertEqual(updated["content"], "红色卡片")
            self.assertEqual(len(updated["variants"]), 1)
            self.assertEqual(updated["variants"][0]["content"], "蓝色科技卡片")
            counted = store.mark_prompt_variant_used(updated["variants"][0]["id"])
            self.assertEqual(counted["use_count"], 1)
            self.assertEqual(counted["variants"][0]["use_count"], 1)

    def test_store_saves_prompt_variant_agent_chain_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = HuashiStore(Path(tmp) / "db.sqlite")
            store.initialize()
            prompt = store.save_prompt({"title": "原提示词", "content": "红色卡片", "tags": "卡片"})

            updated = store.save_prompt_variant(
                prompt["id"],
                {
                    "title": "宫殿版",
                    "content": "A prince in a moonlit palace.",
                    "translation": "月光宫殿里的王子。",
                    "edit_idea": "先换成王子",
                    "user_instruction": "再把金字塔换成皇宫",
                    "model_id": "aihubmix-grok",
                    "parent_variant_id": "parent-1",
                    "session_id": "session-1",
                    "round_index": 2,
                    "explanation_cn": "基于第一版继续微调。",
                    "feature_cn": "保留夜晚、月光和电影感。",
                    "analysis_snapshot": '{"prompt_type":"人像"}',
                },
            )

            variant = updated["variants"][0]
            self.assertEqual(variant["parent_variant_id"], "parent-1")
            self.assertEqual(variant["session_id"], "session-1")
            self.assertEqual(variant["round_index"], 2)
            self.assertEqual(variant["user_instruction"], "再把金字塔换成皇宫")
            self.assertEqual(variant["explanation_cn"], "基于第一版继续微调。")
            self.assertEqual(variant["feature_cn"], "保留夜晚、月光和电影感。")
            self.assertEqual(variant["analysis_snapshot"], '{"prompt_type":"人像"}')

    def test_store_migrates_embedded_prompt_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "db.sqlite"
            store = HuashiStore(db_path)
            store.initialize()
            prompt = store.save_prompt(
                {
                    "title": "卡片提示词",
                    "content": "原始红色卡片\n\n---- AI 衍生提示词 05/18 07:30 ----\n修改想法：改蓝色\n蓝色科技卡片\n中文翻译：blue tech card",
                }
            )
            with store.connect() as conn:
                conn.execute("DELETE FROM schema_meta WHERE key = 'embedded_prompt_variants_v1'")
            store.initialize()
            migrated = store.get_prompt(prompt["id"])

            self.assertEqual(migrated["content"], "原始红色卡片")
            self.assertEqual(len(migrated["variants"]), 1)
            self.assertEqual(migrated["variants"][0]["content"], "蓝色科技卡片")
            self.assertEqual(migrated["variants"][0]["translation"], "blue tech card")


if __name__ == "__main__":
    unittest.main()
