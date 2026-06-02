import importlib.util
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "gbrain_customer_workspace_regression.py"

spec = importlib.util.spec_from_file_location("gbrain_customer_workspace_regression", SCRIPT_PATH)
gbrain_customer_workspace_regression = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gbrain_customer_workspace_regression)


class GBrainCustomerWorkspaceRegressionTests(unittest.TestCase):
    def test_validate_query_response_accepts_customer_scoped_result(self):
        response = {
            "status": "ok",
            "result": [
                {
                    "source_id": "customer-reference",
                    "title": "Lucerna Meeting",
                    "slug": "raw-events/lucerna-meeting",
                    "chunk_text": "Aaron approved the next step.",
                }
            ],
        }

        failures = gbrain_customer_workspace_regression.validate_query_response(
            response,
            expected_source_id="customer-reference",
            expected_terms=["Aaron", "approved"],
        )

        self.assertEqual(failures, [])

    def test_validate_query_response_rejects_cross_source_result(self):
        response = {
            "status": "ok",
            "result": [{"source_id": "company-wiki", "title": "Company Rule", "chunk_text": "Aaron"}],
        }

        failures = gbrain_customer_workspace_regression.validate_query_response(
            response,
            expected_source_id="customer-reference",
            expected_terms=["Aaron"],
        )

        self.assertTrue(any("source_id" in failure for failure in failures))

    def test_validate_think_response_accepts_token_bound_customer_scope(self):
        response = {
            "status": "ok",
            "source_id": "customer-reference",
            "source_scope": {
                "verified": True,
                "scope_is_token_bound": True,
                "allowed_sources": ["customer-reference"],
            },
            "result": {
                "answer": "Aaron is the customer-side decision contact.",
                "citations": [{"page_slug": "contacts/aaron"}],
                "modelUsed": "deepseek:deepseek-chat",
            },
        }

        failures = gbrain_customer_workspace_regression.validate_think_response(
            response,
            expected_source_id="customer-reference",
            expected_terms=["Aaron"],
        )

        self.assertEqual(failures, [])

    def test_validate_think_response_rejects_unscoped_or_uncited_answer(self):
        response = {
            "status": "ok",
            "source_id": "customer-reference",
            "source_scope": {
                "verified": False,
                "scope_is_token_bound": False,
                "allowed_sources": ["company-wiki"],
            },
            "result": {
                "answer": "No citation.",
                "citations": [],
            },
        }

        failures = gbrain_customer_workspace_regression.validate_think_response(
            response,
            expected_source_id="customer-reference",
            expected_terms=["Aaron"],
        )

        self.assertTrue(any("source_scope.verified" in failure for failure in failures))
        self.assertTrue(any("scope_is_token_bound" in failure for failure in failures))
        self.assertTrue(any("citations=0" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
