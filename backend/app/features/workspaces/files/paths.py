from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.workspaces.schemas import (
    CopyWorkspacePathRequest,
    MoveWorkspacePathRequest,
    RenameWorkspacePathRequest,
    WorkspaceFileMutationResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


def delete_workspace_folder(
    db: Session,
    workspace_id: int,
    path: str,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    is_template_root: Callable[[Path], bool],
    resolve_workspace_child: Callable[[Path, Path], Path],
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
    rel = safe_relative_path(path)
    ensure_not_trash_path(rel)
    if is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能删除")
    target = resolve_workspace_child(root, rel)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if any(target.iterdir()):
        raise HTTPException(status_code=400, detail="只能删除空文件夹")
    target.rmdir()
    rel_path = target.relative_to(root).as_posix()
    write_workspace_audit(
        db,
        user.id,
        "workspace_folder_delete",
        audit_detail(workspace_id, rel_path, actor_id=user.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_folder_delete",
        title="删除项目文件夹",
        path=rel_path,
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, agent_run=serialize_agent_run(db, agent_run))


def rename_workspace_path(
    db: Session,
    workspace_id: int,
    req: RenameWorkspacePathRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    is_template_root: Callable[[Path], bool],
    resolve_workspace_child: Callable[[Path, Path], Path],
    safe_name: Callable[[str], str],
    member_can_mutate_file: Callable[[WorkspaceMember, int, WorkspaceFile | None, str], bool],
    sync_file_descendant_paths: Callable[[Session, int, str, str], None],
    write_workspace_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    rel = safe_relative_path(req.path)
    ensure_not_trash_path(rel)
    if is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能重命名")
    source = resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    new_name = safe_name(req.new_name)
    target = resolve_workspace_child(root, rel.parent / new_name)
    if target.exists():
        raise HTTPException(status_code=409, detail="目标位置已存在同名项目")

    rel_path = source.relative_to(root).as_posix()
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.relative_path == rel_path, WorkspaceFile.deleted_at.is_(None))
        .first()
    )
    if source_is_file and not member_can_mutate_file(member, user.id, meta, user.role):
        raise HTTPException(status_code=403, detail="只有上传人或管理员可以重命名该文件")

    shutil.move(str(source), str(target))
    new_rel_path = target.relative_to(root).as_posix()
    now = datetime.now(timezone.utc)
    if source_is_file:
        if meta:
            meta.relative_path = new_rel_path
            meta.original_name = target.name
            meta.rag_status = "pending"
            meta.updated_at = now
    else:
        sync_file_descendant_paths(db, workspace_id, rel_path, new_rel_path)
    write_workspace_audit(db, user.id, "workspace_path_rename", audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_path_rename",
        title="重命名项目路径",
        path=new_rel_path,
        detail=f"{rel_path} -> {new_rel_path}",
        result={"file_id": meta.id if meta else None, "old_path": rel_path, "rag_status": meta.rag_status if meta else None},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=new_rel_path, file_id=meta.id if meta else None, rag_status=meta.rag_status if meta else None, agent_run=serialize_agent_run(db, agent_run))


def move_workspace_path(
    db: Session,
    workspace_id: int,
    req: MoveWorkspacePathRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    is_template_root: Callable[[Path], bool],
    resolve_workspace_child: Callable[[Path, Path], Path],
    member_can_mutate_file: Callable[[WorkspaceMember, int, WorkspaceFile | None, str], bool],
    resolve_conflict_path: Callable[[Path, str, str], Path | None],
    sync_file_descendant_paths: Callable[[Session, int, str, str], None],
    write_workspace_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    root = workspace_file_root(workspace)
    rel = safe_relative_path(req.path)
    ensure_not_trash_path(rel)
    if is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能移动")
    source = resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    target_dir_rel = safe_relative_path(req.target_directory)
    ensure_not_trash_path(target_dir_rel)
    target_dir = resolve_workspace_child(root, target_dir_rel)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标文件夹不存在")
    if not source_is_file and target_dir.resolve().is_relative_to(source.resolve()):
        raise HTTPException(status_code=400, detail="不能移动到自身下级目录")

    rel_path = source.relative_to(root).as_posix()
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.relative_path == rel_path, WorkspaceFile.deleted_at.is_(None))
        .first()
    )
    if source_is_file and not member_can_mutate_file(member, user.id, meta, user.role):
        raise HTTPException(status_code=403, detail="只有上传人或管理员可以移动该文件")

    conflict_path = resolve_conflict_path(target_dir, source.name, req.conflict_strategy)
    if conflict_path is None:
        agent_run = write_workspace_file_agent_run(
            db,
            user_id=user.id,
            workspace=workspace,
            source_type="workspace_path_move",
            title="移动项目路径",
            path=rel_path,
            status="cancelled",
            detail="目标位置已存在同名路径，按策略跳过",
            result={"file_id": meta.id if meta else None, "rag_status": "skipped"},
        )
        db.commit()
        return WorkspaceFileMutationResponse(ok=False, path=rel_path, file_id=meta.id if meta else None, rag_status="skipped", agent_run=serialize_agent_run(db, agent_run))
    target = resolve_workspace_child(root, conflict_path.relative_to(root))
    if target.exists() and target.is_dir() and source_is_file:
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    if target.exists() and not source_is_file:
        raise HTTPException(status_code=409, detail="目标位置已存在同名文件夹")
    if target.exists() and req.conflict_strategy == "replace":
        existing_meta = (
            db.query(WorkspaceFile)
            .filter(
                WorkspaceFile.workspace_id == workspace_id,
                WorkspaceFile.relative_path == target.relative_to(root).as_posix(),
                WorkspaceFile.deleted_at.is_(None),
            )
            .first()
        )
        if existing_meta:
            db.delete(existing_meta)
        target.unlink()

    shutil.move(str(source), str(target))
    new_rel_path = target.relative_to(root).as_posix()
    now = datetime.now(timezone.utc)
    if source_is_file:
        if meta:
            meta.relative_path = new_rel_path
            meta.rag_status = "pending"
            meta.updated_at = now
    else:
        sync_file_descendant_paths(db, workspace_id, rel_path, new_rel_path)
    write_workspace_audit(db, user.id, "workspace_path_move", audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_path_move",
        title="移动项目路径",
        path=new_rel_path,
        detail=f"{rel_path} -> {new_rel_path}",
        result={"file_id": meta.id if meta else None, "old_path": rel_path, "rag_status": meta.rag_status if meta else None},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=new_rel_path, file_id=meta.id if meta else None, rag_status=meta.rag_status if meta else None, agent_run=serialize_agent_run(db, agent_run))


def copy_workspace_path(
    db: Session,
    workspace_id: int,
    req: CopyWorkspacePathRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    is_template_root: Callable[[Path], bool],
    resolve_workspace_child: Callable[[Path, Path], Path],
    resolve_conflict_path: Callable[[Path, str, str], Path | None],
    create_copied_file_metadata: Callable[..., WorkspaceFile],
    copy_descendant_file_metadata: Callable[..., None],
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
    rel = safe_relative_path(req.path)
    ensure_not_trash_path(rel)
    if is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能复制")
    source = resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    target_dir_rel = safe_relative_path(req.target_directory)
    ensure_not_trash_path(target_dir_rel)
    target_dir = resolve_workspace_child(root, target_dir_rel)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标文件夹不存在")
    if not source_is_file and target_dir.resolve().is_relative_to(source.resolve()):
        raise HTTPException(status_code=400, detail="不能复制到自身下级目录")

    rel_path = source.relative_to(root).as_posix()
    source_meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.relative_path == rel_path, WorkspaceFile.deleted_at.is_(None))
        .first()
    )
    conflict_path = resolve_conflict_path(target_dir, source.name, req.conflict_strategy)
    if conflict_path is None:
        agent_run = write_workspace_file_agent_run(
            db,
            user_id=user.id,
            workspace=workspace,
            source_type="workspace_path_copy",
            title="复制项目路径",
            path=rel_path,
            status="cancelled",
            detail="目标位置已存在同名路径，按策略跳过",
            result={"file_id": source_meta.id if source_meta else None, "rag_status": "skipped"},
        )
        db.commit()
        return WorkspaceFileMutationResponse(ok=False, path=rel_path, file_id=source_meta.id if source_meta else None, rag_status="skipped", agent_run=serialize_agent_run(db, agent_run))
    target = resolve_workspace_child(root, conflict_path.relative_to(root))
    if target.exists() and target.is_dir() and source_is_file:
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    if target.exists() and not source_is_file:
        raise HTTPException(status_code=409, detail="目标位置已存在同名文件夹")
    if target.exists() and req.conflict_strategy == "replace":
        existing_meta = (
            db.query(WorkspaceFile)
            .filter(
                WorkspaceFile.workspace_id == workspace_id,
                WorkspaceFile.relative_path == target.relative_to(root).as_posix(),
                WorkspaceFile.deleted_at.is_(None),
            )
            .first()
        )
        if existing_meta:
            db.delete(existing_meta)
        target.unlink()

    if source_is_file:
        shutil.copy2(source, target)
        meta = create_copied_file_metadata(
            db,
            workspace_id=workspace_id,
            source_rel_path=rel_path,
            target_file=target,
            root=root,
            user_id=user.id,
        )
    else:
        shutil.copytree(source, target)
        copy_descendant_file_metadata(
            db,
            workspace_id=workspace_id,
            source_dir=source,
            target_dir=target,
            root=root,
            user_id=user.id,
        )
        meta = None

    new_rel_path = target.relative_to(root).as_posix()
    write_workspace_audit(db, user.id, "workspace_path_copy", audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_path_copy",
        title="复制项目路径",
        path=new_rel_path,
        detail=f"{rel_path} -> {new_rel_path}",
        result={"file_id": meta.id if meta else None, "old_path": rel_path, "rag_status": meta.rag_status if meta else None},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=new_rel_path, file_id=meta.id if meta else None, rag_status=meta.rag_status if meta else None, agent_run=serialize_agent_run(db, agent_run))
