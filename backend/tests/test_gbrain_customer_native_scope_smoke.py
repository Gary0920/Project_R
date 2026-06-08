import importlib.util
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / "scripts" / "gbrain_customer_native_scope_smoke.py"

spec = importlib.util.spec_from_file_location("gbrain_customer_native_scope_smoke", SCRIPT_PATH)
gbrain_customer_native_scope_smoke = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gbrain_customer_native_scope_smoke)


class GBrainCustomerNativeScopeSmokeTests(unittest.TestCase):
    def test_validate_schema_accepts_customer_scoped_schema_stats(self):
        payload = {
            "status": "ok",
            "source_id": "customer-crm",
            "source_scope": {
                "verified": True,
                "scope_is_token_bound": True,
                "allowed_sources": ["customer-crm"],
            },
            "schema_stats": {
                "result": {
                    "aggregate": {"total_pages": 424},
                    "per_source": [{"source_id": "customer-crm", "total_pages": 424}],
                }
            },
            "schema_review_orphans": {"result": {"orphan_count": 0, "orphans": []}},
        }

        failures = gbrain_customer_native_scope_smoke._validate_schema(
            payload,
            expected_source_id="customer-crm",
        )

        self.assertEqual(failures, [])

    def test_validate_graph_rejects_missing_timeline_or_unbound_scope(self):
        payload = {
            "status": "ok",
            "source_id": "customer-crm",
            "source_scope": {
                "verified": False,
                "scope_is_token_bound": False,
                "allowed_sources": ["company-wiki"],
            },
            "traverse_graph": {"result": [{}]},
            "timeline": {"result": []},
            "backlinks": {"result": []},
        }
        case = {
            "min_graph_edges": 1,
            "min_timeline_entries": 1,
            "min_backlinks": 0,
        }

        failures = gbrain_customer_native_scope_smoke._validate_graph(
            payload,
            case,
            expected_source_id="customer-crm",
        )

        self.assertTrue(any("source_scope.verified" in failure for failure in failures))
        self.assertTrue(any("scope_is_token_bound" in failure for failure in failures))
        self.assertTrue(any("allowed_sources" in failure for failure in failures))
        self.assertTrue(any("timeline" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
