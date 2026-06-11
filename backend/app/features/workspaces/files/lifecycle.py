from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.workspaces.schemas import (
    RestoreWorkspaceFileRequest,
    WorkspaceFileMutationResponse,
    WorkspaceTrashClearResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


def delete_workspace_file(
    db: Session,
    workspace_id: int,
    path: str,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    resolve_workspace_child: Callable[[Path, Path], Path],
    member_can_mutate_file: Callable[[WorkspaceMember, int, WorkspaceFile | None, str], bool],
    raise_with_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    upsert_workspace_file: Callable[..., WorkspaceFile],
    trash_target: Callable[[Path, WorkspaceFile, str], Path],
    mark_workspace_rag_pending: Callable[[Session, int], None],
    write_workspace_audit: Callable[..., None],
    notify_user: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    rel = safe_relative_path(path)
    target = resolve_workspace_child(root, rel)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    rel_path = target.relative_to(root).as_posix()
    meta = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == rel_path,
            WorkspaceFile.deleted_at.is_(None),
        )
        .first()
    )
    if not member_can_mutate_file(member, user.id, meta, user.role):
        raise_with_audit(
            db,
            user.id,
            "workspace_file_delete",
            403,
            "只有上传人或管理员可以删除该文件",
            audit_detail(workspace_id, rel_path, meta.id if meta else None, actor_id=user.id, error="permission denied"),
        )
    if not meta:
        meta = upsert_workspace_file(
            db,
            workspace_id,
            user.id,
            rel_path,
            target.name,
            "application/octet-stream",
            target.stat().st_size,
            target,
        )
    trash_path = trash_target(root, meta, rel_path)
    shutil.move(str(target), str(trash_path))
    now = datetime.now(timezone.utc)
    meta.deleted_at = now
    meta.deleted_by = user.id
    meta.trash_path = trash_path.relative_to(root).as_posix()
    meta.rag_status = "source_deleted"
    meta.updated_at = now
    mark_workspace_rag_pending(db, workspace_id)
    write_workspace_audit(
        db,
        user.id,
        "workspace_file_delete",
        audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, trash_path=meta.trash_path),
    )
    if member.role == "admin" and meta.uploaded_by != user.id:
        notify_user(
            db,
            meta.uploaded_by,
            category="workspace",
            severity="warning",
            title="项目文件已被管理员删除",
            content=f"{workspace.name} 中的 {rel_path} 已由项目管理员删除并移入回收区。",
            action_status="none",
            action_kind="open_workspace",
            action_payload={"workspace_id": workspace.id},
            event_key=f"workspace:{workspace.id}:file_deleted:{meta.id}",
        )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_file_delete",
        title="移入项目回收区",
        path=rel_path,
        detail=meta.trash_path,
        result={"file_id": meta.id, "rag_status": meta.rag_status, "trash_path": meta.trash_path},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status, agent_run=serialize_agent_run(db, agent_run))


def restore_workspace_file(
    db: Session,
    workspace_id: int,
    req: RestoreWorkspaceFileRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    resolve_workspace_child: Callable[[Path, Path], Path],
    raise_with_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    record_file_signature: Callable[[WorkspaceFile, Path], None],
    mark_workspace_rag_pending: Callable[[Session, int], None],
    write_workspace_audit: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == req.file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    source = resolve_workspace_child(root, safe_relative_path(meta.trash_path))
    target = resolve_workspace_child(root, safe_relative_path(meta.relative_path))
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if target.exists():
        raise_with_audit(
            db,
            user.id,
            "workspace_file_restore",
            409,
            "原路径已存在同名文件，请先处理冲突",
            audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id, error="target exists"),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    now = datetime.now(timezone.utc)
    meta.deleted_at = None
    meta.deleted_by = None
    meta.trash_path = ""
    meta.rag_status = "new"
    record_file_signature(meta, target)
    meta.updated_at = now
    mark_workspace_rag_pending(db, workspace_id)
    write_workspace_audit(
        db,
        user.id,
        "workspace_file_restore",
        audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_file_restore",
        title="恢复项目文件",
        path=meta.relative_path,
        result={"file_id": meta.id, "rag_status": meta.rag_status},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=meta.relative_path, file_id=meta.id, rag_status=meta.rag_status, agent_run=serialize_agent_run(db, agent_run))


def permanently_delete_workspace_file(
    db: Session,
    workspace_id: int,
    file_id: int,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    resolve_workspace_child: Callable[[Path, Path], Path],
    member_can_restore_file: Callable[[WorkspaceMember, int, WorkspaceFile, str], bool],
    raise_with_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    mark_workspace_rag_pending: Callable[[Session, int], None],
    write_workspace_audit: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if not member_can_restore_file(member, user.id, meta, user.role):
        raise_with_audit(
            db,
            user.id,
            "workspace_file_permanent_delete",
            403,
            "只有上传人或管理员可以永久删除该文件",
            audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id, error="permission denied"),
        )
    if meta.trash_path:
        trash_path = resolve_workspace_child(root, safe_relative_path(meta.trash_path))
        if trash_path.exists() and trash_path.is_file():
            trash_path.unlink()
    rel_path = meta.relative_path
    db.delete(meta)
    mark_workspace_rag_pending(db, workspace_id)
    write_workspace_audit(
        db,
        user.id,
        "workspace_file_permanent_delete",
        audit_detail(workspace_id, rel_path, file_id, actor_id=user.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_file_permanent_delete",
        title="永久删除项目文件",
        path=rel_path,
        result={"file_id": file_id, "rag_status": "pending"},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=file_id, rag_status="pending", agent_run=serialize_agent_run(db, agent_run))


def clear_workspace_trash(
    db: Session,
    workspace_id: int,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    resolve_workspace_child: Callable[[Path, Path], Path],
    write_workspace_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    notify_workspace_bulk_delete_risk: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceTrashClearResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    query = db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_not(None))
    if member.role != "admin":
        query = query.filter(WorkspaceFile.uploaded_by == user.id, WorkspaceFile.deleted_by == user.id)
    deleted = 0
    for meta in query.all():
        if meta.trash_path:
            trash_path = resolve_workspace_child(root, safe_relative_path(meta.trash_path))
            if trash_path.exists() and trash_path.is_file():
                trash_path.unlink()
        db.delete(meta)
        deleted += 1
    write_workspace_audit(db, user.id, "workspace_trash_clear", audit_detail(workspace_id, actor_id=user.id, deleted_files=deleted))
    notify_workspace_bulk_delete_risk(db, workspace=workspace, actor_user_id=user.id, deleted_files=deleted)
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_trash_clear",
        title="清空项目回收区",
        path=".trash",
        result={"deleted_files": deleted},
    )
    db.commit()
    return {"ok": True, "deleted_files": deleted, "agent_run": serialize_agent_run(db, agent_run)}
