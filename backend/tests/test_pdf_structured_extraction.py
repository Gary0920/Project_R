import unittest
from pathlib import Path
from unittest.mock import patch

import app.features.preprocessing.pdf_structured as pdf_structured
from app.features.preprocessing.pdf_structured import (
    PDFPageText,
    SPLIT_THRESHOLD_PAGES,
    _assert_bilingual_markdown,
    _standard_batch_prompt,
    _standard_final_prompt,
    _Batch,
)


class PDFStructuredExtractionTests(unittest.TestCase):
    def test_standard_final_prompt_requires_knowledge_base_format(self):
        prompt = _standard_final_prompt(
            "AS 2047-2014.pdf",
            page_count=72,
            pages_analyzed=72,
            summaries=["## Batch 1\np. 1-10"],
            used_vision=True,
            vision_pages=(1, 19, 37),
        )

        # 11-section knowledge base structure
        self.assertIn("01 Scope", prompt)
        self.assertIn("02 Referenced Standards", prompt)
        self.assertIn("03 Definitions", prompt)
        self.assertIn("04 Terms Library", prompt)
        self.assertIn("05 Symbols Library", prompt)
        self.assertIn("06 Requirements Library", prompt)
        self.assertIn("07 Formula Library", prompt)
        self.assertIn("08 Parameter Library", prompt)
        self.assertIn("09 Table Library", prompt)
        self.assertIn("10 Verification Methods", prompt)
        self.assertIn("11 Source Mapping", prompt)
        self.assertIn("待审核问题 / Review Questions", prompt)

        # Knowledge base principles
        self.assertIn("规范知识库", prompt)
        self.assertIn("RAG", prompt)
        self.assertIn("可追溯", prompt)

        # Prohibition on subjective content
        self.assertIn("禁止出现", prompt)

        # LaTeX formula requirement
        self.assertIn("LaTeX", prompt)

    def test_standard_prompt_requires_table_format(self):
        prompt = _standard_final_prompt(
            "AS 2047-2014.pdf",
            page_count=72,
            pages_analyzed=72,
            summaries=["## Batch 1\np. 1-10"],
            used_vision=True,
            vision_pages=(1, 19, 37),
        )
        # Check that the prompt requires structured knowledge base format
        self.assertIn("11", prompt)
        self.assertIn("Source Mapping", prompt)

    def test_standard_batch_prompt_requires_knowledge_block_format(self):
        batch = _Batch(index=1, start_page=1, end_page=10, text="[Page 1]\nSome standard text here.")
        prompt = _standard_batch_prompt("AS 2047.pdf", batch, 3)

        # Knowledge block types
        self.assertIn("定义块 / Definition Block", prompt)
        self.assertIn("要求块 / Requirement Block", prompt)
        self.assertIn("公式块 / Formula Block", prompt)
        self.assertIn("表格块 / Table Block", prompt)
        self.assertIn("验证方法块 / Verification Block", prompt)

        # Traceability requirement
        self.assertIn("来源 / Source", prompt)
        self.assertIn("Clause", prompt)

        # LaTeX formula requirement
        self.assertIn("LaTeX", prompt)

        # Prohibition on subjective content
        self.assertIn("禁止出现", prompt)

        # Table preservation requirement
        self.assertIn("完整保留行列数值", prompt)

        # Markdown table format
        self.assertIn("Markdown", prompt)

        # New knowledge base specific checks
        self.assertIn("规范知识块抽取", prompt)
        self.assertIn("一个知识点", prompt)

    def test_bilingual_markdown_check_accepts_aligned_output(self):
        _assert_bilingual_markdown(
            "# standard\n\n"
            "## 审核状态 / Review Status\n"
            "待审核。\n\n"
            "## 标准适用范围 / Standard Scope\n"
            "适用产品和场景。\n\n"
            "## 核心引用标准 / Core Referenced Standards\n"
            "| 标准 / Standard | 用途 / Purpose |\n"
            "| --- | --- |\n"
            "| AS/NZS 4420.1 | Test method |\n"
        )

    def test_bilingual_markdown_check_accepts_new_section_markers(self):
        _assert_bilingual_markdown(
            "# AS 2047\n\n"
            "## 审核状态 / Review Status\n"
            "待审核。\n\n"
            "## 标准适用范围 / Standard Scope\n"
            "| 标准 / Standard | 用途 / Purpose |\n"
            "| --- | --- |\n"
            "| AS 1288 | Glass selection |\n\n"
            "## 核心引用标准 / Core Referenced Standards\n"
            "| 标准 / Standard | 用途 / Purpose |\n"
            "| --- | --- |\n"
            "| AS 1288 | Glass selection |\n\n"
            "## 项目执行控制清单 / Project Execution Control Checklist\n"
            "| 阶段 / Phase | 检查项 / Check Item |\n"
            "| --- | --- |\n"
            "| 报价/投标 | Design wind pressure |\n"
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

    def test_split_threshold_pages_is_defined(self):
        self.assertIsInstance(SPLIT_THRESHOLD_PAGES, int)
        self.assertGreater(SPLIT_THRESHOLD_PAGES, 0)

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
