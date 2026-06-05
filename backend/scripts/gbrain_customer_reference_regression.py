from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_customer_reference_regression_cases.json"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _matches_expected(case: dict, source: dict) -> tuple[bool, str]:
    file_value = str(source.get("file") or "").lower()
    title_value = str(source.get("source_title") or "").lower()
    content_value = str(source.get("content") or "").lower()
    expected_file = str(case["expected_top_file_contains"]).lower()
    expected_title = str(case["expected_top_title_contains"]).lower()
    expected_terms = [str(term).lower() for term in case["expected_top_content_terms"]]
    if _normalize_match_text(expected_file) not in _normalize_match_text(file_value):
        return False, f"top file {source.get('file')!r} does not contain {case['expected_top_file_contains']!r}"
    if expected_title not in title_value:
        return False, f"top title {source.get('source_title')!r} does not contain {case['expected_top_title_contains']!r}"
    if not any(term in content_value for term in expected_terms):
        return False, f"top content does not include any expected term {case['expected_top_content_terms']!r}"
    return True, ""


def _normalize_match_text(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def main() -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain import CRM_CUSTOMER_SOURCE_ID, GBrainAdapter
    from core.gbrain_customer_sources import search_customer_intelligence_sources

    adapter = GBrainAdapter()
    source_path = BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm" / "gbrain-ready"
    status = adapter.source_status(
        {
            "source_id": CRM_CUSTOMER_SOURCE_ID,
            "name": "Project_R Customer Intelligence",
            "path": str(source_path.resolve()),
            "federated": False,
        }
    )
    if not status.get("registered"):
        print("GBrain customer intelligence regression preflight failed: customer source is not registered.")
        return 2

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    failed_cases: list[str] = []
    for case in cases:
        sources = search_customer_intelligence_sources(case["query"], limit=5)
        if not sources:
            failed_cases.append(f"{case['id']}: no sources returned")
            continue
        matched, reason = _matches_expected(case, sources[0])
        if not matched:
            failed_cases.append(f"{case['id']}: {reason}")
            continue
        print(f"PASS {case['id']}: {sources[0].get('source_title')} -> {sources[0].get('file')}")

    if failed_cases:
        print("GBrain customer intelligence regression failed:")
        for failure in failed_cases:
            print(f"- {failure}")
        return 1
    print(f"GBrain customer intelligence regression passed ({len(cases)} cases).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
