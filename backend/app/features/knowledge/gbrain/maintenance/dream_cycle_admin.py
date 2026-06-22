from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain.maintenance.dream_cycle import (
    poll_dream_cycle_jobs,
    run_dream_cycle,
    run_dream_cycle_tick,
    save_dream_cycle_config,
)
from app.features.knowledge.gbrain.maintenance.worker import restart_gbrain_maintenance_worker
from app.features.knowledge.quality.admin_helpers import write_audit
from app.features.notifications.service import notify_gbrain_maintenance_event
from models.user import User


def update_dream_cycle_config(db: Session, *, user: User, request: Any) -> dict[str, Any]:
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
    write_audit(
        db,
        user.id,
        "admin_gbrain_dream_cycle_update",
        f"enabled={config.get('enabled')}, interval_hours={config.get('interval_hours')}, jobs={','.join(config.get('job_names') or [])}",
    )
    db.commit()
    return {"ok": True, "config": config}


def run_dream_cycle_now(db: Session, *, user: User, force: bool) -> dict[str, Any]:
    result = run_dream_cycle(force=force, actor=user.username)
    write_audit(
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


def tick_dream_cycle(db: Session, *, user: User) -> dict[str, Any]:
    result = run_dream_cycle_tick(actor=user.username)
    write_audit(
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


def poll_dream_cycle_tracked_jobs(db: Session, *, user: User) -> dict[str, Any]:
    result = poll_dream_cycle_jobs(actor=user.username)
    transitions = result.get("transitions") if isinstance(result.get("transitions"), list) else []
    write_audit(
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


def restart_dream_cycle_worker(db: Session, *, user: User) -> dict[str, Any]:
    result = restart_gbrain_maintenance_worker()
    write_audit(
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
