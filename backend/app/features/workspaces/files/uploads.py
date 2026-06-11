from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Callable

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.features.workspaces.schemas import (
    UploadWorkspaceFileRequest,
    WorkspaceFileMutationResponse,
    WorkspaceMultiUploadResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


async def upload_workspace_files(
    db: Session,
    workspace_id: int,
    directory: str,
    files: list[UploadFile],
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    upload_limit_for: Callable[[User, WorkspaceMember, Workspace | None], tuple[int, str]],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    resolve_workspace_child: Callable[[Path, Path], Path],
    safe_name: Callable[[str], str],
    resolve_conflict_path: Callable[[Path, str, str], Path | None],
    raise_with_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    upsert_workspace_file: Callable[..., WorkspaceFile],
    write_workspace_audit: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceMultiUploadResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    limit_bytes, limit_message = upload_limit_for(user, member, workspace)
    root = workspace_file_root(workspace)
    rel_dir = safe_relative_path(directory)
    ensure_not_trash_path(rel_dir)
    target_dir = resolve_workspace_child(root, rel_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise_with_audit(
            db,
            user.id,
            "workspace_file_upload",
            400,
            "目标文件夹不存在",
            audit_detail(workspace_id, rel_dir.as_posix(), actor_id=user.id, error="target directory missing"),
        )

    responses: list[WorkspaceFileMutationResponse] = []
    uploaded_paths: list[str] = []
    for upload in files:
        filename = safe_name(upload.filename or "untitled")
        content = await upload.read()
        if len(content) > limit_bytes:
            raise_with_audit(
                db,
                user.id,
                "workspace_file_upload",
                400,
                limit_message,
                audit_detail(workspace_id, (rel_dir / filename).as_posix(), actor_id=user.id, error="file too large"),
            )
        conflict_path = resolve_conflict_path(target_dir, filename, "keep_both")
        if conflict_path is None:
            responses.append(WorkspaceFileMutationResponse(ok=False, path=(rel_dir / filename).as_posix(), rag_status="skipped"))
            continue
        target_path = resolve_workspace_child(root, conflict_path.relative_to(root))
        if target_path.exists() and target_path.is_dir():
            raise_with_audit(
                db,
                user.id,
                "workspace_file_upload",
                400,
                "不能覆盖文件夹",
                audit_detail(workspace_id, (rel_dir / filename).as_posix(), actor_id=user.id, error="target is directory"),
            )
        target_path.write_bytes(content)
        rel_path = target_path.relative_to(root).as_posix()
        meta = upsert_workspace_file(
            db,
            workspace_id,
            user.id,
            rel_path,
            filename,
            upload.content_type or "application/octet-stream",
            len(content),
            target_path,
        )
        write_workspace_audit(
            db,
            user.id,
            "workspace_file_upload",
            audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
        )
        responses.append(WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status))
        uploaded_paths.append(rel_path)
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_file_upload",
        title="上传项目文件",
        path=rel_dir.as_posix(),
        detail=f"上传 {len(uploaded_paths)} 个文件",
        result={"file_count": len(uploaded_paths), "paths": uploaded_paths[:20]},
    )
    db.commit()
    return WorkspaceMultiUploadResponse(ok=True, files=responses, agent_run=serialize_agent_run(db, agent_run))


def upload_workspace_file(
    db: Session,
    workspace_id: int,
    req: UploadWorkspaceFileRequest,
    user: User,
    *,
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    upload_limit_for: Callable[[User, WorkspaceMember, Workspace | None], tuple[int, str]],
    workspace_file_root: Callable[[Workspace], Path],
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    safe_name: Callable[[str], str],
    resolve_workspace_child: Callable[[Path, Path], Path],
    resolve_conflict_path: Callable[[Path, str, str], Path | None],
    raise_with_audit: Callable[..., None],
    audit_detail: Callable[..., dict],
    upsert_workspace_file: Callable[..., WorkspaceFile],
    write_workspace_audit: Callable[..., None],
    write_workspace_file_agent_run: Callable[..., object],
    serialize_agent_run: Callable[..., dict],
) -> WorkspaceFileMutationResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = ensure_member(db, user.id, workspace_id)
    limit_bytes, limit_message = upload_limit_for(user, member, workspace)
    root = workspace_file_root(workspace)
    directory = safe_relative_path(req.directory)
    ensure_not_trash_path(directory)
    filename = safe_name(req.filename)
    target_dir = resolve_workspace_child(root, directory)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标文件夹不存在")
    target_path = resolve_workspace_child(root, directory / filename)
    if target_path.exists() and target_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail="文件内容格式不正确") from exc
    if len(content) > limit_bytes:
        raise_with_audit(
            db,
            user.id,
            "workspace_file_upload",
            400,
            limit_message,
            audit_detail(workspace_id, (directory / filename).as_posix(), actor_id=user.id, error="file too large"),
        )

    conflict_path = resolve_conflict_path(target_dir, filename, req.conflict_strategy)
    if conflict_path is None:
        skipped_path = (directory / filename).as_posix()
        agent_run = write_workspace_file_agent_run(
            db,
            user_id=user.id,
            workspace=workspace,
            source_type="workspace_file_upload",
            title="上传项目文件",
            path=skipped_path,
            status="cancelled",
            detail="目标位置已存在同名文件，按策略跳过",
            result={"rag_status": "skipped"},
        )
        db.commit()
        return WorkspaceFileMutationResponse(
            ok=False,
            path=skipped_path,
            rag_status="skipped",
            agent_run=serialize_agent_run(db, agent_run),
        )
    target_path = resolve_workspace_child(root, conflict_path.relative_to(root))
    if target_path.exists() and target_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    target_path.write_bytes(content)
    rel_path = target_path.relative_to(root).as_posix()
    meta = upsert_workspace_file(db, workspace_id, user.id, rel_path, filename, req.content_type, len(content), target_path)
    write_workspace_audit(
        db,
        user.id,
        "workspace_file_upload",
        audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_file_upload",
        title="上传项目文件",
        path=rel_path,
        detail=filename,
        result={"file_id": meta.id, "rag_status": meta.rag_status, "size": len(content)},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status, agent_run=serialize_agent_run(db, agent_run))
