from __future__ import annotations

import ast
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class RunningHubInspectError(ValueError):
    pass


@dataclass
class InspectResult:
    source_url: str
    webapp_id: str
    app_name: str = ""
    description: str = ""
    node_id: str = ""
    field_name: str = ""
    prompt_node_id: str = ""
    prompt_field_name: str = ""
    inputs: list[dict[str, Any]] | None = None
    output_type: str = "png"
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "webapp_id": self.webapp_id,
            "app_name": self.app_name,
            "description": self.description,
            "node_id": self.node_id,
            "field_name": self.field_name,
            "prompt_node_id": self.prompt_node_id,
            "prompt_field_name": self.prompt_field_name,
            "inputs": self.inputs or [],
            "output_type": self.output_type,
            "message": self.message,
        }


def inspect_runninghub_source(source_url: str, sample_text: str = "", api_key: str = "") -> dict[str, Any]:
    webapp_id = extract_webapp_id(source_url) or extract_webapp_id(sample_text)
    if not webapp_id:
        raise RunningHubInspectError("没有识别到 RunningHub 应用 ID")

    texts = [sample_text]
    if api_key:
        try:
            texts.append(fetch_api_call_demo(webapp_id, api_key))
        except RunningHubInspectError as exc:
            texts.append(str(exc))
    if source_url:
        try:
            texts.append(fetch_runninghub_doc(source_url, webapp_id))
        except RunningHubInspectError as exc:
            texts.append(str(exc))

    parsed = InspectResult(source_url=source_url, webapp_id=webapp_id)
    for text in texts:
        if not text:
            continue
        candidate = parse_runninghub_text(text, webapp_id=webapp_id, source_url=source_url)
        parsed = merge_result(parsed, candidate)

    if parsed.inputs:
        parsed.message = f"已自动识别 {len(parsed.inputs)} 个输入项。"
    elif parsed.node_id and parsed.field_name:
        parsed.message = "已自动识别应用和输入节点。"
    elif source_url and not sample_text:
        parsed.message = "已识别应用 ID；节点信息未在网页中找到，可粘贴请求示例再解析。"
    else:
        parsed.message = "已识别应用 ID；请手动补充节点信息。"
    return parsed.to_dict()


