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
  "summary": "一句中文总结，说明这段提示词画什么",
  "translation_cn": "原提示词的完整中文翻译，让不懂英文的用户能看懂",
  "editable_items": [
    {
      "id": "person / hair / clothing / scene / time_light / pose / camera / expression / prop / color / other",
      "label": "中文字段名，例如：人物身份",
      "original": "中文原值，例如：红发年轻女子",
      "placeholder": "中文示例，例如：黑长直发",
      "suggestions": ["3 到 5 个中文改法建议，例如：黑长直发、银色短发、棕色卷发"]
    }
  ],
  "locked_context": ["建议默认保留的画风、摄影、构图、质量词或提示词组结构"],
  "guide": "一句中文引导，告诉用户可以怎么提出修改要求"
}

拆解要具体，不要空泛。优先把用户常改的内容拆成 editable_items：人物身份、发型发色、服装、场景地点、时间光线、姿势动作、镜头景别、镜头角度、表情气质、道具、色彩氛围、材质、背景元素。能拆细就拆细，通常给 8 到 14 个 editable_items。
每个 editable_items 必须给 3 到 5 个中文 suggestions，建议要短、可直接点选填入，帮助用户发散思路；不要只给 1 个。
人物相关 suggestions 必须明确是成年女性或成熟商业人像表达，避免“少女”“萝莉”“未成年”“学生妹”等年龄不明确或未成年感词汇；如果想表达年轻感，写“20岁左右成年女性”“年轻成年女性”“清爽成年女性”。
画风、摄影质感、构图习惯、质量词、模型参数、比例、输出形式通常放进 locked_context，不要让用户默认修改，但如果原提示词里镜头景别或镜头角度明确存在，要放进 editable_items，因为用户可能想拉远、俯拍或特写。
editable_items 的 label、original、placeholder 必须是中文。"""


GENERATE_SYSTEM_PROMPT = """你是高水平 AI 绘图提示词创作编辑器。

任务：
根据原提示词、结构化拆解和用户修改要求，生成一条新的完整绘图提示词。

硬性规则：
1. 只生成 1 条，不要给多个方案。
2. 新提示词必须是完整英文提示词，可直接用于 AI 生图。
3. 保留原提示词的核心结构、镜头语言、质感、光影逻辑、输出形式和质量词。
4. 只替换用户明确要求改变的元素；如果收到局部修改表，只改“新值”非空的项目，空值项目保持原样。
5. 不要把长提示词压缩成摘要。
6. 如果原提示词有参数、比例、禁止项或模型参数，除非用户要求删除，否则尽量保留。
7. 用户可能用中文口语描述专业变化，例如“拉远一点，全身”，你要转成自然的英文镜头语言，例如 wider full-body shot，而不是逐字翻译。

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
ANALYZE_MAX_TOKENS = 4200


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
    text = call_model_text(model, build_analyze_messages(prompt), temperature=0.35, max_tokens=ANALYZE_MAX_TOKENS)
    return {"analysis": normalize_analysis(extract_json_object(text)), "model": model.id}


def generate_prompt_variant(
    prompt: str,
    analysis: dict[str, Any],
    instruction: str = "",
    model_id: str = "",
    edits: list[dict[str, Any]] | None = None,
    extra_instruction: str = "",
) -> dict[str, Any]:
    prompt = prompt.strip()
    instruction = build_edit_instruction(edits, extra_instruction) or instruction.strip()
    if not prompt:
        raise PromptAIError("原提示词不能为空")
    if not instruction:
        raise PromptAIError("修改要求不能为空")
    model = get_agent_model(model_id)
    text = call_model_text(
        model,
        build_generate_messages(prompt, analysis, instruction, edits=edits, extra_instruction=extra_instruction),
        temperature=0.72,
        max_tokens=2600,
    )
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


