"""Code-maintained RunPod apps. Endpoint credentials stay in environment variables."""

import copy
import json
from pathlib import Path


SAMPLERS = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde"]
SCHEDULERS = ["beta", "simple", "normal", "karras"]


def sampling_inputs(default_scheduler: str) -> list[dict]:
    return [
        {"id": "sampler", "nodeId": "459:458", "fieldName": "sampler_name", "type": "select", "label": "采样器", "required": True, "defaultValue": "euler", "options": list(SAMPLERS)},
        {"id": "scheduler", "nodeId": "459:458", "fieldName": "scheduler", "type": "select", "label": "调度器", "required": True, "defaultValue": default_scheduler, "options": list(SCHEDULERS)},
    ]


WORKFLOWS = {
    "qwen21-two-image-edit": {
        "endpoint_env": "RUNPOD_QWEN_ENDPOINT_ID",
        "workflow_path": Path(__file__).resolve().parent / "workflows" / "qwen21-two-image-edit.json",
        "max_input_edge": 2048,
    },
    "qwen21-text-to-image": {
        "endpoint_env": "RUNPOD_QWEN_ENDPOINT_ID",
        "workflow_path": Path(__file__).resolve().parent / "workflows" / "qwen21-text-to-image.json",
        "random_seed_on_empty": True,
    },
    "qwen21-single-image-edit": {
        "endpoint_env": "RUNPOD_QWEN_ENDPOINT_ID",
        "workflow_path": Path(__file__).resolve().parent / "workflows" / "qwen21-single-image-edit.json",
        "max_input_edge": 2048,
        "random_seed_on_empty": True,
    },
}

