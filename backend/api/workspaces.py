import json
import re
import base64
import binascii
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from core.gbrain import GBrainAdapter
from core.gbrain_project_ingest import compile_project_workspace_sources
from core.notification_service import (
    notify_user,
    notify_workspace_bulk_delete_risk,
    notify_workspace_joined,
)
from core.workspace_files import (
    DEFAULT_UNFILED_DIR,
    DEFAULT_USER_WORKSPACE_DIRS,
    DEFAULT_WORKSPACE_DIRS,
    MAX_WORKSPACE_ADMIN_UPLOAD_BYTES,
    MAX_WORKSPACE_ADMIN_UPLOAD_MB,
    MAX_WORKSPACE_UPLOAD_BYTES,
    MAX_WORKSPACE_UPLOAD_MB,
    is_template_root as _is_template_root,
    member_can_mutate_file as _member_can_mutate_file,
    member_can_restore_file as _member_can_restore_file,
    resolve_conflict_path as _resolve_conflict_path,
    resolve_workspace_child as _resolve_workspace_child,
    safe_name as _safe_name,
    safe_relative_path as _safe_relative_path,
    trash_target as _trash_target,
    upload_limit_for,
)
from models import SessionLocal, get_db
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.workspace import Workspace, WorkspaceMember, WorkspaceFile
from models.workspace_ingest_job import WorkspaceIngestJob
from models.user import User

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACES_ROOT = BASE_DIR / "workspace_data"
PROJECT_ROOT_NAME = "project"
USER_ROOT_NAME = "user"
PROJECT_BRANDS = ("AURA", "BFI", "SPECWISE", "SYNOVA")


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    brand: str = "BFI"


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    created_by: int
    member_count: int = 0
    brand: str = "BFI"
    workspace_kind: str = "project"
    is_default: bool = False
    is_archived: bool
    can_rename: bool = True
    can_delete: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceDetailResponse(WorkspaceResponse):
    storage_path: str
    members: list["MemberResponse"]


class WorkspaceFileItemResponse(BaseModel):
    id: int | None = None
    name: str
    path: str
    type: str
    size: int | None = None
    updated_at: datetime | None = None
    uploaded_by: int | None = None
    uploader_name: str | None = None
    deleted_at: datetime | None = None
    deleted_by: int | None = None
    rag_status: str | None = None
    can_delete: bool = False
    can_restore: bool = False
    children: list["WorkspaceFileItemResponse"] = Field(default_factory=list)


class WorkspaceFilesResponse(BaseModel):
    workspace_id: int
    root_name: str
    items: list[WorkspaceFileItemResponse]


class UploadWorkspaceFileRequest(BaseModel):
    directory: str = ""
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"
    conflict_strategy: str = "keep_both"


class CreateWorkspaceFolderRequest(BaseModel):
    parent_path: str = ""
    name: str


class RenameWorkspacePathRequest(BaseModel):
    path: str
    new_name: str


class MoveWorkspacePathRequest(BaseModel):
    path: str
    target_directory: str = ""
    conflict_strategy: str = "keep_both"


class SaveAttachmentToWorkspaceRequest(BaseModel):
    session_id: int
    attachment_id: int
    conflict_strategy: str = "keep_both"


class WorkspaceFileMutationResponse(BaseModel):
    ok: bool
    path: str
    file_id: int | None = None
    rag_status: str | None = None


class WorkspaceMultiUploadResponse(BaseModel):
    ok: bool
    files: list[WorkspaceFileMutationResponse]


class RestoreWorkspaceFileRequest(BaseModel):
    file_id: int


class WorkspaceKnowledgeRefreshResponse(BaseModel):
    ok: bool
    workspace_id: int
    indexed_files: int
    rag_status: str
    compiled_files: int = 0
    pending_extractor_capability_files: int = 0
    pending_transcription_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    pending_reviews_created: int = 0
    gbrain_source_id: str | None = None
    gbrain_status: str | None = None
    gbrain_sync_status: str | None = None
    gbrain_error: str | None = None
    manifest: dict | None = None


class WorkspaceKnowledgeIngestJobResponse(BaseModel):
    id: int
    workspace_id: int
    requested_by: int
    status: str
    result: dict = Field(default_factory=dict)
    error_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class MemberResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    role: str
    joined_at: datetime


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w一-鿿-]", "-", name.strip()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "workspace"


def _safe_username(username: str) -> str:
    return _slugify(username).replace("/", "-") or "user"


def _normalize_brand(brand: str) -> str:
    normalized = brand.strip().upper()
    if normalized not in PROJECT_BRANDS:
        raise HTTPException(status_code=400, detail="项目品牌不合法")
    return normalized


def _workspace_dirs(workspace: Workspace) -> tuple[str, ...]:
    return DEFAULT_USER_WORKSPACE_DIRS if workspace.workspace_kind == "user" else DEFAULT_WORKSPACE_DIRS


def _target_storage_path(workspace: Workspace, owner: User | None = None) -> Path:
    if workspace.workspace_kind == "user":
        username = _safe_username(owner.username if owner else workspace.slug.removeprefix("user-"))
        return (WORKSPACES_ROOT / USER_ROOT_NAME / username).resolve()
    brand = _normalize_brand(workspace.brand or "BFI")
    return (WORKSPACES_ROOT / PROJECT_ROOT_NAME / brand / workspace.slug).resolve()


