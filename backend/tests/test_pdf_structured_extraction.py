import unittest
from pathlib import Path
from unittest.mock import patch

import app.features.preprocessing.pdf_structured as pdf_structured
from app.features.preprocessing.pdf_structured import (
    PDFPageText,
    _Batch,
    _assert_bilingual_markdown,
    _final_prompt,
    _standard_batch_prompt,
    _standard_final_prompt,
)


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

    def test_standard_final_prompt_requires_knowledge_base_format(self):
        prompt = _standard_final_prompt(
            "AS 2047-2014.pdf",
            page_count=72,
            pages_analyzed=72,
            summaries=["## Batch 1\np. 1-10"],
            used_vision=True,
            vision_pages=(1, 19, 37),
        )

        for section in (
            "01 Scope",
            "02 Referenced Standards",
            "03 Definitions",
            "04 Terms Library",
            "05 Symbols Library",
            "06 Requirements Library",
            "07 Formula Library",
            "08 Parameter Library",
            "09 Table Library",
            "10 Verification Methods",
            "11 Source Mapping",
            "待审核问题 / Review Questions",
        ):
            self.assertIn(section, prompt)

        self.assertIn("规范知识库", prompt)
        self.assertIn("RAG", prompt)
        self.assertIn("可追溯", prompt)
        self.assertIn("禁止出现", prompt)
        self.assertIn("LaTeX", prompt)
        self.assertIn("完整保留行列数值", prompt)

    def test_standard_batch_prompt_requires_knowledge_block_format(self):
        batch = _Batch(index=1, start_page=1, end_page=10, text="[Page 1]\nSome standard text here.")
        prompt = _standard_batch_prompt("AS 2047.pdf", batch, 3)

        self.assertIn("定义块 / Definition Block", prompt)
        self.assertIn("要求块 / Requirement Block", prompt)
        self.assertIn("公式块 / Formula Block", prompt)
        self.assertIn("表格块 / Table Block", prompt)
        self.assertIn("验证方法块 / Verification Block", prompt)
        self.assertIn("来源 / Source", prompt)
        self.assertIn("Clause", prompt)
        self.assertIn("LaTeX", prompt)
        self.assertIn("禁止出现", prompt)
        self.assertIn("完整保留行列数值", prompt)

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

    def test_bilingual_markdown_check_accepts_standard_knowledge_base_output(self):
        _assert_bilingual_markdown(
            "# AS 2047\n\n"
            "## 01 Scope / 适用范围\n"
            "适用产品范围。\n\n"
            "## 02 Referenced Standards / 引用标准\n"
            "| 标准编号 / Standard | 名称 / Name | 用途 / Purpose | 涉及条款 / Clauses |\n"
            "| --- | --- | --- | --- |\n"
            "| AS 1288 | Glass selection | 引用玻璃选择要求 | Clause 2 |\n\n"
            "## 03 Definitions / 定义\n"
            "- **术语 / Term**: Window\n\n"
            "## 04 Terms Library / 术语库\n"
            "- **术语 / Term**: U-value\n\n"
            "## 05 Symbols Library / 符号库\n"
            "- **符号 / Symbol**: U\n\n"
            "## 06 Requirements Library / 要求库\n"
            "- **参数 / Parameter**: Water penetration resistance\n\n"
            "## 07 Formula Library / 公式库\n"
            "- **表达式 / Expression**: $U = 1 / R$\n\n"
            "## 08 Parameter Library / 参数库\n"
            "| 参数 / Parameter | 要求 / Requirement | 单位 / Unit | 适用条件 / Applicability | 来源 / Source |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| pressure | 150 | Pa | test | Clause 3 |\n\n"
            "## 09 Table Library / 表格库\n"
            "- **表格编号 / Table Number**: Table 1\n\n"
            "## 10 Verification Methods / 验证方法\n"
            "- **验证项 / Verification Item**: water test\n\n"
            "## 11 Source Mapping / 来源映射\n"
            "| 条款号 / Clause | 条款名 / Title | 对应分区 / Section | 页码 / Page |\n"
            "| --- | --- | --- | --- |\n"
            "| 1 | Scope | 01 Scope | p. 1 |\n\n"
            "## 待审核问题 / Review Questions\n"
            "无。\n"
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

    def test_read_pdf_pages_falls_back_to_fitz_when_pypdf_fails(self):
        with patch.object(pdf_structured, "_read_pdf_pages_with_pypdf", side_effect=ValueError("bad stream")):
            with patch.object(
                pdf_structured,
                "_read_pdf_pages_with_fitz",
                return_value=[PDFPageText(1, "AS 2047 text from fitz")],
            ):
                pages = pdf_structured._read_pdf_pages(Path("standard.pdf"))

        self.assertEqual(pages, [PDFPageText(1, "AS 2047 text from fitz")])


if __name__ == "__main__":
    unittest.main()
