from __future__ import annotations

from datetime import datetime, timezone
import os
import threading
import time
from typing import Any, Callable

from sqlalchemy.orm import Session

from core.gbrain_citation_fixer_jobs import poll_citation_fixer_jobs
from core.gbrain_contradiction_probe import run_contradiction_probe_tick
from core.gbrain_dream_cycle import poll_dream_cycle_jobs, run_dream_cycle_tick
from core.notification_service import notify_gbrain_maintenance_event, system_admin_ids
from models import SessionLocal
from models.audit_log import AuditLog


DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 30
MAX_INTERVAL_SECONDS = 24 * 60 * 60
WORKER_ACTOR = "gbrain-maintenance-worker"

_state_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_state: dict[str, Any] = {
    "enabled": False,
    "running": False,
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "started_at": None,
    "stopped_at": None,
    "last_heartbeat_at": None,
    "last_tick_result": None,
    "last_poll_result": None,
    "last_citation_fixer_poll_result": None,
    "last_contradiction_probe_result": None,
    "last_error": None,
    "run_count": 0,
}


def maintenance_worker_enabled() -> bool:
    raw = os.getenv("PR_GBRAIN_MAINTENANCE_WORKER_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def maintenance_worker_interval_seconds() -> int:
    raw = os.getenv("PR_GBRAIN_MAINTENANCE_WORKER_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_INTERVAL_SECONDS
    return max(MIN_INTERVAL_SECONDS, min(value, MAX_INTERVAL_SECONDS))


def start_gbrain_maintenance_worker(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    interval_seconds: int | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    if enabled is None:
        enabled = maintenance_worker_enabled()
    interval = max(MIN_INTERVAL_SECONDS, min(interval_seconds or maintenance_worker_interval_seconds(), MAX_INTERVAL_SECONDS))
    with _state_lock:
        _state["enabled"] = bool(enabled)
        _state["interval_seconds"] = interval
        if not enabled:
            _state["running"] = False
            return dict(_state)
        global _thread
        if _thread and _thread.is_alive():
            _state["running"] = True
            return dict(_state)
        _stop_event.clear()
        _thread = threading.Thread(
            target=_worker_loop,
            kwargs={"session_factory": session_factory, "interval_seconds": interval},
            name="project-r-gbrain-maintenance-worker",
            daemon=True,
        )
        _state["running"] = True
        _state["started_at"] = _now()
        _state["stopped_at"] = None
        _state["last_error"] = None
        _thread.start()
        return dict(_state)


def stop_gbrain_maintenance_worker(*, timeout_seconds: float = 2.0) -> dict[str, Any]:
    _stop_event.set()
    thread = _thread
    if thread and thread.is_alive():
        thread.join(timeout=timeout_seconds)
    with _state_lock:
        _state["running"] = bool(thread and thread.is_alive())
        _state["stopped_at"] = None if _state["running"] else _now()
        return dict(_state)


def restart_gbrain_maintenance_worker(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    stop_gbrain_maintenance_worker()
    return start_gbrain_maintenance_worker(session_factory=session_factory, interval_seconds=interval_seconds, enabled=True)


def get_gbrain_maintenance_worker_status() -> dict[str, Any]:
    with _state_lock:
        status = dict(_state)
    thread = _thread
    status["thread_alive"] = bool(thread and thread.is_alive())
    return status


def run_gbrain_maintenance_worker_once(
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    actor: str = WORKER_ACTOR,
) -> dict[str, Any]:
    db = session_factory()
    try:
        tick = run_dream_cycle_tick(actor=actor)
        poll = poll_dream_cycle_jobs(actor=actor)
        citation_fixer_poll = poll_citation_fixer_jobs(actor=actor)
        contradiction_probe = run_contradiction_probe_tick(actor=actor)
        _notify_worker_results(
            db,
            tick=tick,
            poll=poll,
            citation_fixer_poll=citation_fixer_poll,
            contradiction_probe=contradiction_probe,
        )
        _write_worker_audit(
            db,
            tick=tick,
            poll=poll,
            citation_fixer_poll=citation_fixer_poll,
            contradiction_probe=contradiction_probe,
        )
        db.commit()
        result = {
            "ok": True,
            "tick": tick,
            "poll": poll,
            "citation_fixer_poll": citation_fixer_poll,
            "contradiction_probe": contradiction_probe,
            "ran_at": _now(),
        }
        with _state_lock:
            _state["last_tick_result"] = _compact_result(tick)
            _state["last_poll_result"] = _compact_result(poll)
            _state["last_citation_fixer_poll_result"] = _compact_result(citation_fixer_poll)
            _state["last_contradiction_probe_result"] = _compact_result(contradiction_probe)
            _state["last_heartbeat_at"] = result["ran_at"]
            _state["last_error"] = None
            _state["run_count"] = int(_state.get("run_count") or 0) + 1
        return result
    except Exception as exc:
        db.rollback()
        error = str(exc)
        with _state_lock:
            _state["last_error"] = error
            _state["last_heartbeat_at"] = _now()
        _record_worker_error(db, error)
        raise
    finally:
        db.close()


def _worker_loop(*, session_factory: Callable[[], Session], interval_seconds: int) -> None:
    while not _stop_event.is_set():
        try:
            run_gbrain_maintenance_worker_once(session_factory=session_factory)
        except Exception:
            pass
        _stop_event.wait(interval_seconds)
    with _state_lock:
        _state["running"] = False
        _state["stopped_at"] = _now()


def _notify_worker_results(
    db: Session,
    *,
    tick: dict[str, Any],
    poll: dict[str, Any],
    citation_fixer_poll: dict[str, Any],
    contradiction_probe: dict[str, Any],
) -> None:
    if tick.get("ran"):
        notify_gbrain_maintenance_event(
            db,
            title="GBrain Dream Cycle 定时任务已提交" if tick.get("ok") else "GBrain Dream Cycle 定时任务失败",
            content=f"worker · status={tick.get('status')} · due={tick.get('due')}",
            severity="success" if tick.get("ok") else "warning",
            action_status="pending" if tick.get("ok") else "pending",
        )
    transitions = poll.get("transitions") if isinstance(poll.get("transitions"), list) else []
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
    citation_transitions = (
        citation_fixer_poll.get("transitions") if isinstance(citation_fixer_poll.get("transitions"), list) else []
    )
    for transition in citation_transitions:
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
                f"worker · citation-fixer · job_id={job_id or '-'} · status={status} · "
                f"page={page_slug or '-'} · reconcile={reconcile.get('status') if reconcile else '-'}"
            ),
            severity="warning" if failed or (status == "completed" and not reconcile_ok) else "success",
            action_status="pending" if failed or (status == "completed" and not reconcile_ok) else "none",
            event_key=f"gbrain:citation-fixer:job:{job_id}:{status}" if job_id else None,
        )
    if contradiction_probe.get("ran"):
        summary = contradiction_probe.get("summary") if isinstance(contradiction_probe.get("summary"), dict) else {}
        flagged = summary.get("total_contradictions_flagged")
        notify_gbrain_maintenance_event(
            db,
            title="GBrain 冲突探针已运行" if contradiction_probe.get("ok") else "GBrain 冲突探针失败",
            content=(
                f"worker · status={contradiction_probe.get('status')} · "
                f"flagged={flagged if flagged is not None else '-'}"
            ),
            severity="warning" if contradiction_probe.get("ok") and flagged else ("success" if contradiction_probe.get("ok") else "warning"),
            action_status="pending" if flagged or not contradiction_probe.get("ok") else "none",
            event_key=f"gbrain:contradiction-probe:{contradiction_probe.get('ran_at') or _now()}",
        )


def _write_worker_audit(
    db: Session,
    *,
    tick: dict[str, Any],
    poll: dict[str, Any],
    citation_fixer_poll: dict[str, Any],
    contradiction_probe: dict[str, Any],
) -> None:
    admin_ids = system_admin_ids(db)
    if not admin_ids:
        return
    transitions = poll.get("transitions") if isinstance(poll.get("transitions"), list) else []
    citation_transitions = (
        citation_fixer_poll.get("transitions") if isinstance(citation_fixer_poll.get("transitions"), list) else []
    )
    db.add(
        AuditLog(
            user_id=admin_ids[0],
            action="gbrain_dream_cycle_worker_tick",
            detail=(
                f"tick_status={tick.get('status')}, ran={tick.get('ran')}, "
                f"poll_status={poll.get('status')}, checked={poll.get('checked')}, transitions={len(transitions)}, "
                f"citation_fixer_poll_status={citation_fixer_poll.get('status')}, "
                f"citation_fixer_checked={citation_fixer_poll.get('checked')}, "
                f"citation_fixer_transitions={len(citation_transitions)}, "
                f"contradiction_probe_status={contradiction_probe.get('status')}, "
                f"contradiction_probe_ran={contradiction_probe.get('ran')}"
            ),
            success=bool(tick.get("ok") and poll.get("ok") and citation_fixer_poll.get("ok") and contradiction_probe.get("ok")),
        )
    )


def _record_worker_error(db: Session, error: str) -> None:
    try:
        notify_gbrain_maintenance_event(
            db,
            title="GBrain 维护 Worker 异常",
            content=f"worker · error={error[:500]}",
            severity="critical",
            action_status="pending",
            event_key=f"gbrain:maintenance-worker:error:{_now()}",
        )
        admin_ids = system_admin_ids(db)
        if admin_ids:
            db.add(
                AuditLog(
                    user_id=admin_ids[0],
                    action="gbrain_dream_cycle_worker_error",
                    detail=f"error={error[:500]}",
                    success=False,
                )
            )
        db.commit()
    except Exception:
        db.rollback()


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "ok": result.get("ok"),
        "status": result.get("status"),
        "ran": result.get("ran"),
        "due": result.get("due"),
        "checked": result.get("checked"),
        "transitions": result.get("transitions"),
        "ran_at": result.get("ran_at"),
    }
    return {key: value for key, value in compact.items() if value is not None}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
