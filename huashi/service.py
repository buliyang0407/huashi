from __future__ import annotations

import shutil
import threading
import html
import json
import os
import re
import secrets
import tempfile
from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .runninghub import RunningHubError
from .runpod import RunPodClient, RunPodError, RunPodSubmissionUnknown, decode_images, make_payload, prepare_image
from .runpod_workflows import WORKFLOWS
from .prompt_ai import rewrite_prompt_stream, translate_prompt_stream
from .prompt_agent import analyze_prompt, generate_prompt_variant, refine_prompt_variant
from .portrait_studio import PortraitStudio, portrait_slot_definitions
from .storage import HuashiStore, utc_now
from .thumbnails import ThumbnailService
from .zip_utils import safe_extract_zip


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
ICON_LIBRARY_FOLDER_ID = "icons"
ICON_LIBRARY_FOLDER_NAME = "图标库"
ICON_LIBRARY_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "icon_library"
ICON_LIBRARY_VERSION = "v6"
ICON_LIBRARY_SPECS = [
    ("portrait", "人像写真", "人", "#f5e6dc", "#8f4f38"),
    ("fashion", "换装搭配", "衣", "#ece7f7", "#5b4f96"),
    ("pose", "姿势参考", "姿", "#e5eef8", "#2f678f"),
    ("retouch", "精修美化", "修", "#f7ead9", "#a56a2b"),
    ("expand", "扩图延展", "扩", "#e7f1ea", "#367653"),
    ("cutout", "智能抠图", "抠", "#eef0f4", "#505767"),
    ("color", "黑白上色", "彩", "#f5e3e8", "#9b4057"),
    ("light", "光影重塑", "光", "#f6efd6", "#9b7526"),
    ("avatar", "头像生成", "头", "#e9edf9", "#4e5b9b"),
    ("illustration", "插画风格", "画", "#efe5d7", "#7d5739"),
    ("three-d", "3D 质感", "3D", "#e2eff0", "#2d757b"),
    ("poster", "海报设计", "报", "#f4e4df", "#9a4d42"),
    ("commerce", "电商主图", "商", "#e7efe2", "#4f7638"),
    ("model", "模特展示", "模", "#eee6f2", "#704f83"),
    ("makeup", "妆容试色", "妆", "#f6e1e5", "#9d4a5f"),
    ("hair", "发型设计", "发", "#eadfda", "#75503f"),
    ("background", "背景替换", "景", "#e4ecf3", "#42667e"),
    ("text", "文字生成", "文", "#f4f0df", "#7c6c37"),
    ("style", "风格迁移", "风", "#e6e5f2", "#57518c"),
    ("filter", "滤镜调色", "滤", "#e1efe8", "#34715a"),
    ("upscale", "高清放大", "清", "#e0edf8", "#386f9d"),
    ("restore", "老照修复", "旧", "#f0e6d9", "#7d6240"),
    ("id-photo", "证件照片", "证", "#e9edf0", "#55616c"),
    ("product", "商品质感", "品", "#f5ead6", "#946c2c"),
    ("interior", "室内空间", "室", "#e9ece3", "#5f7045"),
    ("building", "建筑外观", "筑", "#e3eaee", "#526b78"),
    ("food", "美食摄影", "食", "#f4e7d7", "#986135"),
    ("anime", "动漫转换", "漫", "#e9e4f6", "#654e9b"),
    ("texture", "材质纹理", "纹", "#e8e2dc", "#6d5b4e"),
    ("variant", "批量变体", "变", "#e4eeed", "#3d7470"),
    ("scene", "场景合成", "场", "#e6edf5", "#47688a"),
    ("camera", "镜头语言", "镜", "#ece9e2", "#6b604f"),
]


