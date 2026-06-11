from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import GBrainAdapter
from app.features.workspaces.audit import audit_detail, write_workspace_audit
from app.features.workspaces.ingest.agent_runs import (
    add_workspace_ingest_result_event,
    add_workspace_ingest_started_event,
    fail_workspace_ingest_agent_run,
    finish_workspace_ingest_agent_run,
    get_or_create_workspace_ingest_agent_run,
    serialize_workspace_ingest_agent_run,
)
from app.features.workspaces.ingest.audit import workspace_ingest_audit_fields
from app.features.workspaces.ingest.executor import execute_workspace_ingest_core
from app.features.workspaces.ingest.jobs import (
    mark_workspace_ingest_job_completed,
    mark_workspace_ingest_job_failed,
    mark_workspace_ingest_job_running,
    workspace_ingest_request_from_job,
    workspace_ingest_run_id_from_job,
)
from app.features.workspaces.ingest.notifications import notify_workspace_ingest_failed, notify_workspace_ingest_finished
from app.features.workspaces.ingest.run import workspace_ingest_status_event
from app.features.workspaces.schemas import WorkspaceKnowledgeIngestJobResponse, WorkspaceKnowledgeIngestRequest
from models.workspace import Workspace, WorkspaceFile
from models.workspace_ingest_job import WorkspaceIngestJob
from models.user import User


def normalize_workspace_ingest_request(
    db: Session,
    workspace: Workspace,
    user: User,
    req: WorkspaceKnowledgeIngestRequest | None,
    *,
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    resolve_workspace_child: Callable[[Path, Path], Path],
    is_workspace_admin: Callable[[Session, User, int], bool],
) -> dict:
    requested_path = (req.path if req else "").replace("\\", "/").strip("/")
    recursive = True if req is None else bool(req.recursive)
    root = workspace_file_root(workspace)
    rel = safe_relative_path(requested_path) if requested_path else Path()
    ensure_not_trash_path(rel)
    target = resolve_workspace_child(root, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="录入路径不存在")
    rel_path = target.relative_to(root).as_posix()
    if rel_path == ".":
        rel_path = ""
    is_file = target.is_file()
    is_directory = target.is_dir()
    if not is_file and not is_directory:
        raise HTTPException(status_code=400, detail="录入路径不是文件或文件夹")

    is_admin = is_workspace_admin(db, user, workspace.id)
    if workspace.workspace_kind == "customer" and not is_admin:
        raise HTTPException(status_code=403, detail="客户资料录入仅允许系统管理员或客户工作区管理员执行")
    if workspace.workspace_kind == "project":
        if is_admin:
            pass
        elif is_file and not recursive:
            meta = (
                db.query(WorkspaceFile)
                .filter(
                    WorkspaceFile.workspace_id == workspace.id,
                    WorkspaceFile.relative_path == rel_path,
                    WorkspaceFile.deleted_at.is_(None),
                )
                .first()
            )
            if not meta or meta.uploaded_by != user.id:
                raise HTTPException(status_code=403, detail="普通成员只能录入自己上传的单个文件")
        else:
            raise HTTPException(status_code=403, detail="递归录入文件夹仅允许系统管理员或项目管理员执行")
    if not is_directory:
        recursive = False
    return {
        "path": rel_path,
        "recursive": recursive,
        "target_type": "directory" if is_directory else "file",
    }


def compile_project_workspace_sources_for_request(
    compile_project: Callable,
    workspace: Workspace,
    source_path: str,
    recursive: bool,
) -> dict:
    try:
        return compile_project(workspace, source_path=source_path, recursive=recursive)
    except TypeError:
        if source_path or not recursive:
            raise
        return compile_project(workspace)


def compile_customer_workspace_sources_for_request(
    compile_customer: Callable,
    workspace: Workspace,
    source_path: str,
    recursive: bool,
) -> dict:
    try:
        return compile_customer(workspace, source_path=source_path, recursive=recursive)
    except TypeError:
        if source_path or not recursive:
            raise
        return compile_customer(workspace)


def new_workspace_ingest_run_id(workspace: Workspace) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"workspace-{workspace.id}-{stamp}-{uuid.uuid4().hex[:8]}"


