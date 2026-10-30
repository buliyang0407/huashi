from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .runninghub_inspector import RunningHubInspectError, inspect_runninghub_source
from .runninghub import RunningHubClient, RunningHubError
from .prompt_ai import PromptAIError, list_prompt_models
from .inspiration import InspirationLibrary
from .inspiration_api import InspirationAPI
from .inspiration_media import InspirationMedia
from .inspiration_search import InspirationSearch
from .album_organizer import AlbumOrganizer
from .service import HuashiService
from .storage import HuashiStore


class MissingRunningHubClient:
    def __init__(self):
        self.api_key = ""

    def __getattr__(self, name):
        raise RunningHubError("RUNNINGHUB_API_KEY is not configured. Set it in .env or the shell before generating.")


def load_dotenv(path: Path, *, override: bool = False, allowed: set[str] | None = None) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if allowed is not None and key not in allowed:
            continue
        if override or key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def create_service(data_root: Path) -> HuashiService:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / ".dev-secrets.env", override=True, allowed={"RUNPOD_API_KEY", "RUNPOD_QWEN_ENDPOINT_ID", "RUNPOD_PROXY_URL"})
    store = HuashiStore(data_root / "db.sqlite")
    store.initialize()
    api_key = os.getenv("RUNNINGHUB_API_KEY", "")
    client = RunningHubClient(api_key) if api_key else MissingRunningHubClient()
    service = HuashiService(data_root, store, client)
    service.resume_runpod_tasks()
    return service


