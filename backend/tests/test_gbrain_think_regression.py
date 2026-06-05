import importlib.util
import json
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "gbrain_think_regression.py"
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_think_regression_cases.json"

spec = importlib.util.spec_from_file_location("gbrain_think_regression", SCRIPT_PATH)
gbrain_think_regression = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gbrain_think_regression)


class GBrainThinkRegressionTests(unittest.TestCase):
    def test_fixture_covers_company_and_unified_customer_think(self):
        cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        ids = {case["id"] for case in cases}
        source_ids = {case["source_id"] for case in cases}

        self.assertIn("written_principle_think", ids)
        self.assertIn("customer_five_points_think", ids)
        self.assertIn("customer_18_mary_think", ids)
        self.assertIn("customer_aaron_morris_think", ids)
        self.assertIn("company-wiki", source_ids)
        self.assertIn("customer-crm", source_ids)

    def test_validate_think_case_accepts_scoped_citation_answer(self):
        case = {
            "source_id": "company-wiki",
            "expected_model_contains": "deepseek",
            "expected_answer_terms_any": ["书面化"],
            "expected_citation_contains": "rules/书面化原则",
            "min_citations": 1,
            "max_warnings": 0,
        }
        response = {
            "status": "ok",
            "source_id": "company-wiki",
            "source_scope": {
                "verified": True,
                "scope_is_token_bound": True,
                "allowed_sources": ["company-wiki"],
            },
            "result": {
                "answer": "书面化原则要求重要事项形成书面记录。",
                "modelUsed": "deepseek:deepseek-chat",
                "warnings": [],
                "citations": [{"page_slug": "rules/书面化原则", "row_num": 4}],
            },
        }

        self.assertEqual(gbrain_think_regression.validate_think_case(case, response), [])

    def test_validate_think_case_rejects_unscoped_or_uncited_answer(self):
        case = {
            "source_id": "company-wiki",
            "expected_model_contains": "deepseek",
            "expected_answer_terms_any": ["书面化"],
            "expected_citation_contains": "rules/书面化原则",
            "min_citations": 1,
            "max_warnings": 0,
        }
        response = {
            "status": "ok",
            "source_id": "company-wiki",
            "source_scope": {
                "verified": False,
                "scope_is_token_bound": False,
                "allowed_sources": [],
            },
            "result": {
                "answer": "无引用回答。",
                "modelUsed": "deepseek:deepseek-chat",
                "warnings": ["NO_SOURCE"],
                "citations": [],
            },
        }

        failures = gbrain_think_regression.validate_think_case(case, response)

        self.assertTrue(any("source_scope.verified" in failure for failure in failures))
        self.assertTrue(any("citations=0" in failure for failure in failures))
        self.assertTrue(any("warnings=" in failure for failure in failures))

    def test_validate_think_case_rejects_customer_cross_talk(self):
        case = {
            "source_id": "customer-crm",
            "expected_model_contains": "deepseek",
            "expected_answer_terms_any": ["Aaron Morris"],
            "expected_citation_contains": "aaron-morris",
            "forbidden_answer_terms": ["5Points"],
            "forbidden_citation_contains_any": ["5points"],
            "min_citations": 1,
            "max_warnings": 0,
        }
        response = {
            "status": "ok",
            "source_id": "customer-crm",
            "source_scope": {
                "verified": True,
                "scope_is_token_bound": True,
                "allowed_sources": ["customer-crm"],
            },
            "result": {
                "answer": "Aaron Morris is related to Binah, but 5Points is also mentioned.",
                "modelUsed": "deepseek:deepseek-chat",
                "warnings": [],
                "citations": [
                    {"page_slug": "clients/01_clients__aaron-morris-75b5f010"},
                    {"page_slug": "companies/03_companies__5points-d1d55c2f"},
                ],
            },
        }

        failures = gbrain_think_regression.validate_think_case(case, response)

        self.assertTrue(any("forbidden terms" in failure for failure in failures))
        self.assertTrue(any("forbidden terms" in failure for failure in failures if "citations" in failure))


if __name__ == "__main__":
    unittest.main()
