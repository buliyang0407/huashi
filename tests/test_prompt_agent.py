import unittest
from unittest.mock import patch

from huashi.prompt_agent import (
    build_generate_messages,
    extract_json_object,
    get_agent_model,
    normalize_analysis,
    normalize_variant,
)


class PromptAgentTest(unittest.TestCase):
    def test_extract_json_object_accepts_markdown_wrapped_json(self):
        text = """```json
        {"prompt_type": "人像", "core_points": ["主体", "光线"]}
        ```"""

        self.assertEqual(extract_json_object(text)["prompt_type"], "人像")

    def test_normalize_analysis_keeps_structured_prompt_summary(self):
        analysis = normalize_analysis(
            {
                "prompt_type": "人像摄影",
                "core_image": "韩国教室里的金色时刻人像",
                "core_points": ["女性主体", {"label": "光线", "current": "金色夕阳"}],
                "editable_points": [{"label": "人物", "current": "韩国女性", "suggestions": ["身份", "年龄"]}],
                "avoid_changes": "不要删除电影感和胶片质感",
            }
        )

        self.assertEqual(analysis["prompt_type"], "人像摄影")
        self.assertIn("韩国教室", analysis["core_image"])
        self.assertEqual(analysis["core_points"][1]["label"], "光线")
        self.assertEqual(analysis["editable_points"][0]["suggestions"], ["身份", "年龄"])
        self.assertEqual(analysis["avoid_changes"], ["不要删除电影感和胶片质感"])
        self.assertTrue(analysis["guide"])

    def test_default_agent_model_prefers_grok_when_available(self):
        with patch.dict("os.environ", {"AIHUBMIX_API_KEY": "test-key"}):
            self.assertEqual(get_agent_model("").id, "aihubmix-grok")

    def test_generate_messages_request_exactly_one_prompt(self):
        messages = build_generate_messages(
            original_prompt="Ultra-realistic classroom portrait",
            analysis={"core_image": "教室人像", "core_points": ["电影感"]},
            instruction="换成印度王子",
        )
        joined = "\n".join(message["content"] for message in messages)

        self.assertIn("只生成 1 条", joined)
        self.assertIn("完整英文提示词", joined)
        self.assertIn("完整中文翻译", joined)
        self.assertIn("换成印度王子", joined)

    def test_normalize_variant_returns_single_prompt_with_chinese_translation(self):
        variant = normalize_variant(
            {
                "prompt_en": "A cinematic Indian prince outside a moonlit palace.",
                "translation_cn": "一位电影感印度王子站在月光下的宫殿外。",
                "explanation_cn": "改成印度王子与夜晚宫殿。",
                "feature_cn": "保留电影感和主体叙事。",
            }
        )

        self.assertIn("Indian prince", variant["prompt_en"])
        self.assertIn("月光", variant["translation_cn"])
        self.assertIn("宫殿", variant["explanation_cn"])
        self.assertIn("电影感", variant["feature_cn"])


if __name__ == "__main__":
    unittest.main()