def _ensure_storage_path(workspace: Workspace) -> str:
    root = WORKSPACES_ROOT.resolve()
    target = _target_storage_path(workspace)
    path = Path(workspace.storage_path) if workspace.storage_path else target
    resolved = path.resolve()
    legacy_path = (WORKSPACES_ROOT / workspace.slug).resolve()
    if workspace.workspace_kind == "project" and resolved == legacy_path and legacy_path.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_path), str(target))
        path = target
        resolved = target.resolve()
    if not resolved.is_relative_to(root) or (
        workspace.workspace_kind == "project"
        and not resolved.is_relative_to((WORKSPACES_ROOT / PROJECT_ROOT_NAME).resolve())
    ):
        path = target
    if workspace.workspace_kind == "user" and not path.resolve().is_relative_to((WORKSPACES_ROOT / USER_ROOT_NAME).resolve()):
        path = target
    path.mkdir(parents=True, exist_ok=True)
    for dirname in _workspace_dirs(workspace):
        (path / dirname).mkdir(exist_ok=True)
    return str(path)


def _candidate_storage_path(slug: str, brand: str) -> Path:
    return (WORKSPACES_ROOT / PROJECT_ROOT_NAME / brand / slug).resolve()


def _workspace_response(db: Session, workspace: Workspace, member_count: int | None = None) -> WorkspaceResponse:
    count = member_count
    if count is None:
        count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace.id).count()
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        created_by=workspace.created_by,
        member_count=count,
        brand=workspace.brand,
        workspace_kind=workspace.workspace_kind,
        is_default=workspace.is_default,
        is_archived=workspace.is_archived,
        can_rename=not workspace.is_default,
        can_delete=not workspace.is_default,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def ensure_default_workspace(db: Session, user: User) -> Workspace:
    existing = (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(
            Workspace.workspace_kind == "user",
            Workspace.is_default == True,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if existing:
        storage_path = _ensure_storage_path(existing)
        if existing.storage_path != storage_path:
            existing.storage_path = storage_path
            db.commit()
        return existing

    slug_base = f"user-{_safe_username(user.username)}"
    slug = slug_base
    suffix = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{slug_base}-{suffix}"
        suffix += 1
    workspace = Workspace(
        name=f"{user.username} 的私人空间",
        slug=slug,
        description="用户默认工作区",
        created_by=user.id,
        brand="",
        workspace_kind="user",
        is_default=True,
    )
    db.add(workspace)
    db.flush()
    workspace.storage_path = _ensure_storage_path(workspace)
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def _find_existing_project_folder(brand: str, slug: str, name: str | None = None) -> Path | None:
    brand_dir = (WORKSPACES_ROOT / PROJECT_ROOT_NAME / brand).resolve()
    if not brand_dir.exists() or not brand_dir.is_dir():
        return None
    candidates = {slug.casefold()}
    if name:
        candidates.add(name.casefold())
    for child in brand_dir.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name.casefold() in candidates or _slugify(child.name) == slug:
            return child.resolve()
    return None


def _register_existing_project_folder(
    db: Session,
    user: User,
    brand: str,
    project_dir: Path,
    *,
    add_member: bool = False,
) -> Workspace | None:
    if not project_dir.exists() or not project_dir.is_dir() or project_dir.is_symlink():
        return None
    slug = _slugify(project_dir.name)
    if db.query(Workspace).filter(Workspace.slug == slug).first():
        return None
    workspace = Workspace(
        name=project_dir.name,
        slug=slug,
        description="",
        created_by=user.id,
        storage_path=str(project_dir.resolve()),
        brand=brand,
        workspace_kind="project",
        is_default=False,
    )
    db.add(workspace)
    db.flush()
    workspace.storage_path = _ensure_storage_path(workspace)
    if add_member:
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def _sync_project_folders(db: Session, user: User) -> None:
    project_root = (WORKSPACES_ROOT / PROJECT_ROOT_NAME).resolve()
    if not project_root.exists():
        return
    for brand in PROJECT_BRANDS:
        brand_dir = (project_root / brand).resolve()
        if not brand_dir.exists() or not brand_dir.is_dir():
            continue
        for project_dir in sorted(brand_dir.iterdir(), key=lambda item: item.name.lower()):
            _register_existing_project_folder(db, user, brand, project_dir)


def _audit_detail(workspace_id: int, path: str = "", file_id: int | None = None, **extra) -> str:
    return json.dumps(
        {"workspace_id": workspace_id, "path": path, "file_id": file_id, **extra},
        ensure_ascii=False,
    )


def _write_workspace_audit(db: Session, user_id: int, action: str, detail: str, success: bool = True) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=success))


def _raise_with_audit(
    db: Session,
    user_id: int,
    action: str,
    status_code: int,
    message: str,
    detail: str,
) -> None:
    _write_workspace_audit(db, user_id, action, detail, success=False)
    db.commit()
    raise HTTPException(status_code=status_code, detail=message)


def _mark_workspace_rag_pending(db: Session, workspace_id: int) -> None:
    db.query(WorkspaceFile).filter(
        WorkspaceFile.workspace_id == workspace_id,
        WorkspaceFile.deleted_at.is_(None),
    ).update({"rag_status": "pending"}, synchronize_session=False)


