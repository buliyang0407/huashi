from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .prompt_agent import call_model_text, extract_json_object
from .prompt_ai import PromptAIError, get_prompt_model
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

SLOT_BY_FOLDER = {
    "01_发型": "appearance",
    "02_发饰": "appearance",
    "03_服饰": "clothing",
    "04_表情": "appearance",
    "05_肢体动作姿态": "pose",
    "06_镜头语言": "camera",
    "07_光影": "lighting",
    "08_人物气质身份": "subject",
    "09_场景空间": "scene",
    "10_环境细节道具": "scene",
    "11_画感摄影": "image_feel",
}

DISPLAY_CATEGORY_BY_FOLDER = {
    "08_人物气质身份": "01_人物",
    "01_发型": "02_发型",
    "03_服饰": "03_服饰",
    "05_肢体动作姿态": "04_姿势",
    "09_场景空间": "05_场景",
    "06_镜头语言": "06_镜头",
    "07_光影": "07_光线",
    "04_表情": "08_表情",
    "02_发饰": "09_细节",
    "10_环境细节道具": "09_细节",
}

CATEGORY_ITEM_PRIORITY = {
    "01_人物": ["日韩", "清爽", "自然", "日常", "通勤", "刚入职", "温柔", "休息", "日系", "都市", "轻熟", "文艺", "清冷", "画廊", "古典", "度假"],
    "02_发型": ["黑长直", "长发", "自然", "中长", "锁骨", "及肩", "马尾", "丸子", "盘发", "波波", "短发", "编发", "挑染", "湿发"],
    "03_服饰": ["衬衫", "针织", "连衣裙", "长裙", "西装", "套装", "礼服", "缎面", "真丝", "薄纱", "汉服", "旗袍", "泳", "浴"],
    "04_姿势": ["站", "坐", "回眸", "侧身", "整理", "抬手", "行走", "倚", "躺", "背影"],
    "05_场景": ["白墙", "窗边", "卧室", "客厅", "街", "咖啡", "公园", "酒店", "民宿", "海", "画廊", "天台", "雨"],
    "06_镜头": ["半身", "中景", "全身", "全景", "室内", "房间", "俯拍", "远景", "远拍", "门口", "角落", "床边", "窗边", "走廊", "镜前", "低机位", "近景", "特写", "平视", "三分", "留白", "50mm", "85mm", "35mm", "自拍", "仰拍"],
    "07_光线": ["自然光", "窗光", "柔光", "侧光", "逆光", "晨光", "黄昏", "夜", "伦勃朗", "硬光"],
    "08_表情": ["元气", "微笑", "笑", "自然", "温柔", "平静", "清冷", "回眸", "垂眸", "低头", "闭眼", "慵懒", "神秘", "忧郁", "悲伤", "凶"],
    "09_细节": ["发夹", "发卡", "发带", "丝巾", "珍珠", "花", "簪", "帽", "白墙", "窗帘", "床品", "木地板", "咖啡", "台灯", "花束", "木椅", "水汽", "玻璃", "地面"],
}

SLOT_LABELS = {
    "subject": "人物",
    "appearance": "发型表情",
    "clothing": "服饰",
    "pose": "姿势",
    "scene": "场景",
    "camera": "镜头",
    "lighting": "光线",
    "image_feel": "画感质感",
    "negative": "负面约束",
    "uncategorized": "未归类素材",
}

SLOT_ALIASES = {
    "人物设定": "subject",
    "外貌发型": "appearance",
    "服装材质": "clothing",
    "姿势动作": "pose",
    "场景时间": "scene",
    "镜头构图": "camera",
    "光影": "lighting",
}


