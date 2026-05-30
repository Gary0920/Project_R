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
from core.gbrain import GBrainAdapter, get_gbrain_admin_status, load_gbrain_settings
from core.gbrain_ingest import compile_company_wiki_sources
from core.knowledge_sources import KnowledgeSources
from core.notification_service import notify_gbrain_maintenance_event
from models import get_db
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace

router = APIRouter(prefix="/admin/knowledge", tags=["gbrain"])
BACKEND_DIR = Path(__file__).resolve().parents[1]
QUERY_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_query_regression_cases.json"
THINK_REGRESSION_CASES_PATH = BACKEND_DIR / "tests" / "fixtures" / "gbrain_think_regression_cases.json"


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
    return GBrainAdapter().maintenance_status()


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
    _write_audit(
        db,
        user.id,
        "admin_gbrain_regression",
        (
            f"ok={ok}, query_passed={query_result.get('passed', 0)}/{query_result.get('total', 0)}, "
            f"think_passed={think_result.get('passed', 0)}/{think_result.get('total', 0)}, "
            f"include_think={include_think}"
        ),
    )
    db.commit()
    return {
        "ok": ok,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "include_think": include_think,
        "query": query_result,
        "think": think_result,
    }


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