def _upload_limit_for(user: User, member: WorkspaceMember) -> tuple[int, str]:
    return upload_limit_for(
        user,
        member,
        user_limit_bytes=MAX_WORKSPACE_UPLOAD_BYTES,
        user_limit_mb=MAX_WORKSPACE_UPLOAD_MB,
        admin_limit_bytes=MAX_WORKSPACE_ADMIN_UPLOAD_BYTES,
        admin_limit_mb=MAX_WORKSPACE_ADMIN_UPLOAD_MB,
    )


def _sync_file_descendant_paths(db: Session, workspace_id: int, old_prefix: str, new_prefix: str) -> None:
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
        meta.rag_status = "pending"
        meta.updated_at = datetime.now(timezone.utc)


def _display_user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    return {item.id: item.nickname or item.username for item in users}


def _build_file_tree(
    root: Path,
    path: Path,
    metadata_by_path: dict[str, WorkspaceFile],
    uploader_names: dict[int, str],
    member: WorkspaceMember,
    user_id: int,
    depth: int = 0,
    max_depth: int = 3,
) -> list[WorkspaceFileItemResponse]:
    if depth >= max_depth or not path.exists():
        return []

    items: list[WorkspaceFileItemResponse] = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name.startswith(".") or child.is_symlink():
            continue
        stat = child.stat()
        item_type = "directory" if child.is_dir() else "file"
        rel_path = child.relative_to(root).as_posix()
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
                rag_status=meta.rag_status if meta else ("not_indexed" if item_type == "file" else None),
                can_delete=(
                    item_type == "file" and _member_can_mutate_file(member, user_id, meta)
                ) or (
                    item_type == "directory" and not _is_template_root(Path(rel_path))
                ),
                can_restore=False,
                children=_build_file_tree(
                    root,
                    child,
                    metadata_by_path,
                    uploader_names,
                    member,
                    user_id,
                    depth + 1,
                    max_depth,
                ) if child.is_dir() else [],
            )
        )
    return items


def _build_deleted_file_items(
    db: Session,
    workspace_id: int,
    member: WorkspaceMember,
    user_id: int,
) -> list[WorkspaceFileItemResponse]:
    files = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_not(None))
        .order_by(WorkspaceFile.deleted_at.desc(), WorkspaceFile.id.desc())
        .all()
    )
    names = _display_user_names(db, {item.uploaded_by for item in files} | {item.deleted_by for item in files if item.deleted_by})
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
            rag_status=item.rag_status,
            can_delete=_member_can_restore_file(member, user_id, item),
            can_restore=_member_can_restore_file(member, user_id, item),
            children=[],
        )
        for item in files
    ]


