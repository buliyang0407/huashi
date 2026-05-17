from __future__ import annotations

import shutil
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .runninghub import RunningHubError
from .storage import HuashiStore, utc_now
from .zip_utils import safe_extract_zip


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class HuashiService:
    def __init__(self, data_root: Path | str, store: HuashiStore, runninghub_client: Any):
        self.data_root = Path(data_root)
        self.store = store
        self.runninghub = runninghub_client
        for folder in ("uploads", "cache", "archive", "thumbnails", "backups"):
            (self.data_root / folder).mkdir(parents=True, exist_ok=True)

    def create_task_from_upload(
        self,
        app_id: str,
        filename: str,
        content: bytes,
        prompt: str = "",
        start_background: bool = True,
    ) -> dict[str, Any]:
        return self.create_task_from_form(
            app_id=app_id,
            fields={"input_image": "", "prompt": prompt},
            files={"input_image": {"filename": filename, "content": content}},
            start_background=start_background,
        )

    def create_task_from_form(
        self,
        app_id: str,
        fields: dict[str, str],
        files: dict[str, dict[str, object]],
        start_background: bool = True,
    ) -> dict[str, Any]:
        app = self.store.get_app(app_id)
        inputs = app.get("inputs") or []
        temp_task = self.store.create_task(app_id=app_id, input_path="", input_name="参数生成", input_payload={})
        date_parts = datetime.now().strftime("%Y/%m/%d").split("/")
        task_dir = self.data_root / "uploads" / date_parts[0] / date_parts[1] / date_parts[2] / temp_task["id"]
        task_dir.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {"values": {}, "files": {}}
        first_path = ""
        first_name = ""
        for item in inputs:
            input_id = item["id"]
            form_name = f"input_{input_id}"
            input_type = item.get("type")
            if input_type in {"image", "file"}:
                upload = files.get(form_name)
                if not upload:
                    continue
                safe_name = Path(str(upload["filename"])).name or "input"
                destination = task_dir / f"{input_id}_{safe_name}"
                destination.write_bytes(upload["content"])  # type: ignore[arg-type]
                rel_path = self._rel(destination)
                payload["files"][input_id] = {"path": rel_path, "name": safe_name}
                first_path = first_path or rel_path
                first_name = first_name or safe_name
            else:
                value = (fields.get(form_name) or item.get("defaultValue") or "").strip()
                payload["values"][input_id] = value
                if value and not first_name:
                    first_name = value[:40]

        legacy_prompt = (fields.get("prompt") or "").strip()
        if legacy_prompt:
            payload["values"]["prompt"] = legacy_prompt

        with self.store.connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET input_path = ?, input_name = ?, input_payload = ?, prompt = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    first_path,
                    first_name or "参数生成",
                    self._json_dumps(payload),
                    legacy_prompt,
                    utc_now(),
                    temp_task["id"],
                ),
            )
        task = self.store.get_task(temp_task["id"])
        if start_background:
            threading.Thread(target=self.process_task, args=(task["id"],), daemon=True).start()
        return task

    def _create_legacy_upload_task(
        self,
        app_id: str,
        filename: str,
        content: bytes,
        prompt: str = "",
        start_background: bool = True,
    ) -> dict[str, Any]:
        self.store.get_app(app_id)
        safe_name = Path(filename).name or "input.png"
        date_parts = datetime.now().strftime("%Y/%m/%d").split("/")
        upload_dir = self.data_root / "uploads" / date_parts[0] / date_parts[1] / date_parts[2]
        upload_dir.mkdir(parents=True, exist_ok=True)
        temp_task = self.store.create_task(app_id=app_id, input_path="", input_name=safe_name, prompt=prompt.strip())
        task_dir = upload_dir / temp_task["id"]
        task_dir.mkdir(parents=True, exist_ok=True)
        input_path = task_dir / safe_name
        input_path.write_bytes(content)
        task = self.store.update_task(temp_task["id"], status="queued", error=None)
        # Update input_path directly because create_task generates the task id used in the path.
        with self.store.connect() as conn:
            conn.execute("UPDATE tasks SET input_path = ?, updated_at = ? WHERE id = ?", (self._rel(input_path), utc_now(), task["id"]))
        task = self.store.get_task(task["id"])
        if start_background:
            threading.Thread(target=self.process_task, args=(task["id"],), daemon=True).start()
        return task

    def process_task(self, task_id: str, poll_interval: float = 5, timeout: float = 600) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        app = self.store.get_app(task["app_id"])
        try:
            self.store.update_task(task_id, status="running", error=None)
            node_info_list = self._build_node_info_list(task, app)
            run_data = self._run_app(app["webapp_id"], node_info_list)
            runninghub_task_id = run_data["taskId"]
            self.store.update_task(task_id, runninghub_task_id=runninghub_task_id, status="running")
            self.runninghub.wait_for_success(runninghub_task_id, poll_interval=poll_interval, timeout=timeout)
            outputs = self.runninghub.get_outputs(runninghub_task_id)
            local_outputs = self._download_outputs(task_id, outputs, app)
            return self.store.update_task(
                task_id,
                status="success",
                output_type=app["output_type"],
                cache_path=self._rel(self.data_root / "cache" / task_id),
                outputs=local_outputs,
                completed_at=utc_now(),
                error=None,
            )
        except Exception as exc:
            message = str(exc)
            if isinstance(exc, RunningHubError):
                api_key = getattr(self.runninghub, "api_key", "")
                if api_key:
                    message = message.replace(api_key, "***")
            return self.store.update_task(task_id, status="failed", error=message, completed_at=utc_now())

    def archive_task(self, task_id: str) -> dict[str, Any]:
        task = self.store.get_task(task_id)
        if not task.get("cache_path"):
            raise ValueError("Task has no cached output to archive")
        stamp = datetime.now().strftime("%Y-%m-%d")
        archive_dir = self.data_root / "archive" / datetime.now().strftime("%Y/%m") / f"{stamp}_{task['app_name']}_{task_id}"
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
        shutil.copytree(self.data_root / task["cache_path"], archive_dir)
        input_dir = archive_dir / "input"
        input_dir.mkdir(exist_ok=True)
        if task.get("input_path"):
            shutil.copy2(self.data_root / task["input_path"], input_dir / Path(task["input_path"]).name)
        (input_dir / "inputs.json").write_text(self._json_dumps(task.get("input_payload") or {}), encoding="utf-8")
        return self.store.update_task(task_id, archive_path=self._rel(archive_dir), saved=True)

    def retry_task(self, task_id: str, start_background: bool = True) -> dict[str, Any]:
        old = self.store.get_task(task_id)
        payload = old.get("input_payload") or {}
        fields = {f"input_{key}": str(value) for key, value in (payload.get("values") or {}).items()}
        files = {}
        for key, file_info in (payload.get("files") or {}).items():
            file_path = self.data_root / file_info.get("path", "")
            if file_path.exists():
                files[f"input_{key}"] = {
                    "filename": file_info.get("name") or file_path.name,
                    "content": file_path.read_bytes(),
                }
        new_task = self.create_task_from_form(old["app_id"], fields, files, start_background=False)
        if start_background:
            threading.Thread(target=self.process_task, args=(new_task["id"],), daemon=True).start()
        return new_task

    def _build_node_info_list(self, task: dict[str, Any], app: dict[str, Any]) -> list[dict[str, str]]:
        inputs = app.get("inputs") or []
        payload = task.get("input_payload") or {}
        values = payload.get("values") or {}
        file_map = payload.get("files") or {}
        node_info_list = []
        for item in inputs:
            input_id = item["id"]
            input_type = item.get("type")
            value = ""
            if input_type in {"image", "file"}:
                file_info = file_map.get(input_id) or {}
                path = file_info.get("path")
                if path:
                    value = self.runninghub.upload_media(self.data_root / path)
            else:
                value = str(values.get(input_id) or item.get("defaultValue") or "").strip()
            if not value and not item.get("required", True):
                continue
            if not value:
                raise ValueError(f"缺少输入：{item.get('label') or input_id}")
            node_info_list.append({
                "nodeId": str(item["nodeId"]),
                "fieldName": str(item["fieldName"]),
                "fieldValue": value,
            })
        if node_info_list:
            return node_info_list

        uploaded_file = self.runninghub.upload_media(self.data_root / task["input_path"])
        legacy_nodes = [{"nodeId": app["node_id"], "fieldName": app["field_name"], "fieldValue": uploaded_file}]
        prompt = (task.get("prompt") or app.get("default_prompt") or "").strip()
        if prompt and app.get("prompt_node_id") and app.get("prompt_field_name"):
            legacy_nodes.append({
                "nodeId": app["prompt_node_id"],
                "fieldName": app["prompt_field_name"],
                "fieldValue": prompt,
            })
        return legacy_nodes

    def _run_app(self, webapp_id: str, node_info_list: list[dict[str, str]]) -> dict[str, Any]:
        if hasattr(self.runninghub, "run_app_nodes"):
            return self.runninghub.run_app_nodes(webapp_id, node_info_list)
        first, *extra_nodes = node_info_list
        return self.runninghub.run_app(
            webapp_id,
            first["nodeId"],
            first["fieldName"],
            first["fieldValue"],
            extra_nodes=extra_nodes,
        )

    def _json_dumps(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2)

    def export_apps_bundle(self) -> dict[str, Any]:
        return {
            "kind": "huashi-apps-backup",
            "version": 1,
            "exported_at": utc_now(),
            "apps": service_apps_for_backup(self.store.list_all_apps()),
        }

    def write_apps_backup(self, reason: str = "manual") -> Path:
        safe_reason = "".join(char for char in reason if char.isalnum() or char in {"-", "_"}) or "manual"
        backup_dir = self.data_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = backup_dir / f"huashi-apps-{stamp}-{safe_reason}.json"
        path.write_text(self._json_dumps(self.export_apps_bundle()), encoding="utf-8")
        return path

    def import_apps_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        apps = bundle.get("apps") if isinstance(bundle, dict) else None
        if not isinstance(apps, list):
            raise ValueError("备份文件格式不对：缺少 apps 列表")

        before_backup = self.write_apps_backup("before-import")
        imported = []
        for app in apps:
            if not isinstance(app, dict):
                continue
            app_id = str(app.get("id") or "").strip() or None
            imported.append(self.store.save_app(app, app_id=app_id))
        after_backup = self.write_apps_backup("after-import")
        return {
            "count": len(imported),
            "before_backup": self._rel(before_backup),
            "after_backup": self._rel(after_backup),
        }

    def delete_task(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        for key in ("cache_path", "archive_path"):
            rel = task.get(key)
            if rel:
                target = self.data_root / rel
                if target.exists() and self.data_root.resolve() in target.resolve().parents:
                    shutil.rmtree(target)
        self.store.delete_task_record(task_id)

    def _download_outputs(self, task_id: str, outputs: list[dict[str, Any]], app: dict[str, Any]) -> list[dict[str, Any]]:
        cache_dir = self.data_root / "cache" / task_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        local_outputs: list[dict[str, Any]] = []
        for index, output in enumerate(outputs, start=1):
            file_type = (output.get("fileType") or output.get("type") or app["output_type"]).lower()
            url = output.get("fileUrl") or output.get("url")
            if not url:
                continue
            suffix = "." + file_type.strip(".")
            destination = cache_dir / ("original.zip" if file_type == "zip" else f"output-{index}{suffix}")
            self.runninghub.download_file(url, destination)
            local_outputs.append(
                {
                    "type": file_type,
                    "nodeId": output.get("nodeId"),
                    "path": self._rel(destination),
                    "url": f"/files/{self._rel(destination)}",
                }
            )
            if file_type == "zip" and app.get("auto_unzip"):
                extracted_root = cache_dir / "extracted"
                for member in safe_extract_zip(destination, extracted_root):
                    member_path = extracted_root / member
                    if member_path.suffix.lower() in IMAGE_SUFFIXES:
                        local_outputs.append(
                            {
                                "type": "image",
                                "path": self._rel(member_path),
                                "url": f"/files/{self._rel(member_path)}",
                            }
                        )
        return local_outputs

    def _rel(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.data_root.resolve()))

    def save_cover(self, app_id: str, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("封面只支持图片文件")
        cover_dir = self.data_root / "covers" / app_id
        cover_dir.mkdir(parents=True, exist_ok=True)
        cover_path = cover_dir / f"cover{suffix}"
        cover_path.write_bytes(content)
        return self._rel(cover_path)


def service_apps_for_backup(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in app.items() if key != "cover_url"}
        for app in apps
    ]
