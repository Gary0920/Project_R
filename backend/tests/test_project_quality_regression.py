from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from core.project_quality_regression import (
    RegressionCase,
    _check_terms,
    _kinds_match,
    _extract_location_from_answer,
    _is_meeting_source,
    score_case,
    run_regression,
    _build_summary,
    regression_report_to_dict,
)
from core.project_quality_report import store_report, list_reports, report_summary_to_text


class TestCheckTerms(unittest.TestCase):
    def test_all_terms_present(self):
        text = "Level 17 has 12 windows on the floor plan drawing"
        missing_all, missing_any = _check_terms(text, ["Level 17", "floor plan"], ["window", "drawing"])
        self.assertEqual(missing_all, [])
        self.assertEqual(missing_any, [])

    def test_missing_required_term(self):
        text = "The drawing shows the layout"
        missing_all, missing_any = _check_terms(text, ["Level 17", "window"], ["drawing"])
        self.assertEqual(missing_all, ["Level 17", "window"])
        self.assertEqual(missing_any, [])

    def test_missing_optional_term(self):
        text = "Level 17 drawing"
        missing_all, missing_any = _check_terms(text, ["Level 17"], ["window", "drawing"])
        self.assertEqual(missing_all, [])
        self.assertEqual(missing_any, ["window"])

    def test_chinese_terms(self):
        text = "L17 层图纸里有 12 个窗，详见第9页"
        missing_all, missing_any = _check_terms(text, ["L17", "图纸"], ["窗", "第9页"])
        self.assertEqual(missing_all, [])
        self.assertEqual(missing_any, [])

    def test_empty_terms(self):
        text = "Some answer text"
        missing_all, missing_any = _check_terms(text, [], [])
        self.assertEqual(missing_all, [])
        self.assertEqual(missing_any, [])


