from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import GBrainAdapter
from app.features.knowledge.gbrain.maintenance.citation_fixer_jobs import load_citation_fixer_job_state
from app.features.knowledge.gbrain.maintenance.contradiction_probe import load_contradiction_probe_config
from app.features.knowledge.gbrain.maintenance.dream_cycle import load_dream_cycle_config
from app.features.knowledge.gbrain.maintenance.worker import get_gbrain_maintenance_worker_status
from app.features.knowledge.quality.admin_helpers import gbrain_job_id, gbrain_tool_ok, write_audit
from app.features.notifications.service import notify_gbrain_maintenance_event
from models.user import User


def maintenance_status(adapter_cls: type[GBrainAdapter] = GBrainAdapter) -> dict[str, Any]:
    result = adapter_cls().maintenance_status()
    result["dream_cycle"] = load_dream_cycle_config()
    result["dream_cycle_worker"] = get_gbrain_maintenance_worker_status()
    result["citation_fixer_jobs"] = load_citation_fixer_job_state()
    result["contradiction_probe"] = load_contradiction_probe_config()
    return result


def maintenance_check(
    db: Session,
    *,
    user: User,
    target_score: int,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    result = adapter_cls().maintenance_check(target_score=target_score)
    ok = gbrain_tool_ok(result)
    write_audit(db, user.id, "admin_gbrain_maintenance_check", f"ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护检查完成" if ok else "GBrain 维护检查失败",
        content=str(result.get("error") or result.get("status") or "")[:500],
        severity="success" if ok else "warning",
        action_status="none" if ok else "pending",
    )
    db.commit()
    return {"ok": ok, "result": result}


def list_jobs(
    *,
    status: str | None,
    queue: str | None,
    name: str | None,
    limit: int,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    return adapter_cls().list_jobs(status=status, queue=queue, name=name, limit=limit)


def submit_job(
    db: Session,
    *,
    user: User,
    request: Any,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    result = adapter_cls().submit_job(
        name=request.name,
        data=request.data,
        queue=request.queue,
        priority=request.priority,
        max_attempts=request.max_attempts,
        delay=request.delay,
        timeout_ms=request.timeout_ms,
    )
    ok = gbrain_tool_ok(result)
    job_id = gbrain_job_id(result)
    write_audit(
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


def job_detail(*, job_id: int, adapter_cls: type[GBrainAdapter] = GBrainAdapter) -> dict[str, Any]:
    adapter = adapter_cls()
    return {
        "ok": True,
        "job": adapter.get_job(job_id),
        "progress": adapter.get_job_progress(job_id),
    }


def cancel_job(
    db: Session,
    *,
    user: User,
    job_id: int,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    result = adapter_cls().cancel_job(job_id)
    ok = gbrain_tool_ok(result)
    write_audit(db, user.id, "admin_gbrain_job_cancel", f"job_id={job_id}, ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护任务已取消" if ok else "GBrain 维护任务取消失败",
        content=f"job_id={job_id} · status={result.get('status') or 'unknown'}",
        severity="info" if ok else "warning",
        action_status="none" if ok else "pending",
    )
    db.commit()
    return result


def retry_job(
    db: Session,
    *,
    user: User,
    job_id: int,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    result = adapter_cls().retry_job(job_id)
    ok = gbrain_tool_ok(result)
    write_audit(db, user.id, "admin_gbrain_job_retry", f"job_id={job_id}, ok={ok}, status={result.get('status')}")
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 维护任务已重试" if ok else "GBrain 维护任务重试失败",
        content=f"job_id={job_id} · status={result.get('status') or 'unknown'}",
        severity="info" if ok else "warning",
        action_status="pending" if ok else "pending",
    )
    db.commit()
    return result


def find_contradictions(
    *,
    slug: str | None,
    severity: str | None,
    limit: int,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    return adapter_cls().find_contradictions(slug=slug, severity=severity, limit=limit)
