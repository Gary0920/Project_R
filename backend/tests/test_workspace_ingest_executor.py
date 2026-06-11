from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from core.workspace_ingest_executor import execute_workspace_ingest_core


class _FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return []


class _FakeDb:
    def query(self, *args, **kwargs):
        return _FakeQuery()

    def add(self, value):
        raise AssertionError("no metadata should be created for empty manifests")

    def flush(self):
        raise AssertionError("no metadata should be flushed for empty manifests")


class _FakeAdapter:
    def __init__(self):
        self.settings = SimpleNamespace(
            think_enabled=False,
            think_source_scope_verified=False,
            think_project_clients_enabled=False,
        )


class WorkspaceIngestExecutorTests(unittest.TestCase):
    def test_unsupported_workspace_returns_failed_payload_without_compile(self):
        def fail_compile(*args, **kwargs):
            raise AssertionError("compiler should not be called")

        payload = execute_workspace_ingest_core(
            _FakeDb(),
            SimpleNamespace(id=9, workspace_kind="user", name="User"),
            1,
            source_path="",
            recursive=True,
            run_id="run-user",
            started_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
            status_history=[],
            compile_project=fail_compile,
            compile_customer=fail_compile,
            adapter_factory=_FakeAdapter,
        )

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["run_status"], "failed")
        self.assertEqual(payload["gbrain_status"], "not_applicable_private_workspace")
        self.assertIsNone(payload["manifest"])

    def test_project_no_compiled_files_builds_ignored_payload(self):
        def compile_project(workspace, source_path, recursive):
            return {
                "source_id": "project-bfi-7",
                "summary": {
                    "total": 1,
                    "compiled": 0,
                    "pending_extractor_capability": 0,
                    "pending_transcription": 0,
                    "skipped": 1,
                    "failed": 0,
                },
                "items": [],
            }

        def fail_customer(*args, **kwargs):
            raise AssertionError("customer compiler should not be called")

        payload = execute_workspace_ingest_core(
            _FakeDb(),
            SimpleNamespace(id=7, workspace_kind="project", name="BFI", storage_path=""),
            1,
            source_path="03-会议纪要",
            recursive=True,
            run_id="run-project",
            started_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
            status_history=[],
            compile_project=compile_project,
            compile_customer=fail_customer,
            adapter_factory=_FakeAdapter,
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["run_status"], "ignored")
        self.assertEqual(payload["gbrain_sync_status"], "not_required_no_compiled_files")
        self.assertEqual(payload["skipped_files"], 1)
        self.assertEqual(payload["manifest"]["run"]["run_id"], "run-project")


if __name__ == "__main__":
    unittest.main()