class TestKindsMatch(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(_kinds_match("image", "image"))
        self.assertTrue(_kinds_match("pdf_drawing", "pdf_drawing"))

    def test_broader_grouping(self):
        self.assertTrue(_kinds_match("pdf_drawing", "pdf"))
        self.assertTrue(_kinds_match("pdf", "pdf_drawing"))

    def test_meeting_group(self):
        self.assertTrue(_kinds_match("meeting_transcript_docx", "meeting_media"))
        self.assertTrue(_kinds_match("meeting_media", "meeting_transcript_docx"))

    def test_no_match(self):
        self.assertFalse(_kinds_match("image", "pdf_drawing"))
        self.assertFalse(_kinds_match("email", "spreadsheet"))
        self.assertFalse(_kinds_match("pdf_drawing", "image"))


class TestIsMeetingSource(unittest.TestCase):
    def test_meeting_keywords(self):
        self.assertTrue(_is_meeting_source("03-会议纪要/meeting_audio.docx"))
        self.assertTrue(_is_meeting_source("meeting.mp4"))
        self.assertTrue(_is_meeting_source("some_transcript.md"))

    def test_non_meeting(self):
        self.assertFalse(_is_meeting_source("02-图纸/floor_plan.pdf"))
        self.assertFalse(_is_meeting_source("payment.png"))
        self.assertFalse(_is_meeting_source(""))
        self.assertFalse(_is_meeting_source(None))


class TestExtractLocationFromAnswer(unittest.TestCase):
    def test_page_found(self):
        result = _extract_location_from_answer(
            "See page 9 for Level 17 details.",
            {"type": "page", "value": 9, "strict": True},
        )
        self.assertTrue(result["matched"])
        self.assertEqual(result["location_type"], "page")

    def test_page_not_found_strict(self):
        result = _extract_location_from_answer(
            "The drawing has 12 windows.",
            {"type": "page", "value": 9, "strict": True},
        )
        self.assertFalse(result["matched"])

    def test_page_not_found_non_strict(self):
        result = _extract_location_from_answer(
            "The drawing has 12 windows.",
            {"type": "page", "value": 9, "strict": False},
        )
        self.assertTrue(result["matched"])

    def test_chinese_page_reference(self):
        result = _extract_location_from_answer(
            "详见第9页平面图。",
            {"type": "page", "value": 9, "strict": True},
        )
        self.assertTrue(result["matched"])

    def test_sheet_found(self):
        result = _extract_location_from_answer(
            "Glass sheet shows GL01 spec.",
            {"type": "sheet", "value": "Glass", "strict": True},
        )
        self.assertTrue(result["matched"])

    def test_unknown_type(self):
        result = _extract_location_from_answer(
            "Some answer.",
            {"type": "unknown", "value": "", "strict": False},
        )
        self.assertTrue(result["matched"])


class TestScoreCase(unittest.TestCase):
    def _make_case(
        self,
        case_id: str = "test_case",
        file_kind: str = "image",
        expected_status: str = "should_pass",
        query: str = "test query?",
        source_file: str = "test.png",
        required_terms_all: list[str] | None = None,
        required_terms_any: list[str] | None = None,
        location_type: str = "page",
        location_value: Any = 1,
        location_strict: bool = False,
    ) -> RegressionCase:
        return RegressionCase(
            id=case_id,
            file_kind=file_kind,
            expected_status=expected_status,
            query=query,
            source_file=source_file,
            expected_location={"type": location_type, "value": location_value, "strict": location_strict},
            expected_answer={
                "required_terms_all": required_terms_all or [],
                "required_terms_any": required_terms_any or [],
            },
        )

    def test_pass(self):
        case = self._make_case(required_terms_all=["test"], source_file="test.png")
        result = score_case(case, "This is a test answer.", [{"file": "test.png", "file_kind": "image"}])
        self.assertEqual(result.status, "pass")
        self.assertFalse(result.meeting_false_positive)

    def test_pass_with_raw_mcp_page_slug_citation(self):
        case = self._make_case(required_terms_all=["test"], source_file="production/test-doc")
        result = score_case(
            case,
            "This is a test answer.",
            [{"page_slug": "production/test-doc", "citation_index": 1}],
        )
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.first_hit_source, "production/test-doc")

    def test_service_unavailable(self):
        case = self._make_case()
        result = score_case(case, "", [], service_unavailable=True)
        self.assertEqual(result.status, "service_unavailable")

    def test_wrong_source_kind(self):
        case = self._make_case(file_kind="image", source_file="test.png")
        result = score_case(
            case,
            "This is a test answer.",
            [{"file": "doc.docx", "file_kind": "office_doc"}],
        )
        self.assertEqual(result.status, "wrong_source")

    def test_meeting_false_positive(self):
        """Non-meeting question hitting a meeting source should flag meeting_false_positive."""
        case = self._make_case(file_kind="image", source_file="payment.png")
        result = score_case(
            case,
            "Payment was 68.00",
            [{"file": "03-会议纪要/meeting_audio.docx", "file_kind": "meeting_transcript_docx"}],
        )
        self.assertEqual(result.status, "wrong_source")
        self.assertTrue(result.meeting_false_positive)

    def test_missing_answer_point(self):
        case = self._make_case(required_terms_all=["missing_term", "another_term"])
        result = score_case(
            case,
            "This is a test answer.",
            [{"file": "test.png", "file_kind": "image"}],
        )
        self.assertEqual(result.status, "missing_answer_point")
        self.assertIn("missing_term", result.missing_terms_all)

    def test_known_gap_no_pass(self):
        case = self._make_case(
            expected_status="known_gap",
            required_terms_all=["unmatched_term"],
        )
        result = score_case(
            case,
            "Unrelated answer text.",
            [{"file": "test.png", "file_kind": "image"}],
        )
        self.assertEqual(result.status, "known_gap")
        self.assertIn("unmatched_term", result.missing_terms_all)

    def test_known_gap_unexpected_pass(self):
        case = self._make_case(
            expected_status="known_gap",
            required_terms_all=["specific"],
        )
        result = score_case(
            case,
            "Specific answer text here.",
            [{"file": "test.png", "file_kind": "image"}],
        )
        self.assertEqual(result.status, "unexpected_pass")

    def test_missing_citation_strict(self):
        case = self._make_case(
            location_type="page",
            location_value=5,
            location_strict=True,
        )
        result = score_case(
            case,
            "Answer text without page reference.",
            [{"file": "test.png", "file_kind": "image"}],
        )
        self.assertEqual(result.status, "missing_citation")


