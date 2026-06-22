from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import GBrainAdapter, load_gbrain_settings
from app.features.knowledge.sources import KnowledgeSources
from app.features.knowledge.quality import admin_regression, report_manifest
from app.features.knowledge.quality.admin_helpers import write_audit
from models.user import User


def load_quality_reports(*, settings: Any = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    return report_manifest.load_quality_reports(manifests_path=settings.manifests_path)


def save_quality_report(report: dict, *, actor: str, settings: Any = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    return report_manifest.save_quality_report(report, actor=actor, manifests_path=settings.manifests_path)


def run_query_regression_cases(
    cases_path: Path,
    *,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
    knowledge_sources_cls: type[KnowledgeSources] = KnowledgeSources,
) -> dict[str, Any]:
    cases = admin_regression._load_regression_cases(cases_path)
    health_failures = admin_regression._query_regression_health_failures(adapter_cls().health())
    if health_failures:
        return {
            "ok": False,
            "total": len(cases),
            "passed": 0,
            "failed": len(cases),
            "preflight_failures": health_failures,
            "cases": [],
        }

    knowledge_sources = knowledge_sources_cls()
    results: list[dict[str, Any]] = []
    for case in cases:
        sources = knowledge_sources.search_company_sources(case["query"])
        if not sources:
            results.append({"id": case.get("id"), "ok": False, "reason": "no sources returned", "candidates": []})
            continue
        ok, reason = admin_regression._matches_query_expected(case, sources[0])
        results.append(
            {
                "id": case.get("id"),
                "ok": ok,
                "reason": reason,
                "query": case.get("query"),
                "top_file": sources[0].get("file"),
                "top_title": sources[0].get("source_title"),
                "candidates": [source.get("file") for source in sources[:3]],
            }
        )
    passed = sum(1 for item in results if item.get("ok"))
    return {
        "ok": passed == len(cases),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "preflight_failures": [],
        "cases": results,
    }


def run_think_regression_cases(
    cases_path: Path,
    *,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    cases = admin_regression._load_regression_cases(cases_path)
    adapter = adapter_cls()
    preflight_failures = (
        admin_regression._query_regression_health_failures(adapter.health(), require_embedding=False)
        + admin_regression._think_config_failures()
    )
    if preflight_failures:
        return {
            "ok": False,
            "total": len(cases),
            "passed": 0,
            "failed": len(cases),
            "preflight_failures": preflight_failures,
            "cases": [],
        }

    results: list[dict[str, Any]] = []
    for case in cases:
        response = adapter.think(case["query"], source_id=case.get("source_id"))
        failures = admin_regression._validate_think_case(case, response)
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        results.append(
            {
                "id": case.get("id"),
                "ok": not failures,
                "reason": "; ".join(failures),
                "query": case.get("query"),
                "source_id": response.get("source_id"),
                "model": result.get("modelUsed"),
                "citations": len(result.get("citations") or []) if isinstance(result.get("citations"), list) else 0,
                "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
            }
        )
    passed = sum(1 for item in results if item.get("ok"))
    return {
        "ok": passed == len(cases),
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "preflight_failures": [],
        "cases": results,
    }


def run_admin_regression(
    db: Session,
    *,
    user: User,
    include_think: bool,
    query_runner: Callable[[], dict[str, Any]],
    think_runner: Callable[[], dict[str, Any]],
    save_report: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    query_result = query_runner()
    think_result = (
        think_runner()
        if include_think
        else {"ok": True, "skipped": True, "reason": "include_think=false", "total": 0, "passed": 0, "failed": 0, "cases": []}
    )
    ok = bool(query_result.get("ok") and think_result.get("ok"))
    report = {
        "ok": ok,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "include_think": include_think,
        "query": query_result,
        "think": think_result,
    }
    saved_report = save_report(report, actor=user.username)
    write_audit(
        db,
        user.id,
        "admin_gbrain_regression",
        (
            f"ok={ok}, query_passed={query_result.get('passed', 0)}/{query_result.get('total', 0)}, "
            f"think_passed={think_result.get('passed', 0)}/{think_result.get('total', 0)}, "
            f"include_think={include_think}, report_id={saved_report.get('id') or ''}"
        ),
    )
    db.commit()
    return saved_report


def get_quality_report(report_id: str, *, load_reports: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    reports = load_reports().get("reports")
    report_list = reports if isinstance(reports, list) else []
    if report_id == "latest" and report_list:
        return report_list[0]
    for report in report_list:
        if str(report.get("id") or "") == report_id:
            return report
    raise HTTPException(status_code=404, detail="质量报告不存在")
