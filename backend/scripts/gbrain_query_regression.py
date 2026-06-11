from __future__ import annotations

import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_query_regression_cases.json"


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


def _health_failures(health: dict) -> list[str]:
    failures: list[str] = []
    if health.get("service", {}).get("status") != "ok":
        failures.append("GBrain HTTP service is not ok.")
    company_source = health.get("company_source", {})
    if not company_source.get("registered"):
        failures.append("company-wiki source is not registered.")
    elif not company_source.get("path_matches", True):
        failures.append("company-wiki source path does not match Project_R derived path.")
    embedding = health.get("local_config", {}).get("embedding") or {}
    if not embedding.get("semantic_search_ready"):
        failures.append(f"Embedding is not ready: {embedding.get('reason') or 'unknown reason'}")
    return failures


def _matches_expected(case: dict, source: dict) -> tuple[bool, str]:
    file_value = str(source.get("file") or "").lower()
    title_value = str(source.get("source_title") or "").lower()
    content_value = str(source.get("content") or "").lower()
    expected_file = str(case["expected_top_file_contains"]).lower()
    expected_title = str(case["expected_top_title_contains"]).lower()
    expected_terms = [str(term).lower() for term in case["expected_top_content_terms"]]
    if expected_file not in file_value:
        return False, f"top file {source.get('file')!r} does not contain {case['expected_top_file_contains']!r}"
    if expected_title not in title_value:
        return False, f"top title {source.get('source_title')!r} does not contain {case['expected_top_title_contains']!r}"
    if not any(term in content_value for term in expected_terms):
        return False, f"top content does not include any expected term {case['expected_top_content_terms']!r}"
    return True, ""


def main() -> int:
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import GBrainAdapter
    from app.features.knowledge.sources import KnowledgeSources

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    health = GBrainAdapter().health()
    failures = _health_failures(health)
    if failures:
        print("GBrain query regression preflight failed:")
        for failure in failures:
            print(f"- {failure}")
        return 2

    knowledge_sources = KnowledgeSources()
    failed_cases: list[str] = []
    for case in cases:
        sources = knowledge_sources.search_company_sources(case["query"])
        if not sources:
            failed_cases.append(f"{case['id']}: no sources returned")
            print(f"FAIL {case['id']}: no sources returned")
            continue
        ok, reason = _matches_expected(case, sources[0])
        if ok:
            print(f"PASS {case['id']}: {sources[0].get('file')}")
        else:
            candidates = ", ".join(str(source.get("file")) for source in sources[:3])
            failed_cases.append(f"{case['id']}: {reason}")
            print(f"FAIL {case['id']}: {reason}")
            print(f"  candidates: {candidates}")

    if failed_cases:
        print("\nFailed regression cases:")
        for failure in failed_cases:
            print(f"- {failure}")
        return 1
    print("\nAll GBrain query regression cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