RUNPOD_APPS = [
    {
        "id": "runpod-qwen21-single-image-edit",
        "name": "Qwen Image 2.1 单图编辑",
        "description": "上传一张图片直接编辑。默认跟随输入图尺寸，大图使用最长边 2048 的推理副本。",
        "provider": "runpod",
        "workflow_key": "qwen21-single-image-edit",
        "webapp_id": "",
        "node_id": "",
        "field_name": "",
        "input_type": "image",
        "output_type": "png",
        "auto_unzip": False,
        "category": "图像编辑",
        "favorite": False,
        "accent": "#5b638f",
        "sort_order": 120,
        "enabled": True,
        "inputs": [
            {"id": "image1", "nodeId": "470", "fieldName": "image", "type": "image", "label": "图片", "required": True},
            {"id": "prompt", "nodeId": "459:474", "fieldName": "prompt", "type": "textarea", "label": "编辑提示词", "required": True, "role": "prompt"},
            {"id": "canvas", "nodeId": "459:468", "fieldName": "switch", "type": "select", "label": "尺寸来源", "required": True, "defaultValue": "跟随原图", "options": ["跟随原图", "自定义尺寸"], "valueMap": {"跟随原图": False, "自定义尺寸": True, "reference": False, "custom": True}},
            {"id": "width", "nodeId": "459:456", "fieldName": "width", "type": "number", "label": "宽度（仅自定义尺寸）", "required": True, "defaultValue": "1024"},
            {"id": "height", "nodeId": "459:456", "fieldName": "height", "type": "number", "label": "高度（仅自定义尺寸）", "required": True, "defaultValue": "1024"},
            {"id": "steps", "nodeId": "459:458", "fieldName": "steps", "type": "number", "label": "步数", "required": True, "defaultValue": "30"},
            {"id": "seed", "nodeId": "459:458", "fieldName": "seed", "type": "number", "label": "随机种子（留空随机）", "required": False, "defaultValue": ""},
            *sampling_inputs("beta"),
        ],
    },
    {
        "id": "runpod-qwen21-text-to-image",
        "name": "Qwen Image 2.1 文生图",
        "description": "直接用提示词生成图片，无需上传参考图。",
        "provider": "runpod",
        "workflow_key": "qwen21-text-to-image",
        "webapp_id": "",
        "node_id": "",
        "field_name": "",
        "input_type": "text",
        "output_type": "png",
        "auto_unzip": False,
        "category": "文生图",
        "favorite": False,
        "accent": "#5b638f",
        "sort_order": 110,
        "enabled": True,
        "inputs": [
            {"id": "prompt", "nodeId": "459:452", "fieldName": "prompt", "type": "textarea", "label": "提示词", "required": True, "role": "prompt"},
            {"id": "width", "nodeId": "459:456", "fieldName": "width", "type": "number", "label": "宽度", "required": True, "defaultValue": "1024"},
            {"id": "height", "nodeId": "459:456", "fieldName": "height", "type": "number", "label": "高度", "required": True, "defaultValue": "1024"},
            {"id": "steps", "nodeId": "459:458", "fieldName": "steps", "type": "number", "label": "步数", "required": True, "defaultValue": "25"},
            {"id": "seed", "nodeId": "459:458", "fieldName": "seed", "type": "number", "label": "随机种子（留空随机）", "required": False, "defaultValue": ""},
            *sampling_inputs("simple"),
        ],
    },
    {
        "id": "runpod-qwen21-two-image-edit",
        "name": "Qwen Image 2.1 双图编辑",
        "description": "上传两张图片，用提示词描述如何组合或修改。",
        "provider": "runpod",
        "workflow_key": "qwen21-two-image-edit",
        "webapp_id": "",
        "node_id": "",
        "field_name": "",
        "input_type": "image",
        "output_type": "png",
        "auto_unzip": False,
        "category": "图像编辑",
        "favorite": False,
        "accent": "#5b638f",
        "sort_order": 100,
        "enabled": True,
        "inputs": [
            {"id": "image1", "nodeId": "470", "fieldName": "image", "type": "image", "label": "图片 1", "required": True},
            {"id": "image2", "nodeId": "475", "fieldName": "image", "type": "image", "label": "图片 2", "required": True},
            {"id": "prompt", "nodeId": "459:474", "fieldName": "prompt", "type": "textarea", "label": "编辑提示词", "required": True, "role": "prompt"},
            {"id": "width", "nodeId": "459:456", "fieldName": "width", "type": "number", "label": "宽度", "required": True, "defaultValue": "1024"},
            {"id": "height", "nodeId": "459:456", "fieldName": "height", "type": "number", "label": "高度", "required": True, "defaultValue": "1024"},
            {"id": "steps", "nodeId": "459:458", "fieldName": "steps", "type": "number", "label": "步数", "required": True, "defaultValue": "25"},
            {"id": "seed", "nodeId": "459:458", "fieldName": "seed", "type": "number", "label": "随机种子", "required": True, "defaultValue": "42"},
            {"id": "canvas", "nodeId": "459:468", "fieldName": "switch", "type": "select", "label": "画布尺寸来源", "required": True, "defaultValue": "自定义尺寸", "options": ["自定义尺寸", "参考图尺寸"], "valueMap": {"自定义尺寸": True, "参考图尺寸": False, "custom": True, "reference": False}},
            *sampling_inputs("beta"),
        ],
    },
]

# Retain legacy IDs and graphs for historical task lookup; remove their creation entries.
for _legacy_app in RUNPOD_APPS:
    _legacy_app["enabled"] = False

WORKFLOWS["noctq-v4-text-to-image"] = {
    "endpoint_env": "RUNPOD_QWEN_ENDPOINT_ID",
    "workflow_path": Path(__file__).resolve().parent / "workflows" / "noctq-v4-text-to-image.json",
    "random_seed_on_empty": True,
    "validate_on_create": True,
}

