from __future__ import annotations

import unittest
from pathlib import Path

from core.pdf_structured_extraction import (
    _detect_pdf_subkind,
    validate_pdf_extraction,
    _load_subkind_prompt,
)


class TestDetectPdfSubkind(unittest.TestCase):
    def test_window_schedule(self):
        subkind, key = _detect_pdf_subkind("240715 Orama [WS].pdf")
        self.assertEqual(subkind, "drawing_window_schedule")
        self.assertEqual(key, "pdf-drawing-ws")

    def test_schedule_programme(self):
        subkind, key = _detect_pdf_subkind("260205 Madeline [Facade Supply Programme] Rev04.pdf")
        self.assertEqual(subkind, "drawing_schedule")
        self.assertEqual(key, "pdf-drawing-schedule")

    def test_floor_plan(self):
        subkind, key = _detect_pdf_subkind("240704 Orama [Floor Plans].pdf")
        self.assertEqual(subkind, "drawing_general_arrangement")
        self.assertEqual(key, "pdf-drawing-ga")

    def test_shop_drawing(self):
        subkind, key = _detect_pdf_subkind("SDBaluster GF-L01 Rev05 - Shop Drawing.pdf")
        self.assertEqual(subkind, "drawing_shop_drawing")
        self.assertEqual(key, "pdf-drawing-sd")

    def test_general_pdf(self):
        subkind, key = _detect_pdf_subkind("some_contract.pdf")
        self.assertEqual(subkind, "general_pdf")
        self.assertIsNone(key)

    def test_chinese_drawing_name(self):
        subkind, key = _detect_pdf_subkind("平面图_首层.pdf")
        self.assertEqual(subkind, "drawing_general_arrangement")

    def test_chinese_schedule_name(self):
        subkind, key = _detect_pdf_subkind("项目排期表_v2.pdf")
        self.assertEqual(subkind, "drawing_schedule")


class TestValidatePdfExtraction(unittest.TestCase):
    def test_window_schedule_ok(self):
        md = """## Window Schedule

| Window ID | Width | Height | Qty | Level | Page |
| --- | --- | --- | --- | --- | --- |
| W19 | 1200 | 1800 | 2 | L3-15 | p. 1 |
| W22 | 900 | 1500 | 1 | L3-15 | p. 1 |
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_window_schedule")
        self.assertEqual(result["review_status"], "approved")
        self.assertTrue(result["checks"]["has_window_ids"])
        self.assertTrue(result["checks"]["has_dimensions"])

    def test_window_schedule_no_dimensions(self):
        md = """## Window Schedule
Some text about windows but no dimensions.
p. 1
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_window_schedule")
        self.assertEqual(result["review_status"], "needs_review")
        self.assertFalse(result["checks"]["has_dimensions"])

    def test_window_schedule_no_window_ids(self):
        md = """## Some doc
No window IDs here.
p. 1
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_window_schedule")
        self.assertEqual(result["review_status"], "needs_review")

    def test_schedule_ok(self):
        md = """## Schedule

| Task | Duration | Start | Finish | Page |
| --- | --- | --- | --- | --- |
| L6-L39 Shop Drawing | 45 days | 2026-01-01 | 2026-02-15 | p. 1 |
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_schedule")
        self.assertEqual(result["review_status"], "approved")
        self.assertTrue(result["checks"]["has_duration"])
        self.assertTrue(result["checks"]["has_finish_date"])

    def test_schedule_missing_dates(self):
        md = """## Schedule
General text about tasks but no dates.
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_schedule")
        self.assertEqual(result["review_status"], "needs_review")
        self.assertFalse(result["checks"]["has_duration"])
        self.assertFalse(result["checks"]["has_finish_date"])

    def test_drawing_ga_ok(self):
        md = """## Floor Plan

Level 17 floor plan with window layout (p. 9).
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_general_arrangement")
        self.assertEqual(result["review_status"], "approved")
        self.assertTrue(result["checks"]["has_level_info"])

    def test_drawing_ga_no_level(self):
        md = """## Drawing
Some content without level references.
"""
        result = validate_pdf_extraction(md, Path("test.pdf"), "drawing_general_arrangement")
        self.assertEqual(result["review_status"], "needs_review")
        self.assertFalse(result["checks"]["has_level_info"])

    def test_general_pdf_no_validation(self):
        md = "Some text"
        result = validate_pdf_extraction(md, Path("test.pdf"), "general_pdf")
        self.assertEqual(result["review_status"], "approved")
        self.assertEqual(result["checks"], {})


class TestLoadSubkindPrompt(unittest.TestCase):
    def test_load_ga_prompt(self):
        prompt = _load_subkind_prompt("pdf-drawing-ga")
        self.assertIsNotNone(prompt)
        self.assertIn("平面图", prompt)

    def test_load_ws_prompt(self):
        prompt = _load_subkind_prompt("pdf-drawing-ws")
        self.assertIsNotNone(prompt)
        self.assertIn("Window Schedule", prompt)

    def test_load_schedule_prompt(self):
        prompt = _load_subkind_prompt("pdf-drawing-schedule")
        self.assertIsNotNone(prompt)
        self.assertIn("排期", prompt)

    def test_load_sd_prompt(self):
        prompt = _load_subkind_prompt("pdf-drawing-sd")
        self.assertIsNotNone(prompt)
        self.assertIn("Shop Drawing", prompt)

    def test_none_key(self):
        self.assertIsNone(_load_subkind_prompt(None))

    def test_missing_file(self):
        self.assertIsNone(_load_subkind_prompt("nonexistent"))


if __name__ == "__main__":
    unittest.main()
