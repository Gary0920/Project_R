from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.features.workspaces.schemas import (
    CreateWorkspaceFolderRequest,
    WorkspaceFileMutationResponse,
    WorkspaceFilesResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


def list_workspace_files(
    db: Session,
    workspace_id: int,
    user: User,
    include_deleted: bool,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    ensure_storage_path: Callable[..., str],
    build_deleted_file_items: Callable[..., list],
    build_file_tree: Callable[..., list],
    display_user_names: Callable[[Session, set[int]], dict[int, str]],
) -> WorkspaceFilesResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    member = ensure_member(db, user.id, workspace_id)
    storage_path = ensure_storage_path(workspace)
    if workspace.storage_path != storage_path:
        workspace.storage_path = storage_path
        db.commit()

    root = Path(storage_path).resolve()
    if include_deleted:
        return WorkspaceFilesResponse(
            workspace_id=workspace.id,
            root_name=workspace.name,
            items=build_deleted_file_items(db, workspace.id, member, user.id, user.role),
        )
    metas = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_(None))
        .all()
    )
    metadata_by_path = {item.relative_path: item for item in metas}
    uploader_names = display_user_names(db, {item.uploaded_by for item in metas})
    return WorkspaceFilesResponse(
        workspace_id=workspace.id,
        root_name=workspace.name,
        items=build_file_tree(root, root, metadata_by_path, uploader_names, member, user.id, user.role),
    )


def get_workspace_file_content(
    db: Session,
    workspace_id: int,
    path: str,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    resolve_workspace_child: Callable[[Path, Path], Path],
) -> FileResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_member(db, user.id, workspace_id)
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
    if meta and meta.trash_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = (meta.content_type if meta else None) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=target.name)


def create_workspace_folder(
    db: Session,
    workspace_id: int,
    req: CreateWorkspaceFolderRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    resolve_workspace_child: Callable[[Path, Path], Path],
    safe_name: Callable[[str], str],
    write_workspace_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    parent_rel = safe_relative_path(req.parent_path)
    ensure_not_trash_path(parent_rel)
    parent = resolve_workspace_child(root, parent_rel)
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=400, detail="目标父文件夹不存在")
    folder_name = safe_name(req.name)
    target = resolve_workspace_child(root, parent.relative_to(root) / folder_name)
    if target.exists():
        raise HTTPException(status_code=409, detail="已存在同名文件夹")
    target.mkdir()
    rel_path = target.relative_to(root).as_posix()
    write_workspace_audit(
        db,
        user.id,
        "workspace_folder_create",
        audit_detail(workspace_id, rel_path, actor_id=user.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_folder_create",
        title="新建项目文件夹",
        path=rel_path,
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, agent_run=serialize_agent_run(db, agent_run))
