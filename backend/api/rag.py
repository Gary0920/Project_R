from __future__ import annotations

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
from app.features.knowledge.gbrain import admin_graph
from app.features.knowledge.gbrain.maintenance import (
    citation_fixer_admin,
    contradiction_probe_admin,
    dream_cycle_admin,
    jobs_admin,
)
from app.features.knowledge.gbrain.ingest import compile_company_wiki_sources
from app.features.knowledge.browser import (
    search_knowledge_for_workspace,
    serialize_source_scopes,
    source_scopes_for_workspace,
)
from app.features.knowledge.quality import admin_reports as _admin_reports
from app.features.workspaces.permissions import ensure_can_open_workspace
from models import get_db
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
    return _admin_reports.load_quality_reports(settings=load_gbrain_settings())


def save_quality_report(report: dict, *, actor: str) -> dict:
    return _admin_reports.save_quality_report(report, actor=actor, settings=load_gbrain_settings())


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
    return _admin_reports.run_query_regression_cases(QUERY_REGRESSION_CASES_PATH, adapter_cls=GBrainAdapter)


def _run_think_regression_cases() -> dict[str, Any]:
    """Run think regression cases using module-level adapter (monkeypatch-compatible)."""
    return _admin_reports.run_think_regression_cases(THINK_REGRESSION_CASES_PATH, adapter_cls=GBrainAdapter)


from app.features.knowledge.quality import admin_helpers as _admin_helpers  # noqa: E402, F401

# Pure helpers (no monkeypatch-sensitive dependencies)
_refresh_error = _admin_helpers.refresh_error
_sync_chunks = _admin_helpers.sync_chunks
_write_audit = _admin_helpers.write_audit


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
    return jobs_admin.maintenance_status(adapter_cls=GBrainAdapter)


@router.put("/gbrain/dream-cycle")
def update_gbrain_dream_cycle(
    request: GBrainDreamCycleConfigRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return dream_cycle_admin.update_dream_cycle_config(db, user=user, request=request)


@router.post("/gbrain/dream-cycle/run")
def run_gbrain_dream_cycle(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return dream_cycle_admin.run_dream_cycle_now(db, user=user, force=force)


@router.post("/gbrain/dream-cycle/tick")
def tick_gbrain_dream_cycle(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return dream_cycle_admin.tick_dream_cycle(db, user=user)


@router.post("/gbrain/dream-cycle/poll-jobs")
def poll_gbrain_dream_cycle_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return dream_cycle_admin.poll_dream_cycle_tracked_jobs(db, user=user)


@router.post("/gbrain/dream-cycle/worker/restart")
def restart_gbrain_dream_cycle_worker(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return dream_cycle_admin.restart_dream_cycle_worker(db, user=user)


@router.put("/gbrain/contradiction-probe")
def update_gbrain_contradiction_probe(
    request: GBrainContradictionProbeConfigRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return contradiction_probe_admin.update_contradiction_probe_config(db, user=user, request=request)


@router.post("/gbrain/contradiction-probe/run")
def run_gbrain_contradiction_probe(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return contradiction_probe_admin.run_contradiction_probe_now(db, user=user, force=force)


@router.post("/gbrain/contradiction-probe/tick")
def tick_gbrain_contradiction_probe(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return contradiction_probe_admin.tick_contradiction_probe(db, user=user)


@router.post("/gbrain/maintenance/check")
def gbrain_maintenance_check(
    target_score: int = Query(default=90, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return jobs_admin.maintenance_check(db, user=user, target_score=target_score, adapter_cls=GBrainAdapter)


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
    return jobs_admin.list_jobs(status=status, queue=queue, name=name, limit=limit, adapter_cls=GBrainAdapter)


@router.post("/gbrain/jobs")
def submit_gbrain_job(
    request: GBrainJobSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return jobs_admin.submit_job(db, user=user, request=request, adapter_cls=GBrainAdapter)


@router.get("/gbrain/jobs/{job_id}")
def gbrain_job_detail(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    del db
    _is_admin(user)
    return jobs_admin.job_detail(job_id=job_id, adapter_cls=GBrainAdapter)


@router.post("/gbrain/jobs/{job_id}/cancel")
def cancel_gbrain_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return jobs_admin.cancel_job(db, user=user, job_id=job_id, adapter_cls=GBrainAdapter)


@router.post("/gbrain/jobs/{job_id}/retry")
def retry_gbrain_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return jobs_admin.retry_job(db, user=user, job_id=job_id, adapter_cls=GBrainAdapter)


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
    return jobs_admin.find_contradictions(slug=slug, severity=severity, limit=limit, adapter_cls=GBrainAdapter)


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
    return admin_graph.view_source_graph(
        db,
        user=user,
        source_id=source_id,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
        resolve_source_path=_graph_source_derived_path,
    )


@router.get("/gbrain/entity-merge-candidates")
def gbrain_entity_merge_candidates(
    source_id: str = Query(default=CUSTOMER_INTELLIGENCE_SOURCE_ID),
    focus: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return admin_graph.list_entity_merge_candidates(
        db,
        user=user,
        source_id=source_id,
        focus=focus,
        limit=limit,
        resolve_source_path=_graph_source_derived_path,
    )


@router.post("/gbrain/entity-merge-candidates/action")
def gbrain_entity_merge_candidate_action(
    request: GBrainEntityMergeActionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return admin_graph.apply_entity_merge_action(
        db,
        user=user,
        request=request,
        resolve_source_path=_graph_source_derived_path,
        adapter_cls=GBrainAdapter,
    )


@router.get("/gbrain/entity-merge-candidates/preview")
def gbrain_entity_merge_candidate_preview(
    source_id: str = Query(default=CUSTOMER_INTELLIGENCE_SOURCE_ID),
    candidate_id: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return admin_graph.preview_entity_merge_candidate(
        db,
        user=user,
        source_id=source_id,
        candidate_id=candidate_id,
        resolve_source_path=_graph_source_derived_path,
    )


@router.post("/gbrain/citation-fixer")
def submit_gbrain_citation_fixer(
    request: GBrainCitationFixerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return citation_fixer_admin.submit_citation_fixer(db, user=user, request=request, adapter_cls=GBrainAdapter)


@router.post("/gbrain/citation-fixer/poll-jobs")
def poll_gbrain_citation_fixer_jobs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return citation_fixer_admin.poll_citation_fixer_tracked_jobs(db, user=user)


@router.post("/gbrain/citation-fixer/{job_id}/rollback")
def rollback_gbrain_citation_fixer_job(
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return citation_fixer_admin.rollback_citation_fixer(db, user=user, job_id=job_id)


@router.post("/regression")
def knowledge_regression(
    include_think: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return _admin_reports.run_admin_regression(
        db,
        user=user,
        include_think=include_think,
        query_runner=_run_query_regression_cases,
        think_runner=_run_think_regression_cases,
        save_report=save_quality_report,
    )


@router.get("/quality-reports/{report_id}")
def get_quality_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _is_admin(user)
    return _admin_reports.get_quality_report(report_id, load_reports=load_quality_reports)

