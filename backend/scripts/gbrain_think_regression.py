from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURE_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_think_regression_cases.json"


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


def _health_failures(health: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if health.get("service", {}).get("status") != "ok":
        failures.append("GBrain HTTP service is not ok.")
    company_source = health.get("company_source", {})
    if not company_source.get("registered"):
        failures.append("company-wiki source is not registered.")
    elif not company_source.get("path_matches", True):
        failures.append("company-wiki source path does not match Project_R derived path.")
    return failures


def _think_config_failures() -> list[str]:
    checks = {
        "GBRAIN_THINK_ENABLED": os.getenv("GBRAIN_THINK_ENABLED"),
        "GBRAIN_THINK_SOURCE_SCOPE_VERIFIED": os.getenv("GBRAIN_THINK_SOURCE_SCOPE_VERIFIED"),
        "GBRAIN_THINK_OAUTH_CLIENT_ID": os.getenv("GBRAIN_THINK_OAUTH_CLIENT_ID"),
        "GBRAIN_THINK_OAUTH_CLIENT_SECRET": os.getenv("GBRAIN_THINK_OAUTH_CLIENT_SECRET"),
        "GBRAIN_THINK_MODEL": os.getenv("GBRAIN_THINK_MODEL"),
    }
    failures: list[str] = []
    if str(checks["GBRAIN_THINK_ENABLED"] or "").strip().lower() not in {"1", "true", "yes", "on"}:
        failures.append("GBRAIN_THINK_ENABLED is not true.")
    if str(checks["GBRAIN_THINK_SOURCE_SCOPE_VERIFIED"] or "").strip().lower() not in {"1", "true", "yes", "on"}:
        failures.append("GBRAIN_THINK_SOURCE_SCOPE_VERIFIED is not true.")
    for key in ("GBRAIN_THINK_OAUTH_CLIENT_ID", "GBRAIN_THINK_OAUTH_CLIENT_SECRET", "GBRAIN_THINK_MODEL"):
        if not str(checks[key] or "").strip():
            failures.append(f"{key} is not configured.")
    return failures


def _text_contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(str(term).lower() in lowered for term in terms)


def _citation_text(citation: dict[str, Any]) -> str:
    values = []
    for key in ("page_slug", "slug", "page", "source", "title"):
        value = citation.get(key)
        if value is not None:
            values.append(str(value))
    return " ".join(values)


def validate_think_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if response.get("status") != "ok":
        return [f"status={response.get('status')!r} error={response.get('error')!r}"]
    if response.get("source_id") != case.get("source_id"):
        failures.append(f"source_id={response.get('source_id')!r}, expected {case.get('source_id')!r}")

    scope = response.get("source_scope") if isinstance(response.get("source_scope"), dict) else {}
    if not scope.get("verified"):
        failures.append("source_scope.verified is not true")
    if not scope.get("scope_is_token_bound"):
        failures.append("source_scope.scope_is_token_bound is not true")
    allowed_sources = scope.get("allowed_sources") if isinstance(scope.get("allowed_sources"), list) else []
    if case.get("source_id") not in allowed_sources:
        failures.append(f"source {case.get('source_id')!r} is not in token allowed_sources")

    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    if result.get("error"):
        failures.append(f"result.error={result.get('error')!r}")

    model = str(result.get("modelUsed") or "")
    expected_model = str(case.get("expected_model_contains") or "")
    if expected_model and expected_model.lower() not in model.lower():
        failures.append(f"modelUsed={model!r} does not contain {expected_model!r}")

    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    max_warnings = int(case.get("max_warnings", 0))
    if len(warnings) > max_warnings:
        failures.append(f"warnings={warnings!r}, expected at most {max_warnings}")

    answer = str(result.get("answer") or "")
    expected_terms = [str(term) for term in case.get("expected_answer_terms_any", []) if str(term).strip()]
    if expected_terms and not _text_contains_any(answer, expected_terms):
        failures.append(f"answer does not contain any expected term {expected_terms!r}")
    forbidden_terms = [str(term) for term in case.get("forbidden_answer_terms", []) if str(term).strip()]
    if forbidden_terms:
        lowered_answer = answer.lower()
        leaked_terms = [term for term in forbidden_terms if term.lower() in lowered_answer]
        if leaked_terms:
            failures.append(f"answer contains forbidden terms {leaked_terms!r}")

    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    min_citations = int(case.get("min_citations", 1))
    if len(citations) < min_citations:
        failures.append(f"citations={len(citations)}, expected at least {min_citations}")
    expected_citation = str(case.get("expected_citation_contains") or "").lower()
    if expected_citation and not any(expected_citation in _citation_text(citation).lower() for citation in citations if isinstance(citation, dict)):
        failures.append(f"no citation contains {case.get('expected_citation_contains')!r}")
    forbidden_citations = [str(term) for term in case.get("forbidden_citation_contains_any", []) if str(term).strip()]
    if forbidden_citations:
        citation_blob = "\n".join(
            _citation_text(citation)
            for citation in citations
            if isinstance(citation, dict)
        ).lower()
        leaked_citations = [term for term in forbidden_citations if term.lower() in citation_blob]
        if leaked_citations:
            failures.append(f"citations contain forbidden terms {leaked_citations!r}")

    return failures


def main() -> int:
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import GBrainAdapter

    adapter = GBrainAdapter()
    health_failures = _health_failures(adapter.health())
    config_failures = _think_config_failures()
    failures = health_failures + config_failures
    if failures:
        print("GBrain think regression preflight failed:")
        for failure in failures:
            print(f"- {failure}")
        return 2

    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    failed_cases: list[str] = []
    for case in cases:
        response = adapter.think(case["query"], source_id=case.get("source_id"))
        case_failures = validate_think_case(case, response)
        if case_failures:
            failed_cases.append(f"{case['id']}: {'; '.join(case_failures)}")
            print(f"FAIL {case['id']}: {'; '.join(case_failures)}")
            continue
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        print(
            f"PASS {case['id']}: model={result.get('modelUsed')} "
            f"citations={len(result.get('citations') or [])}"
        )

    if failed_cases:
        print("\nFailed GBrain think regression cases:")
        for failure in failed_cases:
            print(f"- {failure}")
        return 1
    print("\nAll GBrain think regression cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