def build_generate_messages(
    original_prompt: str,
    analysis: dict[str, Any],
    instruction: str = "",
    edits: list[dict[str, Any]] | None = None,
    extra_instruction: str = "",
) -> list[dict[str, str]]:
    edit_instruction = build_edit_instruction(edits, extra_instruction) or instruction
    return [
        {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n\n".join(
                [
                    f"原提示词：\n{original_prompt}",
                    f"原提示词中文翻译：\n{clean_text((analysis or {}).get('translation_cn'))}",
                    f"结构化拆解：\n{json.dumps(analysis or {}, ensure_ascii=False)}",
                    "局部修改规则：只改“新值”非空的项目；没有出现在修改清单里的元素保持原提示词风格和结构。",
                    f"用户修改要求：\n{edit_instruction}",
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
        raise PromptAIError(f"模型接口返回错误：{exc.code} {agent_model_error_message(body)}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PromptAIError("无法连接模型接口：" + str(exc)) from exc


def agent_model_error_message(body: str) -> str:
    if "this key is not enabled" in body:
        return "AIHubMix 已收到密钥，但这把 key 没有开通当前模型权限；请在 AIHubMix 后台启用对应模型，或先切换到第三方备用 qwen3.7-max。"
    try:
        payload = json.loads(body or "{}")
        message = ((payload.get("error") or {}).get("message") or "").strip()
        if message:
            return message[:300]
    except json.JSONDecodeError:
        pass
    return body[:300]


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
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            raise PromptAIError(invalid_json_message(text, exc)) from exc
    raise PromptAIError("模型返回格式不对，没有找到 JSON")


def invalid_json_message(text: str, exc: json.JSONDecodeError) -> str:
    tail = text[max(0, len(text) - 80) :].strip()
    if exc.pos >= max(0, len(text) - 160) or not tail.endswith("}"):
        return "模型输出不完整，可能被长度限制截断了；请重试，或换用默认 Grok4.1。"
    return f"模型返回 JSON 格式不对：{exc.msg}"


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    summary = clean_text(data.get("summary") or data.get("core_image") or "这是一段绘图提示词。")
    editable_items = normalize_edit_items(data.get("editable_items"))
    if not editable_items:
        editable_items = editable_points_to_edit_items(data.get("editable_points"))
    return {
        "prompt_type": clean_text(data.get("prompt_type") or "其他"),
        "summary": summary,
        "translation_cn": clean_text(data.get("translation_cn") or data.get("prompt_translation") or ""),
        "editable_items": editable_items,
        "locked_context": normalize_string_list(data.get("locked_context") or data.get("keep_points")),
        "core_image": summary,
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


LABEL_BY_ID = {
    "person": "人物身份",
    "subject": "人物身份",
    "hair": "发型发色",
    "clothing": "服装",
    "outfit": "服装",
    "scene": "场景地点",
    "location": "场景地点",
    "time_light": "时间光线",
    "lighting": "时间光线",
    "pose": "姿势动作",
    "action": "姿势动作",
    "camera": "镜头景别",
    "shot": "镜头景别",
    "angle": "镜头角度",
    "expression": "表情气质",
    "mood": "表情气质",
    "prop": "道具元素",
    "color": "色彩氛围",
    "other": "其他",
}

LABEL_BY_TEXT = {
    "hair color": "发型发色",
    "hair": "发型发色",
    "clothes": "服装",
    "clothing": "服装",
    "outfit": "服装",
    "scene": "场景地点",
    "location": "场景地点",
    "background": "场景地点",
    "lighting": "时间光线",
    "time": "时间光线",
    "pose": "姿势动作",
    "camera": "镜头景别",
    "shot": "镜头景别",
    "angle": "镜头角度",
    "expression": "表情气质",
    "mood": "表情气质",
}


def normalize_edit_items(value: Any) -> list[dict[str, Any]]:
    values = value if isinstance(value, list) else ([value] if value else [])
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue
        item_id = clean_identifier(item.get("id") or item.get("key") or f"item_{index}")
        label = chinese_label(item_id, item)
        original = clean_text(item.get("original_cn") or item.get("current_cn") or item.get("original") or item.get("current") or item.get("value"))
        placeholder = clean_text(item.get("placeholder_cn") or item.get("placeholder") or item.get("example") or "")
        if not original:
            continue
        key = item_id or f"{label}:{original}"
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "id": item_id,
            "label": label,
            "original": original,
            "placeholder": placeholder,
            "suggestions": safe_prompt_suggestions(normalize_string_list(item.get("suggestions")))[:5],
        })
    return items


def editable_points_to_edit_items(value: Any) -> list[dict[str, Any]]:
    items = []
    for index, point in enumerate(normalize_point_list(value, with_suggestions=True), start=1):
        original = clean_text(point.get("current"))
        if not original:
            continue
        label = clean_text(point.get("label") or f"可修改项 {index}")
        items.append({
            "id": clean_identifier(label) or f"item_{index}",
            "label": label,
            "original": original,
            "placeholder": "",
            "suggestions": safe_prompt_suggestions(normalize_string_list(point.get("suggestions")))[:5],
        })
    return items


def build_edit_instruction(edits: list[dict[str, Any]] | None = None, extra_instruction: str = "") -> str:
    lines = []
    for item in edits or []:
        if not isinstance(item, dict):
            continue
        value = clean_text(item.get("value") or item.get("new_value") or item.get("target"))
        if not value:
            continue
        label = clean_text(item.get("label") or "局部项目")
        original = clean_text(item.get("original") or item.get("current") or "原值")
        lines.append(f"{label}：{original} -> {value}")
    extra = clean_text(extra_instruction)
    if extra:
        lines.append(f"其他补充：{extra}")
    return "\n".join(lines)


def chinese_label(item_id: str, item: dict[str, Any]) -> str:
    explicit = clean_text(item.get("label_cn"))
    if explicit:
        return explicit
    if item_id in LABEL_BY_ID:
        return LABEL_BY_ID[item_id]
    label = clean_text(item.get("label") or item.get("name"))
    if contains_cjk(label):
        return label
    mapped = LABEL_BY_TEXT.get(label.lower())
    return mapped or label or LABEL_BY_ID.get(item_id, "可修改项")


def clean_identifier(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", text).strip("_-")
    return text[:40]


def contains_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


UNSAFE_PROMPT_SUGGESTION_REPLACEMENTS = {
    "东亚少女": "20岁左右东亚成年女性",
    "少女": "年轻成年女性",
    "学生妹": "清爽校园感成年女性",
    "女高中生": "清爽校园感成年女性",
    "高中生": "校园感成年女性",
    "萝莉": "清爽成年女性",
    "未成年": "成年女性",
}


def safe_prompt_suggestions(values: list[str]) -> list[str]:
    safe: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text:
            continue
        for bad, replacement in UNSAFE_PROMPT_SUGGESTION_REPLACEMENTS.items():
            text = text.replace(bad, replacement)
        if text and text not in safe:
            safe.append(text)
    return safe


def clean_text(value: Any) -> str:
    return str(value or "").strip()
