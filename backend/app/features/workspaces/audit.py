from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run
from models.audit_log import AuditLog
from models.workspace import Workspace


def audit_detail(workspace_id: int, path: str = "", file_id: int | None = None, **extra) -> str:
    return json.dumps(
        {"workspace_id": workspace_id, "path": path, "file_id": file_id, **extra},
        ensure_ascii=False,
    )


def write_workspace_audit(db: Session, user_id: int, action: str, detail: str, success: bool = True) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=success))


def write_workspace_file_agent_run(
    db: Session,
    *,
    user_id: int,
    workspace: Workspace,
    source_type: str,
    title: str,
    path: str,
    status: str = "completed",
    detail: str = "",
    result: dict | None = None,
):
    payload = {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "path": path,
        **(result or {}),
    }
    run = create_agent_run(
        db,
        user_id=user_id,
        workspace_id=workspace.id,
        source_type=source_type,
        source_id=str(path or workspace.id),
        title=title,
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="permission_check",
        title="已校验项目权限",
        detail=workspace.name,
        status="completed",
        payload={"workspace_id": workspace.id},
    )
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title=title,
        detail=detail or path,
        status=status,
        payload=payload,
    )
    return finish_agent_run(
        db,
        run,
        status=status,
        result=payload,
        error_message="" if status != "failed" else detail,
    )


def raise_with_audit(
    db: Session,
    user_id: int,
    action: str,
    status_code: int,
    message: str,
    detail: str,
) -> None:
    write_workspace_audit(db, user_id, action, detail, success=False)
    db.commit()
    raise HTTPException(status_code=status_code, detail=message)


def mark_workspace_rag_pending(db: Session, workspace_id: int) -> None:
    return