def execute_workspace_knowledge_ingest(
    db: Session,
    workspace: Workspace,
    actor_user_id: int,
    *,
    compile_project: Callable,
    compile_customer: Callable,
    adapter_factory: Callable[[], GBrainAdapter],
    source_path: str = "",
    recursive: bool = True,
    run_id: str | None = None,
    initial_status_history: list[dict] | None = None,
) -> dict:
    run_id = run_id or new_workspace_ingest_run_id(workspace)
    started_at = datetime.now(timezone.utc)
    status_history = list(initial_status_history or [])
    if not any(item.get("status") == "preprocessing" for item in status_history if isinstance(item, dict)):
        status_history.append(workspace_ingest_status_event("preprocessing", "开始预处理源文件", started_at))
    payload = execute_workspace_ingest_core(
        db,
        workspace,
        actor_user_id,
        source_path=source_path,
        recursive=recursive,
        run_id=run_id,
        started_at=started_at,
        status_history=status_history,
        compile_project=lambda ws, source_path="", recursive=True: compile_project_workspace_sources_for_request(
            compile_project, ws, source_path, recursive
        ),
        compile_customer=lambda ws, source_path="", recursive=True: compile_customer_workspace_sources_for_request(
            compile_customer, ws, source_path, recursive
        ),
        adapter_factory=adapter_factory,
    )
    write_workspace_audit(
        db,
        actor_user_id,
        "workspace_knowledge_refresh",
        audit_detail(
            workspace.id,
            actor_id=actor_user_id,
            **workspace_ingest_audit_fields(payload, source_path=source_path, recursive=recursive),
        ),
    )
    if workspace.workspace_kind in {"project", "customer"}:
        notify_workspace_ingest_finished(
            db,
            workspace=workspace,
            actor_user_id=actor_user_id,
            ok=bool(payload.get("ok")),
            indexed_files=int(payload.get("indexed_files", 0)),
            failed_files=int(payload.get("failed_files", 0)),
            pending_extractor_capability_files=int(payload.get("pending_extractor_capability_files", 0)),
            pending_transcription_files=int(payload.get("pending_transcription_files", 0)),
            gbrain_error=payload.get("gbrain_error"),
        )
    return payload


def run_workspace_knowledge_ingest_job(
    job_id: int,
    *,
    session_factory: Callable[[], Session],
    compile_project: Callable,
    compile_customer: Callable,
    adapter_factory: Callable[[], GBrainAdapter],
) -> None:
    db = session_factory()
    try:
        job = db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job_id).first()
        if not job or job.status not in {"queued", "failed"}:
            return
        workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
        ingest_request = workspace_ingest_request_from_job(job)
        run_id = workspace_ingest_run_id_from_job(job)
        initial_history = mark_workspace_ingest_job_running(
            job,
            workspace=workspace,
            ingest_request=ingest_request,
            run_id=run_id,
        )
        agent_run = get_or_create_workspace_ingest_agent_run(db, job, workspace)
        agent_run.status = "running"
        add_workspace_ingest_started_event(db, agent_run, workspace, ingest_request)
        db.commit()

        if not workspace:
            raise ValueError("workspace no longer exists")
        payload = execute_workspace_knowledge_ingest(
            db,
            workspace,
            job.requested_by,
            compile_project=compile_project,
            compile_customer=compile_customer,
            adapter_factory=adapter_factory,
            source_path=str(ingest_request.get("path") or ""),
            recursive=bool(ingest_request.get("recursive", True)),
            run_id=run_id,
            initial_status_history=initial_history,
        )
        mark_workspace_ingest_job_completed(job, payload)
        add_workspace_ingest_result_event(db, agent_run, payload)
        finish_workspace_ingest_agent_run(db, agent_run, payload)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job_id).first()
        if job:
            workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
            request = workspace_ingest_request_from_job(job)
            run_id = workspace_ingest_run_id_from_job(job)
            mark_workspace_ingest_job_failed(
                job,
                workspace=workspace,
                request=request,
                run_id=run_id,
                error=str(exc),
            )
            agent_run = get_or_create_workspace_ingest_agent_run(db, job, workspace)
            fail_workspace_ingest_agent_run(db, agent_run, workspace_id=job.workspace_id, error=str(exc))
            notify_workspace_ingest_failed(
                db,
                job=job,
                workspace=workspace,
                error=str(exc),
            )
            db.commit()
    finally:
        db.close()


def serialize_ingest_job(db: Session, job: WorkspaceIngestJob) -> WorkspaceKnowledgeIngestJobResponse:
    try:
        result = json.loads(job.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    return WorkspaceKnowledgeIngestJobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        requested_by=job.requested_by,
        status=job.status,
        result=result if isinstance(result, dict) else {},
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        agent_run=serialize_workspace_ingest_agent_run(db, job),
    )