PORTRAIT_SYSTEM_PROMPT = """你是画室的人像提示词导演，专门帮助中文用户把素材选择组合成高端人像生图提示词。

请严格输出 JSON，不要 Markdown，不要解释 JSON 之外的内容。

输出字段：
{
  "prompt_cn": "完整中文提示词，方便用户检查和继续修改",
  "prompt_en": "完整英文生图提示词，可直接用于 AI 生图",
  "negative_prompt": "英文负面提示词，简洁但覆盖手指、肢体、塑料皮肤、文字水印等",
  "safety_note_cn": "一句中文说明你如何使用审核友好的人像/商业摄影表达",
  "next_steps_cn": ["3 到 5 个下一步修改方向，中文短句"]
}

写作原则：
1. 明确成年人物，使用成熟、自然、商业人像、时尚摄影、电影感摄影语言。
2. 避免欲望化、挑逗化、低俗化表达；避免孤立强调身体部位。
3. 服装写剪裁、材质、垂坠、层次、合身度；不要写暴露诱导。
4. 姿势写自然动作、身体方向、视线、手部动作、情绪动作。
5. 光线必须有方向，说明它如何影响脸部、发丝、肩颈、服装和背景。
6. 镜头构图要服务人像重点，包含景别、角度、浅景深、画幅或画面重心。
7. 不要堆关键词，要把人物、服装、场景、光线、镜头、画感写成互相支撑的一张照片。"""


MATERIAL_DRAFT_SYSTEM_PROMPT = """你是画室的人像素材卡片策划师，负责给中文用户扩展可点选的人像提示词素材卡。

请严格输出 JSON，不要 Markdown，不要解释 JSON 之外的内容。

输出字段：
{
  "cards": [
    {
      "category": "人物 / 场景 / 环境细节 / 时间天气 / 情绪气质 / 画面风格",
      "title_cn": "中文卡片标题，短而具体",
      "title_en": "英文关键词标题，适合作为图片文件英文名",
      "prompt_hint_cn": "中文提示词片段，可直接融入人像提示词",
      "prompt_hint_en": "英文提示词片段，可直接融入英文生图提示词",
      "risk_level": "low / medium / high",
      "safety_note_cn": "一句中文说明如何用审核友好的摄影语言表达"
    }
  ]
}

规则：
1. 所有卡片默认服务成年人物、商业人像、时尚摄影、情绪写真。
2. 不要写低俗、挑逗、未成年、偷拍、强迫、色情化表达。
3. 人物卡写身份气质、年龄感、五官轮廓、自然真实感，不写网红脸和低俗身材凝视。
4. 场景卡写空间、时间、背景元素和构图作用。
5. 环境细节卡写窗帘、床品、镜子、花束、灯、玻璃、水汽、木椅、墙面、地板、道具等可入画元素。
6. 风险标签要保守：普通商业摄影为 low，浴室/湿发/贴身剪裁/强身体聚焦为 medium，明显低俗或审核不友好为 high，并尽量避免生成 high。
7. 每张卡的 prompt_hint_cn 和 prompt_hint_en 都要短，像素材片段，不要写成完整大提示词。"""


