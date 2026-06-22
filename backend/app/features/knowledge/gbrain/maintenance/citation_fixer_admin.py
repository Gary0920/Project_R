from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import GBrainAdapter
from app.features.knowledge.gbrain.maintenance.citation_fixer_jobs import (
    poll_citation_fixer_jobs,
    record_citation_fixer_job,
    rollback_citation_fixer_job,
)
from app.features.knowledge.quality.admin_helpers import gbrain_job_id, gbrain_tool_ok, write_audit
from app.features.notifications.service import notify_gbrain_maintenance_event
from models.user import User


def submit_citation_fixer(
    db: Session,
    *,
    user: User,
    request: Any,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    result = adapter_cls().submit_citation_fixer(
        page_slug=request.page_slug,
        review_id=request.review_id,
        notes=request.notes,
        allowed_slug_prefixes=request.allowed_slug_prefixes,
        max_turns=request.max_turns,
        model=request.model,
        queue=request.queue,
    )
    ok = gbrain_tool_ok(result)
    job_id = gbrain_job_id(result)
    tracked_state = (
        record_citation_fixer_job(
            submit_result=result,
            page_slug=request.page_slug,
            review_id=request.review_id,
            allowed_slug_prefixes=request.allowed_slug_prefixes,
            actor=user.username,
        )
        if ok
        else None
    )
    write_audit(
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


def poll_citation_fixer_tracked_jobs(db: Session, *, user: User) -> dict[str, Any]:
    result = poll_citation_fixer_jobs(actor=user.username)
    transitions = result.get("transitions") if isinstance(result.get("transitions"), list) else []
    write_audit(
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


def rollback_citation_fixer(db: Session, *, user: User, job_id: int) -> dict[str, Any]:
    result = rollback_citation_fixer_job(job_id=job_id, actor=user.username)
    ok = bool(result.get("ok"))
    rollback = result.get("rollback") if isinstance(result.get("rollback"), dict) else {}
    write_audit(
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