class TestRunRegression(unittest.TestCase):
    def _make_query_fn(self, responses: dict[str, dict]) -> Any:
        def query_fn(query: str) -> dict:
            return responses.get(query, {"ok": False, "status": "unreachable", "error": "not found", "reply": "", "sources": []})

        return query_fn

    def test_run_regression_all_pass(self):
        cases = [
            RegressionCase(
                id="case1", file_kind="image", expected_status="should_pass",
                query="How much?", source_file="payment.png",
                expected_location={"type": "page", "value": 1, "strict": False},
                expected_answer={"required_terms_all": ["68.00"], "required_terms_any": []},
            ),
        ]
        responses = {
            "How much?": {
                "ok": True, "status": "ok", "reply": "The payment was 68.00.",
                "sources": [{"file": "payment.png", "file_kind": "image"}],
                "source_id": "project-test",
            },
        }
        report = run_regression(cases, self._make_query_fn(responses), mode="query", source_id="project-test")
        self.assertEqual(report.summary["total"], 1)
        self.assertEqual(report.summary["pass"], 1)
        self.assertEqual(report.summary["fail"], 0)

    def test_run_regression_mixed(self):
        cases = [
            RegressionCase(
                id="case_pass", file_kind="image", expected_status="should_pass",
                query="Q1?", source_file="file1.png",
                expected_location={"type": "page", "value": 1, "strict": False},
                expected_answer={"required_terms_all": ["answer"], "required_terms_any": []},
            ),
            RegressionCase(
                id="case_fail_wrong_source", file_kind="image", expected_status="should_pass",
                query="Q2?", source_file="file2.png",
                expected_location={"type": "page", "value": 1, "strict": False},
                expected_answer={"required_terms_all": ["answer"], "required_terms_any": []},
            ),
            RegressionCase(
                id="case_known_gap", file_kind="pdf_drawing", expected_status="known_gap",
                query="Q3?", source_file="drawing.pdf",
                expected_location={"type": "page", "value": 5, "strict": False},
                expected_answer={"required_terms_all": ["rare_specific_term"], "required_terms_any": []},
            ),
        ]
        responses = {
            "Q1?": {
                "ok": True, "status": "ok", "reply": "The answer is here.",
                "sources": [{"file": "file1.png", "file_kind": "image"}],
                "source_id": "project-test",
            },
            "Q2?": {
                "ok": True, "status": "ok", "reply": "Wrong file answer.",
                "sources": [{"file": "document.docx", "file_kind": "office_doc"}],
                "source_id": "project-test",
            },
            "Q3?": {
                "ok": True, "status": "ok", "reply": "No window info.",
                "sources": [{"file": "drawing.pdf", "file_kind": "pdf_drawing"}],
                "source_id": "project-test",
            },
        }
        report = run_regression(cases, self._make_query_fn(responses), mode="query", source_id="project-test")
        self.assertEqual(report.summary["total"], 3)
        self.assertEqual(report.summary["pass"], 1)
        self.assertEqual(report.summary["wrong_source"], 1)
        self.assertEqual(report.summary["known_gap"], 1)
        self.assertEqual(report.summary["should_pass_ok"], 1)
        self.assertEqual(report.summary["should_pass_total"], 2)

    def test_service_unavailable(self):
        cases = [
            RegressionCase(
                id="case1", file_kind="image", expected_status="should_pass",
                query="Q?", source_file="file.png",
                expected_location={"type": "page", "value": 1, "strict": False},
                expected_answer={"required_terms_all": [], "required_terms_any": []},
            ),
        ]
        responses = {
            "Q?": {"ok": False, "status": "adapter_error", "reply": "", "sources": [], "error": "service down"},
        }
        report = run_regression(cases, self._make_query_fn(responses), mode="query", source_id="project-test")
        self.assertEqual(report.summary["service_unavailable"], 1)


