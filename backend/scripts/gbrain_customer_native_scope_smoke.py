from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]

DEFAULT_CASES = [
    {
        "id": "company_5points_native_context",
        "slug": "companies/03_companies__5points-d1d55c2f",
        "min_graph_edges": 1,
        "min_timeline_entries": 1,
        "min_backlinks": 1,
    },
    {
        "id": "project_18_mary_native_context",
        "slug": "projects/02_projects__18-mary-avenue-790f696c",
        "min_graph_edges": 1,
        "min_timeline_entries": 1,
        "min_backlinks": 0,
    },
    {
        "id": "person_aaron_morris_native_timeline",
        "slug": "clients/01_clients__aaron-morris-75b5f010",
        "min_graph_edges": 0,
        "min_timeline_entries": 1,
        "min_backlinks": 0,
    },
]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split("#", 1)[0].strip().strip('"').strip("'")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value


def _result_len(response: dict[str, Any], key: str) -> int:
    section = response.get(key) if isinstance(response.get(key), dict) else {}
    result = section.get("result") if isinstance(section, dict) else None
    return len(result) if isinstance(result, list) else 0


def _validate_scope(payload: dict[str, Any], *, expected_source_id: str) -> list[str]:
    failures: list[str] = []
    if payload.get("status") != "ok":
        return [f"status={payload.get('status')!r} error={payload.get('error')!r}"]
    if payload.get("source_id") != expected_source_id:
        failures.append(f"source_id={payload.get('source_id')!r}, expected {expected_source_id!r}")
    scope = payload.get("source_scope") if isinstance(payload.get("source_scope"), dict) else {}
    if not scope.get("verified"):
        failures.append("source_scope.verified is not true")
    if not scope.get("scope_is_token_bound"):
        failures.append("source_scope.scope_is_token_bound is not true")
    allowed_sources = scope.get("allowed_sources") if isinstance(scope.get("allowed_sources"), list) else []
    if allowed_sources != [expected_source_id]:
        failures.append(f"allowed_sources={allowed_sources!r}, expected [{expected_source_id!r}]")
    return failures


def _validate_schema(payload: dict[str, Any], *, expected_source_id: str) -> list[str]:
    failures = _validate_scope(payload, expected_source_id=expected_source_id)
    stats = payload.get("schema_stats") if isinstance(payload.get("schema_stats"), dict) else {}
    stats_result = stats.get("result") if isinstance(stats.get("result"), dict) else {}
    per_source = stats_result.get("per_source") if isinstance(stats_result.get("per_source"), list) else []
    source_ids = [item.get("source_id") for item in per_source if isinstance(item, dict)]
    if source_ids != [expected_source_id]:
        failures.append(f"schema_stats.per_source={source_ids!r}, expected [{expected_source_id!r}]")
    aggregate = stats_result.get("aggregate") if isinstance(stats_result.get("aggregate"), dict) else {}
    if int(aggregate.get("total_pages") or 0) <= 0:
        failures.append("schema_stats.aggregate.total_pages is empty")
    orphans = payload.get("schema_review_orphans") if isinstance(payload.get("schema_review_orphans"), dict) else {}
    orphan_result = orphans.get("result") if isinstance(orphans.get("result"), dict) else {}
    if int(orphan_result.get("orphan_count") or 0) != 0:
        failures.append(f"schema_review_orphans.orphan_count={orphan_result.get('orphan_count')!r}")
    return failures


def _validate_graph(payload: dict[str, Any], case: dict[str, Any], *, expected_source_id: str) -> list[str]:
    failures = _validate_scope(payload, expected_source_id=expected_source_id)
    checks = [
        ("traverse_graph", "min_graph_edges"),
        ("timeline", "min_timeline_entries"),
        ("backlinks", "min_backlinks"),
    ]
    for section, min_key in checks:
        observed = _result_len(payload, section)
        expected = int(case.get(min_key) or 0)
        if observed < expected:
            failures.append(f"{section} count={observed}, expected >= {expected}")
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test customer-crm native GBrain schema/graph/timeline scope.")
    parser.add_argument("--source-id", default="customer-crm")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from app.features.knowledge.gbrain import GBrainAdapter, customer_source_registration_plan

    args = _parse_args()
    source_id = args.source_id
    adapter = GBrainAdapter()
    crm_workspace = SimpleNamespace(id=1, name="CRM", slug="CRM", workspace_kind="customer")
    status = adapter.source_status(customer_source_registration_plan(crm_workspace))
    failures: list[str] = []
    if not status.get("registered"):
        failures.append("customer source is not registered")
    if status.get("registered") and not status.get("path_matches", True):
        failures.append("customer source path mismatch")

    schema = adapter.schema_context(source_id=source_id, orphan_limit=10)
    failures.extend(f"schema: {failure}" for failure in _validate_schema(schema, expected_source_id=source_id))

    cases: list[dict[str, Any]] = []
    for case in DEFAULT_CASES:
        response = adapter.graph_context(str(case["slug"]), source_id=source_id, depth=2)
        case_failures = _validate_graph(response, case, expected_source_id=source_id)
        cases.append(
            {
                "id": case["id"],
                "slug": case["slug"],
                "graph_edges": _result_len(response, "traverse_graph"),
                "timeline_entries": _result_len(response, "timeline"),
                "backlinks": _result_len(response, "backlinks"),
                "failures": case_failures,
            }
        )
        failures.extend(f"{case['id']}: {failure}" for failure in case_failures)

    schema_stats = schema.get("schema_stats") if isinstance(schema.get("schema_stats"), dict) else {}
    stats_result = schema_stats.get("result") if isinstance(schema_stats.get("result"), dict) else {}
    payload = {
        "ok": not failures,
        "source_id": source_id,
        "registered": bool(status.get("registered")),
        "path_matches": bool(status.get("path_matches", True)),
        "schema_total_pages": (stats_result.get("aggregate") or {}).get("total_pages") if isinstance(stats_result.get("aggregate"), dict) else None,
        "schema_per_source": stats_result.get("per_source") if isinstance(stats_result, dict) else None,
        "cases": cases,
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
