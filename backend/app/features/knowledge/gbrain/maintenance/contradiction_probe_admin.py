from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain.maintenance.contradiction_probe import (
    run_contradiction_probe,
    run_contradiction_probe_tick,
    save_contradiction_probe_config,
)
from app.features.knowledge.quality.admin_helpers import write_audit
from app.features.notifications.service import notify_gbrain_maintenance_event
from models.user import User


def update_contradiction_probe_config(db: Session, *, user: User, request: Any) -> dict[str, Any]:
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
    write_audit(
        db,
        user.id,
        "admin_gbrain_contradiction_probe_update",
        f"enabled={config.get('enabled')}, interval_hours={config.get('interval_hours')}, queries={len(config.get('queries') or [])}",
    )
    db.commit()
    return {"ok": True, "config": config}


def run_contradiction_probe_now(db: Session, *, user: User, force: bool) -> dict[str, Any]:
    result = run_contradiction_probe(force=force, actor=user.username)
    _audit_probe_result(db, user, result, action="admin_gbrain_contradiction_probe_run")
    _notify_probe_result(db, result, ran_title="GBrain 冲突探针已运行", failed_title="GBrain 冲突探针失败")
    db.commit()
    return result


def tick_contradiction_probe(db: Session, *, user: User) -> dict[str, Any]:
    result = run_contradiction_probe_tick(actor=user.username)
    _audit_probe_result(db, user, result, action="admin_gbrain_contradiction_probe_tick")
    _notify_probe_result(db, result, ran_title="GBrain 冲突探针到期已运行", failed_title="GBrain 冲突探针到期失败")
    db.commit()
    return result


def _audit_probe_result(db: Session, user: User, result: dict[str, Any], *, action: str) -> None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    flagged = summary.get("total_contradictions_flagged")
    write_audit(
        db,
        user.id,
        action,
        f"status={result.get('status')}, ran={result.get('ran')}, flagged={flagged if flagged is not None else ''}",
    )


def _notify_probe_result(db: Session, result: dict[str, Any], *, ran_title: str, failed_title: str) -> None:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    flagged = summary.get("total_contradictions_flagged")
    if result.get("ran"):
        notify_gbrain_maintenance_event(
            db,
            title=ran_title if result.get("ok") else failed_title,
            content=f"status={result.get('status')} · flagged={flagged if flagged is not None else '-'}",
            severity="warning" if result.get("ok") and flagged else ("success" if result.get("ok") else "warning"),
            action_status="pending" if flagged or not result.get("ok") else "none",
        )
