from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.service import DEFAULT_UNFILED_DIR, resolve_conflict_path, resolve_workspace_child, safe_name
from app.features.workspaces.files.storage import WorkspaceStorageConfig, workspace_file_root
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.schemas import SaveAttachmentToWorkspaceRequest, WorkspaceFileMutationResponse
from models.attachment import SessionAttachment
from models.user import User
from models.workspace import Workspace


def save_attachment_to_workspace(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    req: SaveAttachmentToWorkspaceRequest,
    storage_config: WorkspaceStorageConfig,
) -> WorkspaceFileMutationResponse:
    attachment = (
        db.query(SessionAttachment)
        .filter(
            SessionAttachment.id == req.attachment_id,
            SessionAttachment.session_id == req.session_id,
            SessionAttachment.user_id == user.id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")

    source = Path(attachment.stored_path)
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")

    root = workspace_file_root(workspace, storage_config)
    target_dir = resolve_workspace_child(root, Path(DEFAULT_UNFILED_DIR))
    target_dir.mkdir(exist_ok=True)
    filename = safe_name(attachment.original_name)
    conflict_path = resolve_conflict_path(target_dir, filename, req.conflict_strategy)
    if conflict_path is None:
        skipped_path = f"{DEFAULT_UNFILED_DIR}/{filename}"
        agent_run = write_workspace_file_agent_run(
            db,
            user_id=user.id,
            workspace=workspace,
            source_type="workspace_attachment_save",
            title="保存会话附件到项目",
            path=skipped_path,
            status="cancelled",
            detail="目标位置已存在同名文件，按策略跳过",
            result={"attachment_id": attachment.id, "rag_status": "skipped"},
        )
        return WorkspaceFileMutationResponse(
            ok=False,
            path=skipped_path,
            rag_status="skipped",
            agent_run=serialize_agent_run(db, agent_run),
        )

    target = resolve_workspace_child(root, conflict_path.relative_to(root))
    shutil.copy2(source, target)
    rel_path = target.relative_to(root).as_posix()
    meta = upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        rel_path,
        target.name,
        attachment.content_type,
        target.stat().st_size,
        target,
    )
    write_workspace_audit(
        db,
        user.id,
        "workspace_attachment_save",
        audit_detail(workspace.id, rel_path, meta.id, actor_id=user.id, attachment_id=attachment.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_attachment_save",
        title="保存会话附件到项目",
        path=rel_path,
        result={"file_id": meta.id, "attachment_id": attachment.id, "rag_status": meta.rag_status},
    )
    return WorkspaceFileMutationResponse(
        ok=True,
        path=rel_path,
        file_id=meta.id,
        rag_status=meta.rag_status,
        agent_run=serialize_agent_run(db, agent_run),
    )
