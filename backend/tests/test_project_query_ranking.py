from __future__ import annotations

import unittest

from app.features.knowledge.project_query.intent import classify_project_query, ProjectQueryIntent
from app.features.knowledge.project_query.ranking import (
    infer_file_kind_from_slug,
    infer_file_kind_from_source,
    adjust_project_ranking,
    apply_ranking_to_sources,
    RankedSource,
)


class TestInferFileKindFromSlug(unittest.TestCase):
    def test_floor_plan(self):
        self.assertEqual(infer_file_kind_from_slug("240704-orama-floor-plans"), "pdf_drawing")

    def test_window_schedule(self):
        self.assertEqual(infer_file_kind_from_slug("240715-orama-ws"), "pdf_drawing")
        self.assertEqual(infer_file_kind_from_slug("240715-orama-ws-1"), "pdf_drawing")

    def test_schedule(self):
        self.assertEqual(
            infer_file_kind_from_slug("260205-madeline-facade-supply-programme-rev04"),
            "pdf_schedule",
        )

    def test_contact_sheet(self):
        self.assertEqual(
            infer_file_kind_from_slug("邱智勇提交的内部联系单"),
            "image_contact_sheet",
        )

    def test_payment_screenshot(self):
        self.assertEqual(infer_file_kind_from_slug("支付截图服务器"), "image_payment")

    def test_meeting(self):
        slug = "20260529-143933-张学辉gary-张学辉发起的视频会议-0529-audio"
        self.assertEqual(infer_file_kind_from_slug(slug), "meeting")

    def test_email(self):
        slug = "2026-03-13-1551-re-bfi-29-dudley-st-skylight-balustrade-shopd"
        self.assertEqual(infer_file_kind_from_slug(slug), "email")

    def test_spreadsheet(self):
        self.assertEqual(infer_file_kind_from_slug("260506-ml-材料清单-rev-01"), "spreadsheet")

    def test_office_doc(self):
        self.assertEqual(infer_file_kind_from_slug("260506-注意事项-bg0812-rooster"), "office_doc")

    def test_no_match(self):
        self.assertIsNone(infer_file_kind_from_slug("some-random-file-name"))


class TestInferFileKindFromSource(unittest.TestCase):
    def test_direct_field(self):
        source = {"file_kind": "pdf_drawing", "file": "drawing.pdf"}
        self.assertEqual(infer_file_kind_from_source(source), "pdf_drawing")

    def test_from_tags(self):
        source = {"tags": "project,test,meeting,audio", "file": "audio.mp4"}
        self.assertEqual(infer_file_kind_from_source(source), "meeting")

    def test_from_file_path(self):
        source = {"file": "gbrain:project-test/technical/240704-orama-floor-plans"}
        self.assertEqual(infer_file_kind_from_source(source), "pdf_drawing")

    def test_from_section_path(self):
        source = {"file": "some-file", "section_path": "meetings / 2026-05-29"}
        self.assertEqual(infer_file_kind_from_source(source), "meeting")

    def test_empty_source(self):
        self.assertIsNone(infer_file_kind_from_source({}))


