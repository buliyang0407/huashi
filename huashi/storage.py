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

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT tasks.*, apps.name AS app_name, apps.category AS app_category
                FROM tasks
                JOIN apps ON apps.id = tasks.app_id
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
                SELECT tasks.*, apps.name AS app_name, apps.category AS app_category
                FROM tasks
                JOIN apps ON apps.id = tasks.app_id
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def delete_task_record(self, task_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def _app_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("auto_unzip", "favorite", "enabled"):
            data[key] = bool(data[key])
        data["inputs"] = self._deserialize_inputs(data.get("inputs"), data)
        data["cover_url"] = f"/files/{data['cover_path']}" if data.get("cover_path") else ""
        return data

    def _task_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["saved"] = bool(data["saved"])
        data["outputs"] = json.loads(data["outputs"] or "[]")
        data["input_payload"] = json.loads(data.get("input_payload") or "{}")
        data["input_url"] = f"/files/{data['input_path']}" if data.get("input_path") else ""
        return data

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

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
            if input_type not in {"image", "file", "text", "textarea", "select", "number"}:
                input_type = "text"
            options = item.get("options") or []
            if not isinstance(options, list):
                options = []
            normalized.append({
                "id": input_id,
                "nodeId": node_id,
                "fieldName": field_name,
                "type": input_type,
                "label": str(item.get("label") or field_name).strip(),
                "required": self._truthy(item.get("required", True)),
                "defaultValue": str(item.get("defaultValue") or item.get("default") or ""),
                "options": [str(option) for option in options],
            })
        return normalized

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
