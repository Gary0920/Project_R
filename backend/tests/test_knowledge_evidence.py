import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.features.knowledge.evidence import enrich_sources_with_evidence
from app.features.knowledge.gbrain import GBrainSettings
from app.features.knowledge.sources import KnowledgeSources


class FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class FakeDb:
    def query(self, *args, **kwargs):
        return FakeQuery()


class FakeThinkAdapter:
    def think(self, query: str, *, source_id: str | None = None):
        return {
            "status": "ok",
            "result": {
                "answer": "需要保留书面记录。",
                "citations": [{"page_slug": "rules/written-record", "row_num": 3}],
                "gaps": [],
                "conflicts": [],
                "warnings": [],
                "modelUsed": "fake-think",
            },
        }


class KnowledgeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.preprocessed_root = self.root / "_preprocessed"
        self.env = patch.dict(os.environ, {"GBRAIN_PREPROCESSED_ROOT": str(self.preprocessed_root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    def settings(self) -> GBrainSettings:
        company = self.preprocessed_root / "company" / "company-wiki" / "gbrain-ready"
        company.mkdir(parents=True, exist_ok=True)
        return GBrainSettings(enabled=False, base_url="", derived_path=company, local_git_enabled=False)

    def project_workspace(self, workspace_id: int = 7):
        return SimpleNamespace(
            id=workspace_id,
            brand="BFI",
            slug=f"BG{workspace_id:03d}",
            name=f"BG{workspace_id:03d}",
            storage_path=str(self.root / "workspace" / f"BG{workspace_id:03d}"),
            workspace_kind="project",
        )

    def customer_workspace(self):
        return SimpleNamespace(
            id=9,
            brand="BFI",
            slug="CRM",
            name="CRM",
            storage_path=str(self.root / "workspace" / "CRM"),
            workspace_kind="customer",
        )

    def project_ready(self, workspace) -> Path:
        return self.preprocessed_root / "project" / workspace.brand / f"{workspace.id}-{workspace.slug}" / "gbrain-ready"

    def customer_ready(self, workspace) -> Path:
        return self.preprocessed_root / "customer" / f"{workspace.id}-{workspace.slug.lower()}" / "gbrain-ready"

    def write_page(self, root: Path, rel: str, *, title: str = "Readable Title", source_file: str = "docs/source.md", body: str = "正文第一段。"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\ntitle: {title}\nproject_r_source_file: {source_file}\ngbrain_source_id: company-wiki\n---\n\n{body}\n",
            encoding="utf-8",
        )
        return path

    def test_enriches_company_and_project_sources_from_each_own_root(self):
        settings = self.settings()
        workspace = self.project_workspace()
        company_root = settings.derived_path
        project_root = self.project_ready(workspace)
        self.write_page(company_root, "rules/company.md", title="公司制度", body="公司制度证据原文。")
        self.write_page(project_root, "meetings/project.md", title="项目纪要", source_file="03-会议/项目纪要.md", body="项目会议证据原文。")

        sources = [
            {"file": "gbrain:company-wiki/rules/company", "source_id": "company-wiki", "page_slug": "rules/company", "content": ""},
            {"file": "gbrain:project-bfi-7/meetings/project", "source_id": "project-bfi-7", "page_slug": "meetings/project", "content": ""},
        ]
        enrich_sources_with_evidence(sources, settings=settings, workspace=workspace)

        self.assertEqual(sources[0]["display_title"], "公司制度")
        self.assertIn("公司制度证据原文", sources[0]["evidence_excerpt"])
        self.assertEqual(sources[1]["display_title"], "项目纪要")
        self.assertIn("项目会议证据原文", sources[1]["evidence_excerpt"])

    def test_missing_excerpt_is_metadata_only_and_content_stays_empty(self):
        source = {"file": "gbrain:company-wiki/rules/missing", "source_id": "company-wiki", "page_slug": "rules/missing", "content": ""}
        enrich_sources_with_evidence([source], settings=self.settings(), workspace=None)
        self.assertTrue(source["metadata_only"])
        self.assertIsNone(source["evidence_excerpt"])
        self.assertEqual(source["content"], "")

    def test_project_customer_and_company_do_not_fallback_to_each_other(self):
        settings = self.settings()
        workspace = self.project_workspace()
        self.write_page(settings.derived_path, "meetings/project-only-in-company.md", body="不应被 project 引用读取。")
        source = {
            "file": "gbrain:project-bfi-7/meetings/project-only-in-company",
            "source_id": "project-bfi-7",
            "page_slug": "meetings/project-only-in-company",
            "content": "",
        }
        enrich_sources_with_evidence([source], settings=settings, workspace=workspace)
        self.assertTrue(source["metadata_only"])
        self.assertIsNone(source["evidence_excerpt"])

        customer = self.customer_workspace()
        customer_root = self.customer_ready(customer)
        self.write_page(customer_root, "clients/acme.md", body="客户资料不应被 project source 读取。")
        source = {
            "file": "gbrain:customer-crm/clients/acme",
            "source_id": "customer-crm",
            "page_slug": "clients/acme",
            "content": "",
        }
        enrich_sources_with_evidence([source], settings=settings, workspace=workspace)
        self.assertTrue(source["metadata_only"])

    def test_cross_workspace_project_source_is_not_read(self):
        settings = self.settings()
        workspace = self.project_workspace(7)
        other_workspace = self.project_workspace(8)
        other_root = self.project_ready(other_workspace)
        self.write_page(other_root, "meetings/other.md", body="其他项目资料。")
        source = {"file": "gbrain:project-bfi-8/meetings/other", "source_id": "project-bfi-8", "page_slug": "meetings/other", "content": ""}
        enrich_sources_with_evidence([source], settings=settings, workspace=workspace)
        self.assertTrue(source["metadata_only"])
        self.assertIsNone(source["evidence_excerpt"])

    def test_multiple_original_file_stem_candidates_return_metadata_only(self):
        settings = self.settings()
        workspace = self.project_workspace()
        root = self.project_ready(workspace)
        self.write_page(root, "a/one.md", source_file="A/quote.docx", body="候选一。")
        self.write_page(root, "b/two.md", source_file="B/quote.docx", body="候选二。")
        source = {"file": "gbrain:project-bfi-7/quote", "source_id": "project-bfi-7", "page_slug": "quote", "content": ""}
        enrich_sources_with_evidence([source], settings=settings, workspace=workspace)
        self.assertTrue(source["metadata_only"])
        self.assertIsNone(source["evidence_excerpt"])

    def test_original_source_file_does_not_expose_absolute_path(self):
        settings = self.settings()
        page = self.write_page(
            settings.derived_path,
            "rules/path.md",
            source_file="C:/Users/secret/company-policy.docx",
            body="路径脱敏证据。",
        )
        self.assertTrue(page.exists())
        source = {"file": "gbrain:company-wiki/rules/path", "source_id": "company-wiki", "page_slug": "rules/path", "content": ""}
        enrich_sources_with_evidence([source], settings=settings, workspace=None)
        self.assertEqual(source["original_source_file"], "company-policy.docx")
        self.assertNotIn("C:/Users", source["original_source_file"])

    def test_excerpt_uses_row_paragraph_and_is_capped(self):
        settings = self.settings()
        body = "# Title\n\n第一段。\n\n第二段目标证据。" + ("长文本" * 300)
        self.write_page(settings.derived_path, "rules/row.md", body=body)
        source = {"file": "gbrain:company-wiki/rules/row", "source_id": "company-wiki", "page_slug": "rules/row", "row_num": 5, "content": ""}
        enrich_sources_with_evidence([source], settings=settings, workspace=None)
        self.assertIn("第二段目标证据", source["evidence_excerpt"])
        self.assertLessEqual(len(source["evidence_excerpt"]), 803)

    def test_evidence_enrichment_failure_does_not_block_think(self):
        with patch("app.features.knowledge.sources.load_gbrain_settings", return_value=self.settings()):
            with patch("app.features.knowledge.sources.enrich_sources_with_evidence", side_effect=RuntimeError("boom")):
                result = KnowledgeSources(gbrain_factory=lambda: FakeThinkAdapter()).think(FakeDb(), "制度是什么")
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sources"][0]["content"], "")
        self.assertTrue(result["sources"][0]["metadata_only"])


if __name__ == "__main__":
    unittest.main()
