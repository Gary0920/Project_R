from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.features.workspaces.ingest.jobs import (
    mark_workspace_ingest_job_completed,
    mark_workspace_ingest_job_failed,
    mark_workspace_ingest_job_queued,
    mark_workspace_ingest_job_running,
    workspace_ingest_request_from_job,
    workspace_ingest_run_id_from_job,
)


class WorkspaceIngestJobsTests(unittest.TestCase):
    def test_queued_payload_preserves_request_and_run_id(self):
        job = SimpleNamespace(
            id=11,
            status="queued",
            created_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
            result_json="",
        )
        workspace = SimpleNamespace(id=7, workspace_kind="project", name="BFI")

        mark_workspace_ingest_job_queued(
            job,
            workspace=workspace,
            ingest_request={"path": "03-会议纪要", "recursive": True, "target_type": "directory"},
            run_id="run-queued",
        )

        payload = json.loads(job.result_json)
        self.assertEqual(payload["run_status"], "queued")
        self.assertEqual(payload["run"]["status"], "queued")
        self.assertEqual(payload["run"]["status_history"][0]["status"], "queued")
        self.assertEqual(workspace_ingest_run_id_from_job(job), "run-queued")

    def test_running_payload_preserves_request_and_run_id(self):
        job = SimpleNamespace(
            id=12,
            status="queued",
            created_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
            started_at=None,
            result_json=json.dumps({"request": {"path": "03-会议纪要", "recursive": True, "target_type": "directory"}}),
        )
        workspace = SimpleNamespace(id=7, workspace_kind="project", name="BFI")
        request = workspace_ingest_request_from_job(job)

        history = mark_workspace_ingest_job_running(
            job,
            workspace=workspace,
            ingest_request=request,
            run_id="run-12",
            started_at=datetime(2026, 6, 11, 0, 1, tzinfo=timezone.utc),
        )

        payload = json.loads(job.result_json)
        self.assertEqual(job.status, "running")
        self.assertEqual(payload["run_id"], "run-12")
        self.assertEqual(payload["run"]["status"], "preprocessing")
        self.assertEqual(payload["request"]["path"], "03-会议纪要")
        self.assertEqual([item["status"] for item in history], ["queued", "preprocessing"])
        self.assertEqual(workspace_ingest_run_id_from_job(job), "run-12")

    def test_completed_payload_uses_result_status(self):
        job = SimpleNamespace(status="running", result_json="", error_message="", finished_at=None)

        mark_workspace_ingest_job_completed(
            job,
            {"ok": False, "gbrain_error": "sync failed", "run_status": "sync_pending"},
            finished_at=datetime(2026, 6, 11, 0, 2, tzinfo=timezone.utc),
        )

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.error_message, "sync failed")
        self.assertEqual(json.loads(job.result_json)["run_status"], "sync_pending")

    def test_failed_payload_includes_error_history(self):
        job = SimpleNamespace(
            id=14,
            status="running",
            workspace_id=7,
            created_at=datetime(2026, 6, 11, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 11, 0, 1, tzinfo=timezone.utc),
            finished_at=None,
            result_json="{}",
            error_message="",
        )
        workspace = SimpleNamespace(id=7, workspace_kind="project", name="BFI")

        mark_workspace_ingest_job_failed(
            job,
            workspace=workspace,
            request={"path": "bad.md", "recursive": False},
            run_id="run-failed",
            error="boom",
            finished_at=datetime(2026, 6, 11, 0, 3, tzinfo=timezone.utc),
        )

        payload = json.loads(job.result_json)
        self.assertEqual(job.status, "failed")
        self.assertEqual(payload["run"]["status"], "failed")
        self.assertEqual(payload["run"]["error"], "boom")
        self.assertEqual(payload["run"]["status_history"][-1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
