import json
import unittest
from pathlib import Path

from core.knowledge_sources import KnowledgeSources


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


class GBrainQueryRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_company_wiki_regression_cases_rank_expected_source_first(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                adapter = RegressionGBrainAdapter(case["mock_results_by_query"])
                sources = KnowledgeSources(gbrain_factory=lambda: adapter).search_company_sources(case["query"])

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
        self.assertIn("as1288_safety_glass", ids)
        self.assertIn("as2047_water_penetration", ids)
        self.assertIn("as1288_heat_soak", ids)
        self.assertIn("vmu_customer_visit", ids)
        self.assertIn("meeting_0515_actions", ids)
        self.assertIn("written_principle", ids)


if __name__ == "__main__":
    unittest.main()
