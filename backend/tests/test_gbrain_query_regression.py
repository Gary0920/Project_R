import json
import os
import unittest
from pathlib import Path

from app.features.knowledge.sources import KnowledgeSources


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gbrain_query_regression_cases.json"


class RegressionGBrainAdapter:
    def __init__(self, responses_by_query: dict[str, list[dict]]):
        self.responses_by_query = responses_by_query
        self.queries: list[str] = []

    def query(self, query: str, *, limit: int = 5, expand: bool = False, detail: str = "medium"):
        self.queries.append(query)
        return {
            "status": "ok",
            "result": self.responses_by_query.get(query, []),
        }


class TimeoutGBrainAdapter:
    def __init__(self):
        self.queries: list[str] = []

    def query(self, query: str, *, limit: int = 5, expand: bool = False, detail: str = "medium"):
        self.queries.append(query)
        return {
            "status": "unreachable",
            "error": "timed out",
        }


class GBrainQueryRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_company_wiki_regression_cases_rank_expected_source_first(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                adapter = RegressionGBrainAdapter(case["mock_results_by_query"])
                previous = os.environ.get("GBRAIN_COMPANY_LOCAL_INDEX_ENABLED")
                os.environ["GBRAIN_COMPANY_LOCAL_INDEX_ENABLED"] = "false"
                try:
                    sources = KnowledgeSources(gbrain_factory=lambda: adapter).search_company_sources(case["query"])
                finally:
                    if previous is None:
                        os.environ.pop("GBRAIN_COMPANY_LOCAL_INDEX_ENABLED", None)
                    else:
                        os.environ["GBRAIN_COMPANY_LOCAL_INDEX_ENABLED"] = previous

                self.assertEqual(adapter.queries, case["expected_query_variants"])
                self.assertGreaterEqual(len(sources), 1)

                top = sources[0]
                self.assertTrue(top["file"].startswith("gbrain:company-wiki/"))
                self.assertIn(case["expected_top_file_contains"].lower(), top["file"].lower())
                self.assertIn(case["expected_top_title_contains"].lower(), top["source_title"].lower())
                self.assertTrue(
                    any(term.lower() in top["content"].lower() for term in case["expected_top_content_terms"]),
                    f"{case['id']} top content did not include expected terms: {top['content']!r}",
                )

    def test_regression_fixture_covers_required_business_areas(self):
        ids = {case["id"] for case in self.cases}
        self.assertIn("written_principle", ids)
        self.assertIn("vmu_standard_procedure", ids)
        self.assertIn("project_email_rule", ids)
        self.assertIn("file_naming_rule", ids)
        self.assertIn("accessory_order_rule", ids)

    def test_company_local_index_handles_gbrain_query_timeout(self):
        adapter = TimeoutGBrainAdapter()
        previous_index = os.environ.get("GBRAIN_COMPANY_LOCAL_INDEX_ENABLED")
        previous_path = os.environ.get("GBRAIN_COMPANY_DERIVED_PATH")
        fixture_root = Path(__file__).parent / "tmp_company_gbrain_ready"
        target = fixture_root / "rules" / "书面化原则-e7807016.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\n"
            "title: 书面化原则\n"
            "project_r_source_file: 书面化原则.md\n"
            "---\n\n"
            "# 书面化原则\n\n"
            "所有重要决策、任务分配、沟通确认，必须通过书面形式记录并留痕。\n",
            encoding="utf-8",
        )
        os.environ["GBRAIN_COMPANY_LOCAL_INDEX_ENABLED"] = "true"
        os.environ["GBRAIN_COMPANY_DERIVED_PATH"] = str(fixture_root)
        try:
            sources = KnowledgeSources(gbrain_factory=lambda: adapter).search_company_sources("书面化原则是什么")
        finally:
            if previous_index is None:
                os.environ.pop("GBRAIN_COMPANY_LOCAL_INDEX_ENABLED", None)
            else:
                os.environ["GBRAIN_COMPANY_LOCAL_INDEX_ENABLED"] = previous_index
            if previous_path is None:
                os.environ.pop("GBRAIN_COMPANY_DERIVED_PATH", None)
            else:
                os.environ["GBRAIN_COMPANY_DERIVED_PATH"] = previous_path
            try:
                target.unlink()
                target.parent.rmdir()
                fixture_root.rmdir()
            except OSError:
                pass

        self.assertGreaterEqual(len(sources), 1)
        self.assertIn("rules/书面化原则", sources[0]["file"])
        self.assertIn("书面化原则", sources[0]["source_title"])
        self.assertIn("留痕", sources[0]["content"])


if __name__ == "__main__":
    unittest.main()
