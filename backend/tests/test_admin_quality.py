from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.features.knowledge.quality.report import (
    store_report,
    list_reports,
    load_report,
    report_summary_to_text,
)


class TestListReports(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reports_base = Path(self._tmpdir.name) / "quality-reports"
        self.reports_base.mkdir(parents=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _stub_report(self, run_id: str, pass_count: int, fail_count: int):
        return {
            "run_id": run_id,
            "generated_at": f"2026-06-09T12:00:00Z",
            "mode": "offline",
            "source_id": "project-test",
            "summary": {
                "total": pass_count + fail_count,
                "pass": pass_count,
                "fail": fail_count,
                "wrong_source": 0,
                "missing_answer_point": 0,
                "missing_citation": 0,
                "known_gap": 0,
                "unexpected_pass": 0,
                "service_unavailable": 0,
                "meeting_false_positive": 0,
                "should_pass_ok": pass_count,
                "should_pass_total": pass_count + fail_count,
                "pass_rate_should_pass": f"{pass_count}/{pass_count + fail_count} = 100%",
            },
            "results": [
                {"case_id": f"case{i}", "status": "pass" if i < pass_count else "wrong_source"}
                for i in range(pass_count + fail_count)
            ],
            "known_gaps": [],
        }

    def test_list_empty_when_no_reports(self):
        reports = list_reports(limit=10)
        self.assertEqual(reports, [])

    def test_list_reports_from_aggregated(self):
        """list_reports reads from _preprocessed/_quality-reports/."""
        # Write a report directly to the aggregated directory
        agg_dir = self.reports_base / "test-project"
        agg_dir.mkdir(parents=True)
        report_data = self._stub_report("run-001", 3, 0)
        (agg_dir / "run-001.json").write_text(json.dumps(report_data, ensure_ascii=False), encoding="utf-8")

        with patch(
            "app.features.knowledge.quality.report.AGGREGATED_REPORTS_DIR",
            self.reports_base,
        ):
            reports = list_reports(project_slug="test-project", limit=10)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["run_id"], "run-001")
            self.assertEqual(reports[0]["summary"]["pass"], 3)

    def test_list_multiple_projects(self):
        """list_reports with project_slug scopes to a single project."""
        for project in ["proj-a", "proj-b"]:
            dir_path = self.reports_base / project
            dir_path.mkdir(parents=True)
            (dir_path / "run-latest.json").write_text(
                json.dumps(self._stub_report("run-latest", 5, 1), ensure_ascii=False),
                encoding="utf-8",
            )

        with patch(
            "app.features.knowledge.quality.report.AGGREGATED_REPORTS_DIR",
            self.reports_base,
        ):
            reports_a = list_reports(project_slug="proj-a", limit=10)
            self.assertEqual(len(reports_a), 1)
            self.assertEqual(reports_a[0]["summary"]["pass"], 5)

            reports_b = list_reports(project_slug="proj-b", limit=10)
            self.assertEqual(len(reports_b), 1)
            self.assertEqual(reports_b[0]["summary"]["pass"], 5)

    def test_list_limit(self):
        """list_reports respects the limit parameter."""
        for i in range(5):
            dir_path = self.reports_base / f"proj-{i}"
            dir_path.mkdir(parents=True)
            (dir_path / f"run-{i:03d}.json").write_text(
                json.dumps(self._stub_report(f"run-{i:03d}", 3, 0), ensure_ascii=False),
                encoding="utf-8",
            )

        with patch(
            "app.features.knowledge.quality.report.AGGREGATED_REPORTS_DIR",
            self.reports_base,
        ):
            reports = list_reports(limit=3)
            self.assertLessEqual(len(reports), 3)


class TestStoreAndLoad(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.reports_dir = Path(self._tmpdir.name) / "reports"
        self.reports_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_round_trip(self):
        from app.features.knowledge.quality.regression import RegressionReport, RegressionResult

        report = RegressionReport(
            run_id="test-roundtrip",
            generated_at="2026-06-09T12:00:00Z",
            source_id="project-test",
            mode="offline",
            summary={
                "total": 2, "pass": 1, "fail": 1, "wrong_source": 1,
                "missing_answer_point": 0, "missing_citation": 0,
                "known_gap": 0, "unexpected_pass": 0, "service_unavailable": 0,
                "meeting_false_positive": 0, "should_pass_ok": 1, "should_pass_total": 2,
                "pass_rate_should_pass": "1/2 = 50%",
            },
            results=[
                type("obj", (object,), {
                    "case_id": "c1", "status": "pass", "first_hit_source": "f1",
                    "first_hit_file_kind": "image", "answer_text": "Answer",
                    "citation": None, "missing_terms_all": [], "missing_terms_any": [],
                    "meeting_false_positive": False, "error": None,
                })(),
                type("obj", (object,), {
                    "case_id": "c2", "status": "wrong_source",
                    "first_hit_source": "f2", "first_hit_file_kind": "meeting",
                    "answer_text": "Wrong", "citation": None,
                    "missing_terms_all": [], "missing_terms_any": [],
                    "meeting_false_positive": True, "error": "wrong kind",
                })(),
            ],
            known_gaps=[],
        )
        # store with explicit reports_dir
        stored = store_report(report, project_slug="test-proj", reports_dir=self.reports_dir)
        self.assertTrue(stored.exists())

        loaded = load_report(stored)
        self.assertEqual(loaded["run_id"], "test-roundtrip")
        self.assertEqual(len(loaded["results"]), 2)


class TestReportSummaryToText(unittest.TestCase):
    def test_format(self):
        summary = {
            "total": 14, "pass": 3, "fail": 3,
            "wrong_source": 1, "missing_answer_point": 1, "missing_citation": 1,
            "known_gap": 8, "unexpected_pass": 0, "service_unavailable": 0,
            "meeting_false_positive": 1, "should_pass_ok": 3, "should_pass_total": 3,
            "pass_rate_should_pass": "3/3 = 100%",
        }
        text = report_summary_to_text(summary)
        self.assertIn("Total: 14", text)
        self.assertIn("Pass: 3", text)
        self.assertIn("Should-pass rate: 3/3 = 100%", text)


if __name__ == "__main__":
    unittest.main()
