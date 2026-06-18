from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.knowledge.gbrain import (
    CUSTOMER_INTELLIGENCE_SOURCE_ID,
    GBrainAdapter,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    get_gbrain_admin_status,
    load_gbrain_settings,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.knowledge.gbrain.customer_sources import CUSTOMER_REFERENCE_DERIVED
from app.features.knowledge.gbrain.maintenance.citation_fixer_jobs import (
    load_citation_fixer_job_state,
    poll_citation_fixer_jobs,
    record_citation_fixer_job,
    rollback_citation_fixer_job,
)
from app.features.knowledge.gbrain.maintenance.contradiction_probe import (
    load_contradiction_probe_config,
    run_contradiction_probe,
    run_contradiction_probe_tick,
    save_contradiction_probe_config,
)
from app.features.knowledge.gbrain.maintenance.dream_cycle import (
    poll_dream_cycle_jobs,
    load_dream_cycle_config,
    run_dream_cycle,
    run_dream_cycle_tick,
    save_dream_cycle_config,
)
from app.features.knowledge.gbrain.graph import (
    apply_entity_merge_candidate_action,
    build_entity_merge_candidate_preview,
    build_entity_merge_candidates,
    build_source_graph,
)
from app.features.knowledge.gbrain.ingest import compile_company_wiki_sources
from app.features.knowledge.gbrain.maintenance.worker import (
    get_gbrain_maintenance_worker_status,
    restart_gbrain_maintenance_worker,
)
from app.features.knowledge.sources import KnowledgeSources
from app.features.knowledge.browser import (
    search_knowledge_for_workspace,
    serialize_source_scopes,
    source_scopes_for_workspace,
)
from app.features.workspaces.permissions import ensure_can_open_workspace
from app.features.notifications.service import notify_gbrain_maintenance_event
from models import get_db
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace

router = APIRouter(prefix="/admin/knowledge", tags=["gbrain"])
knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])
BACKEND_DIR = Path(__file__).resolve().parents[1]
QUERY_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_query_regression_cases.json"
THINK_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_think_regression_cases.json"
from app.features.knowledge.quality import report_manifest as _report_manifest  # noqa: E402, F401

QUALITY_REPORTS_MANIFEST_NAME = _report_manifest.QUALITY_REPORTS_MANIFEST_NAME
QUALITY_REPORTS_LIMIT = _report_manifest.QUALITY_REPORTS_LIMIT


class KnowledgeSourceScopeResponse(BaseModel):
    scope: str
    label: str
    description: str
    workspace_kind: str


class KnowledgeSourcesResponse(BaseModel):
    workspace_id: int | None = None
    workspace_kind: str
    scopes: list[KnowledgeSourceScopeResponse]


class KnowledgeSearchResultResponse(BaseModel):
    scope: str
    title: str
    excerpt: str
    reference_label: str


class KnowledgeSearchResponse(BaseModel):
    query: str
    workspace_id: int | None = None
    workspace_kind: str
    source_scope: str
    results: list[KnowledgeSearchResultResponse]


def _resolve_browse_workspace(db: Session, user: User, workspace_id: int | None) -> Workspace | None:
    if workspace_id is None:
        return None
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_can_open_workspace(db, user, workspace)
    return workspace


def _serialize_knowledge_result(item: dict) -> KnowledgeSearchResultResponse:
    scope = str(item.get("scope") or "company")
    section_path = str(item.get("section_path") or "").strip()
    source_title = str(item.get("source_title") or "").strip()
    return KnowledgeSearchResultResponse(
        scope=scope,
        title=source_title or _scope_reference_label(scope),
        excerpt=str(item.get("content") or ""),
        reference_label=_public_reference_label(scope, section_path, source_title),
    )


def _scope_reference_label(scope: str) -> str:
    if scope == "project":
        return "当前项目资料"
    if scope == "customer":
        return "当前客户情报"
    return "公司知识"


def _public_reference_label(scope: str, section_path: str, source_title: str) -> str:
    base = _scope_reference_label(scope)
    title = source_title or section_path
    if not title:
        return base
    safe_title = title.split("/")[-1].strip()[:80]
    return f"{base} · {safe_title}" if safe_title else base


