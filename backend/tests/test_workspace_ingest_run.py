from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from app.features.workspaces.ingest.run import (
    derive_workspace_ingest_run_status,
    finalize_workspace_ingest_manifest,
    overall_workspace_ingest_rag_status,
    workspace_ingest_item_rag_status,
    workspace_ingest_manifest_counts,
    workspace_ingest_result_payload,
    workspace_ingest_status_event,
    workspace_ingest_summary_text,
)


class WorkspaceIngestRunTests(unittest.TestCase):
    def test_run_status_prefers_sync_pending_for_compiled_files_without_sync(self):
        status = derive_workspace_ingest_run_status(
            compiled_files=1,
            failed_files=0,
            pending_extractor_capability_files=0,
            pending_transcription_files=0,
            skipped_files=0,
            sync_ok=False,
            ok=False,
        )

        self.assertEqual(status, "sync_pending")

    def test_finalize_manifest_normalizes_items_and_writes_run_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = SimpleNamespace(id=7, workspace_kind="project", name="BFI Test")
            manifest = {
                "source_id": "project-bfi-7",
                "manifests_path": str(root / "manifests"),
                "runs_path": str(root / "runs"),
                "summary": {"compiled": 1},
                "items": [
                    {
                        "source_file": "03-会议纪要/kickoff.md",
                        "status": "compiled",
                        "source_sha256": "abc",
                        "target_file": "meetings/kickoff.md",
                    }
                ],
            }
            history = [workspace_ingest_status_event("preprocessing", "开始")]

            finalize_workspace_ingest_manifest(
                workspace,
                manifest,
                run_id="run-1",
                run_status="synced",
                source_path="03-会议纪要",
                recursive=True,
                started_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
                finished_at=datetime(2026, 6, 10, 0, 1, tzinfo=timezone.utc),
                status_history=history,
                sync_ok=True,
                gbrain_sync_status="ok",
                gbrain_error=None,
                gbrain_think_status="disabled",
            )

            item = manifest["items"][0]
            self.assertEqual(manifest["run_status"], "synced")
            self.assertEqual(manifest["run"]["workspace_id"], 7)
            self.assertEqual(item["preprocess_status"], "compiled")
            self.assertEqual(item["source_hash"], "abc")
            self.assertEqual(item["gbrain_ready_file"], "meetings/kickoff.md")
            self.assertEqual(item["sync_status"], "synced")
            self.assertTrue((root / "runs" / "run-1.json").exists())
            persisted = json.loads((root / "manifests" / "project-source-ingest-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["run"]["run_id"], "run-1")

    def test_result_payload_and_summary_are_stable(self):
        payload = {
            "workspace_id": 3,
            "indexed_files": 2,
            "compiled_files": 2,
            "pending_extractor_capability_files": 1,
            "pending_transcription_files": 0,
            "failed_files": 0,
            "gbrain_source_id": "project-bfi-3",
            "gbrain_sync_status": "ok",
            "rag_status": "indexed",
            "run_id": "run-3",
            "run_status": "synced",
            "manifest": {"run": {"status": "synced"}, "summary": {"compiled": 2}},
        }

        result = workspace_ingest_result_payload(payload)

        self.assertEqual(result["run"]["status"], "synced")
        self.assertEqual(result["manifest_summary"], {"compiled": 2})
        self.assertIn("已编译 2 个", workspace_ingest_summary_text(payload))

    def test_overall_rag_status_keeps_file_panel_status_priority(self):
        self.assertEqual(
            overall_workspace_ingest_rag_status(
                ok=True,
                indexed_files=0,
                failed_files=0,
                pending_extractor_capability_files=1,
                pending_transcription_files=0,
                skipped_files=0,
            ),
            "pending_extractor_capability",
        )
        self.assertEqual(
            overall_workspace_ingest_rag_status(
                ok=False,
                indexed_files=1,
                failed_files=0,
                pending_extractor_capability_files=0,
                pending_transcription_files=0,
                skipped_files=0,
            ),
            "pending",
        )

    def test_item_rag_status_tracks_sync_and_preprocess_state(self):
        self.assertEqual(workspace_ingest_item_rag_status({"status": "compiled"}, sync_ok=True), "synced")
        self.assertEqual(workspace_ingest_item_rag_status({"status": "compiled"}, sync_ok=False), "sync_pending")
        self.assertEqual(
            workspace_ingest_item_rag_status({"status": "pending_extractor_capability"}, sync_ok=False),
            "pending_extractor_capability",
        )
        self.assertEqual(workspace_ingest_item_rag_status({"status": "unknown"}, sync_ok=True), "pending")

    def test_manifest_counts_normalizes_missing_summary_values(self):
        counts = workspace_ingest_manifest_counts(
            {
                "source_id": "project-bfi-7",
                "summary": {
                    "compiled": 2,
                    "pending_extractor_capability": 1,
                    "pending_transcription": None,
                },
            }
        )

        self.assertEqual(counts["source_id"], "project-bfi-7")
        self.assertEqual(counts["compiled_files"], 2)
        self.assertEqual(counts["pending_extractor_capability_files"], 1)
        self.assertEqual(counts["pending_transcription_files"], 0)


if __name__ == "__main__":
    unittest.main()
