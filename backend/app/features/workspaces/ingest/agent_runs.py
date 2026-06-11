from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.agent_events import add_agent_event, create_agent_run, finish_agent_run, serialize_agent_run
from app.features.workspaces.ingest.run import workspace_ingest_result_payload, workspace_ingest_summary_text
from models.agent_run import AgentRun


def get_or_create_workspace_ingest_agent_run(db: Any, job: Any, workspace: Any | None):
    run = find_workspace_ingest_agent_run(db, job)
    if run:
        return run
    return create_agent_run(
        db,
        user_id=job.requested_by,
        workspace_id=job.workspace_id,
        source_type="workspace_ingest",
        source_id=job.id,
        title=f"录入工作区知识库：{workspace.name if workspace else job.workspace_id}",
        status=job.status,
    )


def serialize_workspace_ingest_agent_run(db: Any, job: Any) -> dict | None:
    run = find_workspace_ingest_agent_run(db, job)
    return serialize_agent_run(db, run)


def find_workspace_ingest_agent_run(db: Any, job: Any):
    return (
        db.query(AgentRun)
        .filter(
            AgentRun.source_type == "workspace_ingest",
            AgentRun.source_id == str(job.id),
            AgentRun.user_id == job.requested_by,
        )
        .order_by(AgentRun.id.desc())
        .first()
    )


def write_immediate_workspace_ingest_agent_run(
    db: Any,
    workspace: Any,
    user_id: int,
    payload: dict,
):
    run = create_agent_run(
        db,
        user_id=user_id,
        workspace_id=workspace.id,
        source_type="workspace_ingest",
        source_id=f"sync:{workspace.id}:{datetime.now(timezone.utc).timestamp()}",
        title=f"录入工作区知识库：{workspace.name}",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="started",
        title="开始处理工作区资料",
        detail=workspace.name,
        status="completed",
        payload={"workspace_id": workspace.id},
    )
    add_workspace_ingest_result_event(db, run, payload)
    return finish_workspace_ingest_agent_run(db, run, payload)


def create_queued_workspace_ingest_agent_run(db: Any, job: Any, workspace: Any, ingest_request: dict):
    run = create_agent_run(
        db,
        user_id=job.requested_by,
        workspace_id=workspace.id,
        source_type="workspace_ingest",
        source_id=job.id,
        title=f"录入工作区知识库：{workspace.name}",
        status="queued",
    )
    add_agent_event(
        db,
        run,
        event_type="queued",
        title="工作区录入任务已排队",
        detail=_workspace_ingest_request_detail(workspace, ingest_request),
        status="queued",
        payload={"workspace_id": workspace.id, "workspace_name": workspace.name, **ingest_request},
    )
    return run


def add_workspace_ingest_started_event(db: Any, run: Any, workspace: Any | None, ingest_request: dict) -> None:
    add_agent_event(
        db,
        run,
        event_type="started",
        title="开始处理工作区资料",
        detail=_workspace_ingest_request_detail(workspace, ingest_request) if workspace else "",
        status="running",
        payload={"workspace_id": getattr(workspace, "id", None), **ingest_request},
    )


def add_workspace_ingest_result_event(db: Any, run: Any, payload: dict) -> None:
    add_agent_event(
        db,
        run,
        event_type="result",
        title="工作区知识库录入完成" if payload.get("ok") else "工作区知识库录入未完成",
        detail=workspace_ingest_summary_text(payload),
        status="completed" if payload.get("ok") else "failed",
        payload=workspace_ingest_result_payload(payload),
    )


def finish_workspace_ingest_agent_run(db: Any, run: Any, payload: dict):
    return finish_agent_run(
        db,
        run,
        status="completed" if payload.get("ok") else "failed",
        result=workspace_ingest_result_payload(payload),
        error_message=str(payload.get("gbrain_error") or ""),
    )


def fail_workspace_ingest_agent_run(db: Any, run: Any, *, workspace_id: int, error: str):
    add_agent_event(
        db,
        run,
        event_type="error",
        title="工作区知识库录入失败",
        detail=error,
        status="failed",
        payload={"workspace_id": workspace_id},
    )
    return finish_agent_run(db, run, status="failed", error_message=error)


def _workspace_ingest_request_detail(workspace: Any, request: dict) -> str:
    mode = "递归录入" if request.get("recursive") else "单文件录入"
    path = str(request.get("path") or "")
    if not path:
        label = "当前工作区资料"
    elif request.get("target_type") == "file":
        label = f"文件「{path}」"
    else:
        label = f"文件夹「{path}」"
    return f"{workspace.name}：{mode} {label}"
