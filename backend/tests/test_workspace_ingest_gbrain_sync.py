from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.workspace_ingest_gbrain_sync import sync_workspace_gbrain_source


class FakeAdapter:
    def __init__(self, *, sync_status: str = "ok", think_result: dict | None = None):
        self.settings = SimpleNamespace(
            think_enabled=True,
            think_source_scope_verified=True,
            think_project_clients_enabled=True,
        )
        self.sync_status = sync_status
        self.think_result = think_result if think_result is not None else {"ok": True, "status": "ready"}
        self.calls: list[str] = []

    def ensure_project_source(self, workspace):
        self.calls.append("ensure_project_source")
        return {"ok": True, "source": {"status": "registered"}}

    def sync_project_source(self, workspace, **kwargs):
        self.calls.append("sync_project_source")
        if self.sync_status == "ok":
            return {"status": "ok"}
        return {"status": self.sync_status, "error": "sync boom"}

    def ensure_customer_source(self, workspace):
        self.calls.append("ensure_customer_source")
        return {"ok": True, "source": {"status": "registered"}}

    def sync_customer_source(self, workspace, **kwargs):
        self.calls.append("sync_customer_source")
        return {"status": "ok"}

    def ensure_think_source_client(self, source_id: str):
        self.calls.append(f"ensure_think_source_client:{source_id}")
        return self.think_result


class WorkspaceIngestGBrainSyncTests(unittest.TestCase):
    def test_no_compiled_files_skips_gbrain_calls(self):
        adapter = FakeAdapter()

        result = sync_workspace_gbrain_source(
            adapter,
            SimpleNamespace(id=1),
            workspace_kind="project",
            compiled_files=0,
            source_id="project-bfi-1",
        )

        self.assertTrue(result["sync_ok"])
        self.assertEqual(result["gbrain_sync_status"], "not_required_no_compiled_files")
        self.assertEqual(adapter.calls, [])

    def test_project_sync_failure_reports_sync_error_without_think_client(self):
        adapter = FakeAdapter(sync_status="cli_error")

        result = sync_workspace_gbrain_source(
            adapter,
            SimpleNamespace(id=2),
            workspace_kind="project",
            compiled_files=1,
            source_id="project-bfi-2",
        )

        self.assertFalse(result["sync_ok"])
        self.assertEqual(result["gbrain_status"], "registered")
        self.assertEqual(result["gbrain_sync_status"], "cli_error")
        self.assertEqual(result["gbrain_error"], "sync boom")
        self.assertNotIn("ensure_think_source_client:project-bfi-2", adapter.calls)

    def test_customer_think_client_failure_uses_customer_error(self):
        adapter = FakeAdapter(think_result={"ok": False, "status": "failed"})

        result = sync_workspace_gbrain_source(
            adapter,
            SimpleNamespace(id=3),
            workspace_kind="customer",
            compiled_files=1,
            source_id="customer-crm",
        )

        self.assertTrue(result["sync_ok"])
        self.assertFalse(result["gbrain_think_ok"])
        self.assertEqual(result["gbrain_think_status"], "failed")
        self.assertEqual(result["gbrain_error"], "GBrain customer think OAuth client preparation failed")


if __name__ == "__main__":
    unittest.main()
