import unittest
from types import SimpleNamespace

from app.features.knowledge.gbrain import GBrainSettings
from app.features.knowledge.query_orchestration import build_think_plan, execute_think_plan


def _settings() -> GBrainSettings:
    return GBrainSettings(
        enabled=True,
        base_url="http://127.0.0.1:3131",
        company_source_id="company-wiki",
        local_git_enabled=False,
    )


def _project_workspace(workspace_id: int | None = 7):
    return SimpleNamespace(
        id=workspace_id,
        workspace_kind="project",
        brand="BFI",
        slug="BG007",
        name="BG007",
    )


def _customer_workspace():
    return SimpleNamespace(
        id=9,
        workspace_kind="customer",
        slug="CRM",
        name="CRM",
    )


class KnowledgeQueryOrchestrationTests(unittest.TestCase):
    def test_build_plan_without_workspace_queries_company_only(self):
        plan = build_think_plan(None, _settings())

        self.assertEqual(plan.mode, "single")
        self.assertEqual(plan.primary.source_id, "company-wiki")
        self.assertIsNone(plan.secondary)

    def test_build_plan_for_project_queries_project_and_company(self):
        plan = build_think_plan(_project_workspace(), _settings())

        self.assertEqual(plan.mode, "project_with_company")
        self.assertEqual(plan.primary.source_id, "project-bfi-7")
        self.assertTrue(plan.primary.apply_project_ranking)
        self.assertEqual(plan.secondary.source_id, "company-wiki")

    def test_project_without_persisted_id_falls_back_to_company(self):
        plan = build_think_plan(_project_workspace(None), _settings())

        self.assertEqual(plan.mode, "single")
        self.assertEqual(plan.primary.source_id, "company-wiki")

    def test_build_plan_for_customer_queries_customer_only(self):
        plan = build_think_plan(_customer_workspace(), _settings())

        self.assertEqual(plan.mode, "single")
        self.assertEqual(plan.primary.source_id, "customer-crm")

    def test_execute_project_plan_merges_project_and_company_partials(self):
        calls: list[dict] = []

        def think_for_source(content, *, source_id, settings, workspace, apply_project_ranking):
            calls.append(
                {
                    "content": content,
                    "source_id": source_id,
                    "apply_project_ranking": apply_project_ranking,
                }
            )
            return {
                "ok": True,
                "status": "ok",
                "source_id": source_id,
                "raw_answer": f"answer from {source_id}",
                "sources": [
                    {
                        "file": f"gbrain:{source_id}/page",
                        "section_path": "page",
                        "type": "gbrain_think_citation",
                    }
                ],
                "model": "think",
                "metadata": {"gaps": [source_id]},
            }

        result = execute_think_plan(
            "启动会决定是什么",
            workspace=_project_workspace(),
            settings=_settings(),
            think_for_source=think_for_source,
        )

        self.assertTrue(result["ok"])
        self.assertEqual([call["source_id"] for call in calls], ["project-bfi-7", "company-wiki"])
        self.assertEqual([call["apply_project_ranking"] for call in calls], [True, False])
        self.assertEqual(result["source_ids"], ["project-bfi-7", "company-wiki"])
        self.assertIn("【公司知识库补充】", result["reply"])
        self.assertEqual(result["metadata"]["gaps"], ["project-bfi-7", "company-wiki"])


if __name__ == "__main__":
    unittest.main()
