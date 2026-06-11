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
from app.features.notifications.service import notify_gbrain_maintenance_event
from models import get_db
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace

router = APIRouter(prefix="/admin/knowledge", tags=["gbrain"])
BACKEND_DIR = Path(__file__).resolve().parents[1]
QUERY_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_query_regression_cases.json"
THINK_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_think_regression_cases.json"
QUALITY_REPORTS_MANIFEST_NAME = "gbrain-quality-reports.json"
QUALITY_REPORTS_LIMIT = 20


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


def _create_pending_reviews_from_manifest(db: Session, user_id: int, manifest: dict[str, Any]) -> int:
    settings = load_gbrain_settings()
    created = 0
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("review_status") != "pending_review":
            continue
        target_file = item.get("target_file")
        if not isinstance(target_file, str) or not target_file:
            continue
        source = f"gbrain_pending_review:{target_file}"
        existing = (
            db.query(KnowledgeReview)
            .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
            .first()
        )
        if existing:
            continue
        content_path = (settings.derived_path / target_file).resolve()
        try:
            content_path.relative_to(settings.derived_path.resolve())
            content = content_path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            content = f"Pending review file: {target_file}"
        db.add(
            KnowledgeReview(
                submitter_id=user_id,
                content=content,
                source=source,
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
        )
        created += 1
    return created


def load_quality_reports() -> dict[str, Any]:
    path = _quality_reports_path()
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


def save_quality_report(report: dict[str, Any], *, actor: str) -> dict[str, Any]:
    path = _quality_reports_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = load_quality_reports().get("reports")
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


def _quality_reports_path() -> Path:
    return load_gbrain_settings().manifests_path / QUALITY_REPORTS_MANIFEST_NAME


def _quality_report_summary(report: dict[str, Any]) -> dict[str, Any]:
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


def _refresh_error(manifest: dict[str, Any], sync_result: dict[str, Any]) -> str:
    failed = int((manifest.get("summary") or {}).get("failed", 0) or 0)
    if failed:
        return f"raw 编译有 {failed} 个失败项，请查看 manifest 中的 error 后重试。"
    if sync_result.get("status") != "ok":
        return f"GBrain sync 未完成：{sync_result.get('status') or 'unknown'} {sync_result.get('error') or ''}".strip()
    return "刷新失败。"


def _sync_chunks(sync_result: dict[str, Any]) -> int:
    result = sync_result.get("result")
    if isinstance(result, dict):
        for key in ("chunksCreated", "chunks_created", "chunks"):
            value = result.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return 0


def _write_audit(db: Session, user_id: int, action: str, detail: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=True))


def _gbrain_tool_ok(result: dict[str, Any]) -> bool:
    return result.get("status") == "ok" and not (isinstance(result.get("result"), dict) and result["result"].get("error"))


def _gbrain_job_id(result: dict[str, Any]) -> int | None:
    payload = result.get("result")
    if isinstance(payload, dict):
        value = payload.get("id")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _run_query_regression_cases() -> dict[str, Any]:
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


def _project_source_statuses(db: Session) -> list[dict[str, Any]]:
    projects = (
        db.query(Workspace)
        .filter(Workspace.workspace_kind == "project", Workspace.is_archived == False)
        .order_by(Workspace.updated_at.desc(), Workspace.id.desc())
        .limit(100)
        .all()
    )
    if not projects:
        return []
    adapter = GBrainAdapter()
    statuses: list[dict[str, Any]] = []
    for workspace in projects:
        source_status = adapter.project_source_status(workspace)
        expected = source_status.get("expected") or {}
        statuses.append(
            {
                "workspace_id": workspace.id,
                "workspace_name": workspace.name,
                "brand": workspace.brand,
                "slug": workspace.slug,
                "source_id": expected.get("source_id"),
                "source_path": expected.get("path"),
                "status": source_status.get("status"),
                "registered": bool(source_status.get("registered")),
                "path_matches": bool(source_status.get("path_matches")),
                "source": source_status.get("source") or {},
                "error": source_status.get("error"),
            }
        )
    return statuses


def _graph_source_derived_path(db: Session, source_id: str) -> Path | None:
    source_id = str(source_id or "").strip()
    settings = load_gbrain_settings()
    if source_id == settings.company_source_id:
        return settings.derived_path
    if source_id == CUSTOMER_INTELLIGENCE_SOURCE_ID:
        return CUSTOMER_REFERENCE_DERIVED
    if source_id.startswith("project-"):
        projects = (
            db.query(Workspace)
            .filter(Workspace.workspace_kind == "project", Workspace.is_archived == False)
            .all()
        )
        for workspace in projects:
            try:
                if project_source_id_for_workspace(workspace) == source_id:
                    return project_source_paths_for_workspace(workspace)["derived"]
            except ValueError:
                continue
    if source_id.startswith("customer-"):
        customers = (
            db.query(Workspace)
            .filter(Workspace.workspace_kind == "customer", Workspace.is_archived == False)
            .all()
        )
        for workspace in customers:
            try:
                if customer_source_id_for_workspace(workspace) == source_id:
                    return customer_source_paths_for_workspace(workspace)["derived"]
            except ValueError:
                continue
    return None
