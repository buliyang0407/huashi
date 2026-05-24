import unittest

from huashi.prompt_ai import PROMPT_MODELS, build_system_prompt, split_candidates


class PromptAITest(unittest.TestCase):
    def test_prompt_models_exclude_gemma_and_include_grok(self):
        ids = [model.id for model in PROMPT_MODELS]

        self.assertEqual(
            ids,
            [
                "ollama-qwen-vl",
                "ollama-qwen-9b",
                "ollama-qwen-4b",
                "aihubmix-grok",
            ],
        )
        self.assertNotIn("gemma", " ".join(model.model for model in PROMPT_MODELS).lower())

    def test_split_candidates_handles_numbered_lines(self):
        text = """
        1. 第一条提示词
        2、第二条提示词
        3) 第三条提示词
        4. 第四条不取
        """

        self.assertEqual(split_candidates(text), ["第一条提示词", "第二条提示词", "第三条提示词"])

    def test_split_candidates_prefers_explicit_markers_with_paragraphs(self):
        text = """<<<HUASHI_CANDIDATE_1>>>
第一条第一段

第一条第二段
<<<HUASHI_CANDIDATE_2>>>
第二条第一段

第二条第二段
<<<HUASHI_CANDIDATE_3>>>
第三条第一段

第三条第二段"""

        self.assertEqual(
            split_candidates(text),
            [
                "第一条第一段\n\n第一条第二段",
                "第二条第一段\n\n第二条第二段",
                "第三条第一段\n\n第三条第二段",
            ],
        )

    def test_split_candidates_supports_more_than_three_marked_candidates(self):
        text = "\n".join(
            f"<<<HUASHI_CANDIDATE_{index}>>>\n第{index}条"
            for index in range(1, 6)
        )

        self.assertEqual(split_candidates(text), ["第1条", "第2条", "第3条", "第4条", "第5条"])

    def test_system_prompt_uses_requested_candidate_count(self):
        prompt = build_system_prompt(2)

        self.assertIn("生成 2 条", prompt)
        self.assertIn("<<<HUASHI_CANDIDATE_2>>>", prompt)
        self.assertNotIn("<<<HUASHI_CANDIDATE_3>>>", prompt)


if __name__ == "__main__":
    unittest.main()
