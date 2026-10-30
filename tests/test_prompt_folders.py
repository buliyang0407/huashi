import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from huashi.storage import HuashiStore


class PromptFolderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = HuashiStore(Path(self.tmp.name) / "db.sqlite")
        self.store.initialize()

    def leaf(self, name="室内"):
        root = self.store.save_prompt_folder({"name": "人像"})
        return self.store.save_prompt_folder({"name": name, "parent_id": root["id"]})

    def raw_prompts(self):
        with self.store.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM prompts ORDER BY id")]

    def test_initial_folders_have_stable_default_leaf(self):
        folders = self.store.list_prompt_folders()
        self.assertEqual({folder["path"] for folder in folders}, {
            "我的提示词", "我的提示词 / 未分类", "动作素材", "动作素材 / Qwen21姿势参考"})
        default = self.store.get_prompt_folder(self.store.default_prompt_folder_id())
        self.assertEqual(default["path"], "我的提示词 / 未分类")
        self.assertEqual(default["level"], 2)
        self.assertEqual(default["count"], 0)

    def test_migration_classifies_exact_manifest_ids_without_changing_rows(self):
        manifest = json.loads((Path(__file__).parents[1] / "huashi/assets/qwen21-pose-prompt-ids.json").read_text())
        self.assertEqual(len(manifest), 50)
        self.assertEqual(len(set(manifest)), 50)
        self.assertIn("qwen21pose_6b86b273ff34fce19d6b", manifest)
        with self.store.connect() as conn:
            conn.execute("DROP TABLE prompt_folder_links")
            conn.execute("DROP TABLE prompt_folders")
            conn.execute("DELETE FROM schema_meta WHERE key = 'prompt_folders_v1'")
            for index, prompt_id in enumerate([manifest[0], "legacy", "qwen21pose_fake"]):
                conn.execute("INSERT INTO prompts (id,title,content,tags,note,sample_path,use_count,last_used_at,deleted_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                    prompt_id, "Qwen21姿势参考", "正文", '["姿势"]', "备注", "pose:original.webp", 7, "old-used", "deleted" if index == 1 else None, "old-created", "old-updated"))
            conn.execute("INSERT INTO prompt_variants (id,prompt_id,title,content,created_at,updated_at) VALUES ('v','legacy','衍生','原衍生','old','old')")
        before = self.raw_prompts()
        self.store.initialize_prompt_folders()
        self.assertEqual(self.raw_prompts(), before)
        self.assertEqual(self.store.get_prompt(manifest[0])["folder_path"], "动作素材 / Qwen21姿势参考")
        self.assertEqual(self.store.get_prompt("qwen21pose_fake")["folder_id"], self.store.default_prompt_folder_id())
        self.assertTrue(self.store.get_prompt("legacy")["deleted"])
        self.assertEqual(self.store.get_prompt("legacy")["variants"][0]["content"], "原衍生")
        target = self.leaf()
        self.store.move_prompts([manifest[0]], target["id"])
        self.store.initialize()
        self.assertEqual(self.store.get_prompt(manifest[0])["folder_id"], target["id"])
        self.assertEqual(self.raw_prompts(), before)

    def test_save_defaults_and_omitted_folder_keeps_existing_assignment(self):
        prompt = self.store.save_prompt({"title": "原有", "content": "内容"})
        self.assertEqual(prompt["folder_id"], self.store.default_prompt_folder_id())
        target = self.leaf()
        moved = self.store.save_prompt({**prompt, "folder_id": target["id"]}, prompt["id"])
        self.assertEqual(moved["folder_path"], "人像 / 室内")
        edited = self.store.save_prompt({"title": "编辑", "content": "新内容"}, prompt["id"])
        self.assertEqual(edited["folder_id"], target["id"])

    def test_save_invalid_folder_rejects_before_prompt_or_app_link_write(self):
        prompt = self.store.save_prompt({"content": "原文", "app_ids": ["effect-png"]})
        root_id = self.store.get_prompt_folder(self.store.default_prompt_folder_id())["parent_id"]
        for folder_id in ["unknown", "", None, root_id]:
            with self.assertRaises((ValueError, KeyError)):
                self.store.save_prompt({"content": "不应写入", "folder_id": folder_id}, prompt["id"])
            self.assertEqual(self.store.get_prompt(prompt["id"])["content"], "原文")
            self.assertEqual(self.store.get_prompt(prompt["id"])["app_ids"], ["effect-png"])
        with self.assertRaises((ValueError, KeyError)):
            self.store.save_prompt({"id": "rejected-new", "content": "新", "folder_id": "unknown"})
        with self.assertRaises(KeyError):
            self.store.get_prompt("rejected-new")

    def test_link_failure_rolls_back_prompt_and_app_links(self):
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "原文", "app_ids": ["effect-png"]})
        before = self.raw_prompts()
        with self.store.connect() as conn:
            conn.execute("CREATE TRIGGER reject_folder BEFORE UPDATE ON prompt_folder_links BEGIN SELECT RAISE(ABORT, 'reject'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_prompt({"content": "新文", "folder_id": target["id"], "app_ids": []}, prompt["id"])
        self.assertEqual(self.raw_prompts(), before)
        self.assertEqual(self.store.get_prompt(prompt["id"])["app_ids"], ["effect-png"])

    def test_move_validates_entire_batch_and_preserves_prompt_rows(self):
        prompts = [self.store.save_prompt({"content": f"内容{index}"}) for index in range(2)]
        self.store.save_prompt_variant(prompts[0]["id"], {"content": "衍生", "title": "衍生"})
        before = self.raw_prompts()
        target = self.leaf()
        with self.assertRaises(KeyError):
            self.store.move_prompts([prompts[0]["id"], "missing"], target["id"])
        self.assertEqual(self.store.get_prompt(prompts[0]["id"])["folder_id"], self.store.default_prompt_folder_id())
        with self.assertRaises(ValueError):
            self.store.move_prompts([], target["id"])
        with self.assertRaises((ValueError, KeyError)):
            self.store.move_prompts([prompts[0]["id"]], target["parent_id"])
        moved = self.store.move_prompts([p["id"] for p in prompts], target["id"])
        self.assertEqual(len(moved), 2)
        self.assertEqual(self.raw_prompts(), before)
        self.assertEqual(self.store.get_prompt(prompts[0]["id"])["variants"][0]["content"], "衍生")
        self.assertEqual({p["id"] for p in self.store.list_prompts(folder_id=target["id"])}, {p["id"] for p in prompts})

    def test_filter_keeps_app_semantics_and_rejects_non_leaf_folder(self):
        target = self.leaf()
        other = self.store.save_prompt({"content": "别的目录", "app_ids": ["effect-png"]})
        compatible = self.store.save_prompt({"content": "通用", "folder_id": target["id"]})
        self.store.save_prompt({"content": "其他应用", "folder_id": target["id"], "app_ids": ["private-zip"]})
        self.assertEqual([p["id"] for p in self.store.list_prompts(app_id="effect-png", folder_id=target["id"])], [compatible["id"]])
        self.assertIn(other["id"], [p["id"] for p in self.store.list_prompts()])
        with self.assertRaises(ValueError):
            self.store.list_prompts(folder_id=target["parent_id"])

    def test_folder_rules_and_parent_move_update_paths(self):
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "内容", "folder_id": target["id"]})
        before = self.raw_prompts()
        for data in [{"name": " "}, {"name": "第三层", "parent_id": target["id"]}, {"name": "室内", "parent_id": target["parent_id"]}]:
            with self.assertRaises(ValueError):
                self.store.save_prompt_folder(data)
        with self.assertRaises(ValueError):
            self.store.save_prompt_folder({"parent_id": target["id"]}, target["parent_id"])
        other_root = self.store.save_prompt_folder({"name": "写真"})
        moved = self.store.save_prompt_folder({"parent_id": other_root["id"], "name": "户外", "sort_order": 5}, target["id"])
        self.assertEqual(moved["path"], "写真 / 户外")
        self.assertEqual(self.store.get_prompt(prompt["id"])["folder_path"], "写真 / 户外")
        self.assertEqual(self.raw_prompts(), before)

    def test_delete_is_soft_only_empty_and_protects_default(self):
        target = self.leaf()
        for folder_id in [self.store.default_prompt_folder_id(), target["parent_id"]]:
            with self.assertRaises(ValueError):
                self.store.delete_prompt_folder(folder_id)
        prompt = self.store.save_prompt({"content": "内容", "folder_id": target["id"]})
        self.store.soft_delete_prompt(prompt["id"])
        self.assertEqual(self.store.get_prompt_folder(target["id"])["count"], 0)
        with self.assertRaises(ValueError):
            self.store.delete_prompt_folder(target["id"])
        self.store.move_prompts([prompt["id"]], self.store.default_prompt_folder_id())
        deleted = self.store.delete_prompt_folder(target["id"])
        self.assertTrue(deleted["deleted_at"])
        with self.assertRaises(KeyError):
            self.store.get_prompt_folder(target["id"])
        self.assertTrue(self.store.get_prompt_folder(target["id"], include_deleted=True)["deleted_at"])
        self.assertIn(target["id"], [f["id"] for f in self.store.export_prompt_folders()["folders"]])
        replacement = self.store.save_prompt_folder({"name": "室内", "parent_id": target["parent_id"]})
        self.assertNotEqual(replacement["id"], target["id"])

    def test_concurrent_duplicate_names_create_only_one_folder(self):
        def create(_):
            try:
                return self.store.save_prompt_folder({"name": "同时创建"})["id"]
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_bundle_validation_is_read_only_and_restore_keeps_stable_ids(self):
        bundle = [{"id": "backup-root", "name": "归档", "parent_id": None, "sort_order": 8},
                  {"id": "backup-leaf", "name": "素材", "parent_id": "backup-root", "sort_order": 9}]
        links = [{"prompt_id": "imported", "folder_id": "backup-leaf"}]
        before = self.store.export_prompt_folders()
        self.store.validate_prompt_folder_bundle(bundle, links, prompt_ids=["imported"])
        self.assertEqual(self.store.export_prompt_folders(), before)
        self.store.restore_prompt_folders(bundle)
        self.store.save_prompt({"id": "imported", "content": "导入", "folder_id": "backup-leaf"})
        self.store.restore_prompt_folders(bundle, links)
        self.assertEqual(self.store.get_prompt("imported")["folder_path"], "归档 / 素材")
        default = self.store.get_prompt_folder(self.store.default_prompt_folder_id())
        self.store.restore_prompt_folders([{**default, "name": "默认改名"}])
        self.assertEqual(self.store.get_prompt_folder(default["id"])["name"], "默认改名")

    def test_invalid_bundles_never_partially_restore(self):
        root = self.store.get_prompt_folder(self.store.default_prompt_folder_id())["parent_id"]
        before = self.store.export_prompt_folders()
        invalid = [
            [{"id": "x", "name": "我的提示词", "parent_id": None}],
            [{"id": "x", "name": "x", "parent_id": "y"}, {"id": "y", "name": "y", "parent_id": "x"}],
            [{"id": self.store.default_prompt_folder_id(), "name": "默认", "parent_id": root, "deleted_at": "deleted"}],
            [{"id": "x", "name": "x", "parent_id": "missing"}],
            [{"id": "x", "name": "x", "parent_id": root, "sort_order": "bad"}],
        ]
        for folders in invalid:
            with self.assertRaises((ValueError, KeyError)):
                self.store.restore_prompt_folders(folders)
            self.assertEqual(self.store.export_prompt_folders(), before)
        with self.assertRaises((ValueError, KeyError)):
            self.store.validate_prompt_folder_bundle([], [{"prompt_id": "missing", "folder_id": self.store.default_prompt_folder_id()}])
        with self.assertRaises(ValueError):
            self.store.validate_prompt_folder_bundle([], [{"prompt_id": "new", "folder_id": root}], prompt_ids=["new"])

    def test_restore_archived_child_requires_active_parent_and_unique_name(self):
        target = self.leaf()
        self.store.delete_prompt_folder(target["id"])
        self.store.delete_prompt_folder(target["parent_id"])
        with self.assertRaises(ValueError):
            self.store.restore_prompt_folder(target["id"])
        restored_root = self.store.restore_prompt_folder(target["parent_id"])
        self.assertIsNone(restored_root["deleted_at"])
        replacement = self.store.save_prompt_folder({"name": target["name"], "parent_id": target["parent_id"]})
        with self.assertRaises(ValueError):
            self.store.restore_prompt_folder(target["id"])
        self.store.delete_prompt_folder(replacement["id"])
        restored = self.store.restore_prompt_folder(target["id"])
        self.assertEqual(restored["id"], target["id"])
        self.assertIsNone(restored["deleted_at"])

    def test_move_database_failure_rolls_back_every_link(self):
        target = self.leaf()
        first = self.store.save_prompt({"id": "first", "content": "一"})
        second = self.store.save_prompt({"id": "second", "content": "二"})
        before = self.store.export_prompt_folders()
        with self.store.connect() as conn:
            conn.execute("CREATE TRIGGER reject_second BEFORE UPDATE ON prompt_folder_links WHEN NEW.prompt_id = 'second' BEGIN SELECT RAISE(ABORT, 'reject'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.move_prompts([first["id"], second["id"]], target["id"])
        self.assertEqual(self.store.export_prompt_folders(), before)

    def test_migration_failure_rolls_back_links_and_marker(self):
        self.store.save_prompt({"id": "first", "content": "一"})
        self.store.save_prompt({"id": "second", "content": "二"})
        with self.store.connect() as conn:
            conn.execute("DELETE FROM prompt_folder_links")
            conn.execute("DELETE FROM schema_meta WHERE key = 'prompt_folders_v1'")
            conn.execute("CREATE TRIGGER reject_second BEFORE INSERT ON prompt_folder_links WHEN NEW.prompt_id = 'second' BEGIN SELECT RAISE(ABORT, 'reject'); END")
        before = self.raw_prompts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.initialize_prompt_folders()
        with self.store.connect() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM schema_meta WHERE key = 'prompt_folders_v1'").fetchone())
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM prompt_folder_links").fetchone()[0], 0)
        self.assertEqual(self.raw_prompts(), before)

    def test_parent_count_and_soft_deleted_filter_keep_archived_assignment(self):
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "一", "folder_id": target["id"]})
        self.assertEqual(self.store.get_prompt_folder(target["parent_id"])["count"], 1)
        self.store.soft_delete_prompt(prompt["id"])
        self.assertEqual(self.store.list_prompts(folder_id=target["id"]), [])
        self.assertEqual(self.store.list_prompts(folder_id=target["id"], include_deleted=True)[0]["folder_id"], target["id"])
        self.assertEqual(self.store.get_prompt_folder(target["parent_id"])["count"], 0)

    def test_invalid_folder_id_types_raise_validation_errors(self):
        for folder_id in [[], {}, 1]:
            with self.assertRaises(ValueError):
                self.store.save_prompt_folder({"id": folder_id, "name": "x"})

    def test_export_snapshot_has_all_folders_only_active_prompt_links_and_variants(self):
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "有效", "folder_id": target["id"], "app_ids": ["effect-png"]})
        self.store.save_prompt_variant(prompt["id"], {"title": "衍生", "content": "完整衍生"})
        deleted = self.store.save_prompt({"content": "已删除"})
        self.store.soft_delete_prompt(deleted["id"])
        empty = self.store.save_prompt_folder({"name": "已停用"})
        self.store.delete_prompt_folder(empty["id"])
        snapshot = self.store.export_prompt_snapshot()
        self.assertEqual([p["id"] for p in snapshot["prompts"]], [prompt["id"]])
        self.assertEqual(snapshot["prompts"][0]["folder_path"], "人像 / 室内")
        self.assertEqual(snapshot["prompts"][0]["apps"][0]["id"], "effect-png")
        self.assertEqual(snapshot["prompts"][0]["variants"][0]["content"], "完整衍生")
        self.assertEqual([link["prompt_id"] for link in snapshot["links"]], [prompt["id"]])
        self.assertIn(empty["id"], [folder["id"] for folder in snapshot["folders"]])

    def test_snapshot_keeps_directory_and_prompt_assignment_consistent_during_move(self):
        # WAL lets a real second connection commit while the export reads its snapshot.
        with self.store.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "快照"})
        other = HuashiStore(self.store.db_path)
        original_rows = self.store._folder_rows
        moved = False
        def read_then_move(conn):
            nonlocal moved
            rows = original_rows(conn)
            if not moved:
                moved = True
                other.move_prompts([prompt["id"]], target["id"])
                other.save_prompt_folder({"name": "新目录名"}, target["id"])
            return rows
        with patch.object(self.store, "_folder_rows", side_effect=read_then_move):
            snapshot = self.store.export_prompt_snapshot()
        record = snapshot["prompts"][0]
        link = snapshot["links"][0]
        folders = {f["id"]: f for f in snapshot["folders"]}
        self.assertEqual(record["folder_id"], self.store.default_prompt_folder_id())
        self.assertEqual(link["folder_id"], record["folder_id"])
        self.assertEqual(record["folder_path"], "我的提示词 / 未分类")
        self.assertEqual(folders[target["id"]]["name"], "室内")
        self.assertEqual(other.get_prompt(prompt["id"])["folder_path"], "人像 / 新目录名")

    def test_prepare_restore_defers_occupied_source_archive_until_links_move(self):
        target = self.leaf()
        prompt = self.store.save_prompt({"content": "原文", "folder_id": target["id"]})
        before = self.raw_prompts()
        incoming = [{**target, "deleted_at": "archived"},
                    {"id": "replacement", "name": target["name"], "parent_id": target["parent_id"]}]
        links = [{"prompt_id": prompt["id"], "folder_id": "replacement"}]
        self.store.prepare_prompt_folder_restore(incoming, links, prompt_ids=[prompt["id"]])
        self.assertIsNone(self.store.get_prompt_folder(target["id"])["deleted_at"])
        self.assertEqual(self.raw_prompts(), before)
        self.store.move_prompts([prompt["id"]], "replacement")
        self.store.restore_prompt_folders(incoming, links)
        self.assertEqual(self.store.get_prompt(prompt["id"])["folder_id"], "replacement")
        self.assertEqual(self.store.get_prompt(prompt["id"])["folder_path"], "人像 / 室内")
        self.assertTrue(self.store.get_prompt_folder(target["id"], include_deleted=True)["deleted_at"])
        self.assertEqual(self.raw_prompts(), before)

    def test_prepare_restore_invalid_final_topology_is_read_only(self):
        before = self.store.export_prompt_folders()
        with self.assertRaises(ValueError):
            self.store.prepare_prompt_folder_restore([
                {"id": "new-root", "name": "new-root", "parent_id": None},
                {"id": "new-leaf", "name": "new-leaf", "parent_id": "missing"}], [], prompt_ids=[])
        self.assertEqual(self.store.export_prompt_folders(), before)

    def test_atomic_import_is_thread_and_store_isolated(self):
        with self.store.atomic_import():
            created = self.store.save_prompt_folder({"name": "事务内部"})
            self.assertEqual(self.store.get_prompt_folder(created["id"])["name"], "事务内部")
            with ThreadPoolExecutor(max_workers=1) as pool:
                outside = pool.submit(self.store.list_prompt_folders).result(timeout=3)
            self.assertNotIn(created["id"], [folder["id"] for folder in outside])
            another_store = HuashiStore(self.store.db_path)
            self.assertNotIn(created["id"], [folder["id"] for folder in another_store.list_prompt_folders()])
        self.assertEqual(self.store.get_prompt_folder(created["id"])["name"], "事务内部")

    def test_atomic_import_nested_store_contexts_and_snapshot_roll_back(self):
        before = self.store.export_prompt_folders()
        with self.assertRaisesRegex(ValueError, "abort import"):
            with self.store.atomic_import():
                folder = self.leaf()
                self.store.save_prompt({"id":"inside-import", "content":"内部", "folder_id":folder["id"]})
                with self.store.atomic_import():
                    self.assertEqual(self.store.export_prompt_snapshot()["prompts"][0]["id"], "inside-import")
                raise ValueError("abort import")
        self.assertEqual(self.store.export_prompt_folders(), before)
        with self.assertRaises(KeyError): self.store.get_prompt("inside-import")


if __name__ == "__main__":
    unittest.main()
