from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy.orm import Session

from core.time_utils import serialize_datetime_utc
from models.agent_run import AgentEvent, AgentRun


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def create_agent_run(
    db: Session,
    *,
    user_id: int,
    title: str,
    source_type: str,
    source_id: str | int | None = None,
    session_id: int | None = None,
    message_id: int | None = None,
    workspace_id: int | None = None,
    status: str = "running",
    result: dict[str, Any] | None = None,
    error_message: str = "",
) -> AgentRun:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        user_id=user_id,
        session_id=session_id,
        message_id=message_id,
        workspace_id=workspace_id,
        source_type=source_type,
        source_id=str(source_id or ""),
        title=title[:255],
        status=status,
        result_json=json.dumps(result or {}, ensure_ascii=False, default=_json_default),
        error_message=error_message,
        completed_at=now if status in TERMINAL_STATUSES else None,
    )
    db.add(run)
    db.flush()
    return run


def add_agent_event(
    db: Session,
    run: AgentRun,
    *,
    event_type: str,
    title: str,
    detail: str = "",
    status: str = "running",
    payload: dict[str, Any] | None = None,
) -> AgentEvent:
    sequence = (
        db.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id)
        .count()
        + 1
    )
    event = AgentEvent(
        run_id=run.id,
        sequence=sequence,
        event_type=event_type,
        title=title[:255],
        detail=detail,
        status=status,
        payload_json=json.dumps(payload or {}, ensure_ascii=False, default=_json_default),
    )
    db.add(event)
    db.flush()
    return event


def finish_agent_run(
    db: Session,
    run: AgentRun,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error_message: str = "",
) -> AgentRun:
    run.status = status
    run.result_json = json.dumps(result or {}, ensure_ascii=False, default=_json_default)
    run.error_message = error_message
    if status in TERMINAL_STATUSES:
        run.completed_at = datetime.now(timezone.utc)
    db.flush()
    return run


def get_agent_run_for_message(db: Session, user_id: int, message_id: int) -> AgentRun | None:
    return (
        db.query(AgentRun)
        .filter(AgentRun.user_id == user_id, AgentRun.message_id == message_id)
        .order_by(AgentRun.id.desc())
        .first()
    )


def serialize_agent_run(db: Session, run: AgentRun | None) -> dict[str, Any] | None:
    if not run:
        return None
    events = (
        db.query(AgentEvent)
        .filter(AgentEvent.run_id == run.id)
        .order_by(AgentEvent.sequence.asc(), AgentEvent.id.asc())
        .all()
    )
    return {
        "id": run.id,
        "user_id": run.user_id,
        "session_id": run.session_id,
        "message_id": run.message_id,
        "workspace_id": run.workspace_id,
        "source_type": run.source_type,
        "source_id": run.source_id,
        "title": run.title,
        "status": run.status,
        "result": _loads(run.result_json),
        "error_message": run.error_message,
        "created_at": serialize_datetime_utc(run.created_at),
        "updated_at": serialize_datetime_utc(run.updated_at),
        "completed_at": serialize_datetime_utc(run.completed_at) if run.completed_at else None,
        "events": [
            {
                "id": event.id,
                "run_id": event.run_id,
                "sequence": event.sequence,
                "event_type": event.event_type,
                "title": event.title,
                "detail": event.detail,
                "status": event.status,
                "payload": _loads(event.payload_json),
                "created_at": serialize_datetime_utc(event.created_at),
            }
            for event in events
        ],
    }


def _loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return serialize_datetime_utc(value)
    return str(value)
