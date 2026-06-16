from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import (
    audit_detail,
    write_workspace_audit,
    write_workspace_file_agent_run,
)
from app.features.workspaces.files.service import DEFAULT_UNFILED_DIR, resolve_conflict_path, resolve_workspace_child, safe_name
from app.features.workspaces.files.storage import WorkspaceStorageConfig, workspace_file_root
from app.features.workspaces.files.tree import upsert_workspace_file
from models.generated_file import GeneratedFile
from models.user import User
from models.workspace import Workspace


def save_generated_file_to_workspace(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    generated_file_id: str,
    conflict_strategy: str,
    storage_config: WorkspaceStorageConfig,
) -> dict:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台生成文件只能下载，不能保存到工作区文件面板")
    generated = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.id == generated_file_id, GeneratedFile.user_id == user.id)
        .first()
    )
    if not generated:
        raise HTTPException(status_code=404, detail="生成文件不存在")
    source = Path(generated.path)
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="生成文件已过期或被清理")

    root = workspace_file_root(workspace, storage_config)
    target_dir = resolve_workspace_child(root, Path(DEFAULT_UNFILED_DIR))
    target_dir.mkdir(exist_ok=True)
    filename = safe_name(generated.filename)
    conflict_path = resolve_conflict_path(target_dir, filename, conflict_strategy)
    if conflict_path is None:
        skipped_path = f"{DEFAULT_UNFILED_DIR}/{filename}"
        agent_run = write_workspace_file_agent_run(
            db,
            user_id=user.id,
            workspace=workspace,
            source_type="workspace_generated_file_save",
            title="保存生成文件到工作区",
            path=skipped_path,
            status="cancelled",
            detail="目标位置已存在同名文件，按策略跳过",
            result={"generated_file_id": generated.id, "rag_status": "skipped"},
        )
        return {"ok": False, "path": skipped_path, "file_id": None, "rag_status": "skipped", "agent_run": serialize_agent_run(db, agent_run)}

    target = resolve_workspace_child(root, conflict_path.relative_to(root))
    shutil.copy2(source, target)
    rel_path = target.relative_to(root).as_posix()
    meta = upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        rel_path,
        target.name,
        generated.mime_type,
        target.stat().st_size,
        target,
    )
    write_workspace_audit(
        db,
        user.id,
        "workspace_generated_file_save",
        audit_detail(workspace.id, rel_path, meta.id, actor_id=user.id, generated_file_id=generated.id),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_generated_file_save",
        title="保存生成文件到工作区",
        path=rel_path,
        result={"file_id": meta.id, "generated_file_id": generated.id, "rag_status": meta.rag_status},
    )
    return {"ok": True, "path": rel_path, "file_id": meta.id, "rag_status": meta.rag_status, "agent_run": serialize_agent_run(db, agent_run)}
