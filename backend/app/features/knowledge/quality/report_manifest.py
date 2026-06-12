"""GBrain quality report manifest — admin-level aggregated quality reports.

This module manages the single-file manifest (gbrain-quality-reports.json)
that stores recent query/think regression results for the admin dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.features.knowledge.gbrain import load_gbrain_settings

QUALITY_REPORTS_MANIFEST_NAME = "gbrain-quality-reports.json"
QUALITY_REPORTS_LIMIT = 20


def _quality_reports_path(manifests_path: Path | None = None) -> Path:
    if manifests_path is None:
        manifests_path = load_gbrain_settings().manifests_path
    return manifests_path / QUALITY_REPORTS_MANIFEST_NAME


def load_quality_reports(manifests_path: Path | None = None) -> dict[str, Any]:
    """Load the quality reports manifest from disk."""
    path = _quality_reports_path(manifests_path)
    reports: list[dict[str, Any]] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if isinstance(payload, dict) and isinstance(payload.get("reports"), list):
        reports = [item for item in payload["reports"] if isinstance(item, dict)]
    latest = reports[0] if reports else None
    visible_reports = reports[:QUALITY_REPORTS_LIMIT]
    return {
        "path": str(path.resolve()),
        "count": len(reports),
        "latest": latest,
        "reports": visible_reports,
        "trend": [_quality_report_trend_item(item) for item in visible_reports],
    }


def save_quality_report(report: dict[str, Any], *, actor: str, manifests_path: Path | None = None) -> dict[str, Any]:
    """Save a new quality report to the manifest."""
    path = _quality_reports_path(manifests_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = load_quality_reports(manifests_path).get("reports")
    current_reports = reports if isinstance(reports, list) else []
    ran_at = str(report.get("ran_at") or datetime.now(timezone.utc).isoformat())
    report_id = f"gbrain-quality-{ran_at.replace(':', '').replace('.', '').replace('+', 'Z')}"
    saved = {
        "id": report_id,
        "actor": actor,
        **report,
        "summary": _quality_report_summary(report),
    }
    next_reports = [saved, *[item for item in current_reports if item.get("id") != report_id]][:QUALITY_REPORTS_LIMIT]
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reports": next_reports,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return saved


def _quality_report_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Extract a compact summary from a regression report."""
    query = report.get("query") if isinstance(report.get("query"), dict) else {}
    think = report.get("think") if isinstance(report.get("think"), dict) else {}
    query_failed_cases = [
        str(item.get("id") or item.get("query") or "unknown")
        for item in query.get("cases", [])
        if isinstance(item, dict) and not item.get("ok")
    ]
    think_failed_cases = [
        str(item.get("id") or item.get("query") or "unknown")
        for item in think.get("cases", [])
        if isinstance(item, dict) and not item.get("ok")
    ]
    preflight_failures = []
    for suite in (query, think):
        failures = suite.get("preflight_failures") if isinstance(suite.get("preflight_failures"), list) else []
        preflight_failures.extend(str(item) for item in failures if item)
    return {
        "query": {
            "total": int(query.get("total") or 0),
            "passed": int(query.get("passed") or 0),
            "failed": int(query.get("failed") or 0),
        },
        "think": {
            "total": int(think.get("total") or 0),
            "passed": int(think.get("passed") or 0),
            "failed": int(think.get("failed") or 0),
            "skipped": bool(think.get("skipped")),
        },
        "failed_cases": [*query_failed_cases, *think_failed_cases][:20],
        "preflight_failures": preflight_failures[:20],
    }


def _quality_report_trend_item(report: dict[str, Any]) -> dict[str, Any]:
    """Build a compact trend item from a report for the admin dashboard."""
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else _quality_report_summary(report)
    query = summary.get("query") if isinstance(summary.get("query"), dict) else {}
    think = summary.get("think") if isinstance(summary.get("think"), dict) else {}
    failed_cases = summary.get("failed_cases") if isinstance(summary.get("failed_cases"), list) else []
    preflight_failures = (
        summary.get("preflight_failures") if isinstance(summary.get("preflight_failures"), list) else []
    )

    def rate(suite: dict[str, Any]) -> float | None:
        total = int(suite.get("total") or 0)
        if total <= 0:
            return None
        return round(int(suite.get("passed") or 0) / total, 4)

    return {
        "id": report.get("id"),
        "ran_at": report.get("ran_at"),
        "actor": report.get("actor"),
        "ok": bool(report.get("ok")),
        "include_think": bool(report.get("include_think")),
        "query_pass_rate": rate(query),
        "think_pass_rate": rate(think),
        "query_failed": int(query.get("failed") or 0),
        "think_failed": int(think.get("failed") or 0),
        "failed_case_count": len(failed_cases),
        "preflight_failure_count": len(preflight_failures),
    }
