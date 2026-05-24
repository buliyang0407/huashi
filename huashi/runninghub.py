from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class RunningHubError(RuntimeError):
    pass


class RunningHubClient:
    def __init__(self, api_key: str, base_url: str = "https://www.runninghub.cn"):
        if not api_key:
            raise RunningHubError("RUNNINGHUB_API_KEY is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def upload_media(self, file_path: Path | str) -> str:
        file_path = Path(file_path)
        boundary = "----huashi-" + uuid.uuid4().hex
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        safe_filename = "upload" + (file_path.suffix.lower() if file_path.suffix else "")
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{safe_filename}"\r\n'.encode("ascii")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
        body.extend(file_path.read_bytes())
        body.extend(f"\r\n--{boundary}--\r\n".encode("ascii"))
        response = self._request(
            "/openapi/v2/media/upload/binary",
            bytes(body),
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        file_name = response.get("data", {}).get("fileName")
        if not file_name:
            raise RunningHubError(f"Upload response missing fileName: {response}")
        return file_name

    def run_app(
        self,
        webapp_id: str,
        node_id: str,
        field_name: str,
        field_value: str,
        extra_nodes: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        node_info_list = [{"nodeId": node_id, "fieldName": field_name, "fieldValue": field_value}]
        if extra_nodes:
            node_info_list.extend(extra_nodes)
        payload = {
            "webappId": webapp_id,
            "apiKey": self.api_key,
            "nodeInfoList": node_info_list,
        }
        response = self.post_json("/task/openapi/ai-app/run", payload)
        data = response.get("data") or {}
        if not data.get("taskId"):
            raise RunningHubError(f"Run response missing taskId: {response}")
        return data

    def run_app_nodes(self, webapp_id: str, node_info_list: list[dict[str, str]]) -> dict[str, Any]:
        payload = {
            "webappId": webapp_id,
            "apiKey": self.api_key,
            "nodeInfoList": node_info_list,
        }
        response = self.post_json("/task/openapi/ai-app/run", payload)
        data = response.get("data") or {}
        if not data.get("taskId"):
            raise RunningHubError(f"Run response missing taskId: {response}")
        return data

    def get_status(self, task_id: str) -> str:
        response = self.post_json("/task/openapi/status", {"apiKey": self.api_key, "taskId": task_id})
        return str(response.get("data"))

    def wait_for_success(self, task_id: str, poll_interval: float = 5, timeout: float = 600) -> str:
        deadline = time.time() + timeout
        last_status = "UNKNOWN"
        while time.time() < deadline:
            last_status = self.get_status(task_id)
            if last_status == "SUCCESS":
                return last_status
            if last_status in {"FAILED", "FAIL", "ERROR"}:
                raise RunningHubError(f"RunningHub task failed: {task_id}")
            time.sleep(poll_interval)
        raise RunningHubError(f"RunningHub task timed out after {timeout}s, last status: {last_status}")

    def get_outputs(self, task_id: str) -> list[dict[str, Any]]:
        response = self.post_json("/task/openapi/outputs", {"apiKey": self.api_key, "taskId": task_id})
        data = response.get("data")
        if not isinstance(data, list):
            raise RunningHubError(f"Outputs response missing list: {response}")
        return data

    def download_file(self, url: str, destination: Path | str) -> None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(quote_url(url), timeout=120) as response:
            destination.write_bytes(response.read())

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(path, json.dumps(payload, ensure_ascii=True).encode("utf-8"), {"Content-Type": "application/json"})

    def _request(self, path: str, data: bytes, headers: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Host": "www.runninghub.cn",
                **headers,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RunningHubError(f"HTTP {exc.code}: {body}") from exc
        if payload.get("code") != 0:
            raise RunningHubError(f"RunningHub error: {payload}")
        return payload


def quote_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            urllib.parse.quote(parsed.path, safe="/%@:"),
            urllib.parse.quote(parsed.query, safe="=&?/%@:,+"),
            urllib.parse.quote(parsed.fragment, safe="=&?/%@:,+"),
        )
    )
