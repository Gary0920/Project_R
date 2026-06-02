import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.gbrain import (
    CUSTOMER_REFERENCE_SOURCE_ID,
    GBrainAdapter,
    GBrainSettings,
    project_source_id_for_workspace,
    project_source_registration_plan,
)
from core.knowledge_sources import KnowledgeSources


class _RecordingQueryAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    def query(self, query: str, *, source_id: str | None = None, limit: int = 5, expand: bool = False, detail: str = "medium"):
        self.calls.append(
            {
                "query": query,
                "source_id": source_id,
                "limit": limit,
                "expand": expand,
                "detail": detail,
            }
        )
        return {
            "status": "ok",
            "result": [
                {
                    "slug": "meetings/kickoff",
                    "title": "Kickoff Meeting",
                    "chunk_text": "中文：项目启动会决定。\nEnglish: Project kickoff decision.",
                    "score": 0.81,
                }
            ],
        }


class _RecordingThinkAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    def think(self, query: str, *, source_id: str | None = None):
        self.calls.append({"query": query, "source_id": source_id})
        return {
            "status": "ok",
            "result": {
                "answer": "Aaron Morris belongs to the customer intelligence source.",
                "modelUsed": "deepseek:deepseek-chat",
                "warnings": [],
                "citations": [{"page_slug": "clients/01_clients__aaron-morris-75b5f010"}],
            },
        }


class _StatusAdapter(GBrainAdapter):
    def __init__(self, local_path: Path):
        super().__init__(
            GBrainSettings(
                enabled=True,
                base_url="http://127.0.0.1:3131",
                service_bearer_token="test-token",
                local_git_enabled=False,
            )
        )
        self.local_path = local_path
        self.calls: list[dict] = []

    def _call_mcp_tool(self, name: str, arguments: dict | None = None):
        self.calls.append({"name": name, "arguments": arguments or {}})
        return {
            "status": "ok",
            "result": {
                "id": "project-bfi-7",
                "local_path": str(self.local_path),
                "page_count": 3,
            },
        }


class GBrainProjectSourceTests(unittest.TestCase):
    def test_project_source_id_is_stable_across_project_rename(self):
        before = SimpleNamespace(id=42, brand="BFI", slug="BG001", name="旧项目名")
        after = SimpleNamespace(id=42, brand="BFI", slug="BG001-renamed", name="新项目名")

        self.assertEqual(project_source_id_for_workspace(before), "project-bfi-42")
        self.assertEqual(project_source_id_for_workspace(after), "project-bfi-42")

    def test_project_source_registration_plan_uses_project_derived_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = SimpleNamespace(
                id=7,
                brand="BFI",
                slug="BG007",
                name="BG007",
                storage_path=str(Path(temp_dir) / "project" / "BFI" / "BG007"),
            )

            plan = project_source_registration_plan(workspace)

        self.assertEqual(plan["source_id"], "project-bfi-7")
        self.assertTrue(plan["path"].endswith("project\\BFI\\BG007\\derived") or plan["path"].endswith("project/BFI/BG007/derived"))
        self.assertFalse(plan["federated"])
        self.assertIn("--no-federated", plan["operator_command"])

    def test_project_source_status_checks_expected_source_id_and_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            derived = root / "derived"
            workspace = SimpleNamespace(
                id=7,
                brand="BFI",
                slug="BG007",
                name="BG007",
                storage_path=str(root),
                workspace_kind="project",
            )
            adapter = _StatusAdapter(derived)

            status = adapter.project_source_status(workspace)

        self.assertEqual(adapter.calls[0]["arguments"]["id"], "project-bfi-7")
        self.assertEqual(status["status"], "registered")
        self.assertTrue(status["registered"])
        self.assertTrue(status["path_matches"])

    def test_project_query_uses_explicit_gbrain_source_scope(self):
        workspace = SimpleNamespace(
            id=7,
            brand="BFI",
            slug="BG007",
            name="BG007",
            workspace_kind="project",
        )
        adapter = _RecordingQueryAdapter()
        sources = KnowledgeSources(lambda: adapter).search_project_gbrain_sources(workspace, "启动会决定是什么")

        self.assertEqual(adapter.calls[0]["source_id"], "project-bfi-7")
        self.assertEqual(adapter.calls[0]["limit"], 5)
        self.assertEqual(sources[0]["file"], "gbrain:project-bfi-7/meetings/kickoff")
        self.assertEqual(sources[0]["type"], "gbrain_project_source")
        self.assertEqual(sources[0]["authority_level"], "project")

    def test_customer_query_uses_unified_customer_reference_source_scope(self):
        workspace = SimpleNamespace(
            id=9,
            brand="CUSTOMER",
            slug="lucerna",
            name="Lucerna",
            workspace_kind="customer",
        )
        adapter = _RecordingQueryAdapter()
        sources = KnowledgeSources(lambda: adapter).search_scoped_workspace_gbrain_sources(workspace, "客户决策链是什么")

        self.assertEqual(adapter.calls[0]["source_id"], CUSTOMER_REFERENCE_SOURCE_ID)
        self.assertEqual(adapter.calls[0]["limit"], 5)
        self.assertEqual(sources[0]["file"], "gbrain:customer-reference/meetings/kickoff")
        self.assertEqual(sources[0]["type"], "gbrain_customer_source")
        self.assertEqual(sources[0]["authority_level"], "customer")

    def test_customer_think_uses_unified_customer_reference_source_scope(self):
        workspace = SimpleNamespace(
            id=9,
            brand="CUSTOMER",
            slug="lucerna",
            name="Lucerna",
            workspace_kind="customer",
        )

        class _Query:
            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return workspace

        class _Db:
            def query(self, _model):
                return _Query()

        adapter = _RecordingThinkAdapter()
        response = KnowledgeSources(lambda: adapter).think(_Db(), "Aaron Morris 是谁？", workspace_id=workspace.id)

        self.assertTrue(response["ok"])
        self.assertEqual(response["source_id"], CUSTOMER_REFERENCE_SOURCE_ID)
        self.assertEqual(adapter.calls[0]["source_id"], CUSTOMER_REFERENCE_SOURCE_ID)

    def test_project_query_sources_include_derived_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project" / "BFI" / "BG007"
            derived = root / "derived" / "meetings"
            derived.mkdir(parents=True)
            (derived / "kickoff.md").write_text(
                "---\n"
                "title: Kickoff Meeting\n"
                "project_r_source_file: 03-会议纪要/kickoff.md\n"
                "---\n"
                "# Kickoff Meeting\n\n"
                "## Page 3\n\n"
                "中文：项目启动会决定。\n"
                "English: Project kickoff decision.\n",
                encoding="utf-8",
            )
            workspace = SimpleNamespace(
                id=7,
                brand="BFI",
                slug="BG007",
                name="BG007",
                storage_path=str(root),
                workspace_kind="project",
            )
            adapter = _RecordingQueryAdapter()

            sources = KnowledgeSources(lambda: adapter).search_project_gbrain_sources(workspace, "启动会决定是什么")

            self.assertEqual(sources[0]["derived_file"], "meetings/kickoff.md")
            self.assertEqual(sources[0]["source_file"], "03-会议纪要/kickoff.md")
            self.assertEqual(sources[0]["source_page"], 3)
            self.assertIn("Location", sources[0]["content"])


if __name__ == "__main__":
    unittest.main()