RUNPOD_APPS.append(
{'id': 'runpod-noctq-v4-text-to-image',
 'name': 'NoctQ V4 文生图',
 'description': '使用自己的 NoctQ V4 模型生成图片；可调正负提示词、输出尺寸、CFG 和采样参数，不使用 LoRA。',
 'provider': 'runpod',
 'workflow_key': 'noctq-v4-text-to-image',
 'webapp_id': '',
 'node_id': '',
 'field_name': '',
 'input_type': 'text',
 'output_type': 'png',
 'auto_unzip': False,
 'category': '文生图',
 'favorite': False,
 'accent': '#5b638f',
 'sort_order': 100,
 'enabled': True,
 'inputs': [{'id': 'prompt',
             'nodeId': '4',
             'fieldName': 'prompt',
             'type': 'textarea',
             'label': '提示词',
             'required': True,
             'defaultValue': '两位25岁左右的亚洲年轻女性坐在一家现代咖啡馆的窗边，进行自然轻松的交谈。\n'
                             '\n'
                             '左边的女性留着黑色齐肩短发，穿米白色针织衫和深蓝色牛仔裤，右手拿着白色陶瓷咖啡杯，左手自然放在桌面上。\n'
                             '\n'
                             '右边的女性留着棕色波浪长发，穿浅灰色西装外套和黑色长裤，双手交叠放在桌面上，微笑着看向左边的朋友。\n'
                             '\n'
                             '两个人拥有明显不同的面部特征、发型和服装，不要出现相似或重复的脸。\n'
                             '\n'
                             '木质咖啡桌上放着一个玻璃花瓶、一小束白色鲜花和一本合上的杂志。\n'
                             '\n'
                             '窗外是阳光明媚的城市街道，背景有轻微虚化的行人和车辆。\n'
                             '\n'
                             '真实生活纪实摄影，35mm镜头，横向构图，两个人都完整出现在画面内。\n'
                             '\n'
                             '自然的手部结构，准确的手指数量，合理的身体比例，真实的目光交流，准确的物体位置与遮挡关系，柔和自然光，真实皮肤和服装纹理。',
             'role': 'prompt'},
            {'id': 'negative_prompt',
             'nodeId': '4',
             'fieldName': 'negative_prompt',
             'type': 'textarea',
             'label': '负向提示词（可清空）',
             'required': False,
             'defaultValue': 'artifacts, gpt-image, washed-out colors, low quality, low resolution, AI slop, '
                             'deviantart, sloppy lines, rough sketch, blurry, indistinct, missing fingers, badly drawn '
                             'hands, wrong number of fingers'},
            {'id': 'width',
             'nodeId': '5',
             'fieldName': 'width',
             'type': 'number',
             'label': '宽度',
             'required': True,
             'defaultValue': '1024'},
            {'id': 'height',
             'nodeId': '5',
             'fieldName': 'height',
             'type': 'number',
             'label': '高度',
             'required': True,
             'defaultValue': '1536'},
            {'id': 'steps',
             'nodeId': '6',
             'fieldName': 'steps',
             'type': 'number',
             'label': '步数',
             'required': True,
             'defaultValue': '25'},
            {'id': 'cfg',
             'nodeId': '6',
             'fieldName': 'cfg',
             'type': 'number',
             'label': 'CFG',
             'required': True,
             'defaultValue': '3'},
            {'id': 'sampler',
             'nodeId': '6',
             'fieldName': 'sampler_name',
             'type': 'select',
             'label': '采样器',
             'required': True,
             'defaultValue': 'euler',
             'options': ['euler', 'euler_ancestral', 'dpmpp_2m', 'dpmpp_2m_sde']},
            {'id': 'scheduler',
             'nodeId': '6',
             'fieldName': 'scheduler',
             'type': 'select',
             'label': '调度器',
             'required': True,
             'defaultValue': 'simple',
             'options': ['beta', 'simple', 'normal', 'karras']},
            {'id': 'denoise',
             'nodeId': '6',
             'fieldName': 'denoise',
             'type': 'number',
             'label': '降噪强度',
             'required': True,
             'defaultValue': '1'},
            {'id': 'seed',
             'nodeId': '6',
             'fieldName': 'seed',
             'type': 'number',
             'label': '种子（清空随机）',
             'required': False,
             'defaultValue': '483841873673111'},
            {'id': 'batch_size',
             'nodeId': '5',
             'fieldName': 'batch_size',
             'type': 'number',
             'label': '每批图片数量（1–4）',
             'required': True,
             'defaultValue': '1'},
            {'id': 'resolution',
             'nodeId': '4',
             'fieldName': 'resolution',
             'type': 'number',
             'label': '编码分辨率（独立于输出宽高）',
             'required': True,
             'defaultValue': '1024'}]}
)