def extract_webapp_id(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(?:ai-detail|api-detail)/(\d+)",
        r"[?&]webappId=(\d+)",
        r'["\']?webappId["\']?\s*[:=]\s*["\']?(\d+)',
        r'["\']?webapp_id["\']?\s*[:=]\s*["\']?(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def fetch_api_call_demo(webapp_id: str, api_key: str) -> str:
    query = urllib.parse.urlencode({"apiKey": api_key, "webappId": webapp_id})
    url = f"https://www.runninghub.cn/api/webapp/apiCallDemo?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Huashi/0.1",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RunningHubInspectError("无法读取 RunningHub 接口示例：" + str(exc)) from exc
    if payload.get("code") != 0:
        raise RunningHubInspectError("RunningHub 接口示例返回错误：" + str(payload.get("msg") or payload.get("code")))
    return json.dumps(payload.get("data") or {}, ensure_ascii=False)


def fetch_runninghub_doc(source_url: str, webapp_id: str) -> str:
    urls = normalized_doc_urls(source_url, webapp_id)
    errors = []
    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Huashi/0.1",
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as exc:
            errors.append(str(exc))
    raise RunningHubInspectError("无法读取 RunningHub 调用页：" + "; ".join(errors[-2:]))


def normalized_doc_urls(source_url: str, webapp_id: str) -> list[str]:
    parsed = urlparse(source_url)
    if parsed.netloc and not parsed.netloc.endswith("runninghub.cn"):
        raise RunningHubInspectError("只支持 runninghub.cn 链接")
    doc_url = f"https://www.runninghub.cn/call-api/api-detail/{webapp_id}?apiType=4"
    urls = [doc_url]
    if source_url and source_url not in urls:
        urls.append(source_url)
    return urls


def parse_runninghub_text(text: str, webapp_id: str = "", source_url: str = "") -> InspectResult:
    normalized = normalize_text(text)
    result = InspectResult(
        source_url=source_url,
        webapp_id=extract_webapp_id(normalized) or webapp_id,
        app_name=extract_string_field(normalized, "webappName"),
        description=clean_description(extract_string_field(normalized, "description")),
        output_type=guess_output_type(normalized),
    )
    nodes = extract_node_info(text) or extract_node_info(normalized)
    result.inputs = nodes_to_inputs(nodes)
    image_node = pick_image_node(nodes)
    prompt_node = pick_prompt_node(nodes, image_node)
    if image_node:
        result.node_id = str(image_node.get("nodeId") or image_node.get("node_id") or "")
        result.field_name = str(image_node.get("fieldName") or image_node.get("field_name") or "")
    if prompt_node:
        result.prompt_node_id = str(prompt_node.get("nodeId") or prompt_node.get("node_id") or "")
        result.prompt_field_name = str(prompt_node.get("fieldName") or prompt_node.get("field_name") or "")
    return result


def nodes_to_inputs(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inputs = []
    for index, node in enumerate(nodes, start=1):
        node_id = str(node.get("nodeId") or node.get("node_id") or "").strip()
        field_name = str(node.get("fieldName") or node.get("field_name") or "").strip()
        if not node_id or not field_name:
            continue
        field_data = parse_field_data(node.get("fieldData") or node.get("field_data"))
        input_type = infer_input_type(node, field_data)
        label = str(
            node.get("description")
            or node.get("descriptionCn")
            or node.get("descriptionEn")
            or node.get("nodeName")
            or field_name
        ).strip()
        default_value = str(node.get("fieldValue") or "")
        if not default_value and isinstance(field_data, dict):
            default_value = str(field_data.get("default") or "")
        inputs.append(
            {
                "id": f"field_{index}",
                "nodeId": node_id,
                "fieldName": field_name,
                "type": input_type,
                "label": label,
                "required": True,
                "defaultValue": default_value,
                "options": field_options(field_data),
            }
        )
    return inputs


def parse_field_data(raw: Any) -> Any:
    if not raw:
        return None
    if isinstance(raw, (list, dict)):
        value = raw
    else:
        value = parse_jsonish(str(raw))
    if isinstance(value, list) and len(value) > 1 and isinstance(value[1], dict):
        if isinstance(value[0], list):
            return {"options": value[0], **value[1]}
        return value[1]
    return value


def field_options(field_data: Any) -> list[str]:
    if isinstance(field_data, dict) and isinstance(field_data.get("options"), list):
        return [str(item) for item in field_data["options"]]
    if isinstance(field_data, list) and field_data and isinstance(field_data[0], list):
        return [str(item) for item in field_data[0]]
    return []


def infer_input_type(node: dict[str, Any], field_data: Any) -> str:
    field_type = str(node.get("fieldType") or node.get("field_type") or "").upper()
    field = str(node.get("fieldName") or node.get("field_name") or "").lower()
    value = str(node.get("fieldValue") or node.get("field_value") or "").lower()
    if field_type in {"IMAGE", "FILE"} or "image" in field or any(suffix in value for suffix in (".png", ".jpg", ".jpeg", ".webp")):
        return "image"
    if field_type in {"LIST", "COMBO"} or field_options(field_data):
        return "select"
    if field_type in {"INT", "INTEGER", "FLOAT", "NUMBER"}:
        return "number"
    if isinstance(field_data, dict) and field_data.get("multiline"):
        return "textarea"
    return "text"


def extract_string_field(text: str, field_name: str) -> str:
    match = re.search(
        rf'["\']{re.escape(field_name)}["\']\s*:\s*["\'](.*?)["\']',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return normalize_text(match.group(1)).strip()


def clean_description(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize_text(text: str) -> str:
    value = html.unescape(text or "")
    value = value.replace('\\"', '"').replace("\\/", "/")
    value = value.replace("\\n", "\n").replace("\\t", "\t")
    return value


def extract_node_info(text: str) -> list[dict[str, Any]]:
    nodes = []
    for snippet in node_info_snippets(text):
        parsed = parse_jsonish(snippet)
        if isinstance(parsed, list):
            nodes.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            nodes.append(parsed)
    if nodes:
        return dedupe_nodes(nodes)

    matches = re.finditer(
        r'["\']?nodeId["\']?\s*:\s*["\']?([^,"\'}\s]+).*?["\']?fieldName["\']?\s*:\s*["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in matches:
        nodes.append({"nodeId": match.group(1), "fieldName": match.group(2)})
    return dedupe_nodes(nodes)


def node_info_snippets(text: str) -> list[str]:
    snippets = []
    for match in re.finditer(r'["\']?nodeInfoList["\']?\s*[=:]\s*\[', text):
        start = text.find("[", match.start())
        snippet = balanced_segment(text, start, "[", "]")
        if snippet:
            snippets.append(snippet)
    if text.strip().startswith("[") or text.strip().startswith("{"):
        snippets.append(text.strip())
    return snippets


def balanced_segment(text: str, start: int, opener: str, closer: str) -> str:
    depth = 0
    in_string = ""
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = ""
            continue
        if char in {'"', "'"}:
            in_string = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def parse_jsonish(snippet: str) -> Any:
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(snippet)
        except Exception:
            pass
    return None


def pick_image_node(nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for node in nodes:
        field = str(node.get("fieldName") or node.get("field_name") or "").lower()
        value = str(node.get("fieldValue") or node.get("field_value") or "").lower()
        if field in {"image", "img", "photo", "picture", "file"} or "image" in field:
            return node
        if any(suffix in value for suffix in (".png", ".jpg", ".jpeg", ".webp")):
            return node
    return nodes[0] if nodes else None


def pick_prompt_node(nodes: list[dict[str, Any]], image_node: dict[str, Any] | None) -> dict[str, Any] | None:
    for node in nodes:
        if image_node is node:
            continue
        field = str(node.get("fieldName") or node.get("field_name") or "").lower()
        if any(token in field for token in ("prompt", "text", "positive")):
            return node
    return None


def guess_output_type(text: str) -> str:
    lowered = text.lower()
    explicit = re.search(r'["\']?(fileType|output_type|type)["\']?\s*:\s*["\']?(zip|webp|jpe?g|png)', lowered)
    if explicit:
        value = explicit.group(2)
        return "jpg" if value == "jpeg" else value
    if ".zip" in lowered:
        return "zip"
    return "png"


def merge_result(base: InspectResult, candidate: InspectResult) -> InspectResult:
    for key in (
        "webapp_id",
        "app_name",
        "description",
        "node_id",
        "field_name",
        "prompt_node_id",
        "prompt_field_name",
        "output_type",
    ):
        if not getattr(base, key) and getattr(candidate, key):
            setattr(base, key, getattr(candidate, key))
    if not base.inputs and candidate.inputs:
        base.inputs = candidate.inputs
    if base.output_type == "png" and candidate.output_type != "png":
        base.output_type = candidate.output_type
    return base


def dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for node in nodes:
        key = (str(node.get("nodeId") or node.get("node_id") or ""), str(node.get("fieldName") or node.get("field_name") or ""))
        if key in seen or not key[0] or not key[1]:
            continue
        seen.add(key)
        unique.append(node)
    return unique