class HuashiService:
    def __init__(self, data_root: Path | str, store: HuashiStore, runninghub_client: Any):
        self.data_root = Path(data_root)
        self.pose_root = Path(os.getenv("HUASHI_POSE_DIR", str(self.data_root.parent / "pose")))
        self.face_library_root = Path(os.getenv("HUASHI_FACE_LIBRARY_DIR", str(self.data_root / "faces")))
        self.portrait_material_root = Path(os.getenv("HUASHI_PORTRAIT_MATERIAL_DIR", str(self.data_root.parent / "promptscreation")))
        self.portrait_studio = PortraitStudio(self.portrait_material_root)
        self.store = store
        self.runninghub = runninghub_client
        self.thumbnails = ThumbnailService(self.data_root)
        for folder in ("uploads", "cache", "archive", "thumbnails", "backups", "albums", "tmp"):
            (self.data_root / folder).mkdir(parents=True, exist_ok=True)
        self.ensure_icon_library()
        from .task_queue import RunPodQueue
        self.task_queue = RunPodQueue(self)

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
        if app.get("provider") == "runpod" and not app.get("enabled"):
            raise ValueError("这个 RunPod 画布已下架；历史和作品仍可查看，请选择新画布创作")
        if app.get("provider") == "runpod" and WORKFLOWS.get(app.get("workflow_key"), {}).get("random_seed_on_empty"):
            fields = dict(fields)
            raw_seed = (fields.get("input_seed") or "").strip()
            if raw_seed:
                try:
                    seed = int(raw_seed)
                except ValueError as exc:
                    raise ValueError("随机种子必须是整数") from exc
                if not 0 <= seed < 2**64:
                    raise ValueError("随机种子超出范围")
            else:
                # Keep generated values exactly representable in browser number controls.
                seed = secrets.randbits(53)
            # Resolve before creating the task; history and the remote request use the same seed.
            fields["input_seed"] = str(seed)
        if WORKFLOWS.get(app.get("workflow_key"), {}).get("validate_on_create"):
            values = {item["id"]: str(fields.get(f"input_{item['id']}", item.get("defaultValue", ""))).strip() for item in inputs}
            # Validate scalar parameters without encoding image bytes twice.
            make_payload(app["workflow_key"], [item for item in inputs if item["type"] != "image"], values, {})
            for item in inputs:
                if item["type"] != "image":
                    continue
                form_name = f"input_{item['id']}"
                upload = files.get(form_name)
                artwork_path = (fields.get(f"{form_name}_artwork") or "").strip()
                if not upload and not artwork_path:
                    if item.get("required"):
                        raise ValueError(f"缺少输入：{item.get('label') or item['id']}")
                    continue
                source = BytesIO(upload["content"]) if upload else self._resolve_artwork_path(artwork_path)
                from PIL import Image
                try:
                    with Image.open(source) as image:
                        image.verify()
                except (OSError, ValueError) as exc:
                    raise ValueError("RunPod 输入图片无法读取") from exc
        temp_task = self.store.create_task(app_id=app_id, input_path="", input_name="参数生成", input_payload={}, stage="saving_inputs" if app.get("provider") == "runpod" else "")
        try:
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
                        if app.get("workflow_key") in {"noctq-v4-text-to-image", "noctq-v4-lora-text-to-image", "noctq-v4-single-image-edit", "noctq-v4-lora-single-image-edit", "noctq-v4-lora-pose-transfer"}:
                            value = str(fields.get(form_name, item.get("defaultValue") or "")).strip()
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
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.store.update_task(temp_task["id"], status="failed", stage="input_save_failed", error="保存任务输入失败，未提交生成。", completed_at=utc_now())
            raise ValueError("保存任务输入失败，未加入队列；记录和已保存的输入保留。") from exc
        task = self.store.get_task(temp_task["id"])
        if app.get("provider") == "runpod":
            self.task_queue.enqueue(task["id"])
            task = self.store.get_task(task["id"])
            if start_background:
                self.task_queue.start()
        elif start_background:
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
        if task["provider"] == "runpod":
            return self._process_runpod_task(task, app, poll_interval=poll_interval, timeout=max(timeout, 900))
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
            message = self._task_error_message(exc, locals().get("runninghub_task_id", ""))
            if isinstance(exc, RunningHubError):
                api_key = getattr(self.runninghub, "api_key", "")
                if api_key:
                    message = message.replace(api_key, "***")
            return self.store.update_task(task_id, status="failed", error=message, completed_at=utc_now())

    def _process_runpod_task(self, task: dict[str, Any], app: dict[str, Any], poll_interval: float, timeout: float) -> dict[str, Any]:
        task_id = task["id"]
        job_id = task.get("runpod_job_id") or ""
        if task.get("remote_submission_state") == "unknown" and not job_id:
            return self.store.update_task(task_id, status="failed", stage="submission_unknown", error="远端提交结果未知，未自动重投。", completed_at=utc_now())
        try:
            client = RunPodClient.from_workflow(app["workflow_key"])
            if not job_id:
                self.store.update_task(task_id, status="running", stage="preparing", error=None)
                payload_data = task.get("input_payload") or {}
                file_map = payload_data.get("files") or {}
                config = WORKFLOWS[app["workflow_key"]]
                with tempfile.TemporaryDirectory(prefix=f"runpod-{task_id}-", dir=self.data_root / "tmp") as temp_dir:
                    prepared = {}
                    for item in app.get("inputs") or []:
                        if item["type"] != "image":
                            continue
                        rel_path = (file_map.get(item["id"]) or {}).get("path")
                        if rel_path:
                            prepared[item["id"]] = prepare_image(
                                self.data_root / rel_path,
                                Path(temp_dir) / f"{item['id']}.jpg",
                                config.get("max_input_edge", 2048),
                            )
                    payload = make_payload(app["workflow_key"], app.get("inputs") or [], payload_data.get("values") or {}, prepared)
                    self.store.update_task(task_id, stage="checking_network")
                    client.check_connection()
                    # Persist the ambiguous boundary before the POST is sent.
                    self.store.update_task(task_id, stage="submitting", remote_submission_state="unknown")
                    job_id = client.submit(payload)
                    self.store.update_task(task_id, runpod_job_id=job_id, stage="waiting_worker", remote_submission_state="submitted")
            return self._finish_runpod_task(task_id, client, job_id, poll_interval, timeout)
        except RunPodSubmissionUnknown as exc:
            return self.store.update_task(task_id, status="failed", stage="submission_unknown", remote_submission_state="unknown", error=str(exc), completed_at=utc_now())
        except (RunPodError, ValueError, OSError, KeyError) as exc:
            submission_state = "submitted" if job_id else self.store.get_task(task_id)["remote_submission_state"]
            if job_id and self.store.get_task(task_id).get("remote_status") not in {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}:
                return self.store.update_task(task_id, status="running", stage="recovery_wait", error="RunPod 原任务暂时无法查询；队列等待恢复，不重复提交。")
            return self.store.update_task(task_id, status="failed", stage="failed", remote_submission_state=submission_state, error=str(exc), completed_at=utc_now())

    def _finish_runpod_task(self, task_id: str, client: RunPodClient, job_id: str, poll_interval: float, timeout: float) -> dict[str, Any]:
        try:
            def on_status(remote_status: str) -> None:
                stage = {
                    "IN_QUEUE": "waiting_worker",
                    "IN_PROGRESS": "remote_running",
                    "RUNNING": "remote_running",
                    "COMPLETED": "fetching_result",
                }.get(remote_status, "remote_status")
                self.store.update_task(task_id, status="running", stage=stage, remote_status=remote_status)

            response = client.wait(job_id, on_status, poll_interval=poll_interval, timeout=timeout)
            images = decode_images(response)
            cache_dir = self.data_root / "cache" / task_id
            cache_dir.mkdir(parents=True, exist_ok=True)
            outputs = []
            for index, image in enumerate(images, start=1):
                destination = cache_dir / f"runpod-{index}.png"
                destination.write_bytes(image)
                rel_path = self._rel(destination)
                outputs.append({"type": "image", "path": rel_path, "url": f"/files/{rel_path}", "download_name": destination.name})
            return self.store.update_task(task_id, status="success", stage="completed", remote_status="COMPLETED", output_type="png", cache_path=self._rel(cache_dir), outputs=outputs, completed_at=utc_now(), error=None)
        except (RunPodError, OSError) as exc:
            from .task_queue import TERMINAL_REMOTE
            task = self.store.get_task(task_id)
            if task.get("remote_status") not in TERMINAL_REMOTE:
                return self.store.update_task(task_id, status="running", stage="recovery_wait", error="RunPod 结果查询暂时中断；保留原 Job 继续查询，后续任务等待。")
            return self.store.update_task(task_id, status="failed", stage="failed", error=str(exc), completed_at=utc_now())

    def resume_runpod_tasks(self) -> None:
        """Recover durable waiting inputs and poll known jobs without new POSTs."""
        self.task_queue.recover()
        self.task_queue.start()

    def _task_error_message(self, exc: Exception, runninghub_task_id: str = "") -> str:
        message = str(exc)
        if isinstance(exc, RunningHubError) and runninghub_task_id and "RunningHub task failed" in message:
            detail = self._runninghub_failure_detail(runninghub_task_id)
            if detail:
                return detail
        return message

    def _runninghub_failure_detail(self, runninghub_task_id: str) -> str:
        try:
            self.runninghub.get_outputs(runninghub_task_id)
        except RunningHubError as detail_exc:
            return format_runninghub_failed_reason(str(detail_exc), runninghub_task_id)
        except Exception:
            return ""
        return ""

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
        if old.get("provider") == "runpod":
            from .task_queue import TERMINAL_REMOTE
            if old.get("remote_submission_state") == "unknown" or (old.get("runpod_job_id") and old.get("remote_status") not in TERMINAL_REMOTE and old.get("status") != "success"):
                raise ValueError("远端任务状态未确认，不能重投；请等待原任务查询或联系维护。")
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
        return self.create_task_from_form(old["app_id"], fields, files, start_background=start_background)

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
        directory_data = self.store.export_prompt_snapshot()
        prompts = service_prompts_for_backup(directory_data["prompts"])
        return {
            "kind": "huashi-backup",
            "version": 4,
            "exported_at": utc_now(),
            "apps": service_apps_for_backup(self.store.list_all_apps(provider="runninghub")),
            "prompts": prompts,
            "prompt_folders": directory_data["folders"],
            "prompt_folder_links": directory_data["links"],
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

        directory_version = bundle.get("version") == 4
        if isinstance(bundle.get("version"), int) and bundle["version"] > 4:
            raise ValueError("备份版本暂不支持")
        directory_rows = bundle.get("prompt_folders")
        directory_links = bundle.get("prompt_folder_links")
        link_targets = {}
        if directory_version:
            prompts = bundle.get("prompts")
            if not isinstance(prompts, list) or not isinstance(directory_rows, list) or not isinstance(directory_links, list):
                raise ValueError("新版备份缺少提示词目录或归属清单")
            if any(not isinstance(prompt, dict) or not isinstance(prompt.get("id"), str) or not prompt["id"] for prompt in prompts):
                raise ValueError("新版备份的提示词需要有效 ID")
            prompt_ids = {prompt["id"] for prompt in prompts}
            if len(prompt_ids) != len(prompts):
                raise ValueError("备份提示词 ID 重复")
            self.store.validate_prompt_folder_bundle(directory_rows, directory_links, prompt_ids=prompt_ids)
            link_targets = {link["prompt_id"]: link["folder_id"] for link in directory_links}
            if set(link_targets) != prompt_ids:
                raise ValueError("备份目录归属与提示词清单不一致")
            for prompt in prompts:
                if prompt.get("folder_id") and prompt["folder_id"] != link_targets[prompt["id"]]:
                    raise ValueError("备份提示词目录信息不一致")

        before_backup = self.write_apps_backup("before-import")
        with self.store.atomic_import():
            if directory_version:
                self.store.prepare_prompt_folder_restore(directory_rows, directory_links, prompt_ids=prompt_ids)
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
                    prompt_data = {**prompt, "app_ids": linked_ids}
                    if directory_version:
                        prompt_data["folder_id"] = link_targets[prompt["id"]]
                    else:
                        # Older backups have no directory contract. Existing IDs keep their classification.
                        prompt_data.pop("folder_id", None)
                        prompt_data.pop("folder_path", None)
                    saved_prompt = self.store.save_prompt(prompt_data, prompt_id=prompt.get("id"))
                    imported_prompts.append(saved_prompt)
                    variants = prompt.get("variants") if isinstance(prompt.get("variants"), list) else []
                    for variant in variants:
                        if isinstance(variant, dict):
                            self.store.save_prompt_variant(saved_prompt["id"], variant, variant_id=variant.get("id"))
            if directory_version:
                self.store.restore_prompt_folders(directory_rows, directory_links)
        after_backup = self.write_apps_backup("after-import")
        return {
            "count": len(imported),
            "prompt_count": len(imported_prompts),
            "before_backup": self._rel(before_backup),
            "after_backup": self._rel(after_backup),
        }

    def delete_task(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if task.get("provider") == "runpod" and (task["status"] in {"queued", "running"} or task.get("remote_submission_state") == "unknown"):
            raise ValueError("活动或提交未确认的 RunPod 任务不能删除；待执行任务请使用取消排队。")
        for key in ("cache_path", "archive_path"):
            rel = task.get(key)
            if rel:
                target = self.data_root / rel
                if target.exists() and self.data_root.resolve() in target.resolve().parents:
                    shutil.rmtree(target)
        self.store.delete_task_record(task_id)

    def thumbnail_url(self, rel_path: str, size: int = 480) -> str:
        try:
            return self.thumbnails.url_for_existing_source(rel_path, size=size)
        except Exception:
            return f"/files/{rel_path}" if rel_path else ""

    def attach_app_thumbnail_urls(self, app: dict[str, Any]) -> dict[str, Any]:
        updated = dict(app)
        if updated.get("cover_path"):
            updated["cover_thumb_url"] = self.thumbnail_url(str(updated["cover_path"]), 480)
        else:
            updated["cover_thumb_url"] = updated.get("cover_url", "")
        if updated.get("icon_path"):
            updated["icon_thumb_url"] = self.thumbnail_url(str(updated["icon_path"]), 480)
        else:
            updated["icon_thumb_url"] = updated.get("icon_url", "")
        return updated

    def list_apps(self) -> list[dict[str, Any]]:
        return [self.attach_app_thumbnail_urls(app) for app in self.store.list_apps()]

    def list_all_apps(self, provider: str | None = None) -> list[dict[str, Any]]:
        return [self.attach_app_thumbnail_urls(app) for app in self.store.list_all_apps(provider=provider)]

    def attach_task_thumbnail_urls(self, task: dict[str, Any]) -> dict[str, Any]:
        updated = dict(task)
        outputs = []
        for output in task.get("outputs") or []:
            item = dict(output)
            output_type = str(item.get("type") or "").lower()
            if output_type in {"image", "png", "jpg", "jpeg", "webp"} and item.get("path"):
                item["thumb_url"] = self.thumbnail_url(str(item["path"]), 480)
            outputs.append(item)
        updated["outputs"] = outputs
        if updated.get("input_path"):
            updated["input_thumb_url"] = self.thumbnail_url(str(updated["input_path"]), 480)
        return updated

    def list_tasks(self) -> list[dict[str, Any]]:
        return [self.attach_task_thumbnail_urls(task) for task in self.store.list_tasks()]

    def task_summary(self, task: dict[str, Any]) -> dict[str, Any]:
        task = self.attach_task_thumbnail_urls(task)
        preview_outputs = [
            {
                key: output.get(key)
                for key in ("type", "path", "url", "thumb_url", "blurred", "deleted")
                if key in output
            }
            for output in task.get("outputs") or []
            if str(output.get("type") or "").lower() in {"image", "png", "jpg", "jpeg", "webp"} and not output.get("deleted")
        ]
        summary_keys = (
            "id",
            "app_id",
            "app_name",
            "app_category",
            "status",
            "provider",
            "runpod_job_id",
            "remote_status",
            "stage",
            "remote_submission_state",
            "input_path",
            "input_name",
            "input_url",
            "input_thumb_url",
            "output_type",
            "saved",
            "error",
            "created_at",
            "updated_at",
            "completed_at",
        )
        summary = {key: task.get(key) for key in summary_keys if key in task}
        summary["outputs"] = preview_outputs[:1]
        summary["is_summary"] = True
        return summary

    def list_task_summaries(self, limit: int | None = None) -> list[dict[str, Any]]:
        summaries = [self.task_summary(task) for task in self.store.list_tasks()]
        return summaries[:limit] if limit else summaries

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.attach_task_thumbnail_urls(self.store.get_task(task_id))
        task["is_summary"] = False
        return task

    def attach_album_thumbnail_url(self, item: dict[str, Any]) -> dict[str, Any]:
        updated = dict(item)
        if updated.get("path"):
            updated["thumb_url"] = self.thumbnail_url(str(updated["path"]), 480)
        return updated

    def list_album_items(self, folder_id: str) -> list[dict[str, Any]]:
        return [self.attach_album_thumbnail_url(item) for item in self.store.list_album_items(folder_id)]

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
        if rel_path.startswith("face:"):
            return self.resolve_face_library_path(rel_path.removeprefix("face:"))
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

    def face_library_available(self) -> bool:
        return self.face_library_root.exists() and self.face_library_root.is_dir()

    def face_library_summary(self) -> dict[str, Any] | None:
        if not self.face_library_available():
            return None
        directory_count = 0
        image_count = 0
        try:
            for entry in self.face_library_root.iterdir():
                if entry.is_dir():
                    directory_count += 1
                elif entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
                    image_count += 1
        except OSError:
            return None
        return {
            "id": "__faces__",
            "name": "人脸库",
            "sort_order": 8900,
            "created_at": "",
            "updated_at": "",
            "item_count": image_count,
            "directory_count": directory_count,
            "virtual": True,
        }

    def list_face_library_directory(self, rel_path: str = "", offset: int = 0, limit: int = 120) -> dict[str, Any]:
        root = self.face_library_root.resolve()
        target = self.resolve_face_library_directory(rel_path)
        directories: list[dict[str, Any]] = []
        images: list[dict[str, Any]] = []
        try:
            entries = list(target.iterdir())
        except OSError as exc:
            raise ValueError("人脸库文件夹无法读取") from exc
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
                        "id": f"face:{child_rel}",
                        "source_type": "face",
                        "folder_id": "__faces__",
                        "path": f"face:{child_rel}",
                        "face_path": child_rel,
                        "url": f"/face-files/{quote(child_rel)}",
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
            "name": "人脸库" if target == root else target.name,
            "breadcrumbs": breadcrumbs,
            "directories": directories,
            "items": sliced_images,
            "image_count": len(images),
            "next_offset": safe_offset + safe_limit if safe_offset + safe_limit < len(images) else None,
        }

    def resolve_face_library_directory(self, rel_path: str) -> Path:
        target = self._safe_face_library_path(rel_path)
        if not target.exists() or not target.is_dir():
            raise ValueError("人脸库文件夹不存在")
        return target

    def resolve_face_library_path(self, rel_path: str) -> Path:
        target = self._safe_face_library_path(rel_path)
        if not target.exists() or not target.is_file() or target.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("选择的人脸图片不存在")
        return target

    def _safe_face_library_path(self, rel_path: str) -> Path:
        root = self.face_library_root.resolve()
        target = (root / rel_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError("人脸库路径不在允许目录内")
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

    def ensure_icon_library(self) -> None:
        self.store.ensure_album_folder(ICON_LIBRARY_FOLDER_ID, ICON_LIBRARY_FOLDER_NAME, sort_order=10)
        icon_dir = self.data_root / "albums" / ICON_LIBRARY_FOLDER_ID
        icon_dir.mkdir(parents=True, exist_ok=True)
        for index, (slug, title, label, background, foreground) in enumerate(ICON_LIBRARY_SPECS, start=1):
            basename = f"{index:02d}-{slug}-{ICON_LIBRARY_VERSION}"
            asset = ICON_LIBRARY_ASSET_DIR / f"{basename}.png"
            target = icon_dir / f"{basename}.png"
            if asset.exists():
                shutil.copy2(asset, target)
            elif not target.exists():
                target = icon_dir / f"{index:02d}-{slug}.svg"
                target.write_text(
                    self._default_icon_svg(title, label, background, foreground),
                    encoding="utf-8",
                )
            self.store.save_album_asset(
                ICON_LIBRARY_FOLDER_ID,
                self._rel(target),
                title=title,
                source_type="icon_library",
            )

    def save_icon_upload(self, filename: str, content: bytes, title: str = "") -> str:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("图标只支持图片文件")
        self.store.ensure_album_folder(ICON_LIBRARY_FOLDER_ID, ICON_LIBRARY_FOLDER_NAME, sort_order=10)
        safe_name = re.sub(r"[\\/:*?\"<>|\\s]+", "-", Path(filename).stem).strip("-") or "icon"
        icon_dir = self.data_root / "albums" / ICON_LIBRARY_FOLDER_ID
        icon_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        target = icon_dir / f"custom-{stamp}-{safe_name[:36]}{suffix}"
        target.write_bytes(content)
        rel_path = self._rel(target)
        self.store.save_album_asset(
            ICON_LIBRARY_FOLDER_ID,
            rel_path,
            title=title.strip() or Path(filename).stem or "自定义图标",
            source_type="icon_upload",
        )
        return rel_path

    def validate_data_image_path(self, rel_path: str) -> str:
        clean = str(rel_path or "").strip()
        if not clean:
            return ""
        target = (self.data_root / clean).resolve()
        root = self.data_root.resolve()
        if target != root and root not in target.parents:
            raise ValueError("图标路径不在画室数据目录内")
        if not target.exists() or not target.is_file() or target.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("选择的图标不存在")
        return clean

    def _default_icon_svg(self, title: str, label: str, background: str, foreground: str) -> str:
        safe_title = html.escape(title)
        safe_label = html.escape(label)
        return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="{safe_title}">
  <defs>
    <linearGradient id="paper" x1="72" y1="48" x2="438" y2="462" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fffefa"/>
      <stop offset="1" stop-color="{background}"/>
    </linearGradient>
    <filter id="lift" x="-20%" y="-20%" width="140%" height="140%" color-interpolation-filters="sRGB">
      <feDropShadow dx="0" dy="18" stdDeviation="18" flood-color="#2b241f" flood-opacity=".16"/>
    </filter>
  </defs>
  <rect width="512" height="512" rx="108" fill="url(#paper)"/>
  <g filter="url(#lift)">
    <rect x="108" y="116" width="296" height="280" rx="72" fill="#fffdf8"/>
    <path d="M148 330c42-60 78-91 108-91 35 0 58 46 93 46 22 0 38-18 55-44v91c0 39-31 70-70 70H178c-39 0-70-31-70-70v-2h40z" fill="{background}"/>
    <circle cx="342" cy="178" r="34" fill="{foreground}" opacity=".18"/>
    <circle cx="182" cy="190" r="22" fill="{foreground}" opacity=".24"/>
  </g>
  <text x="256" y="292" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'PingFang SC', 'Noto Sans SC', sans-serif" font-size="106" font-weight="800" fill="{foreground}" letter-spacing="0">{safe_label}</text>
  <path d="M160 426h192" stroke="{foreground}" stroke-width="12" stroke-linecap="round" opacity=".18"/>
</svg>
"""

    def save_album_upload(self, folder_id: str, filename: str, content: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower() or ".png"
        if suffix not in IMAGE_SUFFIXES:
            raise ValueError("画册只支持图片文件")
        folder_id = str(folder_id or "").strip()
        if not folder_id:
            folder_id = self.store.default_upload_folder()["id"]
        # Validate the destination before creating any uploaded file.
        self.store.get_album_folder(folder_id)
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

    def generate_prompt_agent(
        self,
        prompt: str,
        analysis: dict[str, Any],
        instruction: str,
        model_id: str = "",
        edits: list[dict[str, Any]] | None = None,
        extra_instruction: str = "",
    ) -> dict[str, Any]:
        return generate_prompt_variant(prompt, analysis, instruction, model_id, edits=edits, extra_instruction=extra_instruction)

    def refine_prompt_agent(
        self,
        prompt: str,
        analysis: dict[str, Any],
        current: dict[str, Any],
        instruction: str,
        model_id: str = "",
    ) -> dict[str, Any]:
        return refine_prompt_variant(prompt, analysis, current, instruction, model_id)

    def list_portrait_materials(
        self,
        slot: str = "",
        category: str = "",
        query: str = "",
        offset: int = 0,
        limit: int = 80,
    ) -> dict[str, Any]:
        return self.portrait_studio.list_materials(slot=slot, category=category, query=query, offset=offset, limit=limit)

    def portrait_slots(self) -> list[dict[str, Any]]:
        return portrait_slot_definitions()

    def resolve_portrait_material_image(self, item_id: str) -> Path:
        return self.portrait_studio.resolve_material_image(item_id)

    def generate_portrait_prompt(
        self,
        selected: dict[str, list[dict[str, Any]]],
        manual: dict[str, str],
        base_prompt: str = "",
        model_id: str = "",
    ) -> dict[str, Any]:
        return self.portrait_studio.generate_prompt(selected=selected, manual=manual, base_prompt=base_prompt, model_id=model_id)

    def _prompt_value_from_payload(self, app: dict[str, Any], payload: dict[str, Any]) -> str:
        prompt_input = next((item for item in app.get("inputs", []) if item.get("role") == "prompt"), None)
        if not prompt_input:
            return ""
        return str((payload.get("values") or {}).get(prompt_input["id"]) or "").strip()


def service_apps_for_backup(apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in app.items() if key not in {"cover_url", "icon_url"}}
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


def format_runninghub_failed_reason(message: str, task_id: str = "") -> str:
    data = parse_runninghub_error_payload(message)
    failed_reason = data.get("failedReason") if isinstance(data, dict) else None
    if not isinstance(failed_reason, dict):
        return message
    exception_type = str(failed_reason.get("exception_type") or "").strip()
    exception_message = str(failed_reason.get("exception_message") or "").strip()
    traceback = clean_runninghub_traceback(failed_reason.get("traceback"))
    if exception_type == "audit.RHAuditException":
        parts = ["RunningHub 审核失败"]
        if exception_message:
            parts.append(exception_message)
        if traceback:
            parts.append(traceback)
        if task_id:
            parts.append(f"taskId: {task_id}")
        return "：".join(parts[:2]) + ("；" + "；".join(parts[2:]) if len(parts) > 2 else "")
    details = [item for item in [exception_type, exception_message, traceback] if item]
    if details:
        return f"RunningHub 任务失败：{'；'.join(details)}" + (f"；taskId: {task_id}" if task_id else "")
    return message


def parse_runninghub_error_payload(message: str) -> dict[str, Any]:
    start = message.find("{")
    if start < 0:
        return {}
    text = message[start:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        try:
            import ast

            payload = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            return {}
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def clean_runninghub_traceback(value: Any) -> str:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                value = decoded
            else:
                return " ".join(value.split())
        except json.JSONDecodeError:
            try:
                import ast

                decoded = ast.literal_eval(value)
                if isinstance(decoded, list):
                    value = decoded
                else:
                    return " ".join(value.split())
            except (SyntaxError, ValueError):
                return " ".join(value.split())
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return ""
