import unittest
from unittest.mock import patch

from huashi.prompt_ai import PromptAIError
from huashi.prompt_agent import (
    agent_model_error_message,
    analyze_prompt,
    build_analyze_messages,
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

    def test_extract_json_object_reports_truncated_model_output(self):
        text = '{"prompt_type":"人像","editable_items":[{"id":"person"}], "'

        with self.assertRaises(PromptAIError) as ctx:
            extract_json_object(text)

        self.assertIn("模型输出不完整", str(ctx.exception))

    def test_analyze_prompt_uses_compact_schema_and_larger_token_budget(self):
        messages = build_analyze_messages("A red-haired woman on a beach.")
        system_prompt = messages[0]["content"]

        self.assertIn("editable_items", system_prompt)
        self.assertNotIn("core_points", system_prompt)
        self.assertNotIn("editable_points", system_prompt)

        with patch("huashi.prompt_agent.call_model_text") as call_model:
            call_model.return_value = '{"prompt_type":"人像","summary":"红发女子","translation_cn":"红发女子","editable_items":[],"locked_context":[]}'
            analyze_prompt("A red-haired woman on a beach.", "aihubmix-grok")

        self.assertGreaterEqual(call_model.call_args.kwargs["max_tokens"], 3600)

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

    def test_normalize_analysis_returns_chinese_translation_and_local_edit_items(self):
        analysis = normalize_analysis(
            {
                "prompt_type": "人像摄影",
                "summary": "沙滩黄昏人像",
                "translation_cn": "一位长红发年轻女子站在黄昏沙滩上。",
                "editable_items": [
                    {
                        "id": "hair",
                        "label": "Hair color",
                        "original": "long red hair",
                        "original_cn": "长红发",
                        "suggestions": ["黑长直发", "银色短发", "棕色卷发"],
                    },
                    {"id": "camera", "label_cn": "镜头景别", "original": "medium shot"},
                ],
                "locked_context": ["photorealistic", "cinematic lighting"],
            }
        )

        self.assertIn("长红发年轻女子", analysis["translation_cn"])
        self.assertEqual(analysis["editable_items"][0]["label"], "发型发色")
        self.assertEqual(analysis["editable_items"][0]["original"], "长红发")
        self.assertEqual(analysis["editable_items"][0]["suggestions"], ["黑长直发", "银色短发", "棕色卷发"])
        self.assertEqual(analysis["editable_items"][1]["label"], "镜头景别")
        self.assertEqual(analysis["editable_items"][1]["original"], "medium shot")
        self.assertIn("cinematic lighting", analysis["locked_context"])

    def test_normalize_analysis_rewrites_age_ambiguous_suggestions(self):
        analysis = normalize_analysis(
            {
                "prompt_type": "人像",
                "summary": "人像",
                "editable_items": [
                    {
                        "id": "person",
                        "label": "人物身份",
                        "original": "成年东亚女性",
                        "suggestions": ["东亚少女", "学生妹", "年轻成年女性"],
                    }
                ],
            }
        )

        suggestions = analysis["editable_items"][0]["suggestions"]
        self.assertIn("20岁左右东亚成年女性", suggestions)
        self.assertIn("清爽校园感成年女性", suggestions)
        self.assertNotIn("东亚少女", suggestions)

    def test_default_agent_model_prefers_grok41_when_available(self):
        with patch.dict("os.environ", {"AIHUBMIX_API_KEY": "test-key"}):
            self.assertEqual(get_agent_model("").id, "aihubmix-grok")
            self.assertEqual(get_agent_model("").label, "Grok4.1")
            self.assertEqual(get_agent_model("").model, "grok-4-1-fast-non-reasoning")

    def test_agent_model_error_message_explains_disabled_aihubmix_key(self):
        message = agent_model_error_message('{"error":{"message":"this key is not enabled"}}')

        self.assertIn("AIHubMix", message)
        self.assertIn("当前模型", message)

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

    def test_generate_messages_include_only_filled_local_edits(self):
        messages = build_generate_messages(
            original_prompt="A young woman with long red hair on the beach, medium shot, cinematic lighting.",
            analysis={
                "translation_cn": "一位长红发年轻女子在沙滩上，中镜头，电影感光线。",
                "editable_items": [
                    {"id": "hair", "label": "发型发色", "original": "长红发"},
                    {"id": "scene", "label": "场景地点", "original": "沙滩"},
                    {"id": "camera", "label": "镜头景别", "original": "中镜头"},
                ],
                "locked_context": ["cinematic lighting"],
            },
            edits=[
                {"id": "hair", "label": "发型发色", "original": "长红发", "value": "黑长直发"},
                {"id": "scene", "label": "场景地点", "original": "沙滩", "value": ""},
                {"id": "camera", "label": "镜头景别", "original": "中镜头", "value": "拉远一点，全身"},
            ],
            extra_instruction="整体更神秘一点",
        )
        joined = "\n".join(message["content"] for message in messages)

        self.assertIn("只改“新值”非空的项目", joined)
        self.assertIn("发型发色：长红发 -> 黑长直发", joined)
        self.assertIn("镜头景别：中镜头 -> 拉远一点，全身", joined)
        self.assertNotIn("场景地点：沙滩 ->", joined)
        self.assertIn("整体更神秘一点", joined)
        self.assertIn("完整中文翻译", joined)

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