class TestAdjustProjectRanking(unittest.TestCase):
    def _make_source(self, file_path: str, score: float = 1.0, **extra) -> dict:
        source = {"file": file_path, "score": score, **extra}
        return source

    def test_empty_sources(self):
        intent = classify_project_query("test query")
        result = adjust_project_ranking([], intent)
        self.assertEqual(result, [])

    def test_boost_matching_kind_high_confidence(self):
        """Drawing query → drawing source should be boosted 1.5x."""
        sources = [
            self._make_source("technical/floor-plan.pdf", score=0.8),
            self._make_source("meetings/audio.docx", score=0.9),
        ]
        intent = classify_project_query("L17 层图纸有多少个窗？")
        ranked = adjust_project_ranking(sources, intent)

        # drawing source should be ranked first despite lower original score
        self.assertEqual(ranked[0].source_index, 0)  # floor-plan
        self.assertAlmostEqual(ranked[0].adjusted_score, 0.8 * 1.5)
        self.assertIsNotNone(ranked[0].boost_reason)

    def test_meeting_penalty_for_non_meeting_query(self):
        """Payment screenshot query → meeting source should be penalized."""
        sources = [
            self._make_source("unfiled/payment-screenshot.png", score=0.9),
            self._make_source("meetings/meeting-audio.docx", score=0.95),
        ]
        intent = classify_project_query("支付截图中花费了多少钱？")
        ranked = adjust_project_ranking(sources, intent)

        # payment source should be first after adjustment (meeting got penalized)
        self.assertEqual(ranked[0].source_index, 0)  # payment
        # meeting source should be penalized
        self.assertIn("penalty", ranked[1].boost_reason or "")

    def test_meeting_query_no_penalty(self):
        """Meeting query → meeting source should NOT be penalized."""
        sources = [
            self._make_source("unfiled/random.txt", score=0.9),
            self._make_source("meetings/meeting-audio.docx", score=0.8),
        ]
        intent = classify_project_query("会议中Gary提出了什么？")
        ranked = adjust_project_ranking(sources, intent)

        # meeting source should remain second (no penalty applied)
        self.assertIsNone(ranked[1].boost_reason)

    def test_low_confidence_slight_penalty(self):
        intent = classify_project_query("今天天气怎么样？")  # low confidence
        self.assertEqual(intent.confidence, "low")
        sources = [self._make_source("some-file.pdf", score=1.0)]
        ranked = adjust_project_ranking(sources, intent)
        self.assertAlmostEqual(ranked[0].adjusted_score, 0.9)

    def test_spreadsheet_over_meeting(self):
        """Material list query → spreadsheet should beat meeting sources."""
        sources = [
            self._make_source("meetings/meeting-audio.docx", score=0.9),
            self._make_source("production/260506-ml-材料清单-rev-01.xlsx", score=0.7),
        ]
        intent = classify_project_query("材料清单中GL01的玻璃规格是什么？")
        ranked = adjust_project_ranking(sources, intent)

        # spreadsheet source should be first after adjustment
        self.assertEqual(ranked[0].source_index, 1)  # spreadsheet
        self.assertIn("boost", ranked[0].boost_reason or "")

    def test_email_over_meeting(self):
        """Email query → email source should beat meeting."""
        sources = [
            self._make_source("meetings/meeting-audio.docx", score=0.9),
            self._make_source("unfiled/skylight-email.eml", score=0.7),
        ]
        intent = classify_project_query("邮件中daisy推荐了什么玻璃？")
        ranked = adjust_project_ranking(sources, intent)

        # email source should be first
        self.assertEqual(ranked[0].source_index, 1)  # email
        self.assertIn("boost", ranked[0].boost_reason or "")


class TestApplyRankingToSources(unittest.TestCase):
    def test_reorders_sources(self):
        sources = [
            {"file": "meetings/audio.docx", "score": 0.95},
            {"file": "payment.png", "score": 0.7, "file_kind": "image_payment"},
        ]
        intent = classify_project_query("支付截图中花费了多少钱？")
        ranked = adjust_project_ranking(sources, intent)
        reordered = apply_ranking_to_sources(sources, ranked)

        self.assertEqual(len(reordered), 2)
        # payment.png should be first
        self.assertIn("payment", reordered[0]["file"])
        self.assertIn("adjusted_score", reordered[0])
        self.assertIn("boost_reason", reordered[0])

    def test_adds_ranking_metadata(self):
        sources = [{"file": "test.pdf", "score": 1.0}]
        intent = classify_project_query("test")
        ranked = adjust_project_ranking(sources, intent)
        reordered = apply_ranking_to_sources(sources, ranked)

        self.assertIn("adjusted_score", reordered[0])
        self.assertIn("original_score", reordered[0])
        self.assertIn("file_kind", reordered[0])


if __name__ == "__main__":
    unittest.main()