def _upsert_workspace_file(
    db: Session,
    workspace_id: int,
    user_id: int,
    rel_path: str,
    filename: str,
    content_type: str,
    size: int,
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
        existing.rag_status = "pending"
        existing.updated_at = now
        existing.trash_path = ""
        return existing
    meta = WorkspaceFile(
        workspace_id=workspace_id,
        uploaded_by=user_id,
        relative_path=rel_path,
        original_name=filename,
        content_type=content_type[:128],
        size=size,
        rag_status="pending",
        updated_at=now,
    )
    db.add(meta)
    db.flush()
    return meta


@router.post("", response_model=WorkspaceResponse)
def create_workspace(
    req: CreateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    if len(name) > 128:
        raise HTTPException(status_code=400, detail="项目名称不能超过 128 个字符")

    brand = _normalize_brand(req.brand)
    slug = _slugify(name)
    existing = db.query(Workspace).filter(Workspace.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="已存在同名项目，请选择已有项目或使用不同项目名称")
    target_path = _candidate_storage_path(slug, brand)
    root = WORKSPACES_ROOT.resolve()
    if not target_path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="项目目录不合法")
    existing_folder = _find_existing_project_folder(brand, slug, name)
    if existing_folder:
        workspace = _register_existing_project_folder(db, user, brand, existing_folder, add_member=True)
        if workspace:
            return _workspace_response(db, workspace)
        raise HTTPException(status_code=409, detail="后端已存在同名项目文件夹，请选择已有项目或更换项目名称")
    if target_path.exists():
        raise HTTPException(status_code=409, detail="后端已存在同名项目文件夹，请选择已有项目或更换项目名称")

    workspace = Workspace(
        name=name,
        slug=slug,
        description=req.description.strip(),
        created_by=user.id,
        brand=brand,
        workspace_kind="project",
        is_default=False,
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    workspace.storage_path = _ensure_storage_path(workspace)
    db.commit()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()

    return _workspace_response(db, workspace, member_count=1)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_default_workspace(db, user)
    member_workspace_ids = (
        db.query(WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id)
        .subquery()
    )
    workspaces = (
        db.query(Workspace)
        .filter(Workspace.id.in_(member_workspace_ids))
        .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())
        .all()
    )
    return [_workspace_response(db, w) for w in workspaces]


@router.get("/search")
def search_workspaces(
    q: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    brand: str | None = None,
):
    _sync_project_folders(db, user)
    query = q.strip()
    normalized_brand = _normalize_brand(brand) if brand else None
    pattern = f"%{query}%" if query else "%"
    workspace_query = (
        db.query(Workspace)
        .filter(
            Workspace.workspace_kind == "project",
            Workspace.is_archived == False,
            Workspace.name.ilike(pattern) | Workspace.slug.ilike(pattern),
        )
    )
    if normalized_brand:
        workspace_query = workspace_query.filter(Workspace.brand == normalized_brand)
    workspaces = workspace_query.order_by(
        Workspace.brand.asc(),
        Workspace.updated_at.desc(),
        Workspace.name.asc(),
    ).limit(100).all()
    member_ids = {
        row.workspace_id
        for row in db.query(WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    }
    return [
        {
            "id": w.id,
            "name": w.name,
            "slug": w.slug,
            "description": w.description,
            "brand": w.brand,
            "workspace_kind": w.workspace_kind,
            "is_default": w.is_default,
            "member_count": db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == w.id)
            .count(),
            "is_member": w.id in member_ids,
            "can_rename": not w.is_default,
            "can_delete": not w.is_default,
            "is_archived": w.is_archived,
            "created_at": w.created_at,
            "updated_at": w.updated_at,
            "created_by": w.created_by,
        }
        for w in workspaces
    ]


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
def get_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    _ensure_member(db, user.id, workspace_id)

    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    member_list = [
        MemberResponse(
            user_id=m.User.id,
            username=m.User.username,
            nickname=m.User.nickname,
            role=wm.role,
            joined_at=wm.joined_at,
        )
        for wm, m in members
    ]

    return WorkspaceDetailResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        created_by=workspace.created_by,
        member_count=len(member_list),
        brand=workspace.brand,
        workspace_kind=workspace.workspace_kind,
        is_default=workspace.is_default,
        is_archived=workspace.is_archived,
        can_rename=not workspace.is_default,
        can_delete=not workspace.is_default,
        storage_path=workspace.storage_path,
        members=member_list,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.get("/{workspace_id}/files", response_model=WorkspaceFilesResponse)
def list_workspace_files(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    include_deleted: bool = False,
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    member = _ensure_member(db, user.id, workspace_id)
    storage_path = _ensure_storage_path(workspace)
    if workspace.storage_path != storage_path:
        workspace.storage_path = storage_path
        db.commit()

    root = Path(storage_path).resolve()
    if include_deleted:
        return WorkspaceFilesResponse(
            workspace_id=workspace.id,
            root_name=workspace.name,
            items=_build_deleted_file_items(db, workspace.id, member, user.id),
        )
    metas = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_(None))
        .all()
    )
    metadata_by_path = {item.relative_path: item for item in metas}
    uploader_names = _display_user_names(db, {item.uploaded_by for item in metas})
    return WorkspaceFilesResponse(
        workspace_id=workspace.id,
        root_name=workspace.name,
        items=_build_file_tree(root, root, metadata_by_path, uploader_names, member, user.id),
    )


@router.post("/{workspace_id}/files/upload", response_model=WorkspaceMultiUploadResponse)
async def upload_workspace_files(
    workspace_id: int,
    directory: str = Form(default=""),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    limit_bytes, limit_message = _upload_limit_for(user, member)
    root = Path(_ensure_storage_path(workspace)).resolve()
    rel_dir = _safe_relative_path(directory)
    target_dir = _resolve_workspace_child(root, rel_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_upload",
            400,
            "目标文件夹不存在",
            _audit_detail(workspace_id, rel_dir.as_posix(), actor_id=user.id, error="target directory missing"),
        )

    responses: list[WorkspaceFileMutationResponse] = []
    for upload in files:
        filename = _safe_name(upload.filename or "untitled")
        content = await upload.read()
        if len(content) > limit_bytes:
            _raise_with_audit(
                db,
                user.id,
                "workspace_file_upload",
                400,
                limit_message,
                _audit_detail(workspace_id, (rel_dir / filename).as_posix(), actor_id=user.id, error="file too large"),
            )
        conflict_path = _resolve_conflict_path(target_dir, filename, "keep_both")
        if conflict_path is None:
            responses.append(WorkspaceFileMutationResponse(ok=False, path=(rel_dir / filename).as_posix(), rag_status="skipped"))
            continue
        target_path = _resolve_workspace_child(root, conflict_path.relative_to(root))
        if target_path.exists() and target_path.is_dir():
            _raise_with_audit(
                db,
                user.id,
                "workspace_file_upload",
                400,
                "不能覆盖文件夹",
                _audit_detail(workspace_id, (rel_dir / filename).as_posix(), actor_id=user.id, error="target is directory"),
            )
        target_path.write_bytes(content)
        rel_path = target_path.relative_to(root).as_posix()
        meta = _upsert_workspace_file(
            db,
            workspace_id,
            user.id,
            rel_path,
            filename,
            upload.content_type or "application/octet-stream",
            len(content),
        )
        _write_workspace_audit(
            db,
            user.id,
            "workspace_file_upload",
            _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
        )
        responses.append(WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status))
    db.commit()
    return WorkspaceMultiUploadResponse(ok=True, files=responses)