class PortraitStudio:
    def __init__(self, material_root: Path | str):
        self.material_root = Path(material_root)

    def list_materials(
        self,
        slot: str = "",
        category: str = "",
        query: str = "",
        offset: int = 0,
        limit: int = 80,
    ) -> dict[str, Any]:
        items = self.scan_materials()
        query = query.strip().lower()
        if slot:
            slot_id = slot_id_from_value(slot)
            items = [item for item in items if item["slot_id"] == slot_id or item["slot"] == slot]
        if category:
            items = [item for item in items if item["category"] == category]
        if query:
            items = [
                item for item in items
                if query in f"{item['title_cn']} {item['title_en']} {item['category']}".lower()
            ]
        safe_offset = max(0, int(offset or 0))
        safe_limit = max(1, min(int(limit or 80), 160))
        sliced = items[safe_offset:safe_offset + safe_limit]
        return {
            "items": sliced,
            "total": len(items),
            "offset": safe_offset,
            "limit": safe_limit,
            "next_offset": safe_offset + safe_limit if safe_offset + safe_limit < len(items) else None,
            "categories": self.categories(),
            "available": self.material_root.exists() and self.material_root.is_dir(),
            "root": str(self.material_root),
        }

    def scan_materials(self) -> list[dict[str, Any]]:
        if not self.material_root.exists() or not self.material_root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(self.material_root.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            try:
                rel = path.resolve().relative_to(self.material_root.resolve()).as_posix()
            except ValueError:
                continue
            raw_category = rel.split("/", 1)[0] if "/" in rel else ""
            category = display_category(raw_category)
            slot_id = SLOT_BY_FOLDER.get(raw_category, "uncategorized")
            title_cn, title_en = split_material_name(path.stem)
            metadata = material_metadata(path)
            title_cn = clean_text(metadata.get("title_cn")) or title_cn
            title_en = clean_text(metadata.get("title_en")) or title_en
            item_id = material_id(rel)
            prompt_hint_cn = clean_text(metadata.get("prompt_hint_cn")) or title_cn
            prompt_hint_en = clean_text(metadata.get("prompt_hint_en")) or title_en or title_cn
            items.append(
                {
                    "id": item_id,
                    "category": category,
                    "raw_category": raw_category,
                    "title_cn": title_cn,
                    "title_en": title_en,
                    "slot_id": slot_id,
                    "slot": SLOT_LABELS.get(slot_id, "未归类素材"),
                    "tags": material_tags(title_cn, title_en, raw_category, category, prompt_hint_cn, prompt_hint_en),
                    "risk_level": normalize_risk_level(metadata.get("risk_level")) if metadata else material_risk(title_cn),
                    "prompt_hint_cn": prompt_hint_cn,
                    "prompt_hint_en": prompt_hint_en,
                    "safety_note_cn": clean_text(metadata.get("safety_note_cn")),
                    "image_url": f"/api/portrait/material-image/{quote(item_id)}",
                    "rel_path": rel,
                }
            )
        return sorted(items, key=material_sort_key)

    def categories(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in self.scan_materials():
            counts[item["category"]] = counts.get(item["category"], 0) + 1
        return [{"name": key, "count": counts[key]} for key in sorted(counts, key=category_sort_key)]

    def resolve_material_image(self, item_id: str) -> Path:
        for item in self.scan_materials():
            if item["id"] == item_id:
                target = (self.material_root / item["rel_path"]).resolve()
                root = self.material_root.resolve()
                if target != root and root in target.parents and target.is_file():
                    return target
        raise ValueError("素材图片不存在")

    def generate_prompt(
        self,
        selected: dict[str, list[dict[str, Any]]],
        manual: dict[str, str],
        base_prompt: str = "",
        model_id: str = "",
    ) -> dict[str, Any]:
        if not any(selected.values()) and not any(str(value or "").strip() for value in manual.values()) and not base_prompt.strip():
            raise PromptAIError("请先选择素材或输入想法")
        model = get_prompt_model(model_id)
        messages = build_portrait_messages(selected, manual, base_prompt=base_prompt)
        text = call_model_text(model, messages, temperature=0.62, max_tokens=3200)
        result = normalize_generation_result(text)
        return {**result, "model": model.id}

    def generate_material_drafts(
        self,
        category: str,
        idea: str = "",
        count: int = 8,
        model_id: str = "",
    ) -> dict[str, Any]:
        model = get_prompt_model(model_id)
        messages = build_material_draft_messages(category, idea, count=count)
        text = call_model_text(model, messages, temperature=0.72, max_tokens=2200)
        return {"cards": normalize_material_drafts(text), "model": model.id}


def portrait_slot_definitions() -> list[dict[str, Any]]:
    return [
        slot("subject", "人物", 1, "成年女性、气质、角色或身份"),
        slot("appearance", "发型表情", 3, "发型、发色、表情、面部气质"),
        slot("clothing", "服饰", 4, "服装类型、剪裁、面料、配饰"),
        slot("pose", "姿势", 3, "身体方向、手部动作、视线和情绪动作"),
        slot("scene", "场景", 2, "地点、时间、天气和空间氛围", conflicts=[conflict("day_night", ["白天", "夜晚", "黄昏"])]),
        slot("camera", "镜头", 4, "景别、角度、焦段、构图", conflicts=[conflict("close_full_body", ["特写", "全身"])]),
        slot("lighting", "光线", 3, "主光、逆光、轮廓光、色温", conflicts=[conflict("hard_soft_light", ["硬光", "柔光"])]),
        slot("image_feel", "画感质感", 3, "真实摄影、电影感、胶片感、肤质"),
        slot("negative", "负面约束", 0, "系统自动生成，可在结果里复制后再修改"),
    ]


def slot(slot_id: str, label: str, limit: int, helper: str, conflicts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": slot_id, "label": label, "limit": limit, "helper": helper, "conflicts": conflicts or []}


def conflict(rule_id: str, keywords: list[str]) -> dict[str, Any]:
    return {"id": rule_id, "keywords": keywords}


def build_portrait_messages(
    selected: dict[str, list[dict[str, Any]]],
    manual: dict[str, str],
    base_prompt: str = "",
) -> list[dict[str, str]]:
    slot_lines = []
    definitions = {item["id"]: item["label"] for item in portrait_slot_definitions()}
    for slot_id, items in selected.items():
        phrases = []
        for item in items or []:
            phrases.append(str(item.get("prompt_hint_cn") or item.get("title_cn") or "").strip())
        note = str((manual or {}).get(slot_id) or "").strip()
        if note:
            phrases.append(note)
        if phrases:
            slot_lines.append(f"{definitions.get(slot_id, slot_id)}：{'、'.join(phrase for phrase in phrases if phrase)}")
    for slot_id, note_value in (manual or {}).items():
        if slot_id == "global" or slot_id in selected:
            continue
        note = str(note_value or "").strip()
        if note:
            slot_lines.append(f"{manual_label(slot_id, definitions)}：{note}")
    global_note = str((manual or {}).get("global") or "").strip()
    if global_note:
        slot_lines.append(f"整体想法：{global_note}")
    base_prompt = base_prompt.strip()
    if base_prompt:
        slot_lines.append(
            "\n".join(
                [
                    "成熟参考提示词：",
                    base_prompt,
                    "融合规则：保留参考提示词里成熟的摄影结构、画质词、镜头和光影优点；融合素材选择和补充想法；冲突时以用户新选择为准。",
                ]
            )
        )
    content = "\n".join(slot_lines)
    return [
        {"role": "system", "content": PORTRAIT_SYSTEM_PROMPT},
        {"role": "user", "content": f"请基于这些素材和想法生成一条高完成度人像提示词：\n{content}"},
    ]


def manual_label(key: str, definitions: dict[str, str]) -> str:
    if key.startswith("step:"):
        return clean_text(key.split(":", 1)[1]) or "手写补充"
    if key.startswith("category:"):
        return clean_text(key.split(":", 1)[1]).replace("_", "：")
    return definitions.get(key, key)


def normalize_generation_result(text: str) -> dict[str, Any]:
    try:
        data = extract_json_object(text)
    except PromptAIError:
        data = json.loads(strip_json_fence(text))
    result = {
        "prompt_cn": clean_text(data.get("prompt_cn") or data.get("中文提示词")),
        "prompt_en": clean_text(data.get("prompt_en") or data.get("英文生图提示词") or data.get("prompt")),
        "negative_prompt": clean_text(data.get("negative_prompt") or data.get("负面提示词")),
        "safety_note_cn": clean_text(data.get("safety_note_cn") or data.get("审核友好说明")),
        "next_steps_cn": normalize_text_list(data.get("next_steps_cn") or data.get("下一步修改方向")),
    }
    if not result["prompt_cn"] or not result["prompt_en"]:
        raise PromptAIError("模型没有返回完整的人像提示词")
    if not result["negative_prompt"]:
        result["negative_prompt"] = "text, watermark, logo, bad anatomy, extra fingers, deformed hands, plastic skin, waxy face"
    if not result["next_steps_cn"]:
        result["next_steps_cn"] = ["拉远或拉近镜头", "调整光线冷暖", "加强商业杂志感"]
    return result


def build_material_draft_messages(category: str, idea: str = "", count: int = 8) -> list[dict[str, str]]:
    category = clean_text(category) or "人物"
    idea = clean_text(idea) or "高端真实人像素材"
    count = max(1, min(int(count or 8), 12))
    return [
        {"role": "system", "content": MATERIAL_DRAFT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n".join(
                [
                    f"请生成 {count} 张候选素材卡片。",
                    f"一级目录：{category}",
                    f"主题想法：{idea}",
                    "输出要覆盖可选素材，而不是完整生图提示词。",
                    "必须包含 category、title_cn、title_en、prompt_hint_cn、prompt_hint_en、risk_level、safety_note_cn。",
                ]
            ),
        },
    ]


def normalize_material_drafts(text: str) -> list[dict[str, Any]]:
    try:
        data = extract_json_object(text)
    except PromptAIError:
        data = json.loads(strip_json_fence(text))
    raw_cards = data.get("cards") if isinstance(data, dict) else []
    if not isinstance(raw_cards, list):
        raise PromptAIError("模型没有返回素材卡片列表")
    cards = []
    for raw in raw_cards:
        if not isinstance(raw, dict):
            continue
        card = {
            "category": clean_text(raw.get("category")) or "人物",
            "title_cn": clean_text(raw.get("title_cn") or raw.get("title")),
            "title_en": clean_text(raw.get("title_en") or raw.get("keyword_en")),
            "prompt_hint_cn": clean_text(raw.get("prompt_hint_cn") or raw.get("hint_cn")),
            "prompt_hint_en": clean_text(raw.get("prompt_hint_en") or raw.get("hint_en")),
            "risk_level": normalize_risk_level(raw.get("risk_level")),
            "safety_note_cn": clean_text(raw.get("safety_note_cn") or raw.get("safety_note")),
        }
        if not card["title_cn"] or not card["prompt_hint_cn"] or not card["prompt_hint_en"]:
            continue
        if not card["title_en"]:
            card["title_en"] = card["title_cn"]
        if not card["safety_note_cn"]:
            card["safety_note_cn"] = "使用成熟商业人像和摄影语言表达。"
        cards.append(card)
    if not cards:
        raise PromptAIError("模型没有返回有效素材卡片")
    return cards


def normalize_risk_level(value: Any) -> str:
    text = clean_text(value).lower()
    if text in {"low", "medium", "high"}:
        return text
    if text in {"低", "低风险"}:
        return "low"
    if text in {"中", "中风险"}:
        return "medium"
    if text in {"高", "高风险"}:
        return "high"
    return "low"


def split_material_name(stem: str) -> tuple[str, str]:
    parts = re.split(r"\s+_\s+|\s+-\s+", stem, maxsplit=1)
    title_cn = clean_text(parts[0])
    title_en = clean_text(parts[1]) if len(parts) > 1 else ""
    return title_cn, title_en


def material_metadata(image_path: Path) -> dict[str, Any]:
    sidecar = image_path.with_suffix(".json")
    if not sidecar.is_file():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def material_id(rel_path: str) -> str:
    return hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:16]


def display_category(raw_category: str) -> str:
    return DISPLAY_CATEGORY_BY_FOLDER.get(raw_category, raw_category)


def category_sort_key(category: str) -> tuple[int, str]:
    match = re.match(r"^(\d+)_", category or "")
    order = int(match.group(1)) if match else 99
    return order, category


def material_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    category = str(item.get("category") or "")
    raw_category = str(item.get("raw_category") or "")
    title = f"{item.get('title_cn') or ''} {item.get('title_en') or ''}"
    category_order = category_sort_key(category)[0]
    raw_order = category_sort_key(display_category(raw_category))[0]
    if category == "09_细节":
        raw_order = 0 if raw_category == "02_发饰" else 1
    return category_order, raw_order, keyword_priority(category, title), title.lower()


def keyword_priority(category: str, text: str) -> int:
    for index, keyword in enumerate(CATEGORY_ITEM_PRIORITY.get(category, [])):
        if keyword.lower() in text.lower():
            return index
    return 999


def material_tags(
    title_cn: str,
    title_en: str,
    raw_category: str,
    category: str,
    prompt_hint_cn: str = "",
    prompt_hint_en: str = "",
) -> list[str]:
    text = f"{title_cn} {title_en} {prompt_hint_cn} {prompt_hint_en}".lower()
    tags = []
    for keyword, tag in [
        ("夜", "夜晚"),
        ("月", "夜晚"),
        ("窗", "窗边"),
        ("侧", "侧面"),
        ("背", "背面"),
        ("全身", "全身"),
        ("特写", "特写"),
        ("satin", "缎面"),
        ("dress", "裙装"),
    ]:
        if keyword.lower() in text:
            tags.append(tag)
    for item in [category, raw_category]:
        if item:
            tags.append(item)
    return list(dict.fromkeys(tags))


def material_risk(title_cn: str) -> str:
    if any(word in title_cn for word in ["泳", "浴", "湿", "低背", "露"]):
        return "medium"
    return "low"


def slot_id_from_value(value: str) -> str:
    if value in SLOT_ALIASES:
        return SLOT_ALIASES[value]
    for slot_id, label in SLOT_LABELS.items():
        if value == slot_id or value == label:
            return slot_id
    return value


def strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def normalize_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean_text(item) for item in value if clean_text(item)]
    text = clean_text(value)
    return [text] if text else []


def clean_text(value: Any) -> str:
    return str(value or "").strip()
