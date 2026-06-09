import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "gbrain_project_quality_regression.py"
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_project_quality_regression_cases.json"

spec = importlib.util.spec_from_file_location("gbrain_project_quality_regression", SCRIPT_PATH)
gbrain_project_quality_regression = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gbrain_project_quality_regression)


class GBrainProjectQualityRegressionTests(unittest.TestCase):
    def test_current_fixture_is_valid_and_covers_expected_formats(self):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

        report = gbrain_project_quality_regression.validate_fixture(data)

        self.assertEqual(report["failures"], [])
        self.assertEqual(report["case_count"], 14)
        self.assertGreaterEqual(report["status_counts"].get("should_pass", 0), 1)
        self.assertGreaterEqual(report["status_counts"].get("known_gap", 0), 1)
        for file_kind in [
            "pdf_drawing",
            "pdf_schedule",
            "image",
            "meeting_transcript_docx",
            "meeting_media",
            "email",
            "spreadsheet",
            "office_doc",
        ]:
            self.assertIn(file_kind, report["file_kind_counts"])

    def test_validate_fixture_rejects_missing_source_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            workspace = project_root / "backend/workspace_data/project/TEST/TEST"
            workspace.mkdir(parents=True)
            data = {
                "fixture_scope": {
                    "workspace_path": "backend/workspace_data/project/TEST/TEST",
                    "uses_real_project_files": True,
                    "requires_same_project_identity": False,
                },
                "cases": [
                    {
                        "id": "missing_file",
                        "file_kind": "email",
                        "expected_status": "should_pass",
                        "query": "test",
                        "source_file": "99-未归档文件/missing.eml",
                        "expected_location": {"type": "text_span", "value": "body", "strict": False},
                        "expected_answer": {
                            "required_terms_all": [],
                            "required_terms_any": ["test"],
                        },
                    }
                ],
            }

            report = gbrain_project_quality_regression.validate_fixture(data, project_root=project_root)

            self.assertFalse(report["ok"])
            self.assertTrue(any("source_file does not exist" in failure for failure in report["failures"]))

    def test_validate_fixture_rejects_invalid_expected_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            workspace = project_root / "backend/workspace_data/project/TEST/TEST"
            source = workspace / "sample.docx"
            source.parent.mkdir(parents=True)
            source.write_text("sample", encoding="utf-8")
            data = {
                "fixture_scope": {
                    "workspace_path": "backend/workspace_data/project/TEST/TEST",
                    "uses_real_project_files": True,
                    "requires_same_project_identity": False,
                },
                "cases": [
                    {
                        "id": "bad_status",
                        "file_kind": "office_doc",
                        "expected_status": "todo",
                        "query": "test",
                        "source_file": "sample.docx",
                        "expected_location": {"type": "text_span", "value": "body", "strict": False},
                        "expected_answer": {
                            "required_terms_all": [],
                            "required_terms_any": ["test"],
                        },
                    }
                ],
            }

            report = gbrain_project_quality_regression.validate_fixture(data, project_root=project_root)

            self.assertFalse(report["ok"])
            self.assertTrue(any("invalid expected_status" in failure for failure in report["failures"]))

    def test_workspace_preflight_builds_test_project_source_plan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            workspace = project_root / "backend/workspace_data/project/TEST/TEST"
            workspace.mkdir(parents=True)
            db_path = project_root / "backend/app.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE workspaces (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        slug TEXT,
                        brand TEXT,
                        workspace_kind TEXT,
                        storage_path TEXT,
                        is_archived INTEGER
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO workspaces (id, name, slug, brand, workspace_kind, storage_path, is_archived)
                    VALUES (6, 'TEST', 'TEST', 'TEST', 'project', ?, 0)
                    """,
                    (str(workspace.resolve()),),
                )
                connection.commit()
            finally:
                connection.close()
            data = {
                "fixture_scope": {
                    "workspace_path": "backend/workspace_data/project/TEST/TEST",
                    "uses_real_project_files": True,
                    "requires_same_project_identity": False,
                },
                "cases": [],
            }

            old_preprocessed_root = os.environ.get("GBRAIN_PREPROCESSED_ROOT")
            os.environ["GBRAIN_PREPROCESSED_ROOT"] = str(project_root / "backend/workspace_data/_preprocessed")
            try:
                report = gbrain_project_quality_regression.build_workspace_preflight(
                    data,
                    project_root=project_root,
                    db_path=db_path,
                )
            finally:
                if old_preprocessed_root is None:
                    os.environ.pop("GBRAIN_PREPROCESSED_ROOT", None)
                else:
                    os.environ["GBRAIN_PREPROCESSED_ROOT"] = old_preprocessed_root

            self.assertEqual(report["failures"], [])
            self.assertEqual(report["source_id"], "project-test-6")
            ready_path = report["paths"]["gbrain_ready"].replace("\\", "/")
            self.assertTrue(ready_path.endswith("backend/workspace_data/_preprocessed/project/TEST/6-TEST/gbrain-ready"))
            self.assertEqual(Path(report["registration_plan"]["path"]), Path(report["paths"]["gbrain_ready"]))

    def test_workspace_preflight_rejects_missing_workspace_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            workspace = project_root / "backend/workspace_data/project/TEST/TEST"
            workspace.mkdir(parents=True)
            db_path = project_root / "backend/app.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE workspaces (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        slug TEXT,
                        brand TEXT,
                        workspace_kind TEXT,
                        storage_path TEXT,
                        is_archived INTEGER
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()
            data = {
                "fixture_scope": {
                    "workspace_path": "backend/workspace_data/project/TEST/TEST",
                    "uses_real_project_files": True,
                    "requires_same_project_identity": False,
                },
                "cases": [],
            }

            report = gbrain_project_quality_regression.build_workspace_preflight(
                data,
                project_root=project_root,
                db_path=db_path,
            )

            self.assertFalse(report["ok"])
            self.assertTrue(any("no project workspace" in failure for failure in report["failures"]))


if __name__ == "__main__":
    unittest.main()
