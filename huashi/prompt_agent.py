from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .prompt_ai import PROMPT_MODELS, PromptAIError, PromptModel, get_prompt_model


ANALYZE_SYSTEM_PROMPT = """你是画室里的提示词拆解顾问。

你的任务是帮助中文用户快速理解一段复杂绘图提示词，并指出它可以如何改。

只输出 JSON，不要 Markdown，不要解释 JSON 以外的内容。

JSON 字段：
{
  "prompt_type": "人像 / 产品图 / 海报 / 图生图 / 场景图 / UI 图 / 其他",
  "core_image": "一句中文总结，说明这段提示词画什么",
  "core_points": [{"label": "主体", "current": "当前设定"}, ...],
  "editable_points": [{"label": "人物身份", "current": "当前设定", "suggestions": ["可改方向1", "可改方向2"]}, ...],
  "keep_points": ["如果要保持同类效果，建议保留的关键词或结构"],
  "avoid_changes": ["不建议轻易改掉的点"],
  "guide": "一句中文引导，告诉用户可以怎么提出修改要求"
}

拆解要具体，不要空泛。重点识别主体、场景、时间、光线、服装、姿态、镜头、色调、质感、情绪、输出形式。"""


GENERATE_SYSTEM_PROMPT = """你是高水平 AI 绘图提示词创作编辑器。

任务：
根据原提示词、结构化拆解和用户修改要求，生成一条新的完整绘图提示词。

硬性规则：
1. 只生成 1 条，不要给多个方案。
2. 新提示词必须是完整英文提示词，可直接用于 AI 生图。
3. 保留原提示词的核心结构、镜头语言、质感、光影逻辑、输出形式和质量词。
4. 只替换用户明确要求改变的元素；替换后需要配套变化时可以补充合理细节。
5. 不要把长提示词压缩成摘要。
6. 如果原提示词有参数、比例、禁止项或模型参数，除非用户要求删除，否则尽量保留。

只输出 JSON，不要 Markdown，不要 JSON 之外的解释。

JSON 字段：
{
  "prompt_en": "完整英文提示词",
  "translation_cn": "完整中文翻译：逐句翻译 prompt_en，方便中文用户直接看懂",
  "explanation_cn": "简短修改说明：只说明这次主要改了什么，不要长篇解释",
  "feature_cn": "主要特点：一句到两句说明它的视觉重点"
}"""


REFINE_SYSTEM_PROMPT = """你是高水平 AI 绘图提示词微调编辑器。

任务：
基于用户选中的当前提示词和追加修改要求，继续输出一条更新后的完整英文提示词。

硬性规则：
1. 只生成 1 条，不要给多个方案。
2. 以当前提示词为基准继续微调，不要重新回到最初原提示词。
3. 保留当前提示词里仍然有效的主体、镜头、光影、构图、质感和质量词。
4. 只改用户追加要求涉及的部分。

只输出 JSON，不要 Markdown，不要 JSON 之外的解释。

JSON 字段：
{
  "prompt_en": "完整英文提示词",
  "translation_cn": "完整中文翻译：逐句翻译 prompt_en，方便中文用户直接看懂",
  "explanation_cn": "简短修改说明：只说明这次微调改了什么，不要长篇解释",
  "feature_cn": "主要特点：一句到两句说明更新后的视觉重点"
}"""


DEFAULT_GUIDE = "你可以告诉我想改人物、服装、地点、时间、光线、色调、情绪或文化风格，我会尽量保留核心结构来生成类似提示词。"


def get_agent_model(model_id: str = "") -> PromptModel:
    if model_id:
        return get_prompt_model(model_id)
    for item in PROMPT_MODELS:
        if item.id == "aihubmix-grok" and os.getenv("AIHUBMIX_API_KEY"):
            return item
    return get_prompt_model("")


def analyze_prompt(prompt: str, model_id: str = "") -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        raise PromptAIError("提示词不能为空")
    model = get_agent_model(model_id)
    text = call_model_text(model, build_analyze_messages(prompt), temperature=0.35, max_tokens=1800)
    return {"analysis": normalize_analysis(extract_json_object(text)), "model": model.id}


def generate_prompt_variant(prompt: str, analysis: dict[str, Any], instruction: str, model_id: str = "") -> dict[str, Any]:
    prompt = prompt.strip()
    instruction = instruction.strip()
    if not prompt:
        raise PromptAIError("原提示词不能为空")
    if not instruction:
        raise PromptAIError("修改要求不能为空")
    model = get_agent_model(model_id)
    text = call_model_text(model, build_generate_messages(prompt, analysis, instruction), temperature=0.72, max_tokens=2600)
    return {"result": normalize_variant(extract_json_object(text)), "model": model.id}