class TestReportSerialization(unittest.TestCase):
    def test_report_to_dict(self):
        from core.project_quality_regression import RegressionReport, RegressionResult

        report = RegressionReport(
            run_id="test-run",
            generated_at="2026-06-09T12:00:00Z",
            source_id="project-test",
            mode="query",
            summary={"total": 1, "pass": 1, "fail": 0, "known_gap": 0, "meeting_false_positive": 0, "should_pass_ok": 1, "should_pass_total": 1},
            results=[
                RegressionResult(
                    case_id="case1",
                    status="pass",
                    first_hit_source="file.png",
                    first_hit_file_kind="image",
                    answer_text="Answer text.",
                    missing_terms_all=[],
                    missing_terms_any=[],
                    meeting_false_positive=False,
                ),
            ],
            known_gaps=[],
        )
        d = regression_report_to_dict(report)
        self.assertEqual(d["run_id"], "test-run")
        self.assertEqual(len(d["results"]), 1)
        self.assertEqual(d["results"][0]["case_id"], "case1")
        self.assertEqual(d["results"][0]["status"], "pass")
        self.assertIn("summary", d)
        self.assertIn("known_gaps", d)


class TestReportStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reports_dir = Path(self._tmpdir.name) / "quality-reports"
        self.reports_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_report(self) -> Any:
        from core.project_quality_regression import RegressionReport, RegressionResult

        return RegressionReport(
            run_id="test-run-001",
            generated_at="2026-06-09T12:00:00Z",
            source_id="project-test",
            mode="offline",
            summary={
                "total": 2, "pass": 1, "fail": 1, "wrong_source": 1,
                "missing_answer_point": 0, "missing_citation": 0,
                "known_gap": 0, "unexpected_pass": 0,
                "service_unavailable": 0, "meeting_false_positive": 0,
                "should_pass_ok": 1, "should_pass_total": 2,
                "pass_rate_should_pass": "1/2 = 50%",
            },
            results=[
                RegressionResult(case_id="c1", status="pass"),
                RegressionResult(case_id="c2", status="wrong_source", error="wrong kind"),
            ],
            known_gaps=[],
        )

    def test_store_and_load_report(self):
        report = self._make_report()
        stored = store_report(report, project_slug="test-project", reports_dir=self.reports_dir)
        self.assertTrue(stored.exists())

        loaded = json.loads(stored.read_text(encoding="utf-8"))
        self.assertEqual(loaded["run_id"], "test-run-001")
        self.assertEqual(len(loaded["results"]), 2)

    def test_list_reports(self):
        report = self._make_report()
        store_report(report, project_slug="test-project", reports_dir=self.reports_dir)

        reports = list_reports(project_slug="test-project")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["run_id"], "test-run-001")

    def test_summary_to_text(self):
        summary = {
            "total": 14, "pass": 3, "fail": 3,
            "wrong_source": 1, "missing_answer_point": 1, "missing_citation": 1,
            "known_gap": 8, "unexpected_pass": 0, "service_unavailable": 0,
            "meeting_false_positive": 1,
            "should_pass_ok": 3, "should_pass_total": 3,
            "pass_rate_should_pass": "3/3 = 100%",
        }
        text = report_summary_to_text(summary)
        self.assertIn("Total: 14", text)
        self.assertIn("Pass: 3", text)
        self.assertIn("Should-pass rate: 3/3 = 100%", text)


if __name__ == "__main__":
    unittest.main()