@router.post("/{workspace_id}/files", response_model=WorkspaceFileMutationResponse)
def upload_workspace_file(
    workspace_id: int,
    req: UploadWorkspaceFileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    limit_bytes, limit_message = _upload_limit_for(user, member)
    root = Path(_ensure_storage_path(workspace)).resolve()
    directory = _safe_relative_path(req.directory)
    filename = _safe_name(req.filename)
    target_dir = _resolve_workspace_child(root, directory)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="目标文件夹不存在")
    target_path = _resolve_workspace_child(root, directory / filename)
    if target_path.exists() and target_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    try:
        content = base64.b64decode(req.content_base64, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=400, detail="文件内容格式不正确") from exc
    if len(content) > limit_bytes:
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_upload",
            400,
            limit_message,
            _audit_detail(workspace_id, (directory / filename).as_posix(), actor_id=user.id, error="file too large"),
        )

    conflict_path = _resolve_conflict_path(target_dir, filename, req.conflict_strategy)
    if conflict_path is None:
        return WorkspaceFileMutationResponse(ok=False, path=(directory / filename).as_posix(), rag_status="skipped")
    target_path = _resolve_workspace_child(root, conflict_path.relative_to(root))
    if target_path.exists() and target_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    target_path.write_bytes(content)
    rel_path = target_path.relative_to(root).as_posix()
    meta = _upsert_workspace_file(db, workspace_id, user.id, rel_path, filename, req.content_type, len(content))
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_upload",
        _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status)


@router.post("/{workspace_id}/folders", response_model=WorkspaceFileMutationResponse)
def create_workspace_folder(
    workspace_id: int,
    req: CreateWorkspaceFolderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    parent = _resolve_workspace_child(root, _safe_relative_path(req.parent_path))
    if not parent.exists() or not parent.is_dir():
        raise HTTPException(status_code=400, detail="目标父文件夹不存在")
    folder_name = _safe_name(req.name)
    target = _resolve_workspace_child(root, parent.relative_to(root) / folder_name)
    if target.exists():
        raise HTTPException(status_code=409, detail="已存在同名文件夹")
    target.mkdir()
    rel_path = target.relative_to(root).as_posix()
    _write_workspace_audit(
        db,
        user.id,
        "workspace_folder_create",
        _audit_detail(workspace_id, rel_path, actor_id=user.id),
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path)


@router.delete("/{workspace_id}/files", response_model=WorkspaceFileMutationResponse)
def delete_workspace_file(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    rel = _safe_relative_path(path)
    target = _resolve_workspace_child(root, rel)
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
    if not _member_can_mutate_file(member, user.id, meta):
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_delete",
            403,
            "只能删除自己上传的文件",
            _audit_detail(workspace_id, rel_path, meta.id if meta else None, actor_id=user.id, error="permission denied"),
        )
    if not meta:
        meta = _upsert_workspace_file(
            db,
            workspace_id,
            user.id,
            rel_path,
            target.name,
            "application/octet-stream",
            target.stat().st_size,
        )
    trash_path = _trash_target(root, meta, rel_path)
    shutil.move(str(target), str(trash_path))
    now = datetime.now(timezone.utc)
    meta.deleted_at = now
    meta.deleted_by = user.id
    meta.trash_path = trash_path.relative_to(root).as_posix()
    meta.rag_status = "pending"
    meta.updated_at = now
    _mark_workspace_rag_pending(db, workspace_id)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_delete",
        _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, trash_path=meta.trash_path),
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
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status)


@router.post("/{workspace_id}/files/restore", response_model=WorkspaceFileMutationResponse)
def restore_workspace_file(
    workspace_id: int,
    req: RestoreWorkspaceFileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == req.file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if not _member_can_restore_file(member, user.id, meta):
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_restore",
            403,
            "只能恢复自己删除的文件",
            _audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id, error="permission denied"),
        )
    source = _resolve_workspace_child(root, _safe_relative_path(meta.trash_path))
    target = _resolve_workspace_child(root, _safe_relative_path(meta.relative_path))
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if target.exists():
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_restore",
            409,
            "原路径已存在同名文件，请先处理冲突",
            _audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id, error="target exists"),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    now = datetime.now(timezone.utc)
    meta.deleted_at = None
    meta.deleted_by = None
    meta.trash_path = ""
    meta.rag_status = "pending"
    meta.updated_at = now
    _mark_workspace_rag_pending(db, workspace_id)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_restore",
        _audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id),
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=meta.relative_path, file_id=meta.id, rag_status=meta.rag_status)


@router.delete("/{workspace_id}/files/permanent", response_model=WorkspaceFileMutationResponse)
def permanently_delete_workspace_file(
    workspace_id: int,
    file_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if not _member_can_restore_file(member, user.id, meta):
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_permanent_delete",
            403,
            "只能永久删除自己删除的文件",
            _audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id, error="permission denied"),
        )
    if meta.trash_path:
        trash_path = _resolve_workspace_child(root, _safe_relative_path(meta.trash_path))
        if trash_path.exists() and trash_path.is_file():
            trash_path.unlink()
    rel_path = meta.relative_path
    db.delete(meta)
    _mark_workspace_rag_pending(db, workspace_id)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_permanent_delete",
        _audit_detail(workspace_id, rel_path, file_id, actor_id=user.id),
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=file_id, rag_status="pending")


