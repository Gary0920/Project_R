import unittest

from app.features.preprocessing.pdf_structured import _assert_bilingual_markdown, _final_prompt


class PDFStructuredExtractionTests(unittest.TestCase):
    def test_final_prompt_requires_bilingual_alignment(self):
        prompt = _final_prompt(
            "standard.pdf",
            page_count=10,
            pages_analyzed=10,
            summaries=["## 页码范围\np. 1-10"],
            used_vision=True,
            vision_pages=(1, 5),
        )

        self.assertIn("最终知识页必须中英文并存", prompt)
        self.assertIn("English Equivalent", prompt)
        self.assertIn("中文要求", prompt)
        self.assertIn("信息不对称", prompt)

    def test_bilingual_markdown_check_accepts_aligned_output(self):
        _assert_bilingual_markdown(
            "# standard\n\n"
            "## 审核状态 / Review Status\n"
            "- 中文：待审核。\n"
            "  English: Pending review.\n\n"
            "## 核心结论 / Key Conclusions\n"
            "- 中文：需要使用安全玻璃。\n"
            "  English: Safety glass is required.\n\n"
            "## 关键要求与参数 / Key Requirements and Parameters\n"
            "| 类别 / Category | 中文要求 / Chinese Requirement | English Equivalent | 页码 / Pages |\n"
            "| --- | --- | --- | --- |\n"
            "| 材料 / Material | 中文：示例要求。 | English: Example requirement. | p. 1 |\n"
        )

    def test_bilingual_markdown_check_rejects_single_language_output(self):
        with self.assertRaises(ValueError):
            _assert_bilingual_markdown(
                "# standard\n\n"
                "## 审核状态\n"
                "待审核。\n\n"
                "## 核心结论\n"
                "需要使用安全玻璃。\n"
            )


if __name__ == "__main__":
    unittest.main()
