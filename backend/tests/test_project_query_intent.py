from __future__ import annotations

import unittest

from app.features.knowledge.project_query.intent import (
    classify_project_query,
    ProjectQueryIntent,
)


class TestClassifyProjectQuery(unittest.TestCase):
    def test_empty_query(self):
        intent = classify_project_query("")
        self.assertEqual(intent.confidence, "low")
        self.assertIsNone(intent.file_kind_hint)

    def test_blank_query(self):
        intent = classify_project_query("   ")
        self.assertEqual(intent.confidence, "low")

    def test_drawing_query_chinese(self):
        intent = classify_project_query("L17 层图纸里有多少个窗？")
        self.assertEqual(intent.file_kind_hint, "pdf_drawing")
        self.assertEqual(intent.source_category_hint, "technical")
        self.assertEqual(intent.confidence, "high")

    def test_window_schedule_query(self):
        intent = classify_project_query("L3-15 W19这个窗的宽高尺寸是多少？")
        self.assertEqual(intent.file_kind_hint, "pdf_drawing")
        self.assertEqual(intent.confidence, "high")

    def test_schedule_query(self):
        intent = classify_project_query("项目排期中L6-L39 Shop Drawing图纸需要多少天才能完成？")
        self.assertEqual(intent.file_kind_hint, "pdf_schedule")
        self.assertEqual(intent.source_category_hint, "technical")
        self.assertEqual(intent.confidence, "high")

    def test_schedule_finish_query(self):
        intent = classify_project_query("项目排期中L6-L39 Shop Drawing图纸计划完成日期是什么时候？")
        self.assertEqual(intent.file_kind_hint, "pdf_schedule")

    def test_payment_screenshot_query(self):
        intent = classify_project_query("支付截图中，花费了多少钱？")
        self.assertEqual(intent.file_kind_hint, "image_payment")
        self.assertEqual(intent.confidence, "high")

    def test_contact_sheet_reason_query(self):
        intent = classify_project_query("内部联系单 BG0806-LXD01-补货 为什么要补货？")
        self.assertEqual(intent.file_kind_hint, "image_contact_sheet")
        self.assertEqual(intent.source_category_hint, "changes")
        self.assertEqual(intent.confidence, "high")

    def test_contact_sheet_items_query(self):
        intent = classify_project_query("内部联系单 BG0806-LXD01-补货 补什么？")
        self.assertEqual(intent.file_kind_hint, "image_contact_sheet")

    def test_meeting_query(self):
        intent = classify_project_query("会议中Gary提出了一个新的知识库系统叫什么？")
        self.assertEqual(intent.file_kind_hint, "meeting")
        self.assertEqual(intent.source_category_hint, "meetings")
        self.assertEqual(intent.confidence, "high")

    def test_english_meeting_query(self):
        intent = classify_project_query("What did Gary propose in the meeting?")
        self.assertEqual(intent.file_kind_hint, "meeting")

    def test_email_query(self):
        intent = classify_project_query("邮件中 daisy推荐客户sky light使用什么玻璃？")
        self.assertEqual(intent.file_kind_hint, "email")
        self.assertEqual(intent.source_category_hint, "unfiled")
        self.assertEqual(intent.confidence, "high")

    def test_spreadsheet_query(self):
        intent = classify_project_query("材料清单中，GL01的玻璃规格是什么？")
        self.assertEqual(intent.file_kind_hint, "spreadsheet")
        self.assertEqual(intent.source_category_hint, "production")
        self.assertEqual(intent.confidence, "high")

    def test_office_doc_query(self):
        intent = classify_project_query("注意事项文件中，适配颜色五金件需要注意什么？")
        self.assertEqual(intent.file_kind_hint, "office_doc")
        self.assertEqual(intent.confidence, "medium")

    def test_bom_abbreviation(self):
        intent = classify_project_query("BOM中GL01的规格？")
        self.assertEqual(intent.file_kind_hint, "spreadsheet")

    def test_no_match(self):
        intent = classify_project_query("今天天气怎么样？")
        self.assertEqual(intent.confidence, "low")
        self.assertIsNone(intent.file_kind_hint)

    def test_matched_patterns_recorded(self):
        intent = classify_project_query("图纸中L17层有多少个窗？")
        self.assertTrue(len(intent.matched_patterns) >= 1)
        self.assertIn(intent.raw_query, "图纸中L17层有多少个窗？")

    def test_source_category_maps_correctly(self):
        tests = [
            ("项目排期多少天", "technical"),
            ("会议内容", "meetings"),
            ("补货原因", "changes"),
            ("材料清单", "production"),
            ("支付金额", "unfiled"),
        ]
        for query, expected_category in tests:
            with self.subTest(query=query):
                intent = classify_project_query(query)
                self.assertEqual(intent.source_category_hint, expected_category)

    def test_confidence_high_for_clear_intent(self):
        """All 14 fixture queries should classify with high confidence."""
        fixture_queries = [
            "L17 层图纸里有多少个窗？",
            "L3-15 W19这个窗的宽高尺寸是多少？",
            "项目排期中L6-L39 Shop Drawing图纸需要多少天才能完成？",
            "项目排期中L6-L39 Shop Drawing图纸计划完成日期是什么时候？",
            "内部联系单 BG0806-LXD01-补货 为什么要补货？",
            "内部联系单 BG0806-LXD01-补货 补什么？",
            "会议中Gary提出了一个新的知识库系统叫什么？",
            "邮件中 daisy推荐客户sky light使用什么玻璃？",
            "支付截图中，花费了多少钱？",
            "材料清单中，GL01的玻璃规格是什么？",
        ]
        high_confidence_count = 0
        for query in fixture_queries:
            intent = classify_project_query(query)
            if intent.confidence == "high":
                high_confidence_count += 1
        # Most should be high confidence
        self.assertGreaterEqual(high_confidence_count, 8)


if __name__ == "__main__":
    unittest.main()