@router.delete("/{workspace_id}/files/trash")
def clear_workspace_trash(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    query = db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.deleted_at.is_not(None))
    if member.role != "admin":
        query = query.filter(WorkspaceFile.uploaded_by == user.id, WorkspaceFile.deleted_by == user.id)
    deleted = 0
    for meta in query.all():
        if meta.trash_path:
            trash_path = _resolve_workspace_child(root, _safe_relative_path(meta.trash_path))
            if trash_path.exists() and trash_path.is_file():
                trash_path.unlink()
        db.delete(meta)
        deleted += 1
    _write_workspace_audit(db, user.id, "workspace_trash_clear", _audit_detail(workspace_id, actor_id=user.id, deleted_files=deleted))
    notify_workspace_bulk_delete_risk(db, workspace=workspace, actor_user_id=user.id, deleted_files=deleted)
    db.commit()
    return {"ok": True, "deleted_files": deleted}


@router.post("/{workspace_id}/attachments/save", response_model=WorkspaceFileMutationResponse)
def save_attachment_to_workspace(
    workspace_id: int,
    req: SaveAttachmentToWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
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
    root = Path(_ensure_storage_path(workspace)).resolve()
    target_dir = _resolve_workspace_child(root, Path(DEFAULT_UNFILED_DIR))
    target_dir.mkdir(exist_ok=True)
    filename = _safe_name(attachment.original_name)
    conflict_path = _resolve_conflict_path(target_dir, filename, req.conflict_strategy)
    if conflict_path is None:
        return WorkspaceFileMutationResponse(ok=False, path=f"{DEFAULT_UNFILED_DIR}/{filename}", rag_status="skipped")
    target = _resolve_workspace_child(root, conflict_path.relative_to(root))
    shutil.copy2(source, target)
    rel_path = target.relative_to(root).as_posix()
    meta = _upsert_workspace_file(db, workspace_id, user.id, rel_path, target.name, attachment.content_type, target.stat().st_size)
    _write_workspace_audit(db, user.id, "workspace_attachment_save", _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, attachment_id=attachment.id))
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status)


@router.delete("/{workspace_id}/folders", response_model=WorkspaceFileMutationResponse)
def delete_workspace_folder(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    rel = _safe_relative_path(path)
    if _is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能删除")
    target = _resolve_workspace_child(root, rel)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if any(target.iterdir()):
        raise HTTPException(status_code=400, detail="只能删除空文件夹")
    target.rmdir()
    rel_path = target.relative_to(root).as_posix()
    _write_workspace_audit(
        db,
        user.id,
        "workspace_folder_delete",
        _audit_detail(workspace_id, rel_path, actor_id=user.id),
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path)


@router.put("/{workspace_id}/paths/rename", response_model=WorkspaceFileMutationResponse)
def rename_workspace_path(
    workspace_id: int,
    req: RenameWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    rel = _safe_relative_path(req.path)
    if _is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能重命名")
    source = _resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    new_name = _safe_name(req.new_name)
    target = _resolve_workspace_child(root, rel.parent / new_name)
    if target.exists():
        raise HTTPException(status_code=409, detail="目标位置已存在同名项目")

    rel_path = source.relative_to(root).as_posix()
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.relative_path == rel_path, WorkspaceFile.deleted_at.is_(None))
        .first()
    )
    if source_is_file and not _member_can_mutate_file(member, user.id, meta):
        raise HTTPException(status_code=403, detail="只能重命名自己上传的文件")

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
        _sync_file_descendant_paths(db, workspace_id, rel_path, new_rel_path)
    _write_workspace_audit(db, user.id, "workspace_path_rename", _audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=new_rel_path, file_id=meta.id if meta else None, rag_status=meta.rag_status if meta else None)


