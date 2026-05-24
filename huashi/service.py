from __future__ import annotations

import shutil
import threading
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .runninghub import RunningHubError
from .prompt_ai import rewrite_prompt_stream, translate_prompt_stream
from .prompt_agent import analyze_prompt, generate_prompt_variant, refine_prompt_variant
from .storage import HuashiStore, utc_now
from .zip_utils import safe_extract_zip


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class HuashiService:
    def __init__(self, data_root: Path | str, store: HuashiStore, runninghub_client: Any):
        self.data_root = Path(data_root)
        self.pose_root = Path(os.getenv("HUASHI_POSE_DIR", str(self.data_root.parent / "pose")))
        self.store = store
        self.runninghub = runninghub_client
        for folder in ("uploads", "cache", "archive", "thumbnails", "backups", "albums"):
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
                artwork_path = (fields.get(f"{form_name}_artwork") or "").strip()
                if upload:
                    safe_name = Path(str(upload["filename"])).name or "input"
                    source = "upload"
                    destination = task_dir / f"{input_id}_{safe_name}"
                    destination.write_bytes(upload["content"])  # type: ignore[arg-type]
                elif artwork_path:
                    artwork = self._resolve_artwork_path(artwork_path)
                    safe_name = artwork.name
                    source = "artwork"
                    destination = task_dir / f"{input_id}_{safe_name}"
                    shutil.copy2(artwork, destination)
                else:
                    continue
                rel_path = self._rel(destination)
                payload["files"][input_id] = {"path": rel_path, "name": safe_name, "source": source}
                first_path = first_path or rel_path
                first_name = first_name or safe_name
            else:
                if input_type == "checkbox":
                    value = "true" if fields.get(form_name) else "false"
                else:
                    value = (fields.get(form_name) or item.get("defaultValue") or "").strip()
                payload["values"][input_id] = value
                if value and not first_name:
                    first_name = value[:40]

        legacy_prompt = (fields.get("prompt") or "").strip()
        if legacy_prompt:
            payload["values"]["prompt"] = legacy_prompt
        prompt = self._prompt_value_from_payload(app, payload) or legacy_prompt

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
                    prompt,
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
            resolved_app = {**app, "output_type": self._resolve_output_type(task, app)}
            local_outputs = self._download_outputs(task_id, outputs, resolved_app)
            return self.store.update_task(
                task_id,
                status="success",
                output_type=resolved_app["output_type"],
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
                elif not item.get("required", True):
                    value = ""
            elif input_type == "checkbox":
                value = "true" if str(values.get(input_id) or item.get("defaultValue") or "").lower() in {"1", "true", "yes", "on"} else "false"
            else:
                value = str(values.get(input_id) or item.get("defaultValue") or "").strip()
            if input_type in {"image", "file"} and not item.get("required", True) and not value:
                node_info_list.append({
                    "nodeId": str(item["nodeId"]),
                    "fieldName": str(item["fieldName"]),
                    "fieldValue": "",
                })
                continue
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

    def _resolve_output_type(self, task: dict[str, Any], app: dict[str, Any]) -> str:
        values = (task.get("input_payload") or {}).get("values") or {}
        for item in app.get("inputs") or []:
            output_map = item.get("outputTypeMap") or {}
            if not output_map:
                continue
            selected = str(values.get(item["id"]) or item.get("defaultValue") or "").strip()
            mapped = output_map.get(selected)
            if mapped:
                return str(mapped).lower()
        return str(app.get("output_type") or "png").lower()

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
            "kind": "huashi-backup",
            "version": 3,
            "exported_at": utc_now(),
            "apps": service_apps_for_backup(self.store.list_all_apps()),
            "prompts": service_prompts_for_backup(self.store.list_prompts()),
        }

    def write_apps_backup(self, reason: str = "manual") -> Path:
        safe_reason = "".join(char for char in reason if char.isalnum() or char in {"-", "_"}) or "manual"
        backup_dir = self.data_root / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = backup_dir / f"huashi-backup-{stamp}-{safe_reason}.json"
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
        imported_prompts = []
        prompts = bundle.get("prompts") if isinstance(bundle, dict) else []
        if isinstance(prompts, list):
            app_by_webapp_id = {app["webapp_id"]: app["id"] for app in self.store.list_all_apps()}
            app_ids = {app["id"] for app in self.store.list_all_apps()}
            for prompt in prompts:
                if not isinstance(prompt, dict):
                    continue
                linked_ids = [app_id for app_id in prompt.get("app_ids", []) if app_id in app_ids]
                linked_ids.extend(
                    app_by_webapp_id[webapp_id]
                    for webapp_id in prompt.get("app_webapp_ids", [])
                    if webapp_id in app_by_webapp_id and app_by_webapp_id[webapp_id] not in linked_ids
                )
                saved_prompt = self.store.save_prompt({**prompt, "app_ids": linked_ids}, prompt_id=prompt.get("id"))
                imported_prompts.append(saved_prompt)
                variants = prompt.get("variants") if isinstance(prompt.get("variants"), list) else []
                for variant in variants:
                    if isinstance(variant, dict):
                        self.store.save_prompt_variant(saved_prompt["id"], variant, variant_id=variant.get("id"))
        after_backup = self.write_apps_backup("after-import")
        return {
            "count": len(imported),
            "prompt_count": len(imported_prompts),
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
        image_index = 1
        for index, output in enumerate(outputs, start=1):
            file_type = (output.get("fileType") or output.get("type") or app["output_type"]).lower()
            url = output.get("fileUrl") or output.get("url")
            if not url:
                continue
            if ".zip" in url.split("?", 1)[0].lower():
                file_type = "zip"
            suffix = "." + file_type.strip(".")
            destination = cache_dir / ("original.zip" if file_type == "zip" else self._output_filename(app, task_id, index, suffix))
            self.runninghub.download_file(url, destination)
            local_outputs.append(
                {
                    "type": file_type,
                    "nodeId": output.get("nodeId"),
                    "path": self._rel(destination),
                    "url": f"/files/{self._rel(destination)}",
                    "download_name": destination.name,
                }
            )
            if file_type == "zip" and app.get("auto_unzip"):
                extracted_root = cache_dir / "extracted"
                for member in safe_extract_zip(destination, extracted_root):
                    member_path = extracted_root / member
                    if member_path.suffix.lower() in IMAGE_SUFFIXES:
                        public_path = cache_dir / self._output_filename(app, task_id, image_index, member_path.suffix.lower())
                        image_index += 1
                        shutil.copy2(member_path, public_path)
                        local_outputs.append(
                            {
                                "type": "image",
                                "path": self._rel(public_path),
                                "url": f"/files/{self._rel(public_path)}",
                                "download_name": public_path.name,
                            }
                        )
        return local_outputs

    def _rel(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.data_root.resolve()))

    def _resolve_artwork_path(self, rel_path: str) -> Path:
        if rel_path.startswith("pose:"):
            return self.resolve_pose_path(rel_path.removeprefix("pose:"))
        target = (self.data_root / rel_path).resolve()
        root = self.data_root.resolve()
        if target != root and root not in target.parents:
            raise ValueError("作品路径不在画室数据目录内")
        if not target.exists() or target.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("选择的作品图片不存在")
        return target

    def pose_available(self) -> bool:
        return self.pose_root.exists() and self.pose_root.is_dir()

    def pose_summary(self) -> dict[str, Any] | None:
        if not self.pose_available():
            return None
        directory_count = 0
        image_count = 0
        try:
            for entry in self.pose_root.iterdir():
                if entry.is_dir():
                    directory_count += 1
                elif entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
                    image_count += 1
        except OSError:
            return None
        return {
            "id": "__pose__",
            "name": "POSE",
            "sort_order": 9000,
            "created_at": "",
            "updated_at": "",
            "item_count": image_count,
            "directory_count": directory_count,
            "virtual": True,
        }

    def list_pose_directory(self, rel_path: str = "", offset: int = 0, limit: int = 120) -> dict[str, Any]:
        root = self.pose_root.resolve()
        target = self.resolve_pose_directory(rel_path)
        directories: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        try:
            entries = list(target.iterdir())
        except OSError as exc:
            raise ValueError("POSE 文件夹无法读取") from exc
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                child_rel = entry.resolve().relative_to(root).as_posix()
                directories.append({"name": entry.name, "path": child_rel})
            elif entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
                child_rel = entry.resolve().relative_to(root).as_posix()
                stat = entry.stat()
                images.append(
                    {
                        "id": f"pose:{child_rel}",
                        "source_type": "pose",
                        "folder_id": "__pose__",
                        "path": f"pose:{child_rel}",
                        "pose_path": child_rel,
                        "url": f"/pose-files/{quote(child_rel)}",
                        "download_name": entry.name,
                        "title": entry.stem,
                        "type": "image",
                        "blurred": False,
                        "deleted": False,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": stat.st_size,
                    }
                )
        directories.sort(key=lambda item: item["name"].lower())
        images.sort(key=lambda item: item["download_name"].lower())
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(20, min(int(limit or 120), 240))
        sliced_images = images[safe_offset:safe_offset + safe_limit]
        breadcrumbs = []
        parts = [part for part in target.relative_to(root).parts if part]
        for index, part in enumerate(parts):
            breadcrumbs.append({"name": part, "path": "/".join(parts[:index + 1])})
        return {
            "path": "" if target == root else target.relative_to(root).as_posix(),
            "name": "POSE" if target == root else target.name,
            "breadcrumbs": breadcrumbs,
            "directories": directories,
            "items": sliced_images,
            "image_count": len(images),
            "next_offset": safe_offset + safe_limit if safe_offset + safe_limit < len(images) else None,
        }

    def resolve_pose_directory(self, rel_path: str) -> Path:
        target = self._safe_pose_path(rel_path)
        if not target.exists() or not target.is_dir():
            raise ValueError("POSE 文件夹不存在")
        return target

    def resolve_pose_path(self, rel_path: str) -> Path:
        target = self._safe_pose_path(rel_path)
        if not target.exists() or not target.is_file() or target.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("选择的 POSE 图片不存在")
        return target

    def _safe_pose_path(self, rel_path: str) -> Path:
        root = self.pose_root.resolve()
        target = (root / rel_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError("POSE 路径不在允许目录内")
        return target

    def _output_filename(self, app: dict[str, Any], task_id: str, index: int, suffix: str) -> str:
        stem = re.sub(r"[\\/:*?\"<>|\\s]+", "-", str(app.get("name") or "huashi")).strip("-") or "huashi"
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return f"{stem[:32]}-{task_id[:8]}-{index}{suffix.lower()}"

    def save_cover(self, app_id: str, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("封面只支持图片文件")
        cover_dir = self.data_root / "covers" / app_id
        cover_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        cover_path = cover_dir / f"cover-{stamp}{suffix}"
        cover_path.write_bytes(content)
        return self._rel(cover_path)

    def save_album_upload(self, folder_id: str, filename: str, content: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("画册只支持图片文件")
        safe_name = Path(filename).name or f"album{suffix}"
        date_parts = datetime.now().strftime("%Y/%m/%d").split("/")
        upload_dir = self.data_root / "albums" / "uploads" / date_parts[0] / date_parts[1] / date_parts[2]
        upload_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%H%M%S%f")
        target = upload_dir / f"{stamp}-{safe_name}"
        target.write_bytes(content)
        return self.store.save_album_upload(folder_id, self._rel(target), title=safe_name)

    def rewrite_prompt_stream(self, original_prompt: str, edit_idea: str, model_id: str = "", count: int = 3):
        return rewrite_prompt_stream(original_prompt, edit_idea, model_id, count=count)

    def translate_prompt_stream(self, prompt: str, model_id: str = ""):
        return translate_prompt_stream(prompt, model_id)

    def analyze_prompt_agent(self, prompt: str, model_id: str = "") -> dict[str, Any]:
        return analyze_prompt(prompt, model_id)

    def generate_prompt_agent(self, prompt: str, analysis: dict[str, Any], instruction: str, model_id: str = "") -> dict[str, Any]:
        return generate_prompt_variant(prompt, analysis, instruction, model_id)

    def refine_prompt_agent(
        self,
        prompt: str,
        analysis: dict[str, Any],
        current: dict[str, Any],
        instruction: str,
        model_id: str = "",
    ) -> dict[str, Any]:
        return refine_prompt_variant(prompt, analysis, current, instruction, model_id)

    def _prompt_value_from_payload(self, app: dict[str, Any], payload: dict[str, Any]) -> str:
        prompt_input = next((item for item in app.get("inputs", []) if item.get("role") == "prompt"), None)
        if not prompt_input:
            return ""
        return str((payload.get("values") or {}).get(prompt_input["id"]) or "").strip()


def service_apps_for_backup(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in app.items() if key != "cover_url"}
        for app in apps
    ]


def service_prompts_for_backup(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean_prompts = []
    for prompt in prompts:
        item = {
            key: value
            for key, value in prompt.items()
            if key not in {"sample_url", "apps", "deleted"}
        }
        item["variants"] = [
            {key: value for key, value in variant.items() if key != "deleted"}
            for variant in prompt.get("variants", [])
        ]
        item["app_webapp_ids"] = [app["webapp_id"] for app in prompt.get("apps", []) if app.get("webapp_id")]
        clean_prompts.append(item)
    return clean_prompts
