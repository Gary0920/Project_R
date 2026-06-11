from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.features.workspaces.files.service import (
    TRASH_DIRNAME,
    is_template_root,
    member_can_mutate_file,
    member_can_restore_file,
)
from app.features.workspaces.files.signature import file_signature, record_file_signature
from app.features.workspaces.schemas import WorkspaceFileItemResponse
from models.user import User
from models.workspace import WorkspaceFile, WorkspaceMember


def source_status_for_file(meta: WorkspaceFile | None, path: Path | None = None) -> str:
    if not meta:
        return "not_indexed"
    status = meta.rag_status or "new"
    if meta.deleted_at is not None:
        return "source_deleted"
    if path is None:
        return status
    if not path.exists():
        return "source_deleted" if status in {"indexed", "synced", "gbrain_ready"} else status
    if status in {"indexed", "synced", "gbrain_ready"} and meta.source_hash:
        try:
            signature = file_signature(path)
        except OSError:
            return status
        if signature["source_hash"] != meta.source_hash:
            return "source_changed"
    return status


def sync_file_descendant_paths(db: Session, workspace_id: int, old_prefix: str, new_prefix: str) -> None:
    metas = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path.like(f"{old_prefix}/%"),
        )
        .all()
    )
    for meta in metas:
        meta.relative_path = f"{new_prefix}/{meta.relative_path[len(old_prefix) + 1:]}"
        meta.rag_status = "new"
        meta.updated_at = datetime.now(timezone.utc)


def create_copied_file_metadata(
    db: Session,
    *,
    workspace_id: int,
    source_rel_path: str,
    target_file: Path,
    root: Path,
    user_id: int,
) -> WorkspaceFile:
    target_rel_path = target_file.relative_to(root).as_posix()
    source_meta = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == source_rel_path,
            WorkspaceFile.deleted_at.is_(None),
        )
        .first()
    )
    existing_meta = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == target_rel_path,
            WorkspaceFile.deleted_at.is_(None),
        )
        .first()
    )
    if existing_meta:
        db.delete(existing_meta)
        db.flush()
    content_type = source_meta.content_type if source_meta else mimetypes.guess_type(target_file.name)[0] or "application/octet-stream"
    now = datetime.now(timezone.utc)
    meta = WorkspaceFile(
        workspace_id=workspace_id,
        uploaded_by=user_id,
        relative_path=target_rel_path,
        original_name=target_file.name,
        content_type=content_type[:128],
        size=target_file.stat().st_size,
        rag_status="new",
        updated_at=now,
    )
    record_file_signature(meta, target_file)
    db.add(meta)
    db.flush()
    return meta


def copy_descendant_file_metadata(
    db: Session,
    *,
    workspace_id: int,
    source_dir: Path,
    target_dir: Path,
    root: Path,
    user_id: int,
) -> None:
    for copied_path in sorted(target_dir.rglob("*")):
        if not copied_path.is_file():
            continue
        source_rel = (source_dir / copied_path.relative_to(target_dir)).relative_to(root).as_posix()
        create_copied_file_metadata(
            db,
            workspace_id=workspace_id,
            source_rel_path=source_rel,
            target_file=copied_path,
            root=root,
            user_id=user_id,
        )


def display_user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {item.id: item.nickname or item.username for item in users}


def build_file_tree(
    root: Path,
    path: Path,
    metadata_by_path: dict[str, WorkspaceFile],
    uploader_names: dict[int, str],
    member: WorkspaceMember,
    user_id: int,
    user_role: str,
    depth: int = 0,
    max_depth: int = 3,
) -> list[WorkspaceFileItemResponse]:
    if depth >= max_depth or not path.exists():
        return []

    items: list[WorkspaceFileItemResponse] = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.is_symlink():
            continue
        if child.name.startswith(".") and child.name != TRASH_DIRNAME:
            continue
        stat = child.stat()
        item_type = "directory" if child.is_dir() else "file"
        rel_path = child.relative_to(root).as_posix()
        if rel_path == TRASH_DIRNAME:
            items.append(
                WorkspaceFileItemResponse(
                    id=None,
                    name=TRASH_DIRNAME,
                    path=TRASH_DIRNAME,
                    type="directory",
                    size=None,
                    updated_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                    can_delete=False,
                    can_restore=False,
                    children=[],
                )
            )
            continue
        meta = metadata_by_path.get(rel_path)
        items.append(
            WorkspaceFileItemResponse(
                id=meta.id if meta else None,
                name=child.name,
                path=rel_path,
                type=item_type,
                size=None if child.is_dir() else stat.st_size,
                updated_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                uploaded_by=meta.uploaded_by if meta else None,
                uploader_name=uploader_names.get(meta.uploaded_by) if meta else None,
                deleted_at=meta.deleted_at if meta else None,
                deleted_by=meta.deleted_by if meta else None,
                rag_status=source_status_for_file(meta, child) if item_type == "file" else None,
                can_delete=(
                    item_type == "file" and member_can_mutate_file(member, user_id, meta, user_role)
                ) or (
                    item_type == "directory" and not is_template_root(Path(rel_path))
                ),
                can_restore=False,
                children=build_file_tree(
                    root,
                    child,
                    metadata_by_path,
                    uploader_names,
                    member,
                    user_id,
                    user_role,
                    depth + 1,
                    max_depth,
                ) if child.is_dir() else [],
            )
        )
    return items


def build_deleted_file_items(
    db: Session,
    workspace_id: int,
    member: WorkspaceMember,
    user_id: int,
    user_role: str,
) -> list[WorkspaceFileItemResponse]:
    files = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_not(None))
        .order_by(WorkspaceFile.deleted_at.desc(), WorkspaceFile.id.desc())
        .all()
    )
    names = display_user_names(db, {item.uploaded_by for item in files} | {item.deleted_by for item in files if item.deleted_by})
    return [
        WorkspaceFileItemResponse(
            id=item.id,
            name=Path(item.relative_path).name,
            path=item.relative_path,
            type="file",
            size=item.size,
            updated_at=item.updated_at,
            uploaded_by=item.uploaded_by,
            uploader_name=names.get(item.uploaded_by),
            deleted_at=item.deleted_at,
            deleted_by=item.deleted_by,
            rag_status=source_status_for_file(item),
            can_delete=member_can_restore_file(member, user_id, item, user_role),
            can_restore=True,
            children=[],
        )
        for item in files
    ]


def upsert_workspace_file(
    db: Session,
    workspace_id: int,
    user_id: int,
    rel_path: str,
    filename: str,
    content_type: str,
    size: int,
    source_path: Path | None = None,
) -> WorkspaceFile:
    existing = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == rel_path,
            WorkspaceFile.deleted_at.is_(None),
        )
        .first()
    )
    now = datetime.now(timezone.utc)
    if existing:
        existing.uploaded_by = user_id
        existing.original_name = filename
        existing.content_type = content_type[:128]
        existing.size = size
        existing.rag_status = "new"
        existing.updated_at = now
        existing.trash_path = ""
        if source_path and source_path.exists() and source_path.is_file():
            record_file_signature(existing, source_path)
        return existing
    meta = WorkspaceFile(
        workspace_id=workspace_id,
        uploaded_by=user_id,
        relative_path=rel_path,
        original_name=filename,
        content_type=content_type[:128],
        size=size,
        rag_status="new",
        updated_at=now,
    )
    if source_path and source_path.exists() and source_path.is_file():
        record_file_signature(meta, source_path)
    db.add(meta)
    db.flush()
    return meta
