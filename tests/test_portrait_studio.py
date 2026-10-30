import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huashi.portrait_studio import (
    PortraitStudio,
    build_material_draft_messages,
    build_portrait_messages,
    normalize_material_drafts,
    normalize_generation_result,
    portrait_slot_definitions,
)


class PortraitStudioTest(unittest.TestCase):
    def make_library(self, root: Path) -> Path:
        library = root / "promptscreation"
        samples = {
            "01_发型": ["黑长直 _ Long Straight Black Hair.jpg"],
            "02_发饰": ["珍珠发夹 _ Pearl Hair Clip.jpg"],
            "03_服饰": ["缎面 _ Satin.jpg", "低背长裙 _ Low Back Dress.jpg"],
            "04_表情": ["元气微笑 _ Bright Smile.jpg"],
            "05_肢体动作姿态": ["背影回眸 _ Back View Looking Over Shoulder.jpg"],
            "06_镜头语言": ["全身 _ Full Body Shot.jpg", "特写 _ Close Up.jpg"],
            "07_光影": ["窗边侧光 _ Window Side Light.jpg", "夜景月光 _ Night Moonlight.jpg"],
            "08_人物气质身份": ["清冷电影感女性 _ Cool Cinematic Woman.jpg"],
            "09_场景空间": ["雨夜酒店门廊 _ Rainy Hotel Portico.jpg"],
            "10_环境细节道具": ["雾面玻璃水汽 _ Steamed Glass Detail.jpg"],
        }
        for folder, names in samples.items():
            path = library / folder
            path.mkdir(parents=True)
            for name in names:
                (path / name).write_bytes(b"jpg")
        return library

    def test_material_sidecar_metadata_enriches_prompt_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            item = library / "06_镜头语言" / "室内全景全房间 _ Interior Room Wide Establishing Portrait.jpg"
            item.write_bytes(b"jpg")
            item.with_suffix(".json").write_text(
                __import__("json").dumps(
                    {
                        "title_cn": "室内全景全房间",
                        "title_en": "Interior Room Wide Establishing Portrait",
                        "prompt_hint_cn": "室内全景建立镜头，人物全身与房间布局都清楚可见",
                        "prompt_hint_en": "interior wide establishing portrait, full body and room layout clearly visible",
                        "risk_level": "low",
                        "safety_note_cn": "使用空间构图和商业摄影语言表达。",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            studio = PortraitStudio(library)

            found = next(item for item in studio.list_materials(query="室内全景", limit=40)["items"] if item["title_cn"] == "室内全景全房间")

            self.assertEqual(found["slot_id"], "camera")
            self.assertIn("房间布局", found["prompt_hint_cn"])
            self.assertIn("room layout", found["prompt_hint_en"])
            self.assertEqual(found["risk_level"], "low")
            self.assertIn("商业摄影", found["safety_note_cn"])

    def test_lists_materials_with_chinese_titles_slots_and_safe_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            studio = PortraitStudio(library)

            result = studio.list_materials(slot="服装材质", query="缎面", limit=20)

            self.assertEqual(result["total"], 1)
            item = result["items"][0]
            self.assertEqual(item["title_cn"], "缎面")
            self.assertEqual(item["title_en"], "Satin")
            self.assertEqual(item["slot"], "服饰")
            self.assertTrue(item["image_url"].startswith("/api/portrait/material-image/"))
            self.assertEqual(studio.resolve_material_image(item["id"]).name, "缎面 _ Satin.jpg")

    def test_material_pagination_and_unknown_folder_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            unknown = library / "99_新素材"
            unknown.mkdir()
            (unknown / "白墙房间 _ White Wall Room.jpg").write_bytes(b"jpg")
            studio = PortraitStudio(library)

            first = studio.list_materials(limit=2)
            second = studio.list_materials(offset=2, limit=2)
            uncategorized = studio.list_materials(slot="未归类素材", limit=10)

            self.assertEqual(len(first["items"]), 2)
            self.assertEqual(first["next_offset"], 2)
            self.assertEqual(len(second["items"]), 2)
            self.assertEqual(uncategorized["items"][0]["title_cn"], "白墙房间")

    def test_slot_definitions_limit_mutually_exclusive_choices(self):
        slots = portrait_slot_definitions()
        lens = next(slot for slot in slots if slot["id"] == "camera")

        self.assertEqual(lens["label"], "镜头")
        self.assertEqual(lens["limit"], 4)
        self.assertIn("close_full_body", [rule["id"] for rule in lens["conflicts"]])

    def test_new_portrait_expansion_folders_map_to_existing_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            studio = PortraitStudio(library)
            by_title = {item["title_cn"]: item for item in studio.list_materials(limit=40)["items"]}

            self.assertEqual(by_title["清冷电影感女性"]["slot_id"], "subject")
            self.assertEqual(by_title["雨夜酒店门廊"]["slot_id"], "scene")
            self.assertEqual(by_title["雾面玻璃水汽"]["slot_id"], "scene")

    def test_portrait_categories_use_virtual_order_and_merge_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            studio = PortraitStudio(library)

            result = studio.list_materials(limit=40)
            categories = result["categories"]

            self.assertEqual(
                [item["name"] for item in categories],
                ["01_人物", "02_发型", "03_服饰", "04_姿势", "05_场景", "06_镜头", "07_光线", "08_表情", "09_细节"],
            )
            details = next(item for item in categories if item["name"] == "09_细节")
            self.assertEqual(details["count"], 2)
            by_title = {item["title_cn"]: item for item in result["items"]}
            self.assertEqual(by_title["清冷电影感女性"]["category"], "01_人物")
            self.assertEqual(by_title["背影回眸"]["category"], "04_姿势")
            self.assertEqual(by_title["雨夜酒店门廊"]["category"], "05_场景")
            self.assertEqual(by_title["窗边侧光"]["category"], "07_光线")
            self.assertEqual(by_title["雾面玻璃水汽"]["category"], "09_细节")

    def test_generation_normalizes_model_json(self):
        raw = """
        ```json
        {
          "prompt_cn": "成年女性，窗边自然光人像。",
          "prompt_en": "Ultra-realistic portrait of an adult woman by a window.",
          "negative_prompt": "text, watermark",
          "safety_note_cn": "已使用商业人像语言。",
          "next_steps_cn": ["更电影感", "更商业杂志"]
        }
        ```
        """

        result = normalize_generation_result(raw)

        self.assertEqual(result["prompt_cn"], "成年女性，窗边自然光人像。")
        self.assertIn("adult woman", result["prompt_en"])
        self.assertEqual(result["next_steps_cn"], ["更电影感", "更商业杂志"])

    def test_build_messages_include_selected_materials_manual_notes_template_and_safety_rules(self):
        selected = {
            "appearance": [{"title_cn": "黑长直", "prompt_hint_cn": "黑色自然长直发"}],
            "clothing": [{"title_cn": "缎面", "prompt_hint_cn": "缎面材质"}],
        }
        manual = {"scene": "酒店窗边，夜晚城市灯光", "step:镜头语言 · 景别": "拉远一点，全身", "global": "更清冷高级"}
        base_prompt = "Ultra-realistic editorial fashion portrait, 50mm lens, soft window light."

        messages = build_portrait_messages(selected, manual, base_prompt=base_prompt)
        user_message = messages[-1]["content"]

        self.assertIn("黑色自然长直发", user_message)
        self.assertIn("酒店窗边，夜晚城市灯光", user_message)
        self.assertIn("镜头语言 · 景别：拉远一点，全身", user_message)
        self.assertIn("成熟参考提示词", user_message)
        self.assertIn(base_prompt, user_message)
        self.assertIn("融合素材选择", user_message)
        self.assertIn("避免欲望化", messages[0]["content"])

    def test_generate_prompt_calls_model_and_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            studio = PortraitStudio(library)
            raw = {
                "prompt_cn": "成年女性，黑长直，缎面礼服，窗边侧逆光。",
                "prompt_en": "An adult woman with long straight black hair in a satin dress, side-backlit by a window.",
                "negative_prompt": "text, watermark, bad anatomy",
                "safety_note_cn": "使用成熟商业人像表达。",
                "next_steps_cn": ["拉远到全身", "加强胶片颗粒"],
            }

            with patch("huashi.portrait_studio.call_model_text", return_value=__import__("json").dumps(raw, ensure_ascii=False)):
                result = studio.generate_prompt(
                    selected={"appearance": [{"title_cn": "黑长直", "prompt_hint_cn": "黑色自然长直发"}]},
                    manual={"global": "安静清冷"},
                    base_prompt="commercial portrait",
                    model_id="aihubmix-grok",
                )

            self.assertEqual(result["prompt_cn"], raw["prompt_cn"])
            self.assertEqual(result["model"], "aihubmix-grok")

    def test_material_draft_messages_focus_on_safe_portrait_cards(self):
        messages = build_material_draft_messages("人物", "清冷电影感女性", 4)
        joined = "\n".join(message["content"] for message in messages)

        self.assertIn("候选素材卡片", joined)
        self.assertIn("人物", joined)
        self.assertIn("清冷电影感女性", joined)
        self.assertIn("risk_level", joined)
        self.assertIn("不要写低俗、挑逗", joined)

    def test_material_drafts_normalize_model_json(self):
        raw = """
        {
          "cards": [
            {
              "category": "人物",
              "title_cn": "清冷文艺女性",
              "title_en": "Cool Literary Woman",
              "prompt_hint_cn": "成年女性，清冷文艺气质，自然真实",
              "prompt_hint_en": "adult woman with a cool literary temperament, natural and realistic",
              "risk_level": "low",
              "safety_note_cn": "使用成年商业人像表达"
            },
            {
              "title_cn": "无效缺字段"
            }
          ]
        }
        """

        result = normalize_material_drafts(raw)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["category"], "人物")
        self.assertEqual(result[0]["risk_level"], "low")
        self.assertIn("adult woman", result[0]["prompt_hint_en"])

    def test_generate_material_drafts_calls_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = self.make_library(Path(tmp))
            studio = PortraitStudio(library)
            raw = {
                "cards": [
                    {
                        "category": "场景",
                        "title_cn": "雨后酒店门廊",
                        "title_en": "Rainy Hotel Portico",
                        "prompt_hint_cn": "雨后酒店门廊，地面反光，暖色门厅光",
                        "prompt_hint_en": "rainy hotel portico with reflective pavement and warm lobby light",
                        "risk_level": "low",
                        "safety_note_cn": "偏场景氛围，低风险",
                    }
                ]
            }

            with patch("huashi.portrait_studio.call_model_text", return_value=__import__("json").dumps(raw, ensure_ascii=False)):
                result = studio.generate_material_drafts("场景", "酒店夜景", count=3, model_id="aihubmix-grok")

            self.assertEqual(result["cards"][0]["title_cn"], "雨后酒店门廊")
            self.assertEqual(result["model"], "aihubmix-grok")


if __name__ == "__main__":
    unittest.main()
