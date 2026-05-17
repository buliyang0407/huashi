from __future__ import annotations

import argparse
import json
import os
import sys
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .runninghub_inspector import RunningHubInspectError, inspect_runninghub_source
from .runninghub import RunningHubClient, RunningHubError
from .service import HuashiService
from .storage import HuashiStore


class MissingRunningHubClient:
    def __init__(self):
        self.api_key = ""

    def __getattr__(self, name):
        raise RunningHubError("RUNNINGHUB_API_KEY is not configured. Set it in .env or the shell before generating.")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def create_service(data_root: Path) -> HuashiService:
    load_dotenv(Path(".env"))
    store = HuashiStore(data_root / "db.sqlite")
    store.initialize()
    api_key = os.getenv("RUNNINGHUB_API_KEY", "")
    client = RunningHubClient(api_key) if api_key else MissingRunningHubClient()
    return HuashiService(data_root, store, client)


def make_handler(service: HuashiService, web_root: Path, data_root: Path):
    class HuashiHandler(SimpleHTTPRequestHandler):
        server_version = "Huashi/0.1"

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/apps":
                self.json_response({"apps": service.store.list_apps()})
                return
            if path == "/api/admin/apps":
                self.json_response({"apps": service.store.list_all_apps()})
                return
            if path == "/api/admin/backup":
                filename = f"huashi-apps-{service.export_apps_bundle()['exported_at'][:10]}.json"
                self.json_download_response(service.export_apps_bundle(), filename)
                return
            if path == "/api/tasks":
                self.json_response({"tasks": service.store.list_tasks()})
                return
            if path.startswith("/api/tasks/"):
                task_id = path.rstrip("/").split("/")[-1]
                self.json_response({"task": service.store.get_task(task_id)})
                return
            if path.startswith("/files/"):
                self.serve_data_file(path.removeprefix("/files/"))
                return
            self.serve_static(path)

        def do_POST(self):
            path = urlparse(self.path).path
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
            if path.startswith("/api/tasks/") and path.endswith("/archive"):
                task_id = path.split("/")[-2]
                self.json_response({"task": service.archive_task(task_id)})
                return
            if path.startswith("/api/tasks/") and path.endswith("/retry"):
                task_id = path.split("/")[-2]
                self.json_response({"task": service.retry_task(task_id)})
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def do_PUT(self):
            path = urlparse(self.path).path
            if path.startswith("/api/admin/apps/"):
                app_id = path.rstrip("/").split("/")[-1]
                self.handle_save_app(app_id)
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def do_DELETE(self):
            path = urlparse(self.path).path
            if path.startswith("/api/admin/apps/"):
                app_id = path.rstrip("/").split("/")[-1]
                self.json_response({"app": service.store.disable_app(app_id)})
                return
            if path.startswith("/api/tasks/"):
                task_id = path.rstrip("/").split("/")[-1]
                service.delete_task(task_id)
                self.json_response({"ok": True})
                return
            self.error_response(HTTPStatus.NOT_FOUND, "Not found")

        def handle_create_task(self):
            fields, files = self.parse_multipart()
            app_id = fields.get("appId")
            if not app_id:
                self.error_response(HTTPStatus.BAD_REQUEST, "Missing appId")
                return
            task = service.create_task_from_form(
                app_id=app_id,
                fields=fields,
                files=files,
                start_background=True,
            )
            self.json_response({"task": task}, status=HTTPStatus.CREATED)

        def handle_save_app(self, app_id: str | None = None):
            fields, files = self.parse_multipart()
            data = {key: value for key, value in fields.items()}
            if app_id:
                current = service.store.get_app(app_id)
                data = {**current, **data}
            cover = files.get("cover")
            target_id = app_id or data.get("id") or ""
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
            self.end_headers()
            with target.open("rb") as handle:
                self.copyfile(handle, self.wfile)

        def serve_static(self, path: str):
            rel = "admin.html" if path in {"/admin", "/admin/"} else "index.html" if path in {"/", ""} else path.lstrip("/")
            target = (web_root / rel).resolve()
            if web_root.resolve() not in target.parents and target != web_root.resolve():
                self.error_response(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            if not target.exists() or target.is_dir():
                target = web_root / "index.html"
            self.path = str(target)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(target)))
            self.send_header("Content-Length", str(target.stat().st_size))
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
