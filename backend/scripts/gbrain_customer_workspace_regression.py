from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def _text_contains_all(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return all(str(term).lower() in lowered for term in terms if str(term).strip())


def validate_query_response(response: dict[str, Any], *, expected_source_id: str, expected_terms: list[str]) -> list[str]:
    failures: list[str] = []
    if response.get("status") != "ok":
        return [f"status={response.get('status')!r} error={response.get('error')!r}"]
    result = response.get("result")
    if not isinstance(result, list) or not result:
        return ["query returned no result rows"]
    first = result[0] if isinstance(result[0], dict) else {}
    first_source = str(first.get("source_id") or expected_source_id)
    if first_source != expected_source_id:
        failures.append(f"top source_id={first_source!r}, expected {expected_source_id!r}")
    if expected_terms:
        haystack = " ".join(
            str(first.get(key) or "")
            for key in ("title", "slug", "chunk_text", "content", "page_id")
        )
        if not _text_contains_all(haystack, expected_terms):
            failures.append(f"top result does not contain all expected terms {expected_terms!r}")
    return failures


def _citation_text(citation: dict[str, Any]) -> str:
    values = []
    for key in ("page_slug", "slug", "page", "source", "title"):
        value = citation.get(key)
        if value is not None:
            values.append(str(value))
    return " ".join(values)


def validate_think_response(response: dict[str, Any], *, expected_source_id: str, expected_terms: list[str]) -> list[str]:
    failures: list[str] = []
    if response.get("status") != "ok":
        return [f"status={response.get('status')!r} error={response.get('error')!r}"]
    if response.get("source_id") != expected_source_id:
        failures.append(f"source_id={response.get('source_id')!r}, expected {expected_source_id!r}")
    scope = response.get("source_scope") if isinstance(response.get("source_scope"), dict) else {}
    if not scope.get("verified"):
        failures.append("source_scope.verified is not true")
    if not scope.get("scope_is_token_bound"):
        failures.append("source_scope.scope_is_token_bound is not true")
    allowed_sources = scope.get("allowed_sources") if isinstance(scope.get("allowed_sources"), list) else []
    if expected_source_id not in allowed_sources:
        failures.append(f"source {expected_source_id!r} is not in token allowed_sources")
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    if result.get("error"):
        failures.append(f"result.error={result.get('error')!r}")
    answer = str(result.get("answer") or "")
    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    if not citations:
        failures.append("citations=0, expected at least 1")
    if expected_terms:
        citation_text = " ".join(
            _citation_text(citation)
            for citation in citations
            if isinstance(citation, dict)
        )
        if not _text_contains_all(f"{answer}\n{citation_text}", expected_terms):
            failures.append(f"answer/citations do not contain all expected terms {expected_terms!r}")
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a Project_R customer workspace GBrain source.")
    parser.add_argument("--workspace-id", type=int, required=True, help="Project_R customer workspace id.")
    parser.add_argument("--query", required=True, help="Question to run against the customer source.")
    parser.add_argument(
        "--expected-term",
        action="append",
        default=[],
        help="Term that must appear in the top query result or Think answer/citations. Repeatable.",
    )
    parser.add_argument("--think", action="store_true", help="Run GBrain native think instead of raw query.")
    parser.add_argument("--limit", type=int, default=5, help="Query result limit for non-Think mode.")
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    _load_dotenv(BACKEND_DIR / ".env")
    sys.path.insert(0, str(BACKEND_DIR))

    from core.gbrain import GBrainAdapter, customer_source_id_for_workspace, customer_source_registration_plan
    from models import SessionLocal
    from models.workspace import Workspace

    args = _parse_args()
    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.id == args.workspace_id).first()
    finally:
        db.close()
    if not workspace:
        print(json.dumps({"ok": False, "error": f"workspace {args.workspace_id} not found"}, ensure_ascii=False, indent=2))
        return 2
    if str(workspace.workspace_kind or "") != "customer":
        print(json.dumps({"ok": False, "error": f"workspace {args.workspace_id} is not a customer workspace"}, ensure_ascii=False, indent=2))
        return 2

    source_id = customer_source_id_for_workspace(workspace)
    plan = customer_source_registration_plan(workspace)
    adapter = GBrainAdapter()
    status = adapter.source_status(plan)
    if not status.get("registered"):
        print(json.dumps({"ok": False, "source_id": source_id, "error": "customer source is not registered", "status": status}, ensure_ascii=False, indent=2))
        return 2
    if status.get("registered") and not status.get("path_matches", True):
        print(json.dumps({"ok": False, "source_id": source_id, "error": "customer source path mismatch", "status": status}, ensure_ascii=False, indent=2))
        return 2

    if args.think:
        response = adapter.think(args.query, source_id=source_id)
        failures = validate_think_response(response, expected_source_id=source_id, expected_terms=args.expected_term)
    else:
        response = adapter.query(args.query, source_id=source_id, limit=args.limit, detail="medium")
        failures = validate_query_response(response, expected_source_id=source_id, expected_terms=args.expected_term)

    payload = {
        "ok": not failures,
        "mode": "think" if args.think else "query",
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "source_id": source_id,
        "failures": failures,
    }
    if args.think:
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        payload["model"] = result.get("modelUsed")
        payload["citations"] = len(result.get("citations") or []) if isinstance(result.get("citations"), list) else 0
    else:
        result = response.get("result") if isinstance(response.get("result"), list) else []
        payload["results"] = len(result)
        if result and isinstance(result[0], dict):
            payload["top"] = {
                "title": result[0].get("title"),
                "slug": result[0].get("slug"),
                "source_id": result[0].get("source_id") or source_id,
            }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
