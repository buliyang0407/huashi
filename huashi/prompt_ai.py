from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator


MAX_CANDIDATES = 6


def candidate_marker(index: int) -> str:
    return f"<<<HUASHI_CANDIDATE_{index}>>>"


SYSTEM_PROMPT_TEMPLATE = """你是中文 AI 绘图提示词改写编辑器。

任务：
根据原提示词和修改想法，生成 {count} 条新的完整绘图提示词。

重要原则：
1. 不要把长提示词压缩成摘要。
2. 不要只替换几个关键词。
3. 必须保留原提示词的核心画面骨架、构图方式、输出形式、主体关系和空间关系。
4. 必须保留原提示词中仍然适用的风格、材质、光影、色彩逻辑、氛围、质量词和禁止项。
5. 只替换修改想法明确要求改变的元素。
6. 如果替换后需要配套变化，可以合理补充细节，但不要偏离原始画面。
7. 输出必须是可直接用于 AI 生图的完整提示词。
8. 不要解释，不要 Markdown，不要编号。
9. 每条候选内部可以保留自然段落和换行。

输出格式必须严格如下：
{format_block}

除这些分隔符和提示词正文外，不要输出任何其他内容。"""


TRANSLATE_PROMPT = """你是绘图提示词翻译助手。

任务：
把用户给出的英文或中英混合绘图提示词翻译成自然、准确的中文，方便中文用户理解。

规则：
1. 不改写提示词含义，不删减细节。
2. 保留 Midjourney、Stable Diffusion、RunningHub 等参数原样，例如 --ar、--style、--v、CFG、seed。
3. 专有风格词、镜头词、材质词可以在中文后保留英文括号。
4. 只输出中文翻译，不要解释。"""


@dataclass(frozen=True)
class PromptModel:
    id: str
    label: str
    provider: str
    model: str
    default: bool = False


PROMPT_MODELS = [
    PromptModel("ollama-qwen-vl", "快速稳定：qwen3-vl:8b-instruct", "ollama", "qwen3-vl:8b-instruct", True),
    PromptModel("ollama-qwen-9b", "高质量：qwen3.5:9b", "ollama", "qwen3.5:9b"),
    PromptModel("ollama-qwen-4b", "本地备选：qwen3.5-uncensored:4b", "ollama", "jaahas/qwen3.5-uncensored:4b"),
    PromptModel("aihubmix-grok", "第三方：grok-4.3", "aihubmix", "grok-4.3"),
]


class PromptAIError(RuntimeError):
    pass


def list_prompt_models() -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "label": item.label,
            "provider": item.provider,
            "model": item.model,
            "default": item.default,
            "available": item.provider != "aihubmix" or bool(os.getenv("AIHUBMIX_API_KEY")),
        }
        for item in PROMPT_MODELS
    ]


def rewrite_prompt_stream(original_prompt: str, edit_idea: str, model_id: str = "", count: int = 3) -> Iterator[dict[str, Any]]:
    original_prompt = original_prompt.strip()
    edit_idea = edit_idea.strip()
    if not original_prompt:
        raise PromptAIError("原提示词不能为空")
    if not edit_idea:
        raise PromptAIError("修改想法不能为空")
    count = clamp_candidate_count(count)
    model = get_prompt_model(model_id)
    yield {"type": "status", "message": "正在连接模型..."}
    if model.provider == "ollama":
        yield from stream_ollama(model, original_prompt, edit_idea, count)
    elif model.provider == "aihubmix":
        yield from stream_aihubmix(model, original_prompt, edit_idea, count)
    else:
        raise PromptAIError(f"不支持的模型来源：{model.provider}")


def translate_prompt_stream(prompt: str, model_id: str = "") -> Iterator[dict[str, Any]]:
    prompt = prompt.strip()
    if not prompt:
        raise PromptAIError("提示词不能为空")
    model = get_prompt_model(model_id)
    yield {"type": "status", "message": "正在准备翻译..."}
    messages = [
        {"role": "system", "content": TRANSLATE_PROMPT},
        {"role": "user", "content": prompt},
    ]
    if model.provider == "ollama":
        yield from stream_ollama_messages(model, messages, "正在翻译提示词...")
    elif model.provider == "aihubmix":
        yield from stream_aihubmix_messages(model, messages, "正在翻译提示词...")
    else:
        raise PromptAIError(f"不支持的模型来源：{model.provider}")


def get_prompt_model(model_id: str = "") -> PromptModel:
    if model_id:
        for item in PROMPT_MODELS:
            if item.id == model_id:
                return item
        raise PromptAIError("未知模型")
    return next(item for item in PROMPT_MODELS if item.default)