@router.post("/{workspace_id}/paths/move", response_model=WorkspaceFileMutationResponse)
def move_workspace_path(
    workspace_id: int,
    req: MoveWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = Path(_ensure_storage_path(workspace)).resolve()
    rel = _safe_relative_path(req.path)
    if _is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能移动")
    source = _resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    target_dir_rel = _safe_relative_path(req.target_directory)
    target_dir = _resolve_workspace_child(root, target_dir_rel)
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
    if source_is_file and not _member_can_mutate_file(member, user.id, meta):
        raise HTTPException(status_code=403, detail="只能移动自己上传的文件")

    conflict_path = _resolve_conflict_path(target_dir, source.name, req.conflict_strategy)
    if conflict_path is None:
        return WorkspaceFileMutationResponse(ok=False, path=rel_path, file_id=meta.id if meta else None, rag_status="skipped")
    target = _resolve_workspace_child(root, conflict_path.relative_to(root))
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
        _sync_file_descendant_paths(db, workspace_id, rel_path, new_rel_path)
    _write_workspace_audit(db, user.id, "workspace_path_move", _audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=new_rel_path, file_id=meta.id if meta else None, rag_status=meta.rag_status if meta else None)


@router.post("/{workspace_id}/knowledge/ingest", response_model=WorkspaceKnowledgeRefreshResponse)
@router.post("/{workspace_id}/knowledge/refresh", response_model=WorkspaceKnowledgeRefreshResponse)
def refresh_workspace_knowledge(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    payload = _execute_workspace_knowledge_ingest(db, workspace, user.id)
    db.commit()
    return WorkspaceKnowledgeRefreshResponse(**payload)


@router.post("/{workspace_id}/knowledge/ingest/async", response_model=WorkspaceKnowledgeIngestJobResponse)
def enqueue_workspace_knowledge_ingest(
    workspace_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    job = WorkspaceIngestJob(
        workspace_id=workspace_id,
        requested_by=user.id,
        status="queued",
        result_json="{}",
    )
    db.add(job)
    db.flush()
    notify_user(
        db,
        user.id,
        category="workspace",
        severity="info",
        title="项目知识库录入已排队",
        content=f"{workspace.name}：后台正在处理项目资料，完成后会再次通知你。",
        action_status="pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id, "ingest_job_id": job.id},
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_workspace_knowledge_ingest_job, job.id)
    return _serialize_ingest_job(job)


@router.get("/{workspace_id}/knowledge/ingest/jobs/{job_id}", response_model=WorkspaceKnowledgeIngestJobResponse)
def get_workspace_knowledge_ingest_job(
    workspace_id: int,
    job_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_member(db, user.id, workspace_id)
    job = (
        db.query(WorkspaceIngestJob)
        .filter(WorkspaceIngestJob.id == job_id, WorkspaceIngestJob.workspace_id == workspace_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="录入任务不存在")
    return _serialize_ingest_job(job)


def _execute_workspace_knowledge_ingest(db: Session, workspace: Workspace, actor_user_id: int) -> dict:
    indexed = 0
    rag_status = "indexed"
    ok = True
    compiled_files = 0
    pending_extractor_capability_files = 0
    pending_transcription_files = 0
    skipped_files = 0
    failed_files = 0
    pending_reviews_created = 0
    gbrain_source_id = None
    gbrain_status = None
    gbrain_sync_status = None
    gbrain_error = None
    manifest = None
    if workspace.workspace_kind == "project":
        manifest = compile_project_workspace_sources(workspace)
        summary = manifest.get("summary") or {}
        compiled_files = int(summary.get("compiled", 0) or 0)
        pending_extractor_capability_files = int(summary.get("pending_extractor_capability", 0) or 0)
        pending_transcription_files = int(summary.get("pending_transcription", 0) or 0)
        skipped_files = int(summary.get("skipped", 0) or 0)
        failed_files = int(summary.get("failed", 0) or 0)
        gbrain_source_id = str(manifest.get("source_id") or "")
        source_ok = True
        if compiled_files > 0:
            adapter = GBrainAdapter()
            source_result = adapter.ensure_project_source(workspace)
            source_ok = bool(source_result.get("ok"))
            gbrain_status = str((source_result.get("source") or {}).get("status") or source_result.get("registration", {}).get("status") or "")
            if source_ok:
                sync_result = adapter.sync_project_source(workspace, no_pull=True)
                gbrain_sync_status = str(sync_result.get("status") or "")
                if sync_result.get("status") != "ok":
                    gbrain_error = str(sync_result.get("error") or "GBrain project source sync failed")
            else:
                gbrain_error = str(source_result.get("registration", {}).get("error") or "")
        else:
            gbrain_status = "not_required_no_compiled_files"
            gbrain_sync_status = "not_required_no_compiled_files"
        sync_ok = compiled_files == 0 or gbrain_sync_status == "ok"
        ok = bool(failed_files == 0 and source_ok and sync_ok)
        indexed = _update_workspace_file_rag_statuses_from_manifest(db, workspace, manifest, sync_ok, actor_user_id)
        rag_status = _overall_project_ingest_status(
            ok=ok,
            indexed_files=indexed,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            skipped_files=skipped_files,
        )
    else:
        ok = False
        rag_status = "skipped"
        gbrain_status = "not_applicable_private_workspace"
        gbrain_sync_status = "not_applicable_private_workspace"
        gbrain_error = "私人空间文件不进入 GBrain 项目知识库"
    _write_workspace_audit(
        db,
        actor_user_id,
        "workspace_knowledge_refresh",
        _audit_detail(
            workspace.id,
            actor_id=actor_user_id,
            indexed_files=indexed,
            gbrain_source_id=gbrain_source_id,
            gbrain_status=gbrain_status,
            gbrain_sync_status=gbrain_sync_status,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            pending_reviews_created=pending_reviews_created,
        ),
    )
    if workspace.workspace_kind == "project":
        _notify_workspace_ingest_finished(
            db,
            workspace=workspace,
            actor_user_id=actor_user_id,
            ok=ok,
            indexed_files=indexed,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            gbrain_error=gbrain_error,
        )
    return {
        "ok": ok,
        "workspace_id": workspace.id,
        "indexed_files": indexed,
        "rag_status": rag_status,
        "compiled_files": compiled_files,
        "pending_extractor_capability_files": pending_extractor_capability_files,
        "pending_transcription_files": pending_transcription_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "pending_reviews_created": pending_reviews_created,
        "gbrain_source_id": gbrain_source_id,
        "gbrain_status": gbrain_status,
        "gbrain_sync_status": gbrain_sync_status,
        "gbrain_error": gbrain_error,
        "manifest": manifest,
    }


def _run_workspace_knowledge_ingest_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job_id).first()
        if not job or job.status not in {"queued", "failed"}:
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
        if not workspace:
            raise ValueError("workspace no longer exists")
        payload = _execute_workspace_knowledge_ingest(db, workspace, job.requested_by)
        job.status = "succeeded" if payload.get("ok") else "failed"
        job.result_json = json.dumps(payload, ensure_ascii=False)
        job.error_message = str(payload.get("gbrain_error") or "")
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
            notify_user(
                db,
                job.requested_by,
                category="workspace",
                severity="warning",
                title="项目知识库录入失败",
                content=f"{workspace.name if workspace else '项目'}：后台录入任务失败，原因：{exc}",
                action_status="pending",
                action_kind="open_workspace",
                action_payload={"workspace_id": job.workspace_id, "ingest_job_id": job.id},
            )
            db.commit()
    finally:
        db.close()


def _serialize_ingest_job(job: WorkspaceIngestJob) -> WorkspaceKnowledgeIngestJobResponse:
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
    )


def _update_workspace_file_rag_statuses_from_manifest(
    db: Session,
    workspace: Workspace,
    manifest: dict,
    sync_ok: bool,
    actor_user_id: int,
) -> int:
    items_by_source = {
        str(item.get("source_file")): item
        for item in manifest.get("items", [])
        if isinstance(item, dict) and item.get("source_file")
    }
    now = datetime.now(timezone.utc)
    indexed = 0
    metas = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace.id, WorkspaceFile.deleted_at.is_(None))
        .all()
    )
    metas_by_path = {meta.relative_path: meta for meta in metas}
    root = Path(workspace.storage_path or "").resolve()
    for rel_path, item in items_by_source.items():
        if rel_path in metas_by_path:
            continue
        source_path = (root / rel_path).resolve()
        try:
            source_path.relative_to(root)
        except ValueError:
            continue
        if not source_path.exists() or not source_path.is_file():
            continue
        guessed_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        meta = WorkspaceFile(
            workspace_id=workspace.id,
            uploaded_by=actor_user_id,
            relative_path=rel_path,
            original_name=source_path.name,
            content_type=guessed_type[:128],
            size=source_path.stat().st_size,
            rag_status="pending",
            updated_at=now,
        )
        db.add(meta)
        db.flush()
        metas_by_path[rel_path] = meta
        metas.append(meta)
    for meta in metas:
        item = items_by_source.get(meta.relative_path)
        if not item:
            continue
        status = str(item.get("status") or "")
        if status == "compiled":
            meta.rag_status = "indexed" if sync_ok else "pending"
        elif status == "pending_extractor_capability":
            meta.rag_status = "pending_extractor_capability"
        elif status == "pending_transcription":
            meta.rag_status = "pending_transcription"
        elif status == "failed":
            meta.rag_status = "failed"
        elif status == "skipped":
            meta.rag_status = "skipped"
        else:
            meta.rag_status = "pending"
        meta.updated_at = now
        if meta.rag_status == "indexed":
            indexed += 1
    return indexed


def _overall_project_ingest_status(
    *,
    ok: bool,
    indexed_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    skipped_files: int,
) -> str:
    if failed_files > 0:
        return "failed"
    if not ok:
        return "pending"
    if indexed_files > 0:
        return "indexed"
    if pending_transcription_files > 0:
        return "pending_transcription"
    if pending_extractor_capability_files > 0:
        return "pending_extractor_capability"
    if skipped_files > 0:
        return "skipped"
    return "indexed"


def _notify_workspace_ingest_finished(
    db: Session,
    *,
    workspace: Workspace,
    actor_user_id: int,
    ok: bool,
    indexed_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    gbrain_error: str | None,
) -> None:
    if ok and failed_files == 0:
        title = "项目知识库录入完成"
        severity = "success"
    else:
        title = "项目知识库录入未完成"
        severity = "warning"
    details = [
        f"已入库 {indexed_files} 个文件",
        f"待能力补齐 {pending_extractor_capability_files} 个",
        f"待转写 {pending_transcription_files} 个",
        f"失败 {failed_files} 个",
    ]
    if gbrain_error:
        details.append(f"GBrain：{gbrain_error}")
    notify_user(
        db,
        actor_user_id,
        category="workspace",
        severity=severity,
        title=title,
        content=f"{workspace.name}：" + "，".join(details) + "。",
        action_status="none" if ok else "pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
    )


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: int,
    req: UpdateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    _ensure_member(db, user.id, workspace_id)
    if workspace.is_default and (req.name is not None or req.description is not None):
        raise HTTPException(status_code=400, detail="默认工作区不能重命名或修改")

    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        if len(name) > 128:
            raise HTTPException(status_code=400, detail="项目名称不能超过 128 个字符")
        workspace.name = name
    if req.description is not None:
        workspace.description = req.description.strip()

    db.commit()
    db.refresh(workspace)
    return _workspace_response(db, workspace)


@router.post("/{workspace_id}/join")
def join_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if existing:
        return {"ok": True, "message": "已是项目成员"}

    db.add(WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role="member"))
    notify_workspace_joined(db, workspace=workspace, user_id=user.id)
    db.commit()
    return {"ok": True}


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    if workspace.is_default:
        raise HTTPException(status_code=400, detail="默认工作区不能删除")

    is_admin = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.role == "admin",
        )
        .first()
    )
    if not is_admin:
        raise HTTPException(status_code=403, detail="仅项目管理员可删除")

    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id
    ).delete()
    db.delete(workspace)
    db.commit()
    return {"ok": True}


def _ensure_member(db: Session, user_id: int, workspace_id: int):
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="你尚未加入该项目")
    return member