# One LoRA per generation. Add exact ComfyUI relative filenames to the catalog,
# then restart Huashi to register the updated dropdown without changing the graph.
WORKFLOWS["noctq-v4-lora-text-to-image"] = {
    **WORKFLOWS["noctq-v4-text-to-image"],
    "workflow_path": Path(__file__).resolve().parent / "workflows" / "noctq-v4-lora-text-to-image.json",
}
_lora_graph = json.loads(WORKFLOWS["noctq-v4-lora-text-to-image"]["workflow_path"].read_text(encoding="utf-8"))
_lora_names = json.loads((Path(__file__).resolve().parent / "workflows" / "noctq-v4-loras.json").read_text(encoding="utf-8"))["loras"]
if not _lora_names or any(not isinstance(name, str) or not name.strip() for name in _lora_names) or len(set(_lora_names)) != len(_lora_names):
    raise ValueError("NoctQ LoRA 清单必须包含不重复的文件名")
if _lora_graph["11"]["inputs"]["lora_name"] not in _lora_names:
    raise ValueError("NoctQ LoRA 清单缺少工作流默认文件")
_lora_app = copy.deepcopy(next(app for app in RUNPOD_APPS if app["id"] == "runpod-noctq-v4-text-to-image"))
_lora_app.update(
    id="runpod-noctq-v4-lora-text-to-image",
    name="NoctQ V4 文生图 · LoRA",
    description="选择一个 LoRA 并调整权重；保留正负提示词、分辨率、CFG 和全部采样参数。",
    workflow_key="noctq-v4-lora-text-to-image",
    sort_order=101,
)
for _input in _lora_app["inputs"]:
    _input["defaultValue"] = str(_lora_graph[_input["nodeId"]]["inputs"][_input["fieldName"]])
_lora_app["inputs"][2:2] = [
    {"id": "lora_name", "nodeId": "11", "fieldName": "lora_name", "type": "select", "label": "LoRA", "required": True,
     "defaultValue": _lora_graph["11"]["inputs"]["lora_name"], "options": _lora_names},
    {"id": "lora_strength", "nodeId": "11", "fieldName": "strength_model", "type": "number", "label": "LoRA 权重（支持小数）", "required": True,
     "defaultValue": str(_lora_graph["11"]["inputs"]["strength_model"])},
]
RUNPOD_APPS.append(_lora_app)

WORKFLOWS["noctq-v4-single-image-edit"] = {
    "endpoint_env": "RUNPOD_QWEN_ENDPOINT_ID",
    "workflow_path": Path(__file__).resolve().parent / "workflows" / "noctq-v4-single-image-edit.json",
    "max_input_edge": 2048,
    "random_seed_on_empty": True,
    "validate_on_create": True,
}
_edit_graph = json.loads(WORKFLOWS["noctq-v4-single-image-edit"]["workflow_path"].read_text(encoding="utf-8"))
_edit_app = copy.deepcopy(next(app for app in RUNPOD_APPS if app["id"] == "runpod-noctq-v4-text-to-image"))
_edit_app.update(
    id="runpod-noctq-v4-single-image-edit",
    name="NoctQ V4 单图编辑",
    description="上传图片或从陈列室选择图片，用提示词编辑；保留图片比例，按编码分辨率调整尺寸。0 保留推理图尺寸并对齐到32倍数；大图先使用最长边2048的副本，原图保留。不使用LoRA。",
    workflow_key="noctq-v4-single-image-edit",
    input_type="image", category="图像编辑", sort_order=102,
)
_edit_app["inputs"] = [item for item in _edit_app["inputs"] if item["id"] not in {"width", "height", "batch_size"}]
for _input in _edit_app["inputs"]:
    _input["defaultValue"] = str(_edit_graph[_input["nodeId"]]["inputs"][_input["fieldName"]])
    if _input["id"] == "prompt":
        _input["label"] = "编辑提示词"
    elif _input["id"] == "resolution":
        _input["label"] = "编码分辨率（0保留推理图尺寸）"