def build_messages(original_prompt: str, edit_idea: str, count: int = 3) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": build_system_prompt(count)},
        {"role": "user", "content": f"原提示词：\n{original_prompt}\n\n修改想法：\n{edit_idea}"},
    ]


def build_system_prompt(count: int) -> str:
    count = clamp_candidate_count(count)
    format_block = "\n".join(
        f"{candidate_marker(index)}\n第{index}条完整提示词"
        for index in range(1, count + 1)
    )
    return SYSTEM_PROMPT_TEMPLATE.format(count=count, format_block=format_block)


def clamp_candidate_count(value: int | str) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 3
    return min(MAX_CANDIDATES, max(1, count))


def stream_ollama(model: PromptModel, original_prompt: str, edit_idea: str, count: int = 3) -> Iterator[dict[str, Any]]:
    yield from stream_ollama_messages(model, build_messages(original_prompt, edit_idea, count), f"正在使用 {model.model} 改写...")


def stream_ollama_messages(model: PromptModel, messages: list[dict[str, str]], status_message: str) -> Iterator[dict[str, Any]]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model.model,
        "stream": True,
        "think": False,
        "options": {"temperature": 0.78, "num_predict": 1100},
        "messages": messages,
    }
    yield {"type": "status", "message": status_message}
    yield from read_sse_json_lines(f"{base_url}/api/chat", payload, token_from_ollama_chunk)


def stream_aihubmix(model: PromptModel, original_prompt: str, edit_idea: str, count: int = 3) -> Iterator[dict[str, Any]]:
    yield from stream_aihubmix_messages(model, build_messages(original_prompt, edit_idea, count), f"正在使用 {model.model} 改写...")


def stream_aihubmix_messages(model: PromptModel, messages: list[dict[str, str]], status_message: str) -> Iterator[dict[str, Any]]:
    api_key = os.getenv("AIHUBMIX_API_KEY", "")
    if not api_key:
        raise PromptAIError("AIHUBMIX_API_KEY 未配置")
    base_url = os.getenv("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1").rstrip("/")
    payload = {
        "model": model.model,
        "stream": True,
        "temperature": 0.78,
        "max_tokens": 1200,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    yield {"type": "status", "message": status_message}
    yield from read_sse_json_lines(f"{base_url}/chat/completions", payload, token_from_openai_chunk, headers=headers)


def read_sse_json_lines(
    url: str,
    payload: dict[str, Any],
    token_reader,
    headers: dict[str, str] | None = None,
) -> Iterator[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    text = ""
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line.removeprefix("data:").strip()
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = token_reader(chunk)
                if token:
                    text += token
                    if len(text) == len(token):
                        yield {"type": "status", "message": "模型已开始输出..."}
                    yield {"type": "token", "text": token}
        yield {"type": "status", "message": "正在整理结果..."}
        yield {"type": "done", "candidates": split_candidates(text), "text": text}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PromptAIError(f"模型接口返回错误：{exc.code} {body[:300]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PromptAIError("无法连接模型接口：" + str(exc)) from exc


def token_from_ollama_chunk(chunk: dict[str, Any]) -> str:
    message = chunk.get("message") if isinstance(chunk, dict) else None
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(chunk.get("response") or "")


def token_from_openai_chunk(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices") if isinstance(chunk, dict) else None
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    return str(delta.get("content") or "")


def split_candidates(text: str) -> list[str]:
    marked = split_marked_candidates(text)
    if marked:
        return marked
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        value = raw.strip()
        if not value:
            continue
        value = value.lstrip("- ")
        if len(value) > 2 and value[0].isdigit() and value[1] in {".", "、", ")"}:
            value = value[2:].strip()
        if value:
            lines.append(value)
    if len(lines) >= 3:
        return lines[:3]
    return lines or ([text.strip()] if text.strip() else [])


def split_marked_candidates(text: str) -> list[str]:
    candidates = []
    markers = [candidate_marker(index) for index in range(1, MAX_CANDIDATES + 1)]
    for index, marker in enumerate(markers):
        start = text.find(marker)
        if start < 0:
            continue
        start += len(marker)
        next_marker = markers[index + 1] if index + 1 < len(markers) else ""
        end = text.find(next_marker, start) if next_marker else len(text)
        if end < 0:
            end = len(text)
        value = text[start:end].strip()
        if value:
            candidates.append(value)
    return candidates[:MAX_CANDIDATES]