def refine_prompt_variant(
    prompt: str,
    analysis: dict[str, Any],
    current: dict[str, Any],
    instruction: str,
    model_id: str = "",
) -> dict[str, Any]:
    instruction = instruction.strip()
    current_prompt = str((current or {}).get("prompt_en") or (current or {}).get("content") or "").strip()
    if not current_prompt:
        raise PromptAIError("当前提示词不能为空")
    if not instruction:
        raise PromptAIError("追加修改要求不能为空")
    model = get_agent_model(model_id)
    text = call_model_text(
        model,
        build_refine_messages(prompt, analysis, current_prompt, instruction),
        temperature=0.68,
        max_tokens=2600,
    )
    return {"result": normalize_variant(extract_json_object(text)), "model": model.id}


def build_analyze_messages(prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ANALYZE_SYSTEM_PROMPT},
        {"role": "user", "content": f"请拆解这段绘图提示词：\n{prompt}"},
    ]


def build_generate_messages(original_prompt: str, analysis: dict[str, Any], instruction: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n\n".join(
                [
                    f"原提示词：\n{original_prompt}",
                    f"结构化拆解：\n{json.dumps(analysis or {}, ensure_ascii=False)}",
                    f"用户修改要求：\n{instruction}",
                    "请只生成 1 条完整英文提示词，并附完整中文翻译、简短修改说明和主要特点。",
                ]
            ),
        },
    ]


def build_refine_messages(original_prompt: str, analysis: dict[str, Any], current_prompt: str, instruction: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REFINE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n\n".join(
                [
                    f"最初原提示词，仅作背景参考：\n{original_prompt}",
                    f"结构化拆解，仅作背景参考：\n{json.dumps(analysis or {}, ensure_ascii=False)}",
                    f"当前选中的提示词，请以它为基准：\n{current_prompt}",
                    f"用户追加修改要求：\n{instruction}",
                    "请只输出 1 条更新后的完整英文提示词，并附完整中文翻译、简短修改说明和主要特点。",
                ]
            ),
        },
    ]


def call_model_text(model: PromptModel, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
    if model.provider == "aihubmix":
        return call_aihubmix_text(model, messages, temperature, max_tokens)
    if model.provider == "ollama":
        return call_ollama_text(model, messages, temperature, max_tokens)
    raise PromptAIError(f"不支持的模型来源：{model.provider}")


def call_aihubmix_text(model: PromptModel, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
    api_key = os.getenv("AIHUBMIX_API_KEY", "")
    if not api_key:
        raise PromptAIError("AIHUBMIX_API_KEY 未配置")
    base_url = os.getenv("AIHUBMIX_BASE_URL", "https://aihubmix.com/v1").rstrip("/")
    payload = {
        "model": model.model,
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    chunk = post_json(f"{base_url}/chat/completions", payload, {"Authorization": f"Bearer {api_key}"})
    choices = chunk.get("choices") if isinstance(chunk, dict) else None
    if not choices:
        raise PromptAIError("模型没有返回内容")
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def call_ollama_text(model: PromptModel, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model.model,
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "messages": messages,
    }
    chunk = post_json(f"{base_url}/api/chat", payload)
    message = chunk.get("message") if isinstance(chunk, dict) else None
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return str(chunk.get("response") or "").strip()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise PromptAIError(f"模型接口返回错误：{exc.code} {body[:300]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PromptAIError("无法连接模型接口：" + str(exc)) from exc


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(text[start : end + 1])
        if isinstance(value, dict):
            return value
    raise PromptAIError("模型返回格式不对，没有找到 JSON")


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_type": clean_text(data.get("prompt_type") or "其他"),
        "core_image": clean_text(data.get("core_image") or "这是一段绘图提示词。"),
        "core_points": normalize_point_list(data.get("core_points")),
        "editable_points": normalize_point_list(data.get("editable_points"), with_suggestions=True),
        "keep_points": normalize_string_list(data.get("keep_points")),
        "avoid_changes": normalize_string_list(data.get("avoid_changes")),
        "guide": clean_text(data.get("guide") or DEFAULT_GUIDE),
    }


def normalize_variant(data: dict[str, Any]) -> dict[str, str]:
    prompt_en = clean_text(data.get("prompt_en") or data.get("prompt") or data.get("content"))
    if not prompt_en:
        raise PromptAIError("模型没有返回提示词正文")
    return {
        "prompt_en": prompt_en,
        "translation_cn": clean_text(data.get("translation_cn") or data.get("translation") or ""),
        "explanation_cn": clean_text(data.get("explanation_cn") or data.get("translation") or ""),
        "feature_cn": clean_text(data.get("feature_cn") or data.get("feature") or ""),
    }


def normalize_point_list(value: Any, with_suggestions: bool = False) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else ([value] if value else [])
    points = []
    for index, item in enumerate(values, start=1):
        if isinstance(item, dict):
            label = clean_text(item.get("label") or item.get("name") or f"要点 {index}")
            current = clean_text(item.get("current") or item.get("value") or item.get("description") or "")
            point: dict[str, Any] = {"label": label, "current": current}
            if with_suggestions:
                point["suggestions"] = normalize_string_list(item.get("suggestions"))
            points.append(point)
        else:
            points.append({"label": f"要点 {index}", "current": clean_text(item)})
    return points


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def clean_text(value: Any) -> str:
    return str(value or "").strip()