def make_handler(service: HuashiService, web_root: Path, data_root: Path, *, inspiration_root: Path | None = None):
    inspiration = InspirationLibrary(inspiration_root or web_root.parent / "inspiration")
    inspiration_v2 = None
    inspiration_media = InspirationMedia(inspiration.root / "animation")

    def inspiration_v2_adapter():
        nonlocal inspiration_v2
        if inspiration_v2 is None:
            inspiration_v2 = InspirationAPI(inspiration, service.store)
        return inspiration_v2
    inspiration_search = None
    album_organizer = None

    def search_adapter():
        nonlocal inspiration_search
        if inspiration_search is None:
            inspiration_search = InspirationSearch(inspiration, service.store)
        return inspiration_search

    def organize_adapter():
        nonlocal album_organizer
        if album_organizer is None:
            album_organizer = AlbumOrganizer(service.store, data_root / "backups")
        return album_organizer

    class HuashiHandler(SimpleHTTPRequestHandler):
        server_version = "Huashi/0.1"

        def do_HEAD(self):
            if inspiration_media.handle(self):return
            if inspiration.handle_get(self):
                return
            super().do_HEAD()

        def do_GET(self):
            if inspiration_media.handle(self):return
            if urlparse(self.path).path.startswith("/api/inspiration/v2/") and inspiration_v2_adapter().handle_get(self):
                return
            if urlparse(self.path).path == "/api/inspiration/search":
                query = self.query_params()
                try:
                    self.json_response(search_adapter().search(query=query.get("q") or "", kind=query.get("kind") or "all", offset=int(query.get("offset") or 0), limit=int(query.get("limit") or 24), prompt_folder_id=query.get("prompt_folder_id") or None))
                except (ValueError, KeyError) as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if inspiration.handle_get(self):
                return
            path = urlparse(self.path).path
            if path == "/api/apps":
                self.json_response({"apps": service.list_apps()})
                return
            if path == "/api/admin/apps":
                self.json_response({"apps": service.list_all_apps(provider="runninghub")})
                return
            if path == "/api/admin/backup":
                filename = f"huashi-backup-{service.export_apps_bundle()['exported_at'][:10]}.json"
                self.json_download_response(service.export_apps_bundle(), filename)
                return
            if path == "/api/runpod/queue":
                self.json_response(service.task_queue.snapshot())
                return
            if path == "/api/tasks":
                query = self.query_params()
                if query.get("summary") in {"1", "true", "yes"}:
                    try:
                        limit = int(query.get("limit") or "0") or None
                    except ValueError:
                        limit = None
                    self.json_response({"tasks": service.list_task_summaries(limit=limit)})
                    return
                self.json_response({"tasks": service.list_tasks()})
                return
            if path == "/api/albums":
                folders = service.store.list_album_folders()
                face_library = service.face_library_summary()
                if face_library:
                    folders.append(face_library)
                pose = service.pose_summary()
                if pose:
                    folders.append(pose)
                self.json_response({"folders": folders})
                return
            if path == "/api/albums/items":
                query = self.query_params()
                self.json_response({"items": service.list_album_items(query.get("folder_id") or "works")})
                return
            if path == "/api/pose":
                query = self.query_params()
                try:
                    self.json_response(
                        service.list_pose_directory(
                            query.get("path") or "",
                            int(query.get("offset") or 0),
                            int(query.get("limit") or 120),
                        )
                    )
                except ValueError as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if path == "/api/faces":
                query = self.query_params()
                try:
                    self.json_response(
                        service.list_face_library_directory(
                            query.get("path") or "",
                            int(query.get("offset") or 0),
                            int(query.get("limit") or 120),
                        )
                    )
                except ValueError as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if path == "/api/prompts":
                query = self.query_params()
                try:
                    self.json_response({"prompts": service.store.list_prompts(app_id=query.get("app_id") or None, folder_id=query.get("folder_id") or None)})
                except (ValueError, KeyError) as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if path == "/api/prompt-folders":
                self.json_response({"folders": service.store.list_prompt_folders(include_deleted=self.query_params().get("include_deleted") == "1"), "default_folder_id": service.store.default_prompt_folder_id()})
                return
            if path == "/api/prompt-models":
                self.json_response({"models": list_prompt_models()})
                return
            if path == "/api/portrait/slots":
                self.json_response({"slots": service.portrait_slots()})
                return
            if path == "/api/portrait/materials":
                query = self.query_params()
                try:
                    self.json_response(
                        service.list_portrait_materials(
                            slot=query.get("slot") or "",
                            category=query.get("category") or "",
                            query=query.get("q") or "",
                            offset=int(query.get("offset") or 0),
                            limit=int(query.get("limit") or 80),
                        )
                    )
                except ValueError as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            if path.startswith("/api/tasks/"):
                task_id = path.rstrip("/").split("/")[-1]
                self.json_response({"task": service.get_task(task_id)})
                return
            if path.startswith("/api/portrait/material-image/"):
                self.serve_portrait_material_image(path.rstrip("/").split("/")[-1])
                return
            if path.startswith("/thumbs/"):
                self.serve_thumbnail(path.removeprefix("/thumbs/"))
                return
            if path.startswith("/files/"):
                self.serve_data_file(path.removeprefix("/files/"))
                return
            if path.startswith("/pose-files/"):
                self.serve_pose_file(path.removeprefix("/pose-files/"))
                return
            if path.startswith("/face-files/"):
                self.serve_face_file(path.removeprefix("/face-files/"))
                return
            self.serve_static(path)

        def do_POST(self):
            path = urlparse(self.path).path
            if path.startswith("/api/runpod/queue/"):
                try:
                    if path in {"/api/runpod/queue/pause", "/api/runpod/queue/resume"}:
                        service.task_queue.set_paused(path.endswith("/pause"))
                        service.task_queue.start()
                    elif path.endswith("/cancel") and len(path.split("/")) == 6:
                        service.task_queue.cancel(path.split("/")[-2])
                    else:
                        self.error_response(HTTPStatus.NOT_FOUND, "Not found")
                        return
                    self.json_response(service.task_queue.snapshot())
                except (ValueError, KeyError) as exc:
                    self.error_response(HTTPStatus.CONFLICT, str(exc))
                return
            if path in {"/api/albums/moves/preview", "/api/albums/moves/apply"}:
                try:
                    payload = self.parse_json_body()
                    if not isinstance(payload, dict):
                        raise ValueError("整理请求必须为对象")
                    moves = payload.get("moves")
                    result = organize_adapter().preview(moves) if path.endswith("/preview") else organize_adapter().apply(moves)
                    self.json_response(result)
                except (ValueError, KeyError, TypeError) as exc:
                    self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                except (OSError, sqlite3.Error):
                    self.error_response(HTTPStatus.SERVICE_UNAVAILABLE, "整理未完成，请核对分类和移回记录后再操作。")
                return
            if path == "/api/tasks":
                self.handle_create_task()
                return
            if path == "/api/admin/apps":
                self.handle_save_app()
                return
            if path == "/api/admin/inspect-runninghub":
                self.handle_inspect_runninghub()
                return
            if path == "/api/admin/backup/import":
                self.handle_import_backup()
                return
            if path == "/api/admin/backup/write":
                backup_path = service.write_apps_backup("manual")
                self.json_response({"backup": service._rel(backup_path)})
                return
            if path == "/api/albums":
                self.handle_create_album_folder()
                return
            if path == "/api/albums/upload":
                self.handle_album_upload()
                return
            if path.startswith("/api/albums/items/") and path.endswith("/move"):
                item_id = path.split("/")[-2]
                self.handle_album_item_move(item_id)
                return
            if path.startswith("/api/albums/items/") and path.endswith("/reorder"):
                item_id = path.split("/")[-2]
                self.handle_album_item_reorder(item_id)
                return
            if path.startswith("/api/albums/items/") and path.endswith("/position"):
                item_id = path.split("/")[-2]
                self.handle_album_item_position(item_id)
                return
            if path.startswith("/api/albums/items/") and path.endswith("/delete"):
                item_id = path.split("/")[-2]
                self.json_response({"item": service.store.soft_delete_album_item(item_id)})
                return
            if path == "/api/prompts":
                self.handle_save_prompt()
                return
            if path == "/api/prompts/move":
                self.handle_prompt_move()
                return
            if path == "/api/prompt-folders":
                self.handle_prompt_folder_change()
                return
            if path.startswith("/api/prompt-folders/") and path.endswith("/restore"):
                self.handle_prompt_folder_change(path.split("/")[-2], restore=True)
                return
            if path in {"/api/prompts/rewrite", "/api/prompts/translate"}:
                self.error_response(HTTPStatus.GONE, "翻译和改写功能已下线，请在提示词库手动编辑。")
                return
            if path == "/api/prompt-agent/analyze":
                self.handle_prompt_agent_analyze()
                return
            if path == "/api/prompt-agent/generate":
                self.handle_prompt_agent_generate()
                return
            if path == "/api/prompt-agent/refine":
                self.handle_prompt_agent_refine()
                return
            if path == "/api/portrait/generate":
                self.handle_portrait_generate()
                return
            if path.startswith("/api/prompts/") and path.endswith("/use"):
                prompt_id = path.split("/")[-2]
                self.json_response({"prompt": service.store.mark_prompt_used(prompt_id)})
                return
            if path.startswith("/api/prompts/") and path.endswith("/variants"):
                prompt_id = path.split("/")[-2]
                self.handle_save_prompt_variant(prompt_id)
                return
            if path.startswith("/api/prompt-variants/") and path.endswith("/use"):
                variant_id = path.split("/")[-2]
                self.json_response({"prompt": service.store.mark_prompt_variant_used(variant_id)})
                return
            if path.startswith("/api/tasks/") and path.endswith("/archive"):
                task_id = path.split("/")[-2]
                self.json_response({"task": service.archive_task(task_id)})
                return
            if path.startswith("/api/tasks/") and path.endswith("/retry"):
                task_id = path.split("/")[-2]
                try:
                    self.json_response({"task": service.retry_task(task_id)})
                except (ValueError, KeyError) as exc:
                    self.error_response(HTTPStatus.CONFLICT, str(exc))
                return
            if path.startswith("/api/tasks/") and path.endswith("/outputs/blur"):
                task_id = path.split("/")[-3]
                self.handle_task_output_blur(task_id)
                return
            if path.startswith("/api/tasks/") and path.endswith("/outputs/delete"):
                task_id = path.split("/")[-3]
                self.handle_task_output_delete(task_id)
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def do_PUT(self):
            if urlparse(self.path).path == "/api/inspiration/v2/favorites" and inspiration_v2_adapter().handle_put(self):
                return
            if inspiration.handle_put(self):
                return
            path = urlparse(self.path).path
            if path.startswith("/api/prompt-folders/"):
                self.handle_prompt_folder_change(path.rstrip("/").split("/")[-1])
                return
            if path.startswith("/api/admin/apps/"):
                app_id = path.rstrip("/").split("/")[-1]
                self.handle_save_app(app_id)
                return
            if path.startswith("/api/prompts/"):
                prompt_id = path.rstrip("/").split("/")[-1]
                self.handle_save_prompt(prompt_id)
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def do_DELETE(self):
            path = urlparse(self.path).path
            if path.startswith("/api/prompt-folders/"):
                self.handle_prompt_folder_change(path.rstrip("/").split("/")[-1], remove=True)
                return
            if path.startswith("/api/admin/apps/"):
                app_id = path.rstrip("/").split("/")[-1]
                self.json_response({"app": service.store.delete_app(app_id)})
                return
            if path.startswith("/api/tasks/"):
                task_id = path.rstrip("/").split("/")[-1]
                try:
                    service.delete_task(task_id)
                    self.json_response({"ok": True})
                except (ValueError, KeyError) as exc:
                    self.error_response(HTTPStatus.CONFLICT, str(exc))
                return
            if path.startswith("/api/prompts/"):
                prompt_id = path.rstrip("/").split("/")[-1]
                self.json_response({"prompt": service.store.soft_delete_prompt(prompt_id)})
                return
            if path.startswith("/api/prompt-variants/"):
                variant_id = path.rstrip("/").split("/")[-1]
                self.json_response({"prompt": service.store.soft_delete_prompt_variant(variant_id)})
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def handle_create_task(self):
            fields, files = self.parse_multipart()
            app_id = fields.get("appId")
            if not app_id:
                self.error_response(HTTPStatus.BAD_REQUEST, "Missing appId")
                return
            try:
                task = service.create_task_from_form(
                    app_id=app_id,
                    fields=fields,
                    files=files,
                    start_background=True,
                )
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self.json_response({"task": task}, status=HTTPStatus.CREATED)

        def handle_save_app(self, app_id: str | None = None):
            fields, files = self.parse_multipart()
            data = {key: value for key, value in fields.items()}
            if app_id:
                current = service.store.get_app(app_id)
                data = {**current, **data}
            cover = files.get("cover")
            icon = files.get("icon")
            target_id = app_id or data.get("id") or ""
            if str(data.get("clear_cover") or "").lower() in {"1", "true", "yes", "on"}:
                data["cover_path"] = ""
            if str(data.get("clear_icon") or "").lower() in {"1", "true", "yes", "on"}:
                data["icon_path"] = ""
            elif data.get("icon_path"):
                data["icon_path"] = service.validate_data_image_path(str(data.get("icon_path") or ""))
            if icon:
                data["icon_path"] = service.save_icon_upload(
                    str(icon["filename"]),
                    icon["content"],  # type: ignore[arg-type]
                    title=str(data.get("name") or "").strip(),
                )
            if cover and target_id:
                data["cover_path"] = service.save_cover(
                    target_id,
                    str(cover["filename"]),
                    cover["content"],
                )
            app = service.store.save_app(data, app_id=app_id)
            if cover and not data.get("cover_path"):
                cover_path = service.save_cover(app["id"], str(cover["filename"]), cover["content"])
                app = service.store.save_app({**app, "cover_path": cover_path}, app_id=app["id"])
            self.safe_write_backup("save")
            self.json_response({"app": app}, status=HTTPStatus.CREATED if app_id is None else HTTPStatus.OK)

        def handle_create_album_folder(self):
            data = self.parse_json_body()
            try:
                self.json_response({"folder": service.store.create_album_folder(str(data.get("name") or ""))}, status=HTTPStatus.CREATED)
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_album_upload(self):
            fields, files = self.parse_multipart()
            upload = files.get("image")
            if not upload:
                self.error_response(HTTPStatus.BAD_REQUEST, "请选择要上传的图片")
                return
            folder_id = (fields.get("folder_id") or "").strip()
            try:
                item = service.save_album_upload(folder_id, str(upload["filename"]), upload["content"])  # type: ignore[arg-type]
                self.json_response({"item": item}, status=HTTPStatus.CREATED)
            except (ValueError, KeyError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_album_item_move(self, item_id: str):
            data = self.parse_json_body()
            folder_id = str(data.get("folder_id") or "").strip()
            if not folder_id:
                self.error_response(HTTPStatus.BAD_REQUEST, "缺少目标文件夹")
                return
            self.json_response({"item": service.store.move_album_item(item_id, folder_id)})

        def handle_album_item_reorder(self, item_id: str):
            data = self.parse_json_body()
            direction = str(data.get("direction") or "").strip()
            if direction not in {"up", "down"}:
                self.error_response(HTTPStatus.BAD_REQUEST, "排序方向不正确")
                return
            self.json_response({"item": service.store.reorder_album_item(item_id, direction)})

        def handle_album_item_position(self, item_id: str):
            data = self.parse_json_body()
            try:
                to_index = int(data.get("to_index"))
            except (TypeError, ValueError):
                self.error_response(HTTPStatus.BAD_REQUEST, "目标位置不正确")
                return
            self.json_response({"item": service.store.position_album_item(item_id, to_index)})

        def handle_inspect_runninghub(self):
            try:
                data = self.parse_json_body()
                result = inspect_runninghub_source(
                    str(data.get("source_url") or ""),
                    str(data.get("sample_text") or ""),
                    getattr(service.runninghub, "api_key", ""),
                )
                self.json_response({"result": result})
            except RunningHubInspectError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_import_backup(self):
            fields, files = self.parse_multipart()
            backup = files.get("backup")
            if not backup:
                self.error_response(HTTPStatus.BAD_REQUEST, "请选择备份文件")
                return
            try:
                bundle = json.loads(backup["content"].decode("utf-8"))  # type: ignore[union-attr]
                result = service.import_apps_bundle(bundle)
                self.json_response({"result": result})
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.error_response(HTTPStatus.BAD_REQUEST, "备份文件不是有效 JSON")
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def prompt_directory_request_allowed(self, *, require_json=True):
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{self.headers.get('Host')}", f"https://{self.headers.get('Host')}"}:
                self.error_response(HTTPStatus.FORBIDDEN, "请从画室页面管理提示词目录")
                return False
            if require_json and "application/json" not in self.headers.get("Content-Type", ""):
                self.error_response(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "目录操作需使用 JSON")
                return False
            return True

        def handle_prompt_folder_change(self, folder_id=None, *, restore=False, remove=False):
            if not self.prompt_directory_request_allowed(require_json=not remove):
                return
            try:
                if remove:
                    folder = service.store.delete_prompt_folder(folder_id)
                elif restore:
                    folder = service.store.restore_prompt_folder(folder_id)
                else:
                    data = self.parse_json_body()
                    if not isinstance(data, dict):
                        raise ValueError("目录信息必须是对象")
                    folder = service.store.save_prompt_folder(data, folder_id=folder_id)
                self.safe_write_backup("prompt-folder-change")
                self.json_response({"folder": folder}, status=HTTPStatus.CREATED if not folder_id else HTTPStatus.OK)
            except (ValueError, KeyError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_move(self):
            if not self.prompt_directory_request_allowed():
                return
            try:
                data = self.parse_json_body()
                if not isinstance(data, dict) or not isinstance(data.get("prompt_ids"), list):
                    raise ValueError("请提交待移动的提示词列表")
                moved = service.store.move_prompts(data["prompt_ids"], data.get("folder_id"))
                self.safe_write_backup("prompt-move")
                self.json_response({"moved": len(moved), "folder_id": data["folder_id"], "prompts": moved})
            except (ValueError, KeyError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_save_prompt(self, prompt_id: str | None = None):
            try:
                if "application/json" in self.headers.get("Content-Type", ""):
                    data = self.parse_json_body()
                else:
                    fields, _files = self.parse_multipart()
                    data = {key: value for key, value in fields.items()}
                prompt = service.store.save_prompt(data, prompt_id=prompt_id)
                self.safe_write_backup("prompt-save")
                self.json_response({"prompt": prompt}, status=HTTPStatus.CREATED if prompt_id is None else HTTPStatus.OK)
            except (ValueError, KeyError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_rewrite(self):
            try:
                data = self.parse_json_body()
                self.stream_jsonl_response(
                    service.rewrite_prompt_stream(
                        original_prompt=str(data.get("prompt") or ""),
                        edit_idea=str(data.get("idea") or ""),
                        model_id=str(data.get("model") or ""),
                        count=int(data.get("count") or 3),
                    )
                )
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_translate(self):
            try:
                data = self.parse_json_body()
                self.stream_jsonl_response(
                    service.translate_prompt_stream(
                        prompt=str(data.get("prompt") or ""),
                        model_id=str(data.get("model") or ""),
                    )
                )
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_agent_analyze(self):
            try:
                data = self.parse_json_body()
                result = service.analyze_prompt_agent(
                    prompt=str(data.get("prompt") or ""),
                    model_id=str(data.get("model") or ""),
                )
                self.json_response(result)
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_agent_generate(self):
            try:
                data = self.parse_json_body()
                result = service.generate_prompt_agent(
                    prompt=str(data.get("prompt") or ""),
                    analysis=data.get("analysis") if isinstance(data.get("analysis"), dict) else {},
                    instruction=str(data.get("instruction") or ""),
                    model_id=str(data.get("model") or ""),
                    edits=data.get("edits") if isinstance(data.get("edits"), list) else [],
                    extra_instruction=str(data.get("extra_instruction") or ""),
                )
                self.json_response(result)
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_prompt_agent_refine(self):
            try:
                data = self.parse_json_body()
                result = service.refine_prompt_agent(
                    prompt=str(data.get("prompt") or ""),
                    analysis=data.get("analysis") if isinstance(data.get("analysis"), dict) else {},
                    current=data.get("current") if isinstance(data.get("current"), dict) else {},
                    instruction=str(data.get("instruction") or ""),
                    model_id=str(data.get("model") or ""),
                )
                self.json_response(result)
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_portrait_generate(self):
            try:
                data = self.parse_json_body()
                selected = data.get("selected") if isinstance(data.get("selected"), dict) else {}
                manual = data.get("manual") if isinstance(data.get("manual"), dict) else {}
                result = service.generate_portrait_prompt(
                    selected=selected,
                    manual={str(key): str(value or "") for key, value in manual.items()},
                    base_prompt=str(data.get("base_prompt") or ""),
                    model_id=str(data.get("model") or ""),
                )
                self.json_response(result)
            except (ValueError, PromptAIError) as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_save_prompt_variant(self, prompt_id: str):
            try:
                data = self.parse_json_body()
                prompt = service.store.save_prompt_variant(prompt_id, data)
                self.safe_write_backup("prompt-variant")
                self.json_response({"prompt": prompt}, status=HTTPStatus.CREATED)
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_task_output_blur(self, task_id: str):
            try:
                data = self.parse_json_body()
                task = service.store.set_task_output_blurred(
                    task_id,
                    str(data.get("path") or ""),
                    bool(data.get("blurred")),
                )
                self.json_response({"task": task})
            except KeyError as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def handle_task_output_delete(self, task_id: str):
            try:
                data = self.parse_json_body()
                task = service.store.set_task_output_deleted(
                    task_id,
                    str(data.get("path") or ""),
                    True,
                )
                self.json_response({"task": task})
            except KeyError as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
            except ValueError as exc:
                self.error_response(HTTPStatus.BAD_REQUEST, str(exc))

        def parse_multipart(self):
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self.error_response(HTTPStatus.BAD_REQUEST, "Expected multipart/form-data")
                raise ValueError("Invalid content type")
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            message = BytesParser(policy=default).parsebytes(
                f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw
            )
            fields: dict[str, str] = {}
            files: dict[str, dict[str, object]] = {}
            for part in message.iter_parts():
                disposition = part.get("Content-Disposition", "")
                if "form-data" not in disposition:
                    continue
                name = part.get_param("name", header="content-disposition")
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename:
                    files[str(name)] = {"filename": Path(filename).name, "content": payload}
                elif name:
                    fields[str(name)] = payload.decode("utf-8")
            return fields, files

        def parse_json_body(self):
            content_type = self.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                self.error_response(HTTPStatus.BAD_REQUEST, "Expected application/json")
                raise ValueError("Invalid content type")
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8") or "{}")

        def query_params(self):
            parsed = urlparse(self.path)
            params = {}
            for part in parsed.query.split("&"):
                if not part or "=" not in part:
                    continue
                key, value = part.split("=", 1)
                params[unquote(key)] = unquote(value)
            return params

        def serve_thumbnail(self, thumb_path: str):
            size_text, _, encoded_rel = thumb_path.partition("/")
            try:
                size = int(size_text)
                rel_path = unquote(encoded_rel)
                target = service.thumbnails.ensure(rel_path, size=size)
            except Exception as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
                return
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            with target.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile)

        def serve_data_file(self, rel_url_path: str):
            rel_path = Path(unquote(rel_url_path))
            target = (data_root / rel_path).resolve()
            if data_root.resolve() not in target.parents and target != data_root.resolve():
                self.error_response(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not target.exists() or not target.is_file():
                self.error_response(HTTPStatus.NOT_FOUND, "File not found")
                return
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def serve_pose_file(self, rel_url_path: str):
            try:
                target = service.resolve_pose_path(unquote(rel_url_path))
            except ValueError as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
                return
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def serve_face_file(self, rel_url_path: str):
            try:
                target = service.resolve_face_library_path(unquote(rel_url_path))
            except ValueError as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
                return
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def serve_portrait_material_image(self, item_id: str):
            try:
                target = service.resolve_portrait_material_image(unquote(item_id))
            except ValueError as exc:
                self.error_response(HTTPStatus.NOT_FOUND, str(exc))
                return
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def serve_static(self, path: str):
            rel = "admin.html" if path in {"/admin", "/admin/"} else "index.html" if path in {"/", ""} else path.lstrip("/")
            target = (web_root / rel).resolve()
            # A fresh install has no personal material index. Keep the studio usable
            # without generating files in the source tree or bundling private assets.
            if rel in {"portrait-materials.json", "portrait-materials.json.gz"} and not target.exists():
                data = gzip.compress(b"[]", mtime=0) if rel.endswith(".gz") else b"[]"
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/gzip" if rel.endswith(".gz") else "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(data)
                return
            if web_root.resolve() not in target.parents and target != web_root.resolve():
                self.error_response(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not target.exists() or target.is_dir():
                target = web_root / "index.html"
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
            if target.name not in {"index.html", "admin.html"}:
                self.send_header("Cache-Control", "public, max-age=604800")
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def json_response(self, payload, status=HTTPStatus.OK):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def json_download_response(self, payload, filename: str):
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def stream_jsonl_response(self, events):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                for event in events:
                    body = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
                    self.wfile.write(body)
                    self.wfile.flush()
            except PromptAIError as exc:
                body = (json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8")
                self.wfile.write(body)
                self.wfile.flush()

        def error_response(self, status, message):
            self.json_response({"error": message}, status=status)

        def safe_write_backup(self, reason: str):
            try:
                service.write_apps_backup(reason)
            except Exception as exc:
                sys.stderr.write(f"auto backup failed: {exc}\n")

        def log_message(self, format, *args):
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    return HuashiHandler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run Huashi private RunningHub studio.")
    parser.add_argument("--host", default=os.getenv("HUASHI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HUASHI_PORT", "8787")))
    parser.add_argument("--data", default=os.getenv("HUASHI_DATA_DIR", "data"))
    args = parser.parse_args(argv)

    project_root = Path(__file__).resolve().parents[1]
    data_root = (project_root / args.data).resolve()
    web_root = project_root / "web"
    service = create_service(data_root)
    handler = make_handler(service, web_root, data_root)
    httpd = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"画室 running at http://{args.host}:{args.port}")
    print(f"data directory: {data_root}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
