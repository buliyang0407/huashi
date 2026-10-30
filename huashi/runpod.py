"""RunPod Serverless transport and the code-configured ComfyUI workflow payload."""

from __future__ import annotations

import base64
import copy
import json
import math
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener

from .runpod_workflows import WORKFLOWS


MAX_REQUEST_BYTES = 9_500_000
TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


class RunPodError(RuntimeError):
    pass


class RunPodSubmissionUnknown(RunPodError):
    """The POST may have reached RunPod; never resubmit automatically."""


def prepare_image(source: Path, destination: Path, max_edge: int = 2048) -> Path:
    """Make a disposable inference copy. Never modify the uploaded original."""
    from PIL import Image, ImageOps
    if not 64 <= max_edge <= 8192:
        raise ValueError("RunPod 图片最长边配置无效")
    try:
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened)
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            if image.mode == "RGBA" or "transparency" in image.info:
                background = Image.new("RGB", image.size, "white")
                background.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, "JPEG", quality=88, optimize=True)
    except (OSError, ValueError) as exc:
        raise ValueError("RunPod 输入图片无法读取") from exc
    return destination


def make_payload(workflow_key: str, inputs: list[dict[str, Any]], values: dict[str, Any], files: dict[str, Path]) -> bytes:
    config = WORKFLOWS.get(workflow_key)
    if not config:
        raise ValueError("RunPod 工作流未配置")
    if config.get("random_seed_on_empty") and values.get("seed", "") == "":
        raise ValueError("随机种子尚未确定，请先创建画室任务")
    workflow = copy.deepcopy(json.loads(config["workflow_path"].read_text(encoding="utf-8")))
    images = []
    for item in inputs:
        input_id = item["id"]
        node_id = str(item.get("nodeId") or "")
        field_name = str(item.get("fieldName") or "")
        if node_id not in workflow or field_name not in workflow[node_id]["inputs"]:
            raise ValueError(f"RunPod 工作流字段不存在：{input_id}")
        if item["type"] == "image":
            source = files.get(input_id)
            if not source:
                if item.get("required"):
                    raise ValueError(f"缺少输入：{item.get('label') or input_id}")
                continue
            name = f"input_{len(images) + 1}.jpg"
            workflow[node_id]["inputs"][field_name] = name
            images.append({"name": name, "image": base64.b64encode(source.read_bytes()).decode("ascii")})
        else:
            raw = values.get(input_id, item.get("defaultValue", ""))
            if raw == "" and item.get("required"):
                raise ValueError(f"缺少输入：{item.get('label') or input_id}")
            if raw == "" and item["type"] not in {"text", "textarea"}:
                continue
            if item["type"] == "select" and item.get("options") and str(raw) not in item["options"] and str(raw) not in (item.get("valueMap") or {}):
                raise ValueError(f"{item.get('label') or input_id} 选项无效")
            if item["type"] == "number":
                try:
                    value = float(str(raw)) if input_id in {"cfg", "denoise", "lora_strength"} else int(str(raw))
                except ValueError as exc:
                    kind = "数字" if input_id in {"cfg", "denoise", "lora_strength"} else "整数"
                    raise ValueError(f"{item.get('label') or input_id} 必须是{kind}") from exc
                if input_id in {"cfg", "denoise", "lora_strength"} and not math.isfinite(value):
                    raise ValueError(f"{item.get('label') or input_id} 必须是有限数字")
                if input_id == "cfg" and not 0 <= value <= 100:
                    raise ValueError("CFG 必须在 0–100 之间")
                if input_id == "denoise" and not 0 <= value <= 1:
                    raise ValueError("降噪强度必须在 0–1 之间")
                if input_id == "lora_strength" and not -100 <= value <= 100:
                    raise ValueError("LoRA 权重必须在 -100–100 之间")
                if input_id == "batch_size" and not 1 <= value <= 4:
                    raise ValueError("每批图片数量必须在 1–4 之间")
                if input_id == "resolution" and not 0 <= value <= 2048:
                    raise ValueError("编码分辨率必须在 0–2048 之间")
                if input_id in {"width", "height"} and (value < 64 or value > 2048 or value % 16):
                    raise ValueError("宽高必须在 64–2048 之间，且为 16 的倍数")
                if input_id == "steps" and not 1 <= value <= 100:
                    raise ValueError("步数必须在 1–100 之间")
                if input_id == "seed" and not 0 <= value < 2**64:
                    raise ValueError("随机种子超出范围")
            elif item["type"] == "checkbox":
                value = str(raw).lower() in {"1", "true", "yes", "on"}
            else:
                value = str(raw)
            mapping = item.get("valueMap") or {}
            if mapping:
                if str(raw) not in mapping:
                    raise ValueError(f"{item.get('label') or input_id} 选项无效")
                value = mapping[str(raw)]
            workflow[node_id]["inputs"][field_name] = value
    payload = json.dumps({"input": {"workflow": workflow, "images": images}}, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("RunPod 请求超过大小限制，请换用更小的输入图片")
    return payload


class RunPodClient:
    def __init__(self, api_key: str, endpoint_id: str, proxy_url: str):
        self.api_key = api_key
        self.endpoint_id = endpoint_id.strip()
        self.proxy_url = proxy_url.strip()
        if self.proxy_url and "://" not in self.proxy_url:
            self.proxy_url = "http://" + self.proxy_url
        parsed = urlparse(self.proxy_url)
        if parsed.scheme != "http" or not parsed.hostname or not parsed.port:
            raise RunPodError("RUNPOD_PROXY_URL 需要填写 http://Mac Mini 局域网IP:17891")
        if not self.endpoint_id or not self.api_key:
            raise RunPodError("RunPod API Key 或 Endpoint ID 尚未配置")
        self.base_url = f"https://api.runpod.ai/v2/{self.endpoint_id}"
        # An explicit handler prevents environment HTTP(S)_PROXY from affecting this client.
        self.opener = build_opener(ProxyHandler({"https": self.proxy_url}))

    @classmethod
    def from_workflow(cls, workflow_key: str) -> RunPodClient:
        config = WORKFLOWS.get(workflow_key)
        if not config:
            raise RunPodError("RunPod 工作流未配置")
        return cls(os.getenv("RUNPOD_API_KEY", ""), os.getenv(config["endpoint_env"], ""), os.getenv("RUNPOD_PROXY_URL", ""))

    def _request(self, path: str, payload: bytes | None = None, timeout: float = 30) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with self.opener.open(request, timeout=timeout) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise RunPodError("RunPod 返回了无效响应")
            return result
        except HTTPError as exc:
            # Do not include response bodies or URLs: they can contain sensitive values.
            raise RunPodError(f"RunPod HTTP {exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise RunPodError("RunPod 代理或网络连接失败") from None
        except (json.JSONDecodeError, UnicodeError):
            raise RunPodError("RunPod 返回了无效 JSON") from None

    def check_connection(self) -> None:
        try:
            self._request("/health", timeout=10)
        except RunPodError as exc:
            raise RunPodError("Mac Mini 代理或 RunPod 连通性检查失败；任务尚未提交 RunPod，未启动远端 GPU。" + str(exc)) from None

    def submit(self, payload: bytes) -> str:
        try:
            response = self._request("/run", payload=payload, timeout=45)
        except RunPodError as exc:
            raise RunPodSubmissionUnknown("RunPod 提交请求已发出但未确认结果；可能已创建远端任务，请勿自动重试。" + str(exc)) from None
        job_id = response.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise RunPodSubmissionUnknown("RunPod 未返回任务 ID；提交结果不确定，请勿自动重试")
        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        if not job_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in job_id):
            raise RunPodError("RunPod 任务 ID 无效")
        return self._request(f"/status/{job_id}", timeout=30)

    def wait(self, job_id: str, on_status, poll_interval: float = 5, timeout: float = 900) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = self.status(job_id)
            status = str(response.get("status") or "")
            on_status(status)
            if status == "COMPLETED":
                return response
            if status in TERMINAL_STATUSES:
                detail = response.get("error")
                if isinstance(detail, (dict, list)):
                    detail = json.dumps(detail, ensure_ascii=False)
                detail = str(detail or "")[:300].replace(self.api_key, "***").replace(self.proxy_url, "***")
                raise RunPodError(f"RunPod {status}" + (f"：{detail}" if detail else ""))
            time.sleep(poll_interval)
        raise RunPodError("等待 RunPod 结果超时；远端任务可能仍在运行，可凭任务 ID 查询")


def decode_images(response: dict[str, Any]) -> list[bytes]:
    output = response.get("output") or {}
    images = output.get("images") if isinstance(output, dict) else None
    if not isinstance(images, list) or not images:
        raise RunPodError("RunPod 已完成，但没有返回图片")
    decoded = []
    for item in images:
        if not isinstance(item, dict) or item.get("type") != "base64":
            raise RunPodError("RunPod 返回了不支持的图片格式")
        try:
            data = base64.b64decode(item["data"], validate=True)
        except (KeyError, ValueError) as exc:
            raise RunPodError("RunPod 图片数据损坏") from exc
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RunPodError("RunPod 返回的图片不是 PNG")
        decoded.append(data)
    return decoded
