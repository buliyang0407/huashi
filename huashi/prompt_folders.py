"""Two-level prompt folders, kept separate from the prompt content records."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PROMPT_FOLDER_ID = "prompt-default"
QWEN21_PROMPT_FOLDER_ID = "prompt-qwen21-poses"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptFolderStoreMixin:
    def default_prompt_folder_id(self) -> str:
        return DEFAULT_PROMPT_FOLDER_ID

    def initialize_prompt_folders(self) -> None:
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""CREATE TABLE IF NOT EXISTS prompt_folders (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT,
                sort_order INTEGER NOT NULL DEFAULT 100, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, deleted_at TEXT,
                FOREIGN KEY(parent_id) REFERENCES prompt_folders(id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS prompt_folder_links (
                prompt_id TEXT PRIMARY KEY, folder_id TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                FOREIGN KEY(prompt_id) REFERENCES prompts(id),
                FOREIGN KEY(folder_id) REFERENCES prompt_folders(id))""")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS prompt_folder_active_name
                ON prompt_folders(COALESCE(parent_id, ''), name) WHERE deleted_at IS NULL""")
            conn.execute("CREATE INDEX IF NOT EXISTS prompt_folder_link_folder ON prompt_folder_links(folder_id)")
            if conn.execute("SELECT 1 FROM schema_meta WHERE key = 'prompt_folders_v1'").fetchone():
                return
            now = _now()
            initial = [
                ("prompt-mine", "我的提示词", None, 0),
                (DEFAULT_PROMPT_FOLDER_ID, "未分类", "prompt-mine", 0),
                ("prompt-actions", "动作素材", None, 100),
                (QWEN21_PROMPT_FOLDER_ID, "Qwen21姿势参考", "prompt-actions", 0),
            ]
            conn.executemany("""INSERT OR IGNORE INTO prompt_folders
                (id,name,parent_id,sort_order,created_at,updated_at)
                VALUES (?,?,?,?,?,?)""", [(*row, now, now) for row in initial])
            pose_ids = set(json.loads((Path(__file__).parent / "assets/qwen21-pose-prompt-ids.json").read_text(encoding="utf-8")))
            conn.executemany("""INSERT OR IGNORE INTO prompt_folder_links
                (prompt_id,folder_id,created_at,updated_at) VALUES (?,?,?,?)""", [
                (row["id"], QWEN21_PROMPT_FOLDER_ID if row["id"] in pose_ids else DEFAULT_PROMPT_FOLDER_ID, now, now)
                for row in conn.execute("SELECT id FROM prompts")
            ])
            conn.execute("INSERT INTO schema_meta (key,value) VALUES ('prompt_folders_v1',?)", (now,))

    def _folder_rows(self, conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM prompt_folders ORDER BY sort_order,id")}

    def _folder_leaf(self, conn: sqlite3.Connection, folder_id: Any) -> dict[str, Any]:
        if not isinstance(folder_id, str) or not folder_id.strip():
            raise ValueError("请选择有效的二级提示词目录")
        row = conn.execute("SELECT * FROM prompt_folders WHERE id = ? AND deleted_at IS NULL", (folder_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown prompt folder: {folder_id}")
        folder = dict(row)
        parent = conn.execute("SELECT * FROM prompt_folders WHERE id = ? AND deleted_at IS NULL", (folder["parent_id"],)).fetchone()
        if parent is None or parent["parent_id"] is not None:
            raise ValueError("提示词只能保存到有效的二级目录")
        return folder

    def _folder_output(self, folder: dict[str, Any], rows: dict[str, dict[str, Any]], counts: dict[str, int]) -> dict[str, Any]:
        parent = rows.get(folder["parent_id"])
        path = f"{parent['name']} / {folder['name']}" if parent else folder["name"]
        count = counts.get(folder["id"], 0)
        if folder["parent_id"] is None:
            count = sum(counts.get(child["id"], 0) for child in rows.values() if child["parent_id"] == folder["id"] and not child["deleted_at"])
        return {**folder, "path": path, "count": count, "level": 2 if folder["parent_id"] else 1}

    def list_prompt_folders(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        with closing(self.connect()) as conn, conn:
            rows = self._folder_rows(conn)
            counts = {row["folder_id"]: row["total"] for row in conn.execute("""SELECT links.folder_id, COUNT(*) AS total
                FROM prompt_folder_links links JOIN prompts ON prompts.id = links.prompt_id
                WHERE prompts.deleted_at IS NULL GROUP BY links.folder_id""")}
        return [self._folder_output(folder, rows, counts) for folder in rows.values() if include_deleted or not folder["deleted_at"]]

    def get_prompt_folder(self, folder_id: str, include_deleted: bool = False) -> dict[str, Any]:
        for folder in self.list_prompt_folders(include_deleted=include_deleted):
            if folder["id"] == folder_id:
                return folder
        raise KeyError(f"Unknown prompt folder: {folder_id}")

    def save_prompt_folder(self, data: dict[str, Any], folder_id: str | None = None) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("目录数据必须为对象")
        if folder_id is not None and (not isinstance(folder_id, str) or not folder_id.strip()):
            raise ValueError("目录 ID 无效")
        if "id" in data and (not isinstance(data["id"], str) or not data["id"].strip()):
            raise ValueError("目录 ID 无效")
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = self._folder_rows(conn)
            existing = rows.get(folder_id) if folder_id else None
            if folder_id and (existing is None or existing["deleted_at"]):
                raise KeyError(f"Unknown prompt folder: {folder_id}")
            now = _now()
            folder = {"id": folder_id or data.get("id") or uuid.uuid4().hex,
                      "name": data.get("name", existing["name"] if existing else ""),
                      "parent_id": data.get("parent_id", existing["parent_id"] if existing else None),
                      "sort_order": data.get("sort_order", existing["sort_order"] if existing else 100),
                      "created_at": existing["created_at"] if existing else now,
                      "updated_at": now, "deleted_at": None}
            if not folder_id and folder["id"] in rows:
                raise ValueError("目录 ID 已存在")
            if existing and bool(existing["parent_id"]) != bool(folder["parent_id"]):
                raise ValueError("目录层级不能修改；二级目录可以移至其他一级目录")
            folders, _ = self._validate_folder_bundle(conn, [folder], [], None)
            self._write_folder_rows(conn, folders)
        return self.get_prompt_folder(folder["id"])

    def delete_prompt_folder(self, folder_id: str) -> dict[str, Any]:
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = self._folder_rows(conn)
            folder = rows.get(folder_id)
            if folder is None or folder["deleted_at"]:
                raise KeyError(f"Unknown prompt folder: {folder_id}")
            if folder_id == DEFAULT_PROMPT_FOLDER_ID:
                raise ValueError("默认提示词目录不能删除")
            if any(row["parent_id"] == folder_id and not row["deleted_at"] for row in rows.values()):
                raise ValueError("请先移出子目录")
            if conn.execute("SELECT 1 FROM prompt_folder_links WHERE folder_id = ? LIMIT 1", (folder_id,)).fetchone():
                raise ValueError("请先移出目录中的提示词（含已删除记录）")
            conn.execute("UPDATE prompt_folders SET deleted_at = ?, updated_at = ? WHERE id = ?", (_now(), _now(), folder_id))
        return self.get_prompt_folder(folder_id, include_deleted=True)

    def restore_prompt_folder(self, folder_id: str) -> dict[str, Any]:
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            folder = self._folder_rows(conn).get(folder_id)
            if folder is None:
                raise KeyError(f"Unknown prompt folder: {folder_id}")
            folder.update(deleted_at=None, updated_at=_now())
            clean, _ = self._validate_folder_bundle(conn, [folder], [], None)
            self._write_folder_rows(conn, clean)
        return self.get_prompt_folder(folder_id)

    def _set_prompt_folder(self, conn: sqlite3.Connection, prompt_id: str, folder_id: str, now: str) -> None:
        conn.execute("""INSERT INTO prompt_folder_links (prompt_id,folder_id,created_at,updated_at)
            VALUES (?,?,?,?) ON CONFLICT(prompt_id) DO UPDATE SET
            folder_id = excluded.folder_id, updated_at = excluded.updated_at""", (prompt_id, folder_id, now, now))

    def _prompt_folder_for_save(self, conn: sqlite3.Connection, data: dict[str, Any], prompt_id: str) -> str:
        if "folder_id" in data:
            folder_id = data["folder_id"]
        else:
            link = conn.execute("SELECT folder_id FROM prompt_folder_links WHERE prompt_id = ?", (prompt_id,)).fetchone()
            folder_id = link["folder_id"] if link else DEFAULT_PROMPT_FOLDER_ID
        self._folder_leaf(conn, folder_id)
        return folder_id

    def move_prompts(self, prompt_ids: list[str], folder_id: str) -> list[dict[str, Any]]:
        if not isinstance(prompt_ids, list) or not prompt_ids or any(not isinstance(value, str) or not value.strip() for value in prompt_ids):
            raise ValueError("请选择需要移动的提示词")
        ids = list(dict.fromkeys(prompt_ids))
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            self._folder_leaf(conn, folder_id)
            for prompt_id in ids:
                if not conn.execute("SELECT 1 FROM prompts WHERE id = ?", (prompt_id,)).fetchone():
                    raise KeyError(f"Unknown prompt: {prompt_id}")
            now = _now()
            for prompt_id in ids:
                self._set_prompt_folder(conn, prompt_id, folder_id, now)
        return [self.get_prompt(prompt_id) for prompt_id in ids]

    def _attach_prompt_folders(self, prompts: list[dict[str, Any]], conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
        if not prompts:
            return prompts
        with nullcontext(conn) if conn is not None else closing(self.connect()) as conn:
            rows = self._folder_rows(conn)
            ids = [prompt["id"] for prompt in prompts]
            placeholders = ",".join("?" for _ in ids)
            links = {row["prompt_id"]: row["folder_id"] for row in conn.execute(f"SELECT prompt_id,folder_id FROM prompt_folder_links WHERE prompt_id IN ({placeholders})", ids)}
        for prompt in prompts:
            folder_id = links.get(prompt["id"])
            folder = rows.get(folder_id)
            prompt["folder_id"] = folder_id
            prompt["folder_path"] = self._folder_output(folder, rows, {})["path"] if folder else ""
        return prompts

    def export_prompt_folders(self) -> dict[str, list[dict[str, Any]]]:
        with closing(self.connect()) as conn, conn:
            return {"folders": list(self._folder_rows(conn).values()),
                    "links": [dict(row) for row in conn.execute("SELECT * FROM prompt_folder_links ORDER BY prompt_id")]}

    def export_prompt_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Export content, folders and associations from one SQLite read snapshot."""
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN")
            folders = list(self._folder_rows(conn).values())
            rows = conn.execute("""SELECT * FROM prompts WHERE deleted_at IS NULL
                ORDER BY favorite DESC,last_used_at DESC,updated_at DESC""").fetchall()
            prompts = [self._prompt_from_row(row, conn=conn) for row in rows]
            self._attach_prompt_variants(prompts, conn=conn)
            self._attach_prompt_folders(prompts, conn=conn)
            prompt_ids = {prompt["id"] for prompt in prompts}
            links = [dict(row) for row in conn.execute("SELECT * FROM prompt_folder_links ORDER BY prompt_id") if row["prompt_id"] in prompt_ids]
            return {"prompts": prompts, "folders": folders, "links": links}

    def validate_prompt_folder_bundle(self, folders: list[dict[str, Any]], links: list[dict[str, Any]], prompt_ids: list[str] | None = None) -> None:
        with closing(self.connect()) as conn, conn:
            self._validate_folder_bundle(conn, folders, links, prompt_ids)

    def _validate_folder_bundle(self, conn: sqlite3.Connection, folders: Any, links: Any, prompt_ids: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not isinstance(folders, list) or not isinstance(links, list):
            raise ValueError("目录及归属清单必须为数组")
        if prompt_ids is not None and (not isinstance(prompt_ids, (list, set, tuple)) or any(not isinstance(value, str) or not value.strip() for value in prompt_ids)):
            raise ValueError("提示词 ID 清单无效")
        merged = self._folder_rows(conn)
        normalized = []
        seen = set()
        now = _now()
        for data in folders:
            if not isinstance(data, dict):
                raise ValueError("目录必须为对象")
            folder_id = data.get("id")
            name = data.get("name")
            parent_id = data.get("parent_id")
            sort_order = data.get("sort_order", 100)
            if not isinstance(folder_id, str) or not folder_id.strip() or folder_id in seen:
                raise ValueError("目录 ID 为空或重复")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("目录名称不能为空")
            if parent_id is not None and (not isinstance(parent_id, str) or not parent_id.strip()):
                raise ValueError("父目录 ID 无效")
            if not isinstance(sort_order, int) or isinstance(sort_order, bool):
                raise ValueError("目录排序必须为整数")
            for key in ("created_at", "updated_at", "deleted_at"):
                if data.get(key) is not None and not isinstance(data[key], str):
                    raise ValueError("目录时间字段无效")
            old = merged.get(folder_id, {})
            folder = {"id": folder_id, "name": name.strip(), "parent_id": parent_id, "sort_order": sort_order,
                      "created_at": data.get("created_at") or old.get("created_at") or now,
                      "updated_at": data.get("updated_at") or now, "deleted_at": data.get("deleted_at") or None}
            seen.add(folder_id)
            merged[folder_id] = folder
            normalized.append(folder)
        names = set()
        for folder in merged.values():
            parent_id = folder["parent_id"]
            if parent_id is not None:
                parent = merged.get(parent_id)
                if not parent or parent["parent_id"] is not None or parent_id == folder["id"]:
                    raise ValueError("目录最多两级，父目录必须为一级目录")
                if not folder["deleted_at"] and parent["deleted_at"]:
                    raise ValueError("有效目录不能位于已删除目录中")
            if not folder["deleted_at"]:
                key = (parent_id, folder["name"])
                if key in names:
                    raise ValueError("同一级目录下名称不能重复")
                names.add(key)
        default = merged.get(DEFAULT_PROMPT_FOLDER_ID)
        if not default or default["deleted_at"] or default["parent_id"] is None:
            raise ValueError("默认提示词目录必须保留为有效二级目录")
        existing_links = {row["prompt_id"]: dict(row) for row in conn.execute("SELECT * FROM prompt_folder_links")}
        known_prompts = {row["id"] for row in conn.execute("SELECT id FROM prompts")}
        known_prompts.update(prompt_ids or [])
        clean_links = []
        seen_links = set()
        for data in links:
            if not isinstance(data, dict):
                raise ValueError("提示词归属必须为对象")
            prompt_id, folder_id = data.get("prompt_id"), data.get("folder_id")
            if not isinstance(prompt_id, str) or prompt_id not in known_prompts or prompt_id in seen_links:
                raise ValueError("提示词归属 ID 不存在或重复")
            if not isinstance(folder_id, str) or not folder_id.strip():
                raise ValueError("提示词归属目录 ID 无效")
            for key in ("created_at", "updated_at"):
                if data.get(key) is not None and not isinstance(data[key], str):
                    raise ValueError("归属时间字段无效")
            old = existing_links.get(prompt_id, {})
            link = {"prompt_id": prompt_id, "folder_id": folder_id,
                    "created_at": data.get("created_at") or old.get("created_at") or now,
                    "updated_at": data.get("updated_at") or now}
            seen_links.add(prompt_id)
            existing_links[prompt_id] = link
            clean_links.append(link)
        for link in existing_links.values():
            folder = merged.get(link["folder_id"])
            if not folder or folder["deleted_at"] or folder["parent_id"] is None:
                raise ValueError("提示词归属必须引用有效二级目录；请先移出提示词")
        return normalized, clean_links

    def _write_folder_rows(self, conn: sqlite3.Connection, folders: list[dict[str, Any]]) -> None:
        # Temporarily suspend imported IDs so name swaps can pass the unique index.
        for folder in folders:
            conn.execute("UPDATE prompt_folders SET deleted_at = ? WHERE id = ?", (_now(), folder["id"]))
        conn.executemany("""INSERT INTO prompt_folders (id,name,parent_id,sort_order,created_at,updated_at,deleted_at)
            VALUES (:id,:name,:parent_id,:sort_order,:created_at,:updated_at,:deleted_at)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,parent_id=excluded.parent_id,
            sort_order=excluded.sort_order,created_at=excluded.created_at,updated_at=excluded.updated_at,deleted_at=excluded.deleted_at""",
            sorted(folders, key=lambda row: row["parent_id"] is not None))

    def restore_prompt_folders(self, folders: list[dict[str, Any]], links: list[dict[str, Any]] | None = None) -> None:
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            clean_folders, clean_links = self._validate_folder_bundle(conn, folders, links if links is not None else [], None)
            self._write_folder_rows(conn, clean_folders)
            conn.executemany("""INSERT INTO prompt_folder_links (prompt_id,folder_id,created_at,updated_at)
                VALUES (:prompt_id,:folder_id,:created_at,:updated_at) ON CONFLICT(prompt_id) DO UPDATE SET
                folder_id=excluded.folder_id,created_at=excluded.created_at,updated_at=excluded.updated_at""", clean_links)

    def prepare_prompt_folder_restore(self, folders: list[dict[str, Any]], links: list[dict[str, Any]], prompt_ids: list[str] | None = None) -> None:
        """Install active import destinations; apply archived rows after prompts move.

        A replacement may reuse an occupied source's name. Stage that destination
        with a temporary unique name, then restore_prompt_folders installs the final
        names and archived states together with the final links in one transaction.
        """
        with closing(self.connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            clean_folders, _ = self._validate_folder_bundle(conn, folders, links, prompt_ids)
            current = self._folder_rows(conn)
            active = [dict(folder) for folder in clean_folders if not folder["deleted_at"]]
            incoming_ids = {folder["id"] for folder in active}
            # Incoming active IDs are written together; only retained current IDs
            # can conflict with their final sibling names during this staging step.
            names = {(folder["parent_id"], folder["name"]) for folder in current.values()
                     if not folder["deleted_at"] and folder["id"] not in incoming_ids}
            reserved = names | {(folder["parent_id"], folder["name"]) for folder in active}
            for folder in active:
                key = (folder["parent_id"], folder["name"])
                if key in names:
                    temporary = f"恢复中 {folder['id']}"
                    while (folder["parent_id"], temporary) in reserved:
                        temporary += "_"
                    folder["name"] = temporary
                reserved.add((folder["parent_id"], folder["name"]))
            self._write_folder_rows(conn, active)
