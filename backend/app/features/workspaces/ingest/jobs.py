from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.features.workspaces.ingest.run import workspace_ingest_run_payload, workspace_ingest_status_event


def workspace_ingest_request_label(request: dict) -> str:
    path = str(request.get("path") or "")
    if not path:
        return "当前工作区资料"
    if request.get("target_type") == "file":
        return f"文件「{path}」"
    return f"文件夹「{path}」"


def workspace_ingest_request_detail(workspace: Any, request: dict) -> str:
    mode = "递归录入" if request.get("recursive") else "单文件录入"
    return f"{workspace.name}：{mode} {workspace_ingest_request_label(request)}"


def workspace_ingest_request_from_job(job: Any) -> dict:
    try:
        payload = json.loads(job.result_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    request = payload.get("request") if isinstance(payload, dict) else {}
    if not isinstance(request, dict):
        request = {}
    return {
        "path": str(request.get("path") or ""),
        "recursive": bool(request.get("recursive", True)),
        "target_type": str(request.get("target_type") or "directory"),
    }


def workspace_ingest_job_run_id(job: Any) -> str:
    return f"workspace-ingest-job-{job.id}"


def workspace_ingest_run_id_from_job(job: Any) -> str:
    try:
        payload = json.loads(job.result_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        run = payload.get("run")
        if isinstance(run, dict) and run.get("run_id"):
            return str(run["run_id"])
        if payload.get("run_id"):
            return str(payload["run_id"])
    return workspace_ingest_job_run_id(job)


def workspace_ingest_initial_history(job: Any) -> list[dict]:
    return [
        workspace_ingest_status_event("queued", "任务已排队", job.created_at),
        workspace_ingest_status_event("preprocessing", "开始预处理源文件", job.started_at),
    ]


def mark_workspace_ingest_job_queued(job: Any, *, workspace: Any | None, ingest_request: dict, run_id: str) -> None:
    job.result_json = json.dumps(
        {
            "request": ingest_request,
            "run": workspace_ingest_run_payload(
                run_id=run_id,
                status="queued",
                workspace=workspace,
                source_id=None,
                source_path=str(ingest_request.get("path") or ""),
                recursive=bool(ingest_request.get("recursive", True)),
                started_at=None,
                finished_at=None,
                error=None,
                status_history=[
                    workspace_ingest_status_event("queued", "任务已排队", job.created_at),
                ],
            ),
            "run_status": "queued",
            "run_id": run_id,
        },
        ensure_ascii=False,
    )


def mark_workspace_ingest_job_running(
    job: Any,
    *,
    workspace: Any | None,
    ingest_request: dict,
    run_id: str,
    started_at: datetime | None = None,
) -> list[dict]:
    job.status = "running"
    job.started_at = started_at or datetime.now(timezone.utc)
    initial_history = workspace_ingest_initial_history(job)
    job.result_json = json.dumps(
        {
            "request": ingest_request,
            "run": workspace_ingest_run_payload(
                run_id=run_id,
                status="preprocessing",
                workspace=workspace,
                source_id=None,
                source_path=str(ingest_request.get("path") or ""),
                recursive=bool(ingest_request.get("recursive", True)),
                started_at=job.started_at,
                finished_at=None,
                error=None,
                status_history=initial_history,
            ),
            "run_status": "preprocessing",
            "run_id": run_id,
        },
        ensure_ascii=False,
    )
    return initial_history


def mark_workspace_ingest_job_completed(job: Any, payload: dict, *, finished_at: datetime | None = None) -> None:
    job.status = "succeeded" if payload.get("ok") else "failed"
    job.result_json = json.dumps(payload, ensure_ascii=False)
    job.error_message = str(payload.get("gbrain_error") or "")
    job.finished_at = finished_at or datetime.now(timezone.utc)


def mark_workspace_ingest_job_failed(
    job: Any,
    *,
    workspace: Any | None,
    request: dict,
    run_id: str,
    error: str,
    finished_at: datetime | None = None,
) -> None:
    job.status = "failed"
    job.error_message = error
    job.finished_at = finished_at or datetime.now(timezone.utc)
    history = [
        workspace_ingest_status_event("queued", "任务已排队", job.created_at),
        workspace_ingest_status_event("preprocessing", "开始预处理源文件", job.started_at),
        workspace_ingest_status_event("failed", error, job.finished_at),
    ]
    job.result_json = json.dumps(
        {
            "request": request,
            "run": workspace_ingest_run_payload(
                run_id=run_id,
                status="failed",
                workspace=workspace,
                source_id=None,
                source_path=str(request.get("path") or ""),
                recursive=bool(request.get("recursive", True)),
                started_at=job.started_at,
                finished_at=job.finished_at,
                error=error,
                status_history=history,
            ),
            "run_status": "failed",
            "run_id": run_id,
            "error": error,
        },
        ensure_ascii=False,
    )
