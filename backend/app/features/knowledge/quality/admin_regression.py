"""Admin-level GBrain query/think regression runner.

These functions run the admin-facing GBrain regression test suite,
comparing query/think results against expected outcomes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException


def _load_regression_cases(path: Path) -> list[dict[str, Any]]:
    try:
        cases = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"无法读取 GBrain 回归用例：{exc}") from exc
    if not isinstance(cases, list):
        raise HTTPException(status_code=500, detail="GBrain 回归用例格式错误。")
    return [case for case in cases if isinstance(case, dict)]


def _query_regression_health_failures(health: dict[str, Any], *, require_embedding: bool = True) -> list[str]:
    failures: list[str] = []
    if health.get("service", {}).get("status") != "ok":
        failures.append("GBrain HTTP service is not ok.")
    company_source = health.get("company_source", {})
    if not company_source.get("registered"):
        failures.append("company-wiki source is not registered.")
    elif not company_source.get("path_matches", True):
        failures.append("company-wiki source path does not match Project_R derived path.")
    if require_embedding:
        embedding = health.get("local_config", {}).get("embedding") or {}
        if not embedding.get("semantic_search_ready"):
            failures.append(f"Embedding is not ready: {embedding.get('reason') or 'unknown reason'}")
    return failures


def _matches_query_expected(case: dict[str, Any], source: dict[str, Any]) -> tuple[bool, str]:
    file_value = str(source.get("file") or "").lower()
    title_value = str(source.get("source_title") or "").lower()
    content_value = str(source.get("content") or "").lower()
    expected_file = str(case.get("expected_top_file_contains") or "").lower()
    expected_title = str(case.get("expected_top_title_contains") or "").lower()
    expected_terms = [str(term).lower() for term in case.get("expected_top_content_terms", [])]
    if expected_file and expected_file not in file_value:
        return False, f"top file {source.get('file')!r} does not contain {case.get('expected_top_file_contains')!r}"
    if expected_title and expected_title not in title_value:
        return False, f"top title {source.get('source_title')!r} does not contain {case.get('expected_top_title_contains')!r}"
    if expected_terms and not any(term in content_value for term in expected_terms):
        return False, f"top content does not include any expected term {case.get('expected_top_content_terms')!r}"
    return True, ""


def _think_config_failures() -> list[str]:
    failures: list[str] = []
    if str(os.getenv("GBRAIN_THINK_ENABLED") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        failures.append("GBRAIN_THINK_ENABLED is not true.")
    if str(os.getenv("GBRAIN_THINK_SOURCE_SCOPE_VERIFIED") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        failures.append("GBRAIN_THINK_SOURCE_SCOPE_VERIFIED is not true.")
    for key in ("GBRAIN_THINK_OAUTH_CLIENT_ID", "GBRAIN_THINK_OAUTH_CLIENT_SECRET", "GBRAIN_THINK_MODEL"):
        if not str(os.getenv(key) or "").strip():
            failures.append(f"{key} is not configured.")
    return failures


def _validate_think_case(case: dict[str, Any], response: dict[str, Any]) -> list[str]:
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
    expected_model = str(case.get("expected_model_contains") or "")
    model = str(result.get("modelUsed") or "")
    if expected_model and expected_model.lower() not in model.lower():
        failures.append(f"modelUsed={model!r} does not contain {expected_model!r}")
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    max_warnings = int(case.get("max_warnings", 0))
    if len(warnings) > max_warnings:
        failures.append(f"warnings={warnings!r}, expected at most {max_warnings}")
    expected_terms = [str(term) for term in case.get("expected_answer_terms_any", []) if str(term).strip()]
    answer = str(result.get("answer") or "")
    if expected_terms and not any(term.lower() in answer.lower() for term in expected_terms):
        failures.append(f"answer does not contain any expected term {expected_terms!r}")
    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    min_citations = int(case.get("min_citations", 1))
    if len(citations) < min_citations:
        failures.append(f"citations={len(citations)}, expected at least {min_citations}")
    expected_citation = str(case.get("expected_citation_contains") or "").lower()
    if expected_citation and not any(
        expected_citation in _citation_text(citation).lower() for citation in citations if isinstance(citation, dict)
    ):
        failures.append(f"no citation contains {case.get('expected_citation_contains')!r}")
    return failures


def _citation_text(citation: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("page_slug", "slug", "page", "source", "title"):
        value = citation.get(key)
        if value is not None:
            values.append(str(value))
    return " ".join(values)