_edit_app["inputs"].insert(0, {"id": "image1", "nodeId": "12", "fieldName": "image", "type": "image", "label": "原图", "required": True})
RUNPOD_APPS.append(_edit_app)

WORKFLOWS["noctq-v4-lora-single-image-edit"] = {
    **WORKFLOWS["noctq-v4-single-image-edit"],
    "workflow_path": Path(__file__).resolve().parent / "workflows" / "noctq-v4-lora-single-image-edit.json",
}
_edit_lora_graph = json.loads(WORKFLOWS["noctq-v4-lora-single-image-edit"]["workflow_path"].read_text(encoding="utf-8"))
if _edit_lora_graph["11"]["inputs"]["lora_name"] not in _lora_names:
    raise ValueError("NoctQ LoRA 清单缺少单图编辑默认文件")
_edit_lora_app = copy.deepcopy(_edit_app)
_edit_lora_app.update(
    id="runpod-noctq-v4-lora-single-image-edit",
    name="NoctQ V4 单图编辑 · LoRA",
    description="上传图片或从陈列室选择图片，选择LoRA并调整小数权重；按编码分辨率保持图片比例。0保留推理图尺寸并对齐32倍数，大图使用最长边2048的副本，原图保留。",
    workflow_key="noctq-v4-lora-single-image-edit", sort_order=103,
)
for _input in _edit_lora_app["inputs"]:
    if _input["type"] != "image":
        _input["defaultValue"] = str(_edit_lora_graph[_input["nodeId"]]["inputs"][_input["fieldName"]])
_edit_lora_app["inputs"][1:1] = [
    {"id": "lora_name", "nodeId": "11", "fieldName": "lora_name", "type": "select", "label": "LoRA", "required": True,
     "defaultValue": _edit_lora_graph["11"]["inputs"]["lora_name"], "options": list(_lora_names)},
    {"id": "lora_strength", "nodeId": "11", "fieldName": "strength_model", "type": "number", "label": "LoRA 权重（支持小数）", "required": True,
     "defaultValue": str(_edit_lora_graph["11"]["inputs"]["strength_model"])},
]
RUNPOD_APPS.append(_edit_lora_app)

WORKFLOWS["noctq-v4-lora-pose-transfer"] = {
    **WORKFLOWS["noctq-v4-lora-single-image-edit"],
    "workflow_path": Path(__file__).resolve().parent / "workflows" / "noctq-v4-lora-pose-transfer.json",
}
_pose_graph = json.loads(WORKFLOWS["noctq-v4-lora-pose-transfer"]["workflow_path"].read_text(encoding="utf-8"))
if _pose_graph["11"]["inputs"]["lora_name"] not in _lora_names:
    raise ValueError("NoctQ LoRA 清单缺少姿势迁移默认文件")
_pose_app = copy.deepcopy(_edit_lora_app)
_pose_app.update(
    id="runpod-noctq-v4-lora-pose-transfer",
    name="NoctQ V4 姿势迁移 · LoRA",
    description="选择人物原图和姿势参考图，保留人物身份、服装与配饰，按参考图迁移姿势和构图；支持LoRA小数权重。大图使用最长边2048的副本，两张原图保留。",
    workflow_key="noctq-v4-lora-pose-transfer", sort_order=104,
)
for _input in _pose_app["inputs"]:
    if _input["type"] == "image":
        _input["label"] = "人物原图"
    else:
        _input["defaultValue"] = str(_pose_graph[_input["nodeId"]]["inputs"][_input["fieldName"]])
        if _input["id"] == "prompt":
            _input["label"] = "姿势迁移提示词"
_pose_app["inputs"].insert(1, {"id": "image2", "nodeId": "13", "fieldName": "image", "type": "image", "label": "姿势参考图", "required": True})
RUNPOD_APPS.append(_pose_app)
