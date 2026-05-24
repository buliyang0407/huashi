from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .app_templates import DEFAULT_APPS


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HuashiStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS apps (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  description TEXT NOT NULL,
                  webapp_id TEXT NOT NULL,
                  node_id TEXT NOT NULL,
                  field_name TEXT NOT NULL,
                  input_type TEXT NOT NULL,
                  output_type TEXT NOT NULL,
                  auto_unzip INTEGER NOT NULL,
                  category TEXT NOT NULL,
                  favorite INTEGER NOT NULL,
                  accent TEXT NOT NULL,
                  cover_path TEXT NOT NULL DEFAULT '',
                  source_url TEXT NOT NULL DEFAULT '',
                  prompt_node_id TEXT NOT NULL DEFAULT '',
                  prompt_field_name TEXT NOT NULL DEFAULT '',
                  default_prompt TEXT NOT NULL DEFAULT '',
                  inputs TEXT NOT NULL DEFAULT '[]',
                  sort_order INTEGER NOT NULL DEFAULT 100,
                  enabled INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY,
                  app_id TEXT NOT NULL,
                  runninghub_task_id TEXT,
                  status TEXT NOT NULL,
                  input_path TEXT NOT NULL,
                  input_name TEXT NOT NULL,
                  output_type TEXT,
                  cache_path TEXT,
                  archive_path TEXT,
                  saved INTEGER NOT NULL DEFAULT 0,
                  outputs TEXT NOT NULL DEFAULT '[]',
                  prompt TEXT NOT NULL DEFAULT '',
                  input_payload TEXT NOT NULL DEFAULT '{}',
                  error TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  completed_at TEXT,
                  FOREIGN KEY (app_id) REFERENCES apps(id)
                );

                CREATE TABLE IF NOT EXISTS prompts (
                  id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  tags TEXT NOT NULL DEFAULT '[]',
                  favorite INTEGER NOT NULL DEFAULT 0,
                  note TEXT NOT NULL DEFAULT '',
                  sample_path TEXT NOT NULL DEFAULT '',
                  use_count INTEGER NOT NULL DEFAULT 0,
                  last_used_at TEXT,
                  deleted_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompt_app_links (
                  prompt_id TEXT NOT NULL,
                  app_id TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  PRIMARY KEY (prompt_id, app_id),
                  FOREIGN KEY (prompt_id) REFERENCES prompts(id),
                  FOREIGN KEY (app_id) REFERENCES apps(id)
                );

                CREATE TABLE IF NOT EXISTS prompt_variants (
                  id TEXT PRIMARY KEY,
                  prompt_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  translation TEXT NOT NULL DEFAULT '',
                  edit_idea TEXT NOT NULL DEFAULT '',
                  model_id TEXT NOT NULL DEFAULT '',
                  parent_variant_id TEXT NOT NULL DEFAULT '',
                  session_id TEXT NOT NULL DEFAULT '',
                  round_index INTEGER NOT NULL DEFAULT 0,
                  user_instruction TEXT NOT NULL DEFAULT '',
                  explanation_cn TEXT NOT NULL DEFAULT '',
                  feature_cn TEXT NOT NULL DEFAULT '',
                  analysis_snapshot TEXT NOT NULL DEFAULT '',
                  use_count INTEGER NOT NULL DEFAULT 0,
                  last_used_at TEXT,
                  deleted_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (prompt_id) REFERENCES prompts(id)
                );

                CREATE TABLE IF NOT EXISTS album_folders (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 100,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS album_items (
                  id TEXT PRIMARY KEY,
                  folder_id TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  task_id TEXT NOT NULL DEFAULT '',
                  output_path TEXT NOT NULL DEFAULT '',
                  file_path TEXT NOT NULL,
                  title TEXT NOT NULL DEFAULT '',
                  position INTEGER NOT NULL DEFAULT 100,
                  blurred INTEGER NOT NULL DEFAULT 0,
                  deleted_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY (folder_id) REFERENCES album_folders(id)
                );
                """
            )
            self._ensure_columns(conn, "apps", {
                "cover_path": "TEXT NOT NULL DEFAULT ''",
                "source_url": "TEXT NOT NULL DEFAULT ''",
                "prompt_node_id": "TEXT NOT NULL DEFAULT ''",
                "prompt_field_name": "TEXT NOT NULL DEFAULT ''",
                "default_prompt": "TEXT NOT NULL DEFAULT ''",
                "inputs": "TEXT NOT NULL DEFAULT '[]'",
                "sort_order": "INTEGER NOT NULL DEFAULT 100",
            })
            self._ensure_columns(conn, "tasks", {
                "prompt": "TEXT NOT NULL DEFAULT ''",
                "input_payload": "TEXT NOT NULL DEFAULT '{}'",
            })
            self._ensure_columns(conn, "prompts", {
                "sample_path": "TEXT NOT NULL DEFAULT ''",
                "use_count": "INTEGER NOT NULL DEFAULT 0",
                "last_used_at": "TEXT",
                "deleted_at": "TEXT",
            })
            self._ensure_columns(conn, "prompt_variants", {
                "parent_variant_id": "TEXT NOT NULL DEFAULT ''",
                "session_id": "TEXT NOT NULL DEFAULT ''",
                "round_index": "INTEGER NOT NULL DEFAULT 0",
                "user_instruction": "TEXT NOT NULL DEFAULT ''",
                "explanation_cn": "TEXT NOT NULL DEFAULT ''",
                "feature_cn": "TEXT NOT NULL DEFAULT ''",
                "analysis_snapshot": "TEXT NOT NULL DEFAULT ''",
            })
            seeded = conn.execute("SELECT value FROM schema_meta WHERE key = 'default_apps_v2'").fetchone()
            if seeded is None:
                conn.executemany(
                    """
                    INSERT INTO apps (
                      id, name, description, webapp_id, node_id, field_name,
                      input_type, output_type, auto_unzip, category, favorite,
                      accent, cover_path, source_url, prompt_node_id,
                      prompt_field_name, default_prompt, inputs, sort_order, enabled
                    )
                    VALUES (
                      :id, :name, :description, :webapp_id, :node_id, :field_name,
                      :input_type, :output_type, :auto_unzip, :category, :favorite,
                      :accent, :cover_path, :source_url, :prompt_node_id,
                      :prompt_field_name, :default_prompt, :inputs, :sort_order, :enabled
                    )
                    ON CONFLICT(id) DO UPDATE SET
                      name = excluded.name,
                      description = excluded.description,
                      webapp_id = excluded.webapp_id,
                      node_id = excluded.node_id,
                      field_name = excluded.field_name,
                      input_type = excluded.input_type,
                      output_type = excluded.output_type,
                      auto_unzip = excluded.auto_unzip,
                      category = excluded.category,
                      favorite = excluded.favorite,
                      accent = excluded.accent,
                      cover_path = excluded.cover_path,
                      source_url = excluded.source_url,
                      prompt_node_id = excluded.prompt_node_id,
                      prompt_field_name = excluded.prompt_field_name,
                      default_prompt = excluded.default_prompt,
                      inputs = excluded.inputs,
                      sort_order = excluded.sort_order,
                      enabled = excluded.enabled
                    """,
                    [self._serialize_app(app) for app in DEFAULT_APPS],
                )
                conn.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('default_apps_v2', ?)",
                    (utc_now(),),
                )
            migrated_variants = conn.execute("SELECT value FROM schema_meta WHERE key = 'embedded_prompt_variants_v1'").fetchone()
            if migrated_variants is None:
                self._migrate_embedded_prompt_variants(conn)
                conn.execute(
                    "INSERT INTO schema_meta (key, value) VALUES ('embedded_prompt_variants_v1', ?)",
                    (utc_now(),),
                )
            conn.execute(
                """
                INSERT OR IGNORE INTO album_folders (id, name, sort_order, created_at, updated_at)
                VALUES ('works', '作品', 0, ?, ?)
                """,
                (utc_now(), utc_now()),
            )

    def list_apps(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM apps WHERE enabled = 1 ORDER BY favorite DESC, sort_order ASC, rowid ASC"
            ).fetchall()
        return [self._app_from_row(row) for row in rows]

    def list_all_apps(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM apps ORDER BY enabled DESC, sort_order ASC, rowid ASC").fetchall()
        return [self._app_from_row(row) for row in rows]

    def get_app(self, app_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM apps WHERE id = ?", (app_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown app: {app_id}")
        return self._app_from_row(row)

    def create_task(
        self,
        app_id: str,
        input_path: str,
        input_name: str,
        prompt: str = "",
        input_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                  id, app_id, status, input_path, input_name, outputs, prompt, input_payload, created_at, updated_at
                )
                VALUES (?, ?, 'queued', ?, ?, '[]', ?, ?, ?, ?)
                """,
                (
                    task_id,
                    app_id,
                    input_path,
                    input_name,
                    prompt,
                    json.dumps(input_payload or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return self.get_task(task_id)

    def save_app(self, data: dict[str, Any], app_id: str | None = None) -> dict[str, Any]:
        clean = self._serialize_app(self._normalize_app(data, app_id))
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO apps (
                  id, name, description, webapp_id, node_id, field_name,
                  input_type, output_type, auto_unzip, category, favorite,
                  accent, cover_path, source_url, prompt_node_id,
                  prompt_field_name, default_prompt, inputs, sort_order, enabled
                )
                VALUES (
                  :id, :name, :description, :webapp_id, :node_id, :field_name,
                  :input_type, :output_type, :auto_unzip, :category, :favorite,
                  :accent, :cover_path, :source_url, :prompt_node_id,
                  :prompt_field_name, :default_prompt, :inputs, :sort_order, :enabled
                )
                ON CONFLICT(id) DO UPDATE SET
                  name = excluded.name,
                  description = excluded.description,
                  webapp_id = excluded.webapp_id,
                  node_id = excluded.node_id,
                  field_name = excluded.field_name,
                  input_type = excluded.input_type,
                  output_type = excluded.output_type,
                  auto_unzip = excluded.auto_unzip,
                  category = excluded.category,
                  favorite = excluded.favorite,
                  accent = excluded.accent,
                  cover_path = excluded.cover_path,
                  source_url = excluded.source_url,
                  prompt_node_id = excluded.prompt_node_id,
                  prompt_field_name = excluded.prompt_field_name,
                  default_prompt = excluded.default_prompt,
                  inputs = excluded.inputs,
                  sort_order = excluded.sort_order,
                  enabled = excluded.enabled
                """,
                clean,
            )
        return self.get_app(clean["id"])

    def disable_app(self, app_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("UPDATE apps SET enabled = 0 WHERE id = ?", (app_id,))
        return self.get_app(app_id)

    def delete_app(self, app_id: str) -> dict[str, Any]:
        app = self.get_app(app_id)
        with self.connect() as conn:
            conn.execute("DELETE FROM prompt_app_links WHERE app_id = ?", (app_id,))
            conn.execute("DELETE FROM apps WHERE id = ?", (app_id,))
        return app

    def update_task(self, task_id: str, **changes: Any) -> dict[str, Any]:
        allowed = {
            "runninghub_task_id",
            "status",
            "output_type",
            "cache_path",
            "archive_path",
            "saved",
            "outputs",
            "error",
            "completed_at",
        }
        updates: dict[str, Any] = {}
        for key, value in changes.items():
            if key not in allowed:
                raise ValueError(f"Cannot update task field: {key}")
            if key == "outputs":
                value = json.dumps(value, ensure_ascii=False)
            if key == "saved":
                value = int(bool(value))
            updates[key] = value
        updates["updated_at"] = utc_now()

        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [task_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE tasks SET {assignments} WHERE id = ?", values)
        return self.get_task(task_id)

    def set_task_output_blurred(self, task_id: str, output_path: str, blurred: bool) -> dict[str, Any]:
        task = self._set_task_output_flag(task_id, output_path, "blurred", bool(blurred))
        with self.connect() as conn:
            conn.execute(
                "UPDATE album_items SET blurred = ?, updated_at = ? WHERE task_id = ? AND output_path = ?",
                (1 if blurred else 0, utc_now(), task_id, output_path),
            )
        return task

    def set_task_output_deleted(self, task_id: str, output_path: str, deleted: bool) -> dict[str, Any]:
        task = self._set_task_output_flag(task_id, output_path, "deleted", bool(deleted))
        with self.connect() as conn:
            conn.execute(
                "UPDATE album_items SET deleted_at = ?, updated_at = ? WHERE task_id = ? AND output_path = ?",
                (utc_now() if deleted else None, utc_now(), task_id, output_path),
            )
        return task

    def _set_task_output_flag(self, task_id: str, output_path: str, flag: str, enabled: bool) -> dict[str, Any]:
        task = self.get_task(task_id)
        found = False
        outputs = []
        for item in task.get("outputs") or []:
            output = dict(item)
            if str(output.get("path") or "") == output_path:
                output[flag] = enabled
                found = True
            outputs.append(output)
        if not found:
            raise KeyError(f"Unknown task output: {output_path}")
        return self.update_task(task_id, outputs=outputs)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT tasks.*,
                       COALESCE(apps.name, '已删除应用') AS app_name,
                       COALESCE(apps.category, '历史记录') AS app_category
                FROM tasks
                LEFT JOIN apps ON apps.id = tasks.app_id
                WHERE tasks.id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown task: {task_id}")
        return self._task_from_row(row)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.*,
                       COALESCE(apps.name, '已删除应用') AS app_name,
                       COALESCE(apps.category, '历史记录') AS app_category
                FROM tasks
                LEFT JOIN apps ON apps.id = tasks.app_id
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def delete_task_record(self, task_id: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE album_items SET deleted_at = ?, updated_at = ? WHERE task_id = ?", (utc_now(), utc_now(), task_id))
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def list_album_folders(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT album_folders.*,
                       COUNT(album_items.id) AS item_count
                FROM album_folders
                LEFT JOIN album_items
                  ON album_items.folder_id = album_folders.id
                 AND album_items.deleted_at IS NULL
                GROUP BY album_folders.id
                ORDER BY album_folders.sort_order ASC, album_folders.created_at ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_album_folder(self, name: str) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("文件夹名称不能为空")
        folder_id = uuid.uuid4().hex
        now = utc_now()
        with self.connect() as conn:
            max_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS value FROM album_folders").fetchone()["value"]
            conn.execute(
                "INSERT INTO album_folders (id, name, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (folder_id, clean_name, int(max_order or 0) + 10, now, now),
            )
        return self.get_album_folder(folder_id)

    def get_album_folder(self, folder_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM album_folders WHERE id = ?", (folder_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown album folder: {folder_id}")
        return dict(row)

    def list_album_items(self, folder_id: str = "works") -> list[dict[str, Any]]:
        self.sync_generated_album_items()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT album_items.*, tasks.app_id, apps.name AS app_name
                FROM album_items
                LEFT JOIN tasks ON tasks.id = album_items.task_id
                LEFT JOIN apps ON apps.id = tasks.app_id
                WHERE album_items.folder_id = ?
                  AND album_items.deleted_at IS NULL
                ORDER BY album_items.position ASC, album_items.created_at DESC
                """,
                (folder_id,),
            ).fetchall()
        return [self._album_item_from_row(row) for row in rows]

    def sync_generated_album_items(self) -> None:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT tasks.id AS task_id, tasks.outputs, tasks.created_at, apps.name AS app_name
                FROM tasks
                LEFT JOIN apps ON apps.id = tasks.app_id
                WHERE tasks.status = 'success'
                ORDER BY tasks.created_at ASC
                """
            ).fetchall()
            min_pos = conn.execute("SELECT COALESCE(MIN(position), 0) AS value FROM album_items WHERE folder_id = 'works'").fetchone()["value"] or 0
            position = int(min_pos)
            for row in rows:
                outputs = json.loads(row["outputs"] or "[]")
                for output in outputs:
                    if not self._is_image_output(output):
                        continue
                    output_path = str(output.get("path") or "")
                    if not output_path:
                        continue
                    existing = conn.execute(
                        "SELECT id, deleted_at, blurred FROM album_items WHERE task_id = ? AND output_path = ?",
                        (row["task_id"], output_path),
                    ).fetchone()
                    if existing:
                        if output.get("deleted") and existing["deleted_at"] is None:
                            conn.execute(
                                "UPDATE album_items SET deleted_at = ?, updated_at = ? WHERE id = ?",
                                (utc_now(), utc_now(), existing["id"]),
                            )
                        if existing["blurred"] != (1 if output.get("blurred") else 0):
                            conn.execute(
                                "UPDATE album_items SET blurred = ?, updated_at = ? WHERE id = ?",
                                (1 if output.get("blurred") else 0, utc_now(), existing["id"]),
                            )
                        continue
                    if output.get("deleted"):
                        continue
                    position -= 10
                    now = utc_now()
                    conn.execute(
                        """
                        INSERT INTO album_items (
                          id, folder_id, source_type, task_id, output_path, file_path,
                          title, position, blurred, deleted_at, created_at, updated_at
                        )
                        VALUES (?, 'works', 'generated', ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                        """,
                        (
                            uuid.uuid4().hex,
                            row["task_id"],
                            output_path,
                            output_path,
                            row["app_name"] or "作品",
                            position,
                            1 if output.get("blurred") else 0,
                            now,
                            now,
                        ),
                    )

    def save_album_upload(self, folder_id: str, file_path: str, title: str = "") -> dict[str, Any]:
        self.get_album_folder(folder_id)
        now = utc_now()
        with self.connect() as conn:
            min_pos = conn.execute(
                "SELECT COALESCE(MIN(position), 0) AS value FROM album_items WHERE folder_id = ?",
                (folder_id,),
            ).fetchone()["value"] or 0
            item_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO album_items (
                  id, folder_id, source_type, file_path, title, position, blurred, created_at, updated_at
                )
                VALUES (?, ?, 'upload', ?, ?, ?, 0, ?, ?)
                """,
                (item_id, folder_id, file_path, title, int(min_pos) - 10, now, now),
            )
        return self.get_album_item(item_id)

    def get_album_item(self, item_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT album_items.*, tasks.app_id, apps.name AS app_name
                FROM album_items
                LEFT JOIN tasks ON tasks.id = album_items.task_id
                LEFT JOIN apps ON apps.id = tasks.app_id
                WHERE album_items.id = ?
                """,
                (item_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown album item: {item_id}")
        return self._album_item_from_row(row)

    def move_album_item(self, item_id: str, folder_id: str) -> dict[str, Any]:
        self.get_album_folder(folder_id)
        with self.connect() as conn:
            min_pos = conn.execute(
                "SELECT COALESCE(MIN(position), 0) AS value FROM album_items WHERE folder_id = ?",
                (folder_id,),
            ).fetchone()["value"] or 0
            conn.execute(
                "UPDATE album_items SET folder_id = ?, position = ?, updated_at = ? WHERE id = ?",
                (folder_id, int(min_pos) - 10, utc_now(), item_id),
            )
        return self.get_album_item(item_id)

    def position_album_item(self, item_id: str, to_index: int) -> dict[str, Any]:
        current = self.get_album_item(item_id)
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM album_items
                WHERE folder_id = ? AND deleted_at IS NULL
                ORDER BY position ASC, created_at DESC
                """,
                (current["folder_id"],),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if item_id not in ids:
                return current
            ids.remove(item_id)
            index = max(0, min(int(to_index), len(ids)))
            ids.insert(index, item_id)
            now = utc_now()
            for position, row_id in enumerate(ids, start=1):
                conn.execute(
                    "UPDATE album_items SET position = ?, updated_at = ? WHERE id = ?",
                    (position * 10, now, row_id),
                )
        return self.get_album_item(item_id)

    def reorder_album_item(self, item_id: str, direction: str) -> dict[str, Any]:
        current = self.get_album_item(item_id)
        op = "<" if direction == "up" else ">"
        order = "DESC" if direction == "up" else "ASC"
        with self.connect() as conn:
            neighbor = conn.execute(
                f"""
                SELECT id, position FROM album_items
                WHERE folder_id = ? AND deleted_at IS NULL AND position {op} ?
                ORDER BY position {order}, created_at {order}
                LIMIT 1
                """,
                (current["folder_id"], current["position"]),
            ).fetchone()
            if neighbor:
                conn.execute(
                    "UPDATE album_items SET position = ?, updated_at = ? WHERE id = ?",
                    (neighbor["position"], utc_now(), item_id),
                )
                conn.execute(
                    "UPDATE album_items SET position = ?, updated_at = ? WHERE id = ?",
                    (current["position"], utc_now(), neighbor["id"]),
                )
        return self.get_album_item(item_id)

    def soft_delete_album_item(self, item_id: str) -> dict[str, Any]:
        item = self.get_album_item(item_id)
        if item.get("source_type") == "generated" and item.get("task_id") and item.get("output_path"):
            self.set_task_output_deleted(item["task_id"], item["output_path"], True)
            return self.get_album_item(item_id)
        with self.connect() as conn:
            conn.execute("UPDATE album_items SET deleted_at = ?, updated_at = ? WHERE id = ?", (utc_now(), utc_now(), item_id))
        return self.get_album_item(item_id)

    def list_prompts(self, app_id: str | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if app_id:
                rows = conn.execute(
                    """
                    SELECT DISTINCT prompts.*
                    FROM prompts
                    LEFT JOIN prompt_app_links ON prompt_app_links.prompt_id = prompts.id
                    WHERE (? = 1 OR prompts.deleted_at IS NULL)
                      AND (prompt_app_links.app_id = ? OR prompt_app_links.app_id IS NULL)
                    ORDER BY
                      CASE WHEN prompt_app_links.app_id = ? THEN 0 ELSE 1 END,
                      prompts.favorite DESC,
                      prompts.last_used_at DESC,
                      prompts.updated_at DESC
                    """,
                    (1 if include_deleted else 0, app_id, app_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM prompts
                    WHERE (? = 1 OR deleted_at IS NULL)
                    ORDER BY favorite DESC, last_used_at DESC, updated_at DESC
                    """,
                    (1 if include_deleted else 0,),
                ).fetchall()
        prompts = [self._prompt_from_row(row) for row in rows]
        return self._attach_prompt_variants(prompts, include_deleted=include_deleted)

    def get_prompt(self, prompt_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown prompt: {prompt_id}")
        return self._attach_prompt_variants([self._prompt_from_row(row)], include_deleted=True)[0]

    def save_prompt(self, data: dict[str, Any], prompt_id: str | None = None) -> dict[str, Any]:
        clean = self._normalize_prompt(data, prompt_id)
        app_ids = clean.pop("app_ids")
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute("SELECT created_at FROM prompts WHERE id = ?", (clean["id"],)).fetchone()
            clean["created_at"] = existing["created_at"] if existing else now
            clean["updated_at"] = now
            conn.execute(
                """
                INSERT INTO prompts (
                  id, title, content, tags, favorite, note, sample_path,
                  use_count, last_used_at, deleted_at, created_at, updated_at
                )
                VALUES (
                  :id, :title, :content, :tags, :favorite, :note, :sample_path,
                  :use_count, :last_used_at, :deleted_at, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                  title = excluded.title,
                  content = excluded.content,
                  tags = excluded.tags,
                  favorite = excluded.favorite,
                  note = excluded.note,
                  sample_path = excluded.sample_path,
                  deleted_at = excluded.deleted_at,
                  updated_at = excluded.updated_at
                """,
                clean,
            )
            conn.execute("DELETE FROM prompt_app_links WHERE prompt_id = ?", (clean["id"],))
            conn.executemany(
                "INSERT OR IGNORE INTO prompt_app_links (prompt_id, app_id, created_at) VALUES (?, ?, ?)",
                [(clean["id"], app_id, now) for app_id in app_ids],
            )
        return self.get_prompt(clean["id"])

    def save_prompt_variant(self, prompt_id: str, data: dict[str, Any], variant_id: str | None = None) -> dict[str, Any]:
        self.get_prompt(prompt_id)
        now = utc_now()
        clean = {
            "id": variant_id or str(data.get("id") or "").strip() or uuid.uuid4().hex,
            "prompt_id": prompt_id,
            "title": str(data.get("title") or "").strip() or "AI 衍生提示词",
            "content": str(data.get("content") or "").strip(),
            "translation": str(data.get("translation") or "").strip(),
            "edit_idea": str(data.get("edit_idea") or data.get("idea") or "").strip(),
            "model_id": str(data.get("model_id") or data.get("model") or "").strip(),
            "parent_variant_id": str(data.get("parent_variant_id") or "").strip(),
            "session_id": str(data.get("session_id") or "").strip(),
            "round_index": int(data.get("round_index") or 0),
            "user_instruction": str(data.get("user_instruction") or "").strip(),
            "explanation_cn": str(data.get("explanation_cn") or "").strip(),
            "feature_cn": str(data.get("feature_cn") or "").strip(),
            "analysis_snapshot": str(data.get("analysis_snapshot") or "").strip(),
            "use_count": int(data.get("use_count") or 0),
            "last_used_at": data.get("last_used_at"),
            "deleted_at": data.get("deleted_at"),
        }
        if not clean["content"]:
            raise ValueError("提示词内容不能为空")
        with self.connect() as conn:
            existing = conn.execute("SELECT created_at FROM prompt_variants WHERE id = ?", (clean["id"],)).fetchone()
            clean["created_at"] = existing["created_at"] if existing else now
            clean["updated_at"] = now
            conn.execute(
                """
                INSERT INTO prompt_variants (
                  id, prompt_id, title, content, translation, edit_idea, model_id,
                  parent_variant_id, session_id, round_index, user_instruction,
                  explanation_cn, feature_cn, analysis_snapshot,
                  use_count, last_used_at, deleted_at, created_at, updated_at
                )
                VALUES (
                  :id, :prompt_id, :title, :content, :translation, :edit_idea, :model_id,
                  :parent_variant_id, :session_id, :round_index, :user_instruction,
                  :explanation_cn, :feature_cn, :analysis_snapshot,
                  :use_count, :last_used_at, :deleted_at, :created_at, :updated_at
                )
                ON CONFLICT(id) DO UPDATE SET
                  title = excluded.title,
                  content = excluded.content,
                  translation = excluded.translation,
                  edit_idea = excluded.edit_idea,
                  model_id = excluded.model_id,
                  parent_variant_id = excluded.parent_variant_id,
                  session_id = excluded.session_id,
                  round_index = excluded.round_index,
                  user_instruction = excluded.user_instruction,
                  explanation_cn = excluded.explanation_cn,
                  feature_cn = excluded.feature_cn,
                  analysis_snapshot = excluded.analysis_snapshot,
                  deleted_at = excluded.deleted_at,
                  updated_at = excluded.updated_at
                """,
                clean,
            )
            conn.execute("UPDATE prompts SET updated_at = ? WHERE id = ?", (now, prompt_id))
        return self.get_prompt(prompt_id)

    def mark_prompt_variant_used(self, variant_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT prompt_id FROM prompt_variants WHERE id = ?", (variant_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown prompt variant: {variant_id}")
            conn.execute(
                "UPDATE prompt_variants SET use_count = use_count + 1, last_used_at = ?, updated_at = ? WHERE id = ?",
                (utc_now(), utc_now(), variant_id),
            )
            conn.execute(
                "UPDATE prompts SET use_count = use_count + 1, last_used_at = ?, updated_at = ? WHERE id = ?",
                (utc_now(), utc_now(), row["prompt_id"]),
            )
            prompt_id = row["prompt_id"]
        return self.get_prompt(prompt_id)

    def soft_delete_prompt_variant(self, variant_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT prompt_id FROM prompt_variants WHERE id = ?", (variant_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown prompt variant: {variant_id}")
            conn.execute("UPDATE prompt_variants SET deleted_at = ?, updated_at = ? WHERE id = ?", (utc_now(), utc_now(), variant_id))
            prompt_id = row["prompt_id"]
        return self.get_prompt(prompt_id)

    def soft_delete_prompt(self, prompt_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("UPDATE prompts SET deleted_at = ?, updated_at = ? WHERE id = ?", (utc_now(), utc_now(), prompt_id))
        return self.get_prompt(prompt_id)

    def mark_prompt_used(self, prompt_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                "UPDATE prompts SET use_count = use_count + 1, last_used_at = ?, updated_at = ? WHERE id = ?",
                (utc_now(), utc_now(), prompt_id),
            )
        return self.get_prompt(prompt_id)

    def _app_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("auto_unzip", "favorite", "enabled"):
            data[key] = bool(data[key])
        data["inputs"] = self._deserialize_inputs(data.get("inputs"), data)
        data["cover_url"] = f"/files/{data['cover_path']}" if data.get("cover_path") else "/default-app-icon.png"
        return data

    def _task_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["saved"] = bool(data["saved"])
        data["outputs"] = json.loads(data["outputs"] or "[]")
        data["input_payload"] = json.loads(data.get("input_payload") or "{}")
        data["input_url"] = f"/files/{data['input_path']}" if data.get("input_path") else ""
        return data

    def _album_item_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["blurred"] = bool(data.get("blurred"))
        data["deleted"] = bool(data.get("deleted_at"))
        data["path"] = data.get("file_path") or ""
        data["url"] = f"/files/{data['file_path']}" if data.get("file_path") else ""
        data["download_name"] = Path(data["file_path"]).name if data.get("file_path") else ""
        data["type"] = "image"
        if not data.get("title"):
            data["title"] = data.get("app_name") or "作品"
        return data

    def _prompt_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["favorite"] = bool(data["favorite"])
        data["tags"] = self._loads_list(data.get("tags"))
        data["deleted"] = bool(data.get("deleted_at"))
        sample_path = data.get("sample_path") or ""
        data["sample_url"] = f"/pose-files/{sample_path.removeprefix('pose:')}" if sample_path.startswith("pose:") else f"/files/{sample_path}" if sample_path else ""
        with self.connect() as conn:
            links = conn.execute(
                """
                SELECT apps.id, apps.name, apps.webapp_id
                FROM prompt_app_links
                JOIN apps ON apps.id = prompt_app_links.app_id
                WHERE prompt_app_links.prompt_id = ?
                ORDER BY apps.sort_order ASC, apps.name ASC
                """,
                (data["id"],),
            ).fetchall()
        data["app_ids"] = [row["id"] for row in links]
        data["apps"] = [dict(row) for row in links]
        data["variants"] = []
        return data

    def _attach_prompt_variants(self, prompts: list[dict[str, Any]], include_deleted: bool = False) -> list[dict[str, Any]]:
        if not prompts:
            return prompts
        prompt_ids = [prompt["id"] for prompt in prompts]
        placeholders = ",".join("?" for _ in prompt_ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM prompt_variants
                WHERE prompt_id IN ({placeholders})
                  AND (? = 1 OR deleted_at IS NULL)
                ORDER BY updated_at DESC
                """,
                (*prompt_ids, 1 if include_deleted else 0),
            ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {prompt_id: [] for prompt_id in prompt_ids}
        for row in rows:
            item = dict(row)
            item["deleted"] = bool(item.get("deleted_at"))
            grouped.setdefault(item["prompt_id"], []).append(item)
        for prompt in prompts:
            prompt["variants"] = grouped.get(prompt["id"], [])
        return prompts

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _is_image_output(self, output: dict[str, Any]) -> bool:
        output_type = str(output.get("type") or "").lower()
        if output_type in {"image", "png", "jpg", "jpeg", "webp"}:
            return True
        path = str(output.get("path") or "")
        return Path(path).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

    def _migrate_embedded_prompt_variants(self, conn: sqlite3.Connection) -> None:
        marker = "---- AI 衍生提示词"
        rows = conn.execute("SELECT id, content FROM prompts WHERE content LIKE ?", (f"%{marker}%",)).fetchall()
        for row in rows:
            content = str(row["content"] or "")
            marker_index = content.find(marker)
            if marker_index <= 0:
                continue
            base_content = content[:marker_index].strip()
            blocks = [block.strip() for block in content[marker_index:].split(marker) if block.strip()]
            now = utc_now()
            for block in blocks:
                title_end = block.find("----")
                title = f"AI 衍生 {block[:title_end].strip()}" if title_end >= 0 else "AI 衍生提示词"
                body = block[title_end + 4:].strip() if title_end >= 0 else block
                edit_idea = ""
                if body.startswith("修改想法："):
                    first_line, _, rest = body.partition("\n")
                    edit_idea = first_line.removeprefix("修改想法：").strip()
                    body = rest.strip()
                prompt_text, translation = body, ""
                if "\n中文翻译：" in body:
                    prompt_text, _, translation = body.partition("\n中文翻译：")
                prompt_text = prompt_text.strip()
                translation = translation.strip()
                if not prompt_text:
                    continue
                conn.execute(
                    """
                    INSERT INTO prompt_variants (
                      id, prompt_id, title, content, translation, edit_idea, model_id,
                      use_count, last_used_at, deleted_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, '', 0, NULL, NULL, ?, ?)
                    """,
                    (uuid.uuid4().hex, row["id"], title or "AI 衍生提示词", prompt_text, translation, edit_idea, now, now),
                )
            conn.execute("UPDATE prompts SET content = ?, updated_at = ? WHERE id = ?", (base_content, now, row["id"]))

    def _normalize_app(self, data: dict[str, Any], app_id: str | None = None) -> dict[str, Any]:
        normalized = {
            "id": app_id or data.get("id") or uuid.uuid4().hex,
            "name": str(data.get("name") or "").strip(),
            "description": str(data.get("description") or "").strip(),
            "webapp_id": str(data.get("webapp_id") or "").strip(),
            "node_id": str(data.get("node_id") or "").strip(),
            "field_name": str(data.get("field_name") or "").strip(),
            "input_type": str(data.get("input_type") or "image").strip(),
            "output_type": str(data.get("output_type") or "png").strip().lower(),
            "auto_unzip": self._truthy(data.get("auto_unzip")),
            "category": str(data.get("category") or "其他").strip(),
            "favorite": self._truthy(data.get("favorite")),
            "accent": str(data.get("accent") or "#6d5dfc").strip(),
            "cover_path": str(data.get("cover_path") or "").strip(),
            "source_url": str(data.get("source_url") or "").strip(),
            "prompt_node_id": str(data.get("prompt_node_id") or "").strip(),
            "prompt_field_name": str(data.get("prompt_field_name") or "").strip(),
            "default_prompt": str(data.get("default_prompt") or "").strip(),
            "inputs": self._normalize_inputs(data.get("inputs")),
            "sort_order": int(data.get("sort_order") or 100),
            "enabled": self._truthy(data.get("enabled", True)),
        }
        if not normalized["name"]:
            raise ValueError("样式名称不能为空")
        if not normalized["webapp_id"]:
            raise ValueError("RunningHub 应用 ID 不能为空")
        if not normalized["inputs"] and normalized["node_id"] and normalized["field_name"]:
            normalized["inputs"] = self._legacy_inputs(normalized)
        else:
            normalized["inputs"] = self._merge_legacy_nodes(normalized, normalized["inputs"])
        if not normalized["inputs"]:
            raise ValueError("至少需要一个输入项")
        normalized = self._sync_prompt_metadata(normalized)
        if normalized["output_type"] not in {"png", "jpg", "jpeg", "webp", "zip"}:
            raise ValueError("输出类型只能是 png、jpg、jpeg、webp 或 zip")
        return normalized

    def _serialize_app(self, app: dict[str, Any]) -> dict[str, Any]:
        return {
            **app,
            "auto_unzip": int(self._truthy(app.get("auto_unzip"))),
            "favorite": int(self._truthy(app.get("favorite"))),
            "enabled": int(self._truthy(app.get("enabled", True))),
            "sort_order": int(app.get("sort_order") or 100),
            "cover_path": app.get("cover_path") or "",
            "source_url": app.get("source_url") or "",
            "prompt_node_id": app.get("prompt_node_id") or "",
            "prompt_field_name": app.get("prompt_field_name") or "",
            "default_prompt": app.get("default_prompt") or "",
            "inputs": json.dumps(self._normalize_inputs(app.get("inputs")) or self._legacy_inputs(app), ensure_ascii=False),
        }

    def _deserialize_inputs(self, raw: Any, app: dict[str, Any]) -> list[dict[str, Any]]:
        inputs = self._normalize_inputs(raw)
        return inputs or self._legacy_inputs(app)

    def _normalize_inputs(self, raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("输入项配置不是有效 JSON") from exc
        if not isinstance(raw, list):
            return []
        normalized = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("nodeId") or item.get("node_id") or "").strip()
            field_name = str(item.get("fieldName") or item.get("field_name") or "").strip()
            if not node_id or not field_name:
                continue
            input_id = str(item.get("id") or f"input_{index}").strip()
            input_type = str(item.get("type") or "text").strip().lower()
            if input_type not in {"image", "file", "text", "textarea", "select", "number", "checkbox", "hidden"}:
                input_type = "text"
            options = item.get("options") or []
            if not isinstance(options, list):
                options = []
            required = self._truthy(item.get("required", True))
            label = str(item.get("label") or field_name).strip()
            if input_type in {"image", "file"} and any(token in label.lower() for token in ("选填", "可选", "非必填", "不用", "不上传", "optional")):
                required = False
            normalized.append({
                "id": input_id,
                "nodeId": node_id,
                "fieldName": field_name,
                "type": input_type,
                "label": label,
                "required": required,
                "defaultValue": str(item.get("defaultValue") or item.get("default") or ""),
                "options": [str(option) for option in options],
                "role": "prompt" if self._is_prompt_input(item, input_type, field_name) else "",
                "outputTypeMap": self._normalize_output_type_map(item.get("outputTypeMap") or item.get("output_type_map")),
            })
        return normalized

    def _normalize_output_type_map(self, raw: Any) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        allowed = {"png", "jpg", "jpeg", "webp", "zip"}
        return {
            str(key): str(value).lower()
            for key, value in raw.items()
            if str(value).lower() in allowed
        }

    def _legacy_inputs(self, app: dict[str, Any]) -> list[dict[str, Any]]:
        inputs = []
        node_id = str(app.get("node_id") or "").strip()
        field_name = str(app.get("field_name") or "image").strip()
        if node_id and field_name:
            inputs.append({
                "id": "image",
                "nodeId": node_id,
                "fieldName": field_name,
                "type": "image",
                "label": "图片",
                "required": True,
                "defaultValue": "",
                "options": [],
            })
        prompt_node_id = str(app.get("prompt_node_id") or "").strip()
        prompt_field_name = str(app.get("prompt_field_name") or "").strip()
        if prompt_node_id and prompt_field_name:
            inputs.append({
                "id": "prompt",
                "nodeId": prompt_node_id,
                "fieldName": prompt_field_name,
                "type": "textarea",
                "label": "提示词",
                "required": False,
                "defaultValue": str(app.get("default_prompt") or ""),
                "options": [],
                "role": "prompt",
            })
        return inputs

    def _merge_legacy_nodes(self, app: dict[str, Any], inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        existing = {(item["nodeId"], item["fieldName"]) for item in inputs}
        merged = list(inputs)
        for item in self._legacy_inputs(app):
            key = (item["nodeId"], item["fieldName"])
            if key not in existing:
                merged.append(item)
                existing.add(key)
        return merged

    def _truthy(self, value: Any) -> bool:
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _normalize_prompt(self, data: dict[str, Any], prompt_id: str | None = None) -> dict[str, Any]:
        title = str(data.get("title") or "").strip()
        content = str(data.get("content") or "").strip()
        if not content:
            raise ValueError("提示词内容不能为空")
        if not title:
            title = content.splitlines()[0][:40] or "未命名提示词"
        tags = data.get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in re_split_tags(tags) if item.strip()]
        if not isinstance(tags, list):
            tags = []
        app_ids = data.get("app_ids") or data.get("appIds") or []
        if isinstance(app_ids, str):
            app_ids = [item.strip() for item in app_ids.split(",") if item.strip()]
        if not isinstance(app_ids, list):
            app_ids = []
        return {
            "id": prompt_id or data.get("id") or uuid.uuid4().hex,
            "title": title,
            "content": content,
            "tags": json.dumps([str(item).strip() for item in tags if str(item).strip()], ensure_ascii=False),
            "favorite": int(self._truthy(data.get("favorite"))),
            "note": str(data.get("note") or "").strip(),
            "sample_path": str(data.get("sample_path") or "").strip(),
            "use_count": int(data.get("use_count") or 0),
            "last_used_at": data.get("last_used_at") or None,
            "deleted_at": data.get("deleted_at") or None,
            "app_ids": [str(app_id).strip() for app_id in app_ids if str(app_id).strip()],
        }

    def _loads_list(self, raw: Any) -> list[Any]:
        if isinstance(raw, list):
            return raw
        if not raw:
            return []
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    def _sync_prompt_metadata(self, app: dict[str, Any]) -> dict[str, Any]:
        prompt_node = app.get("prompt_node_id")
        prompt_field = app.get("prompt_field_name")
        inputs = []
        prompt_input = None
        for item in app["inputs"]:
            current = dict(item)
            if prompt_node and prompt_field and current["nodeId"] == prompt_node and current["fieldName"] == prompt_field:
                current["role"] = "prompt"
            if current.get("role") == "prompt" and prompt_input is None:
                prompt_input = current
            inputs.append(current)
        if prompt_input:
            app["prompt_node_id"] = prompt_input["nodeId"]
            app["prompt_field_name"] = prompt_input["fieldName"]
            if not app.get("default_prompt"):
                app["default_prompt"] = prompt_input.get("defaultValue") or ""
        app["inputs"] = inputs
        return app

    def _is_prompt_input(self, item: dict[str, Any], input_type: str, field_name: str) -> bool:
        role = str(item.get("role") or "").strip().lower()
        if role == "prompt" or self._truthy(item.get("isPrompt")) or self._truthy(item.get("is_prompt")):
            return True
        label = str(item.get("label") or "").lower()
        field = field_name.lower()
        if input_type not in {"text", "textarea"}:
            return False
        return any(token in field for token in ("prompt",)) or any(token in label for token in ("提示词", "prompt", "输入文本"))


def re_split_tags(value: str) -> list[str]:
    return [item for chunk in value.splitlines() for item in chunk.replace("，", ",").replace("、", ",").split(",")]