@knowledge_router.get("/sources", response_model=KnowledgeSourcesResponse)
def list_employee_knowledge_sources(
    workspace_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = _resolve_browse_workspace(db, user, workspace_id)
    scopes = source_scopes_for_workspace(workspace)
    workspace_kind = str(workspace.workspace_kind or "user") if workspace else "user"
    return KnowledgeSourcesResponse(
        workspace_id=workspace.id if workspace else None,
        workspace_kind=workspace_kind,
        scopes=serialize_source_scopes(scopes),
    )


@knowledge_router.get("/search", response_model=KnowledgeSearchResponse)
def search_employee_knowledge(
    q: str = Query(..., min_length=1, max_length=500),
    workspace_id: int | None = Query(default=None),
    source_scope: str = Query(default="all", pattern="^(all|company|project|customer)$"),
    limit: int = Query(default=10, ge=1, le=20),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = _resolve_browse_workspace(db, user, workspace_id)
    results = search_knowledge_for_workspace(
        db,
        q,
        workspace=workspace,
        source_scope=source_scope,
        limit=limit,
    )
    workspace_kind = str(workspace.workspace_kind or "user") if workspace else "user"
    return KnowledgeSearchResponse(
        query=q,
        workspace_id=workspace.id if workspace else None,
        workspace_kind=workspace_kind,
        source_scope=source_scope,
        results=[_serialize_knowledge_result(item) for item in results],
    )


# Wrappers that pass the monkeypatch-compatible load_gbrain_settings
def load_quality_reports():
    return _report_manifest.load_quality_reports(manifests_path=load_gbrain_settings().manifests_path)


def save_quality_report(report: dict, *, actor: str) -> dict:
    return _report_manifest.save_quality_report(report, actor=actor, manifests_path=load_gbrain_settings().manifests_path)


# Backward-compat re-exports
_quality_report_summary = _report_manifest._quality_report_summary
_quality_report_trend_item = _report_manifest._quality_report_trend_item

from app.features.knowledge.quality import admin_regression as _admin_regression  # noqa: E402, F401

# Re-export pure helpers from admin_regression (no monkeypatch-sensitive imports)
_load_regression_cases = _admin_regression._load_regression_cases
_query_regression_health_failures = _admin_regression._query_regression_health_failures
_matches_query_expected = _admin_regression._matches_query_expected
_think_config_failures = _admin_regression._think_config_failures
_validate_think_case = _admin_regression._validate_think_case
_citation_text = _admin_regression._citation_text


def _run_query_regression_cases() -> dict[str, Any]:
    """Run query regression cases using module-level adapter and sources (monkeypatch-compatible)."""
    cases = _load_regression_cases(QUERY_REGRESSION_CASES_PATH)
    health_failures = _query_regression_health_failures(GBrainAdapter().health())
    if health_failures:
        return {
            "ok": False,
            "total": len(cases),
            "passed": 0,
            "failed": len(cases),
            "preflight_failures": health_failures,
            "cases": [],
        }

    knowledge_sources = KnowledgeSources()
    results: list[dict[str, Any]] = []
    for case in cases:
        sources = knowledge_sources.search_company_sources(case["query"])
        if not sources:
            results.append({"id": case.get("id"), "ok": False, "reason": "no sources returned", "candidates": []})
            continue
        ok, reason = _matches_query_expected(case, sources[0])
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


def _run_think_regression_cases() -> dict[str, Any]:
    """Run think regression cases using module-level adapter (monkeypatch-compatible)."""
    cases = _load_regression_cases(THINK_REGRESSION_CASES_PATH)
    adapter = GBrainAdapter()
    preflight_failures = _query_regression_health_failures(adapter.health(), require_embedding=False) + _think_config_failures()
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
        failures = _validate_think_case(case, response)
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


from app.features.knowledge.quality import admin_helpers as _admin_helpers  # noqa: E402, F401

# Pure helpers (no monkeypatch-sensitive dependencies)
_refresh_error = _admin_helpers.refresh_error
_sync_chunks = _admin_helpers.sync_chunks
_write_audit = _admin_helpers.write_audit
_gbrain_tool_ok = _admin_helpers.gbrain_tool_ok
_gbrain_job_id = _admin_helpers.gbrain_job_id


# Wrappers that use module-level monkeypatched names
def _create_pending_reviews_from_manifest(db: Session, user_id: int, manifest: dict[str, Any]) -> int:
    return _admin_helpers.create_pending_reviews_from_manifest(db, user_id, manifest, settings=load_gbrain_settings())


def _project_source_statuses(db: Session) -> list[dict[str, Any]]:
    return _admin_helpers.project_source_statuses(db, gbrain_adapter_cls=GBrainAdapter)


def _graph_source_derived_path(db: Session, source_id: str) -> Path | None:
    return _admin_helpers.graph_source_derived_path(db, source_id, settings=load_gbrain_settings())


class GBrainJobSubmitRequest(BaseModel):
    name: str
    data: dict[str, Any] = Field(default_factory=dict)
    queue: str | None = None
    priority: int | float | None = None
    max_attempts: int | None = None
    delay: int | None = None
    timeout_ms: int | None = None


class GBrainCitationFixerRequest(BaseModel):
    page_slug: str | None = None
    review_id: int | None = None
    notes: str | None = None
    allowed_slug_prefixes: list[str] = Field(default_factory=list)
    max_turns: int = 30
    model: str | None = None
    queue: str | None = None


class GBrainEntityMergeActionRequest(BaseModel):
    source_id: str = CUSTOMER_INTELLIGENCE_SOURCE_ID
    candidate_id: str
    action: str


class GBrainDreamCycleConfigRequest(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=168, ge=1, le=24 * 90)
    target_score: int = Field(default=90, ge=1, le=100)
    source_id: str = "company-wiki"
    job_names: list[str] = Field(default_factory=lambda: ["autopilot-cycle"])


class GBrainContradictionProbeConfigRequest(BaseModel):
    enabled: bool = False
    interval_hours: int = Field(default=168, ge=1, le=24 * 90)
    source_id: str = "company-wiki"
    queries: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)
    budget_usd: float = Field(default=1.0, ge=0.01, le=100.0)
    judge_model: str | None = None
    timeout_seconds: int = Field(default=600, ge=30, le=3600)
    result_limit: int = Field(default=20, ge=1, le=100)


def _is_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


@router.get("/status")
def knowledge_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    status = get_gbrain_admin_status()
    status["project_sources"] = _project_source_statuses(db)
    status["quality_reports"] = load_quality_reports()
    return status


@router.post("/refresh")
def refresh_knowledge(
    enable_pdf_structured_extraction: bool | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    settings = load_gbrain_settings()
    manifest = compile_company_wiki_sources(
        settings,
        enable_pdf_structured_extraction=enable_pdf_structured_extraction,
    )
    pending_reviews = _create_pending_reviews_from_manifest(db, user.id, manifest)
    sync_result = GBrainAdapter(settings).sync_source(no_pull=True)
    sync_ok = sync_result.get("status") == "ok"
    summary = manifest.get("summary") or {}
    ok = bool(summary.get("failed", 0) == 0 and sync_ok)
    error = None if ok else _refresh_error(manifest, sync_result)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_refresh",
        (
            f"compiled={summary.get('compiled', 0)}, skipped={summary.get('skipped', 0)}, "
            f"failed={summary.get('failed', 0)}, pending_reviews={pending_reviews}, sync={sync_result.get('status')}"
        ),
    )
    db.commit()
    return {
        "ok": ok,
        "error": error,
        "indexed": int(summary.get("compiled", 0) or 0),
        "synced": 1 if sync_ok else 0,
        "skipped": int(summary.get("skipped", 0) or 0),
        "removed": 0,
        "chunks": _sync_chunks(sync_result),
        "errors": int(summary.get("failed", 0) or 0) + (0 if sync_ok else 1),
        "manifest": manifest,
        "sync": sync_result,
        "pending_reviews_created": pending_reviews,
    }


@router.post("/gbrain/start")
def start_gbrain_service(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().start_http_service()
    _write_audit(db, user.id, "admin_gbrain_start", str(result.get("status") or "")[:500])
    db.commit()
    return result


@router.post("/gbrain/restart")
def restart_gbrain_service(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().restart_http_service()
    _write_audit(db, user.id, "admin_gbrain_restart", str(result.get("status") or "")[:500])
    db.commit()
    return result


@router.get("/gbrain/doctor")
def gbrain_doctor(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    return GBrainAdapter().doctor()


@router.get("/gbrain/maintenance")
def gbrain_maintenance(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    result = GBrainAdapter().maintenance_status()
    result["dream_cycle"] = load_dream_cycle_config()
    result["dream_cycle_worker"] = get_gbrain_maintenance_worker_status()
    result["citation_fixer_jobs"] = load_citation_fixer_job_state()
    result["contradiction_probe"] = load_contradiction_probe_config()
    return result


@router.put("/gbrain/dream-cycle")
def update_gbrain_dream_cycle(
    request: GBrainDreamCycleConfigRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    config = save_dream_cycle_config(
        {
            "enabled": request.enabled,
            "interval_hours": request.interval_hours,
            "target_score": request.target_score,
            "source_id": request.source_id,
            "job_names": request.job_names,
        },
        actor=user.username,
    )
    _write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_update",
        f"enabled={config.get('enabled')}, interval_hours={config.get('interval_hours')}, jobs={','.join(config.get('job_names') or [])}",
    )
    db.commit()
    return {"ok": True, "config": config}


@router.post("/gbrain/dream-cycle/run")
def run_gbrain_dream_cycle(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = run_dream_cycle(force=force, actor=user.username)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_run",
        f"status={result.get('status')}, ran={result.get('ran')}, force={force}",
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain Dream Cycle 已执行" if result.get("ran") and result.get("ok") else "GBrain Dream Cycle 未执行",
        content=f"status={result.get('status')} · due={result.get('due')}",
        severity="success" if result.get("ran") and result.get("ok") else "info",
        action_status="none" if result.get("ok") else "pending",
    )
    db.commit()
    return result


@router.post("/gbrain/dream-cycle/tick")
def tick_gbrain_dream_cycle(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = run_dream_cycle_tick(actor=user.username)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_tick",
        f"status={result.get('status')}, ran={result.get('ran')}, due={result.get('due')}",
    )
    if result.get("ran"):
        notify_gbrain_maintenance_event(
            db,
            title="GBrain Dream Cycle 到期任务已提交" if result.get("ok") else "GBrain Dream Cycle 到期任务失败",
            content=f"status={result.get('status')} · due={result.get('due')}",
            severity="success" if result.get("ok") else "warning",
            action_status="pending" if result.get("ok") else "pending",
        )
    db.commit()
    return result


@router.post("/gbrain/dream-cycle/poll-jobs")
def poll_gbrain_dream_cycle_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = poll_dream_cycle_jobs(actor=user.username)
    transitions = result.get("transitions") if isinstance(result.get("transitions"), list) else []
    _write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_poll_jobs",
        f"status={result.get('status')}, checked={result.get('checked')}, transitions={len(transitions)}",
    )
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        job_id = transition.get("job_id")
        status = str(transition.get("status") or "unknown")
        name = str(transition.get("name") or "dream-cycle")
        failed = status in {"failed", "dead", "cancelled", "canceled"}
        notify_gbrain_maintenance_event(
            db,
            title="GBrain Dream Cycle 任务失败" if failed else "GBrain Dream Cycle 任务完成",
            content=f"{name} · job_id={job_id or '-'} · status={status}",
            severity="warning" if failed else "success",
            action_status="pending" if failed else "none",
            event_key=f"gbrain:dream-cycle:job:{job_id}:{status}" if job_id else None,
        )
    db.commit()
    return result


@router.post("/gbrain/dream-cycle/worker/restart")
def restart_gbrain_dream_cycle_worker(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = restart_gbrain_maintenance_worker()
    _write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_worker_restart",
        f"running={result.get('running')}, enabled={result.get('enabled')}, interval_seconds={result.get('interval_seconds')}",
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain Dream Cycle Worker 已重启" if result.get("running") else "GBrain Dream Cycle Worker 未运行",
        content=f"enabled={result.get('enabled')} · interval={result.get('interval_seconds')}s",
        severity="success" if result.get("running") else "warning",
        action_status="none" if result.get("running") else "pending",
    )
    db.commit()
    return {"ok": bool(result.get("running")), "worker": result}


@router.put("/gbrain/contradiction-probe")
def update_gbrain_contradiction_probe(
    request: GBrainContradictionProbeConfigRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    config = save_contradiction_probe_config(
        {
            "enabled": request.enabled,
            "interval_hours": request.interval_hours,
            "source_id": request.source_id,
            "queries": request.queries,
            "top_k": request.top_k,
            "budget_usd": request.budget_usd,
            "judge_model": request.judge_model or "",
            "timeout_seconds": request.timeout_seconds,
            "result_limit": request.result_limit,
        },
        actor=user.username,
    )
    _write_audit(
        db,
        user.id,
        "admin_gbrain_contradiction_probe_update",
        f"enabled={config.get('enabled')}, interval_hours={config.get('interval_hours')}, queries={len(config.get('queries') or [])}",
    )
    db.commit()
    return {"ok": True, "config": config}


@router.post("/gbrain/contradiction-probe/run")
def run_gbrain_contradiction_probe(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = run_contradiction_probe(force=force, actor=user.username)
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    flagged = summary.get("total_contradictions_flagged")
    _write_audit(
        db,
        user.id,
        "admin_gbrain_contradiction_probe_run",
        f"status={result.get('status')}, ran={result.get('ran')}, flagged={flagged if flagged is not None else ''}",
    )
    if result.get("ran"):
        notify_gbrain_maintenance_event(
            db,
            title="GBrain 冲突探针已运行" if result.get("ok") else "GBrain 冲突探针失败",
            content=f"status={result.get('status')} · flagged={flagged if flagged is not None else '-'}",
            severity="warning" if result.get("ok") and flagged else ("success" if result.get("ok") else "warning"),
            action_status="pending" if flagged or not result.get("ok") else "none",
        )
    db.commit()
    return result


@router.post("/gbrain/contradiction-probe/tick")
def tick_gbrain_contradiction_probe(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = run_contradiction_probe_tick(actor=user.username)
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    flagged = summary.get("total_contradictions_flagged")
    _write_audit(
        db,
        user.id,
        "admin_gbrain_contradiction_probe_tick",
        f"status={result.get('status')}, ran={result.get('ran')}, flagged={flagged if flagged is not None else ''}",
    )
    if result.get("ran"):
        notify_gbrain_maintenance_event(
            db,
            title="GBrain 冲突探针到期已运行" if result.get("ok") else "GBrain 冲突探针到期失败",
            content=f"status={result.get('status')} · flagged={flagged if flagged is not None else '-'}",
            severity="warning" if result.get("ok") and flagged else ("success" if result.get("ok") else "warning"),
            action_status="pending" if flagged or not result.get("ok") else "none",
        )
    db.commit()
    return result


@router.post("/gbrain/maintenance/check")
def gbrain_maintenance_check(
    target_score: int = Query(default=90, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().maintenance_check(target_score=target_score)
    ok = _gbrain_tool_ok(result)
    _write_audit(db, user.id, "admin_gbrain_maintenance_check", f"ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护检查完成" if ok else "GBrain 维护检查失败",
        content=str(result.get("error") or result.get("status") or "")[:500],
        severity="success" if ok else "warning",
        action_status="none" if ok else "pending",
    )
    db.commit()
    return {"ok": ok, "result": result}


@router.get("/gbrain/jobs")
def gbrain_jobs(
    status: str | None = Query(default=None),
    queue: str | None = Query(default=None),
    name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    return GBrainAdapter().list_jobs(status=status, queue=queue, name=name, limit=limit)


@router.post("/gbrain/jobs")
def submit_gbrain_job(
    request: GBrainJobSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().submit_job(
        name=request.name,
        data=request.data,
        queue=request.queue,
        priority=request.priority,
        max_attempts=request.max_attempts,
        delay=request.delay,
        timeout_ms=request.timeout_ms,
    )
    ok = _gbrain_tool_ok(result)
    job_id = _gbrain_job_id(result)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_job_submit",
        f"name={request.name}, ok={ok}, status={result.get('status')}, job_id={job_id or ''}",
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护任务已提交" if ok else "GBrain 维护任务提交失败",
        content=f"{request.name} · status={result.get('status') or 'unknown'} · job_id={job_id or '-'}",
        severity="info" if ok else "warning",
        action_status="pending" if ok else "pending",
    )
    db.commit()
    return result


@router.get("/gbrain/jobs/{job_id}")
def gbrain_job_detail(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    adapter = GBrainAdapter()
    return {
        "ok": True,
        "job": adapter.get_job(job_id),
        "progress": adapter.get_job_progress(job_id),
    }


@router.post("/gbrain/jobs/{job_id}/cancel")
def cancel_gbrain_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().cancel_job(job_id)
    ok = _gbrain_tool_ok(result)
    _write_audit(db, user.id, "admin_gbrain_job_cancel", f"job_id={job_id}, ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护任务已取消" if ok else "GBrain 维护任务取消失败",
        content=f"job_id={job_id} · status={result.get('status') or 'unknown'}",
        severity="info" if ok else "warning",
        action_status="none" if ok else "pending",
    )
    db.commit()
    return result


@router.post("/gbrain/jobs/{job_id}/retry")
def retry_gbrain_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().retry_job(job_id)
    ok = _gbrain_tool_ok(result)
    _write_audit(db, user.id, "admin_gbrain_job_retry", f"job_id={job_id}, ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护任务已重试" if ok else "GBrain 维护任务重试失败",
        content=f"job_id={job_id} · status={result.get('status') or 'unknown'}",
        severity="info" if ok else "warning",
        action_status="pending" if ok else "pending",
    )
    db.commit()
    return result


@router.get("/gbrain/contradictions")
def gbrain_contradictions(
    slug: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    return GBrainAdapter().find_contradictions(slug=slug, severity=severity, limit=limit)


@router.get("/gbrain/graph")
def gbrain_graph(
    source_id: str = Query(default=CUSTOMER_INTELLIGENCE_SOURCE_ID),
    focus: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    derived_path = _graph_source_derived_path(db, source_id)
    if derived_path is None:
        raise HTTPException(status_code=404, detail="未知或不可用的 GBrain source")
    result = build_source_graph(
        source_id,
        derived_path=derived_path,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
    )
    _write_audit(
        db,
        user.id,
        "admin_gbrain_graph_view",
        f"source_id={source_id}, focus={focus or ''}, nodes={len(result.get('nodes') or [])}, edges={len(result.get('edges') or [])}",
    )
    db.commit()
    return result


@router.get("/gbrain/entity-merge-candidates")
def gbrain_entity_merge_candidates(
    source_id: str = Query(default=CUSTOMER_INTELLIGENCE_SOURCE_ID),
    focus: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    derived_path = _graph_source_derived_path(db, source_id)
    if derived_path is None:
        raise HTTPException(status_code=404, detail="未知或不可用的 GBrain source")
    result = build_entity_merge_candidates(source_id, derived_path=derived_path, focus=focus, limit=limit)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidates_view",
        f"source_id={source_id}, focus={focus or ''}, candidates={len(result.get('candidates') or [])}",
    )
    db.commit()
    return result


@router.post("/gbrain/entity-merge-candidates/action")
def gbrain_entity_merge_candidate_action(
    request: GBrainEntityMergeActionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    source_id = request.source_id.strip() or CUSTOMER_INTELLIGENCE_SOURCE_ID
    derived_path = _graph_source_derived_path(db, source_id)
    if derived_path is None:
        raise HTTPException(status_code=404, detail="未知或不可用的 GBrain source")
    result = apply_entity_merge_candidate_action(
        source_id,
        request.candidate_id,
        request.action,
        derived_path=derived_path,
        actor=user.username,
    )
    sync_result: dict[str, Any] | None = None
    if result.get("ok") and result.get("status") in {
        "created",
        "already_exists",
        "alias_recorded",
        "alias_already_exists",
        "relink_applied",
    }:
        sync_result = GBrainAdapter().sync_source(source_id=source_id, repo_path=derived_path, no_pull=True)
        result["sync"] = sync_result
    _write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidate_action",
        (
            f"source_id={source_id}, action={request.action}, status={result.get('status')}, "
            f"candidate_id={request.candidate_id[:160]}, sync={(sync_result or {}).get('status') or ''}"
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选操作失败")
    return result


@router.get("/gbrain/entity-merge-candidates/preview")
def gbrain_entity_merge_candidate_preview(
    source_id: str = Query(default=CUSTOMER_INTELLIGENCE_SOURCE_ID),
    candidate_id: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    source_id = source_id.strip() or CUSTOMER_INTELLIGENCE_SOURCE_ID
    derived_path = _graph_source_derived_path(db, source_id)
    if derived_path is None:
        raise HTTPException(status_code=404, detail="未知或不可用的 GBrain source")
    result = build_entity_merge_candidate_preview(source_id, candidate_id, derived_path=derived_path)
    _write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidate_preview",
        (
            f"source_id={source_id}, status={result.get('status')}, "
            f"candidate_id={candidate_id[:160]}, changes={((result.get('stats') or {}).get('planned_relink_changes') or 0)}"
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选预览失败")
    return result


@router.post("/gbrain/citation-fixer")
def submit_gbrain_citation_fixer(
    request: GBrainCitationFixerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = GBrainAdapter().submit_citation_fixer(
        page_slug=request.page_slug,
        review_id=request.review_id,
        notes=request.notes,
        allowed_slug_prefixes=request.allowed_slug_prefixes,
        max_turns=request.max_turns,
        model=request.model,
        queue=request.queue,
    )
    ok = _gbrain_tool_ok(result)
    job_id = _gbrain_job_id(result)
    tracked_state = record_citation_fixer_job(
        submit_result=result,
        page_slug=request.page_slug,
        review_id=request.review_id,
        allowed_slug_prefixes=request.allowed_slug_prefixes,
        actor=user.username,
    ) if ok else None
    _write_audit(
        db,
        user.id,
        "admin_gbrain_citation_fixer_submit",
        (
            f"page_slug={request.page_slug or ''}, review_id={request.review_id or ''}, "
            f"ok={ok}, status={result.get('status')}, job_id={job_id or ''}"
        ),
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 引用修复任务已提交" if ok else "GBrain 引用修复任务提交失败",
        content=f"citation-fixer · status={result.get('status') or 'unknown'} · job_id={job_id or '-'}",
        severity="info" if ok else "warning",
        action_status="pending" if ok else "pending",
    )
    db.commit()
    return {**result, "tracking": tracked_state}


@router.post("/gbrain/citation-fixer/poll-jobs")
def poll_gbrain_citation_fixer_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = poll_citation_fixer_jobs(actor=user.username)
    transitions = result.get("transitions") if isinstance(result.get("transitions"), list) else []
    _write_audit(
        db,
        user.id,
        "admin_gbrain_citation_fixer_poll_jobs",
        f"status={result.get('status')}, checked={result.get('checked')}, transitions={len(transitions)}",
    )
    for transition in transitions:
        if not isinstance(transition, dict):
            continue
        job_id = transition.get("job_id")
        status = str(transition.get("status") or "unknown")
        page_slug = str(transition.get("page_slug") or "")
        failed = status in {"failed", "dead", "cancelled", "canceled"}
        reconcile = transition.get("reconcile") if isinstance(transition.get("reconcile"), dict) else {}
        reconcile_ok = bool(reconcile.get("ok")) if reconcile else False
        notify_gbrain_maintenance_event(
            db,
            title="GBrain 引用修复任务失败" if failed else "GBrain 引用修复任务完成",
            content=(
                f"citation-fixer · job_id={job_id or '-'} · status={status} · "
                f"page={page_slug or '-'} · reconcile={reconcile.get('status') if reconcile else '-'}"
            ),
            severity="warning" if failed or (status == "completed" and not reconcile_ok) else "success",
            action_status="pending" if failed or (status == "completed" and not reconcile_ok) else "none",
            event_key=f"gbrain:citation-fixer:job:{job_id}:{status}" if job_id else None,
        )
    db.commit()
    return result


@router.post("/gbrain/citation-fixer/{job_id}/rollback")
def rollback_gbrain_citation_fixer_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    result = rollback_citation_fixer_job(job_id=job_id, actor=user.username)
    ok = bool(result.get("ok"))
    rollback = result.get("rollback") if isinstance(result.get("rollback"), dict) else {}
    _write_audit(
        db,
        user.id,
        "admin_gbrain_citation_fixer_rollback",
        f"job_id={job_id}, ok={ok}, status={result.get('status')}, commit={rollback.get('commit_hash') or ''}",
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 引用修复已回滚" if ok else "GBrain 引用修复回滚失败",
        content=f"citation-fixer · job_id={job_id} · status={result.get('status')}",
        severity="success" if ok else "warning",
        action_status="none" if ok else "pending",
        event_key=f"gbrain:citation-fixer:rollback:{job_id}:{result.get('status')}",
    )
    db.commit()
    return result


@router.post("/regression")
def knowledge_regression(
    include_think: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    query_result = _run_query_regression_cases()
    think_result = (
        _run_think_regression_cases()
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
    saved_report = save_quality_report(report, actor=user.username)
    _write_audit(
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


@router.get("/quality-reports/{report_id}")
def get_quality_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    reports = load_quality_reports().get("reports")
    report_list = reports if isinstance(reports, list) else []
    if report_id == "latest" and report_list:
        return report_list[0]
    for report in report_list:
        if str(report.get("id") or "") == report_id:
            return report
    raise HTTPException(status_code=404, detail="质量报告不存在")

