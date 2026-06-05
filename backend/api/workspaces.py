import json
import re
import base64
import binascii
import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.agent_models import AgentRunResponse
from api.auth import get_current_user
from api.time_models import UTCDateTimeModel
from core.time_utils import serialize_datetime_utc
from core.agent_events import add_agent_event, create_agent_run, finish_agent_run, serialize_agent_run
from core.gbrain import (
    GBrainAdapter,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from core.gbrain_customer_sources import CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME, compile_customer_workspace_sources
from core.gbrain_graph import (
    apply_entity_merge_candidate_action,
    build_entity_merge_candidate_preview,
    build_entity_merge_candidates,
    build_source_graph,
)
from core.gbrain_project_ingest import PROJECT_INGEST_MANIFEST_NAME, compile_project_workspace_sources
from core.notification_service import (
    notify_user,
    notify_workspace_bulk_delete_risk,
    notify_workspace_joined,
)
from core.workspace_files import (
    DEFAULT_UNFILED_DIR,
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
    TRASH_DIRNAME,
    trash_target as _trash_target,
    upload_limit_for,
)
from models import SessionLocal, get_db
from models.agent_run import AgentRun
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.workspace import Workspace, WorkspaceMember, WorkspaceGroupAccess, WorkspaceFile
from models.workspace_ingest_job import WorkspaceIngestJob
from models.user import User

router = APIRouter(prefix="/workspaces", tags=["workspaces"])

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACES_ROOT = BASE_DIR / "workspace_data"
PROJECT_ROOT_NAME = "project"
USER_ROOT_NAME = "user"
CUSTOMER_ROOT_NAME = "customer"
PROJECT_BRANDS = ("AURA", "BFI", "SPECWISE", "SYNOVA")
CUSTOMER_BRAND = "CUSTOMER"
CRM_WORKSPACE_NAME = "CRM"
CRM_WORKSPACE_SLUG = "CRM"
CRM_RAW_DIR = "raw"


def _normalize_group_name(value: str | None) -> str:
    return (value or "").strip()


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    brand: str = "BFI"
    workspace_kind: str = "project"


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_hidden: bool | None = None


class WorkspaceResponse(UTCDateTimeModel):
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
    is_hidden: bool = False
    can_rename: bool = True
    can_delete: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceDetailResponse(WorkspaceResponse):
    storage_path: str
    members: list["MemberResponse"]
    access_groups: list[str] = Field(default_factory=list)


class WorkspaceFileItemResponse(UTCDateTimeModel):
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


class WorkspaceKnowledgeGraphResponse(BaseModel):
    ok: bool
    workspace_id: int
    workspace_name: str
    workspace_kind: str
    source_id: str
    source_scope: str
    intelligence_kind: str
    derived_path: str | None = None
    focus: str | None = None
    entity_type: str | None = None
    nodes: list[dict]
    edges: list[dict]
    events: list[dict]
    profile_cards: list[dict] = Field(default_factory=list)
    stats: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspaceEntityMergeCandidatesResponse(BaseModel):
    ok: bool
    workspace_id: int
    workspace_name: str
    workspace_kind: str
    source_id: str
    source_scope: str
    derived_path: str | None = None
    focus: str | None = None
    candidates: list[dict]
    stats: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspaceEntityMergeActionRequest(BaseModel):
    candidate_id: str
    action: str


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


class CopyWorkspacePathRequest(BaseModel):
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
    agent_run: AgentRunResponse | None = None


class WorkspaceMultiUploadResponse(BaseModel):
    ok: bool
    files: list[WorkspaceFileMutationResponse]
    agent_run: AgentRunResponse | None = None


class WorkspaceTrashClearResponse(BaseModel):
    ok: bool
    deleted_files: int
    agent_run: AgentRunResponse | None = None


class RestoreWorkspaceFileRequest(BaseModel):
    file_id: int


class WorkspaceKnowledgeIngestRequest(BaseModel):
    path: str = ""
    recursive: bool = True


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
    ingest_path: str = ""
    ingest_recursive: bool = True
    gbrain_source_id: str | None = None
    gbrain_status: str | None = None
    gbrain_sync_status: str | None = None
    gbrain_think_status: str | None = None
    gbrain_error: str | None = None
    run_status: str | None = None
    run_id: str | None = None
    manifest: dict | None = None
    agent_run: AgentRunResponse | None = None


class WorkspaceKnowledgeIngestJobResponse(UTCDateTimeModel):
    id: int
    workspace_id: int
    requested_by: int
    status: str
    result: dict = Field(default_factory=dict)
    error_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    agent_run: AgentRunResponse | None = None


class MemberResponse(UTCDateTimeModel):
    user_id: int
    username: str
    nickname: str
    role: str
    joined_at: datetime


class UpsertWorkspaceMemberRequest(BaseModel):
    user_id: int | None = None
    username: str | None = None
    role: str = "member"


class UpdateWorkspaceMemberRoleRequest(BaseModel):
    role: str


class UpsertWorkspaceGroupRequest(BaseModel):
    group_name: str


class WorkspaceGroupResponse(BaseModel):
    group_name: str


class WorkspaceMemberCandidateResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    work_group: str = ""
    role: str
    is_member: bool = False
    member_role: str | None = None


class WorkspaceGroupCandidateResponse(BaseModel):
    group_name: str
    source: str = "user"
    is_authorized: bool = False


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w一-鿿-]", "-", name.strip()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "workspace"


def _safe_username(username: str) -> str:
    return _slugify(username).replace("/", "-") or "user"


def _project_brand_names() -> list[str]:
    names = set(PROJECT_BRANDS)
    for brand, _ in _project_brand_dirs():
        names.add(brand)
    return sorted(names)


def _project_brand_dirs() -> list[tuple[str, Path]]:
    project_root = (WORKSPACES_ROOT / PROJECT_ROOT_NAME).resolve()
    entries: dict[str, Path] = {}
    for brand in PROJECT_BRANDS:
        entries[brand] = (project_root / brand).resolve()
    if project_root.exists():
        for child in project_root.iterdir():
            if child.is_dir() and not child.is_symlink():
                normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", child.name.strip()).strip("-._")
                if normalized:
                    entries[normalized.upper()] = child.resolve()
    return sorted(entries.items(), key=lambda item: item[0])


def _normalize_brand(brand: str) -> str:
    normalized = brand.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", normalized or ""):
        raise HTTPException(status_code=400, detail="项目品牌不合法")
    if normalized not in _project_brand_names():
        raise HTTPException(status_code=400, detail="项目品牌不合法")
    return normalized


def _normalize_workspace_kind(kind: str | None, brand: str | None = None) -> str:
    normalized = (kind or "").strip().lower()
    if (brand or "").strip().upper() == CUSTOMER_BRAND:
        normalized = "customer"
    if not normalized:
        normalized = "project"
    if normalized not in {"project", "customer"}:
        raise HTTPException(status_code=400, detail="工作区类型不合法")
    return normalized


def _workspace_dirs(workspace: Workspace) -> tuple[str, ...]:
    if workspace.workspace_kind == "project":
        return DEFAULT_WORKSPACE_DIRS
    if workspace.workspace_kind == "customer":
        return (CRM_RAW_DIR,)
    return ()


def _is_trash_relative_path(path: Path) -> bool:
    return bool(path.parts) and path.parts[0] == TRASH_DIRNAME


def _ensure_not_trash_path(path: Path) -> None:
    if _is_trash_relative_path(path):
        raise HTTPException(status_code=400, detail="回收站不能作为普通文件夹操作")


def _target_storage_path(workspace: Workspace, owner: User | None = None) -> Path:
    if workspace.workspace_kind == "user":
        return WORKSPACES_ROOT.resolve()
    if workspace.workspace_kind == "customer":
        return (WORKSPACES_ROOT / CUSTOMER_ROOT_NAME / CRM_WORKSPACE_SLUG).resolve()
    brand = _normalize_brand(workspace.brand or "BFI")
    return (WORKSPACES_ROOT / PROJECT_ROOT_NAME / brand / workspace.slug).resolve()


def _ensure_storage_path(workspace: Workspace, *, create_user_scaffold: bool = False) -> str:
    if workspace.workspace_kind == "user":
        return ""
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
    if workspace.workspace_kind == "customer" and path.resolve() != target:
        path = target
    path.mkdir(parents=True, exist_ok=True)
    for dirname in _workspace_dirs(workspace):
        (path / dirname).mkdir(parents=True, exist_ok=True)
    (path / TRASH_DIRNAME).mkdir(exist_ok=True)
    return str(path)


def _workspace_file_root(workspace: Workspace) -> Path:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不提供后端文件区")
    return Path(_ensure_storage_path(workspace)).resolve()


def _candidate_storage_path(slug: str, brand: str, workspace_kind: str = "project") -> Path:
    if workspace_kind == "customer":
        return (WORKSPACES_ROOT / CUSTOMER_ROOT_NAME / CRM_WORKSPACE_SLUG).resolve()
    return (WORKSPACES_ROOT / PROJECT_ROOT_NAME / brand / slug).resolve()


def _workspace_response(
    db: Session,
    workspace: Workspace,
    member_count: int | None = None,
    user: User | None = None,
) -> WorkspaceResponse:
    count = member_count
    if count is None:
        count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace.id).count()
    can_manage = bool(user and _is_workspace_admin(db, user, workspace.id))
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
        is_hidden=workspace.is_hidden,
        can_rename=not workspace.is_default and can_manage,
        can_delete=not workspace.is_default and can_manage,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _serialize_workspace_member(member: WorkspaceMember, user: User) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        username=user.username,
        nickname=user.nickname,
        role=member.role,
        joined_at=member.joined_at,
    )


def _validate_workspace_member_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in {"admin", "member"}:
        raise HTTPException(status_code=400, detail="工作区成员角色不合法")
    return normalized


def _workspace_membership(db: Session, user_id: int, workspace_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )


def _workspace_access_groups(db: Session, workspace_id: int) -> list[str]:
    return [
        row.group_name
        for row in db.query(WorkspaceGroupAccess)
        .filter(WorkspaceGroupAccess.workspace_id == workspace_id)
        .order_by(WorkspaceGroupAccess.group_name.asc())
        .all()
    ]


def _has_workspace_group_access(db: Session, user: User, workspace_id: int) -> bool:
    group_name = _normalize_group_name(getattr(user, "work_group", ""))
    if not group_name:
        return False
    return bool(
        db.query(WorkspaceGroupAccess)
        .filter(
            WorkspaceGroupAccess.workspace_id == workspace_id,
            WorkspaceGroupAccess.group_name == group_name,
        )
        .first()
    )


def _can_open_workspace(db: Session, user: User, workspace: Workspace) -> bool:
    if workspace.workspace_kind == "user":
        return _workspace_membership(db, user.id, workspace.id) is not None
    if user.role == "admin":
        return True
    if workspace.workspace_kind == "customer":
        return _workspace_membership(db, user.id, workspace.id) is not None or _has_workspace_group_access(db, user, workspace.id)
    if not workspace.is_hidden:
        return True
    return _workspace_membership(db, user.id, workspace.id) is not None or _has_workspace_group_access(db, user, workspace.id)


def _ensure_can_open_workspace(db: Session, user: User, workspace: Workspace) -> None:
    if not _can_open_workspace(db, user, workspace):
        raise HTTPException(status_code=403, detail="无权访问该工作区")


def _workspace_gbrain_graph_scope(workspace: Workspace) -> dict[str, object]:
    if workspace.workspace_kind == "project":
        paths = project_source_paths_for_workspace(workspace)
        return {
            "source_id": project_source_id_for_workspace(workspace),
            "derived_path": _workspace_gbrain_read_path(paths),
            "gbrain_ready_path": paths["gbrain_ready"],
            "legacy_derived_path": paths.get("legacy_derived"),
            "source_scope": "project",
            "intelligence_kind": "project_event_graph",
        }
    if workspace.workspace_kind == "customer":
        paths = customer_source_paths_for_workspace(workspace)
        return {
            "source_id": customer_source_id_for_workspace(workspace),
            "derived_path": _workspace_gbrain_read_path(paths),
            "gbrain_ready_path": paths["gbrain_ready"],
            "legacy_derived_path": paths.get("legacy_derived"),
            "source_scope": "customer",
            "intelligence_kind": "customer_intelligence",
        }
    raise HTTPException(status_code=400, detail="当前工作区不支持 GBrain 图谱")


def _workspace_gbrain_read_path(paths: dict[str, Path]) -> Path:
    ready = paths["gbrain_ready"]
    legacy = paths.get("legacy_derived")
    if _has_markdown_files(ready) or legacy is None:
        return ready
    if _has_markdown_files(legacy):
        return legacy
    return ready


def _has_markdown_files(path: Path) -> bool:
    if not path.exists():
        return False
    return any(item.is_file() and item.suffix.lower() in {".md", ".markdown"} for item in path.rglob("*"))


def _workspace_profile_cards(graph: dict[str, object]) -> list[dict[str, object]]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    events = [event for event in graph.get("events", []) if isinstance(event, dict)]
    relation_count: dict[str, int] = {}
    event_count: dict[str, int] = {}
    for edge in edges:
        for key in ("from", "to"):
            node_id = str(edge.get(key) or "")
            if node_id:
                relation_count[node_id] = relation_count.get(node_id, 0) + 1
    for event in events:
        node_id = str(event.get("entity_id") or "")
        if node_id:
            event_count[node_id] = event_count.get(node_id, 0) + 1

    def card_priority(node: dict[str, object]) -> tuple[int, int, str]:
        node_id = str(node.get("id") or "")
        kind = str(node.get("entity_type") or "").lower()
        type_score = 0
        if any(token in kind for token in ("client", "customer", "contact", "person", "company")):
            type_score = 3
        elif "project" in kind:
            type_score = 2
        elif "event" in kind:
            type_score = 1
        return (type_score, relation_count.get(node_id, 0) + event_count.get(node_id, 0), str(node.get("title") or "").lower())

    cards: list[dict[str, object]] = []
    for node in sorted(nodes, key=card_priority, reverse=True)[:8]:
        node_id = str(node.get("id") or "")
        cards.append(
            {
                "id": node_id,
                "title": str(node.get("title") or ""),
                "entity_type": str(node.get("entity_type") or "page"),
                "relation_count": relation_count.get(node_id, 0),
                "event_count": event_count.get(node_id, 0),
                "citation": node.get("citation") if isinstance(node.get("citation"), dict) else None,
            }
        )
    return cards


def _is_workspace_admin(db: Session, user: User, workspace_id: int) -> bool:
    member = _workspace_membership(db, user.id, workspace_id)
    if member and member.role == "admin":
        return True
    if user.role == "admin":
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        return bool(workspace and workspace.workspace_kind != "user")
    return False


def _ensure_workspace_admin(db: Session, user: User, workspace_id: int) -> WorkspaceMember:
    member = _ensure_member(db, user.id, workspace_id)
    if member.role != "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="仅工作区管理员可管理成员")
    return member


def _ensure_mutable_membership_workspace(workspace: Workspace) -> None:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持邀请成员")


def _resolve_member_target_user(db: Session, req: UpsertWorkspaceMemberRequest) -> User:
    target_user: User | None = None
    if req.user_id is not None:
        target_user = db.query(User).filter(User.id == req.user_id).first()
    elif req.username and req.username.strip():
        target_user = db.query(User).filter(User.username == req.username.strip()).first()
    else:
        raise HTTPException(status_code=400, detail="需要提供用户 ID 或用户名")
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not target_user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return target_user


def _local_workspace_admin_count(db: Session, workspace_id: int) -> int:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "admin")
        .count()
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
        expected_name = f"{user.username}的工作台"
        if existing.name.endswith(" 的私人空间") or existing.name.endswith("的私人空间"):
            existing.name = expected_name
            existing.description = "用户默认个人工作台"
        if existing.storage_path:
            existing.storage_path = ""
            db.commit()
        elif existing.name == expected_name:
            db.commit()
        return existing

    slug_base = f"user-{_safe_username(user.username)}"
    slug = slug_base
    suffix = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{slug_base}-{suffix}"
        suffix += 1
    workspace = Workspace(
        name=f"{user.username}的工作台",
        slug=slug,
        description="用户默认个人工作台",
        created_by=user.id,
        brand="",
        workspace_kind="user",
        is_default=True,
    )
    db.add(workspace)
    db.flush()
    workspace.storage_path = ""
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


def _find_crm_workspace(db: Session) -> Workspace | None:
    exact = (
        db.query(Workspace)
        .filter(
            Workspace.workspace_kind == "customer",
            or_(Workspace.slug == CRM_WORKSPACE_SLUG, Workspace.name == CRM_WORKSPACE_NAME),
        )
        .order_by(Workspace.id.asc())
        .first()
    )
    if exact:
        return exact
    return (
        db.query(Workspace)
        .filter(Workspace.workspace_kind == "customer")
        .order_by(Workspace.id.asc())
        .first()
    )


def _ensure_crm_workspace(db: Session, user: User, *, add_member: bool = False) -> Workspace:
    workspace = _find_crm_workspace(db)
    if workspace is None:
        workspace = Workspace(
            name=CRM_WORKSPACE_NAME,
            slug=CRM_WORKSPACE_SLUG,
            description="全公司 CRM 客户情报工作区",
            created_by=user.id,
            storage_path=str((WORKSPACES_ROOT / CUSTOMER_ROOT_NAME / CRM_WORKSPACE_SLUG).resolve()),
            brand=CUSTOMER_BRAND,
            workspace_kind="customer",
            is_default=False,
            is_hidden=True,
        )
        db.add(workspace)
        db.flush()
    workspace.name = CRM_WORKSPACE_NAME
    workspace.slug = CRM_WORKSPACE_SLUG
    workspace.brand = CUSTOMER_BRAND
    workspace.workspace_kind = "customer"
    workspace.storage_path = _ensure_storage_path(workspace)
    if add_member and not _workspace_membership(db, user.id, workspace.id):
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def _sync_project_folders(db: Session, user: User) -> None:
    project_root = (WORKSPACES_ROOT / PROJECT_ROOT_NAME).resolve()
    if not project_root.exists():
        return
    for brand, brand_dir in _project_brand_dirs():
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


def _write_workspace_file_agent_run(
    db: Session,
    *,
    user_id: int,
    workspace: Workspace,
    source_type: str,
    title: str,
    path: str,
    status: str = "completed",
    detail: str = "",
    result: dict | None = None,
):
    payload = {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "path": path,
        **(result or {}),
    }
    run = create_agent_run(
        db,
        user_id=user_id,
        workspace_id=workspace.id,
        source_type=source_type,
        source_id=str(path or workspace.id),
        title=title,
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="permission_check",
        title="已校验项目权限",
        detail=workspace.name,
        status="completed",
        payload={"workspace_id": workspace.id},
    )
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title=title,
        detail=detail or path,
        status=status,
        payload=payload,
    )
    return finish_agent_run(
        db,
        run,
        status=status,
        result=payload,
        error_message="" if status != "failed" else detail,
    )


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
    # A3 keeps ingest state at file/run granularity. Historical callers still
    # invoke this after broad file mutations, but bulk-flipping the whole
    # workspace would mark unrelated synced files as dirty.
    return


def _file_signature(path: Path) -> dict[str, str | int]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "source_hash": digest.hexdigest(),
        "source_size": stat.st_size,
        "source_mtime": str(stat.st_mtime_ns),
    }


def _record_file_signature(meta: WorkspaceFile, path: Path) -> None:
    signature = _file_signature(path)
    meta.source_hash = str(signature["source_hash"])
    meta.source_size = int(signature["source_size"])
    meta.source_mtime = str(signature["source_mtime"])


def _source_status_for_file(meta: WorkspaceFile | None, path: Path | None = None) -> str:
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
            signature = _file_signature(path)
        except OSError:
            return status
        if signature["source_hash"] != meta.source_hash:
            return "source_changed"
    return status


def _upload_limit_for(user: User, member: WorkspaceMember, workspace: Workspace | None = None) -> tuple[int, str]:
    if workspace and workspace.workspace_kind == "user":
        return MAX_WORKSPACE_UPLOAD_BYTES, f"个人工作台文件超过 {MAX_WORKSPACE_UPLOAD_MB}MB"
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
        meta.rag_status = "new"
        meta.updated_at = datetime.now(timezone.utc)


def _create_copied_file_metadata(
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
    _record_file_signature(meta, target_file)
    db.add(meta)
    db.flush()
    return meta


def _copy_descendant_file_metadata(
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
        _create_copied_file_metadata(
            db,
            workspace_id=workspace_id,
            source_rel_path=source_rel,
            target_file=copied_path,
            root=root,
            user_id=user_id,
        )


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
                rag_status=_source_status_for_file(meta, child) if item_type == "file" else None,
                can_delete=(
                    item_type == "file" and _member_can_mutate_file(member, user_id, meta, user_role)
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
                    user_role,
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
    user_role: str,
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
            rag_status=_source_status_for_file(item),
            can_delete=_member_can_restore_file(member, user_id, item, user_role),
            can_restore=True,
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
            _record_file_signature(existing, source_path)
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
        _record_file_signature(meta, source_path)
    db.add(meta)
    db.flush()
    return meta


@router.post("", response_model=WorkspaceResponse)
def create_workspace(
    req: CreateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅系统管理员可新建工作区")

    workspace_kind = _normalize_workspace_kind(req.workspace_kind, req.brand)
    if workspace_kind == "customer":
        workspace = _ensure_crm_workspace(db, user, add_member=True)
        return _workspace_response(db, workspace, user=user)

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="工作区名称不能为空")
    if len(name) > 128:
        raise HTTPException(status_code=400, detail="工作区名称不能超过 128 个字符")

    brand = _normalize_brand(req.brand)
    slug = _slugify(name)
    existing = db.query(Workspace).filter(Workspace.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="已存在同名工作区，请选择已有工作区或使用不同名称")
    target_path = _candidate_storage_path(slug, brand, workspace_kind)
    root = WORKSPACES_ROOT.resolve()
    if not target_path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="工作区目录不合法")
    if workspace_kind == "project":
        existing_folder = _find_existing_project_folder(brand, slug, name)
        if existing_folder:
            workspace = _register_existing_project_folder(db, user, brand, existing_folder, add_member=True)
            if workspace:
                return _workspace_response(db, workspace, user=user)
            raise HTTPException(status_code=409, detail="后端已存在同名项目文件夹，请选择已有项目或更换项目名称")
    if target_path.exists():
        raise HTTPException(status_code=409, detail="后端已存在同名工作区文件夹，请选择已有工作区或更换名称")

    workspace = Workspace(
        name=name,
        slug=slug,
        description=req.description.strip(),
        created_by=user.id,
        brand=brand,
        workspace_kind=workspace_kind,
        is_default=False,
        is_hidden=workspace_kind == "customer",
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    workspace.storage_path = _ensure_storage_path(workspace)
    db.commit()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()

    return _workspace_response(db, workspace, member_count=1, user=user)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ensure_default_workspace(db, user)
    _sync_project_folders(db, user)
    _ensure_crm_workspace(db, user)
    if user.role == "admin":
        workspaces = (
            db.query(Workspace)
            .filter(or_(Workspace.workspace_kind != "user", Workspace.created_by == user.id))
            .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())
            .all()
        )
        workspaces = [w for w in workspaces if w.workspace_kind != "customer" or w.slug == CRM_WORKSPACE_SLUG]
    else:
        member_workspace_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        group_workspace_ids = select(WorkspaceGroupAccess.workspace_id).where(
            WorkspaceGroupAccess.group_name == _normalize_group_name(user.work_group)
        )
        workspaces = (
            db.query(Workspace)
            .filter(
                or_(
                    Workspace.id.in_(member_workspace_ids),
                    Workspace.workspace_kind == "project",
                    Workspace.workspace_kind == "customer",
                    Workspace.id.in_(group_workspace_ids),
                )
            )
            .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())
            .all()
        )
        workspaces = [w for w in workspaces if _can_open_workspace(db, user, w)]
        workspaces = [w for w in workspaces if w.workspace_kind != "customer" or w.slug == CRM_WORKSPACE_SLUG]
    return [_workspace_response(db, w, user=user) for w in workspaces]


@router.get("/search")
def search_workspaces(
    q: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    brand: str | None = None,
):
    _sync_project_folders(db, user)
    _ensure_crm_workspace(db, user)
    query = q.strip()
    raw_brand = (brand or "").strip().upper()
    search_customer = raw_brand == CUSTOMER_BRAND
    normalized_brand = _normalize_brand(raw_brand) if raw_brand and not search_customer else None
    pattern = f"%{query}%" if query else "%"
    workspace_query = (
        db.query(Workspace)
        .filter(
            Workspace.workspace_kind == "customer" if search_customer else Workspace.workspace_kind.in_(("project", "customer")),
            Workspace.is_archived == False,
            Workspace.name.ilike(pattern) | Workspace.slug.ilike(pattern),
        )
    )
    if normalized_brand:
        workspace_query = workspace_query.filter(Workspace.workspace_kind == "project", Workspace.brand == normalized_brand)
    if search_customer:
        workspace_query = workspace_query.filter(Workspace.slug == CRM_WORKSPACE_SLUG)
    else:
        workspace_query = workspace_query.filter(
            or_(Workspace.workspace_kind == "project", Workspace.slug == CRM_WORKSPACE_SLUG)
        )
    if user.role != "admin":
        member_workspace_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        group_workspace_ids = select(WorkspaceGroupAccess.workspace_id).where(
            WorkspaceGroupAccess.group_name == _normalize_group_name(user.work_group)
        )
        workspace_query = workspace_query.filter(
            or_(
                (Workspace.workspace_kind == "project") & (Workspace.is_hidden == False),
                Workspace.id.in_(member_workspace_ids),
                Workspace.id.in_(group_workspace_ids),
            )
        )
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
    manageable_ids = {w.id for w in workspaces if _is_workspace_admin(db, user, w.id)}
    return [
        {
            "id": w.id,
            "name": w.name,
            "slug": w.slug,
            "description": w.description,
            "brand": w.brand,
            "workspace_kind": w.workspace_kind,
            "is_default": w.is_default,
            "is_hidden": w.is_hidden,
            "member_count": db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == w.id)
            .count(),
            "is_member": w.id in member_ids,
            "can_open": _can_open_workspace(db, user, w),
            "can_rename": not w.is_default and w.id in manageable_ids,
            "can_delete": not w.is_default and w.id in manageable_ids,
            "is_archived": w.is_archived,
            "created_at": serialize_datetime_utc(w.created_at),
            "updated_at": serialize_datetime_utc(w.updated_at),
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

    if not _can_open_workspace(db, user, workspace):
        raise HTTPException(status_code=403, detail="你无权访问该隐藏项目")
    member = _ensure_member(db, user.id, workspace_id)

    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    member_list = [
        MemberResponse(
            user_id=member_user.id,
            username=member_user.username,
            nickname=member_user.nickname,
            role=wm.role,
            joined_at=wm.joined_at,
        )
        for wm, member_user in members
    ]

    can_manage = _is_workspace_admin(db, user, workspace.id)
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
        is_hidden=workspace.is_hidden,
        can_rename=not workspace.is_default and can_manage,
        can_delete=not workspace.is_default and can_manage,
        storage_path=workspace.storage_path,
        members=member_list,
        access_groups=_workspace_access_groups(db, workspace.id),
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
            items=_build_deleted_file_items(db, workspace.id, member, user.id, user.role),
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
        items=_build_file_tree(root, root, metadata_by_path, uploader_names, member, user.id, user.role),
    )


@router.get("/{workspace_id}/files/content")
def get_workspace_file_content(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    root = _workspace_file_root(workspace)
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
    if meta and meta.trash_path:
        raise HTTPException(status_code=404, detail="文件不存在")
    media_type = (meta.content_type if meta else None) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type, filename=target.name)


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
    limit_bytes, limit_message = _upload_limit_for(user, member, workspace)
    root = _workspace_file_root(workspace)
    rel_dir = _safe_relative_path(directory)
    _ensure_not_trash_path(rel_dir)
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
    uploaded_paths: list[str] = []
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
            target_path,
        )
        _write_workspace_audit(
            db,
            user.id,
            "workspace_file_upload",
            _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
        )
        responses.append(WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status))
        uploaded_paths.append(rel_path)
    agent_run = _write_workspace_file_agent_run(
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
    limit_bytes, limit_message = _upload_limit_for(user, member, workspace)
    root = _workspace_file_root(workspace)
    directory = _safe_relative_path(req.directory)
    _ensure_not_trash_path(directory)
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
        skipped_path = (directory / filename).as_posix()
        agent_run = _write_workspace_file_agent_run(
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
        return WorkspaceFileMutationResponse(ok=False, path=skipped_path, rag_status="skipped", agent_run=serialize_agent_run(db, agent_run))
    target_path = _resolve_workspace_child(root, conflict_path.relative_to(root))
    if target_path.exists() and target_path.is_dir():
        raise HTTPException(status_code=400, detail="不能覆盖文件夹")
    target_path.write_bytes(content)
    rel_path = target_path.relative_to(root).as_posix()
    meta = _upsert_workspace_file(db, workspace_id, user.id, rel_path, filename, req.content_type, len(content), target_path)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_upload",
        _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, size=len(content)),
    )
    agent_run = _write_workspace_file_agent_run(
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
    root = _workspace_file_root(workspace)
    parent_rel = _safe_relative_path(req.parent_path)
    _ensure_not_trash_path(parent_rel)
    parent = _resolve_workspace_child(root, parent_rel)
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
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_folder_create",
        title="新建项目文件夹",
        path=rel_path,
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, agent_run=serialize_agent_run(db, agent_run))


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
    root = _workspace_file_root(workspace)
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
    if not _member_can_mutate_file(member, user.id, meta, user.role):
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_delete",
            403,
            "只有上传人或管理员可以删除该文件",
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
            target,
        )
    trash_path = _trash_target(root, meta, rel_path)
    shutil.move(str(target), str(trash_path))
    now = datetime.now(timezone.utc)
    meta.deleted_at = now
    meta.deleted_by = user.id
    meta.trash_path = trash_path.relative_to(root).as_posix()
    meta.rag_status = "source_deleted"
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
    agent_run = _write_workspace_file_agent_run(
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
    _ensure_member(db, user.id, workspace_id)
    root = _workspace_file_root(workspace)
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == req.file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
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
    meta.rag_status = "new"
    _record_file_signature(meta, target)
    meta.updated_at = now
    _mark_workspace_rag_pending(db, workspace_id)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_file_restore",
        _audit_detail(workspace_id, meta.relative_path, meta.id, actor_id=user.id),
    )
    agent_run = _write_workspace_file_agent_run(
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
    root = _workspace_file_root(workspace)
    meta = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace_id, WorkspaceFile.id == file_id)
        .first()
    )
    if not meta or not meta.deleted_at:
        raise HTTPException(status_code=404, detail="回收区文件不存在")
    if not _member_can_restore_file(member, user.id, meta, user.role):
        _raise_with_audit(
            db,
            user.id,
            "workspace_file_permanent_delete",
            403,
            "只有上传人或管理员可以永久删除该文件",
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
    agent_run = _write_workspace_file_agent_run(
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


@router.delete("/{workspace_id}/files/trash", response_model=WorkspaceTrashClearResponse)
def clear_workspace_trash(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    member = _ensure_member(db, user.id, workspace_id)
    root = _workspace_file_root(workspace)
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
    agent_run = _write_workspace_file_agent_run(
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
    root = _workspace_file_root(workspace)
    target_dir = _resolve_workspace_child(root, Path(DEFAULT_UNFILED_DIR))
    target_dir.mkdir(exist_ok=True)
    filename = _safe_name(attachment.original_name)
    conflict_path = _resolve_conflict_path(target_dir, filename, req.conflict_strategy)
    if conflict_path is None:
        skipped_path = f"{DEFAULT_UNFILED_DIR}/{filename}"
        agent_run = _write_workspace_file_agent_run(
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
        db.commit()
        return WorkspaceFileMutationResponse(ok=False, path=skipped_path, rag_status="skipped", agent_run=serialize_agent_run(db, agent_run))
    target = _resolve_workspace_child(root, conflict_path.relative_to(root))
    shutil.copy2(source, target)
    rel_path = target.relative_to(root).as_posix()
    meta = _upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        rel_path,
        target.name,
        attachment.content_type,
        target.stat().st_size,
        target,
    )
    _write_workspace_audit(db, user.id, "workspace_attachment_save", _audit_detail(workspace_id, rel_path, meta.id, actor_id=user.id, attachment_id=attachment.id))
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_attachment_save",
        title="保存会话附件到项目",
        path=rel_path,
        result={"file_id": meta.id, "attachment_id": attachment.id, "rag_status": meta.rag_status},
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, file_id=meta.id, rag_status=meta.rag_status, agent_run=serialize_agent_run(db, agent_run))


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
    root = _workspace_file_root(workspace)
    rel = _safe_relative_path(path)
    _ensure_not_trash_path(rel)
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
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="workspace_folder_delete",
        title="删除项目文件夹",
        path=rel_path,
    )
    db.commit()
    return WorkspaceFileMutationResponse(ok=True, path=rel_path, agent_run=serialize_agent_run(db, agent_run))


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
    root = _workspace_file_root(workspace)
    rel = _safe_relative_path(req.path)
    _ensure_not_trash_path(rel)
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
    if source_is_file and not _member_can_mutate_file(member, user.id, meta, user.role):
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
        _sync_file_descendant_paths(db, workspace_id, rel_path, new_rel_path)
    _write_workspace_audit(db, user.id, "workspace_path_rename", _audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    agent_run = _write_workspace_file_agent_run(
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
    root = _workspace_file_root(workspace)
    rel = _safe_relative_path(req.path)
    _ensure_not_trash_path(rel)
    if _is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能移动")
    source = _resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    target_dir_rel = _safe_relative_path(req.target_directory)
    _ensure_not_trash_path(target_dir_rel)
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
    if source_is_file and not _member_can_mutate_file(member, user.id, meta, user.role):
        raise HTTPException(status_code=403, detail="只有上传人或管理员可以移动该文件")

    conflict_path = _resolve_conflict_path(target_dir, source.name, req.conflict_strategy)
    if conflict_path is None:
        agent_run = _write_workspace_file_agent_run(
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
    agent_run = _write_workspace_file_agent_run(
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


@router.post("/{workspace_id}/paths/copy", response_model=WorkspaceFileMutationResponse)
def copy_workspace_path(
    workspace_id: int,
    req: CopyWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    root = _workspace_file_root(workspace)
    rel = _safe_relative_path(req.path)
    _ensure_not_trash_path(rel)
    if _is_template_root(rel):
        raise HTTPException(status_code=400, detail="默认模板文件夹不能复制")
    source = _resolve_workspace_child(root, rel)
    if not source.exists():
        raise HTTPException(status_code=404, detail="文件或文件夹不存在")
    source_is_file = source.is_file()
    target_dir_rel = _safe_relative_path(req.target_directory)
    _ensure_not_trash_path(target_dir_rel)
    target_dir = _resolve_workspace_child(root, target_dir_rel)
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
    conflict_path = _resolve_conflict_path(target_dir, source.name, req.conflict_strategy)
    if conflict_path is None:
        agent_run = _write_workspace_file_agent_run(
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

    if source_is_file:
        shutil.copy2(source, target)
        meta = _create_copied_file_metadata(
            db,
            workspace_id=workspace_id,
            source_rel_path=rel_path,
            target_file=target,
            root=root,
            user_id=user.id,
        )
    else:
        shutil.copytree(source, target)
        _copy_descendant_file_metadata(
            db,
            workspace_id=workspace_id,
            source_dir=source,
            target_dir=target,
            root=root,
            user_id=user.id,
        )
        meta = None

    new_rel_path = target.relative_to(root).as_posix()
    _write_workspace_audit(db, user.id, "workspace_path_copy", _audit_detail(workspace_id, new_rel_path, meta.id if meta else None, actor_id=user.id, old_path=rel_path))
    agent_run = _write_workspace_file_agent_run(
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


@router.post("/{workspace_id}/knowledge/ingest", response_model=WorkspaceKnowledgeRefreshResponse)
@router.post("/{workspace_id}/knowledge/refresh", response_model=WorkspaceKnowledgeRefreshResponse)
def refresh_workspace_knowledge(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    req: WorkspaceKnowledgeIngestRequest | None = None,
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    if workspace.workspace_kind not in {"project", "customer"}:
        raise HTTPException(status_code=400, detail="当前工作区类型暂不支持一键录入知识库")
    ingest_request = _normalize_workspace_ingest_request(db, workspace, user, req)
    payload = _execute_workspace_knowledge_ingest(
        db,
        workspace,
        user.id,
        source_path=ingest_request["path"],
        recursive=ingest_request["recursive"],
    )
    agent_run = _write_immediate_workspace_ingest_agent_run(db, workspace, user.id, payload)
    payload["agent_run"] = serialize_agent_run(db, agent_run)
    db.commit()
    return WorkspaceKnowledgeRefreshResponse(**payload)


@router.post("/{workspace_id}/knowledge/ingest/async", response_model=WorkspaceKnowledgeIngestJobResponse)
def enqueue_workspace_knowledge_ingest(
    workspace_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    req: WorkspaceKnowledgeIngestRequest | None = None,
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    if workspace.workspace_kind not in {"project", "customer"}:
        raise HTTPException(status_code=400, detail="当前工作区类型暂不支持一键录入知识库")
    ingest_request = _normalize_workspace_ingest_request(db, workspace, user, req)
    job = WorkspaceIngestJob(
        workspace_id=workspace_id,
        requested_by=user.id,
        status="queued",
        result_json=json.dumps({"request": ingest_request}, ensure_ascii=False),
    )
    db.add(job)
    db.flush()
    run_id = _workspace_ingest_job_run_id(job)
    job.result_json = json.dumps(
        {
            "request": ingest_request,
            "run": _workspace_ingest_run_payload(
                run_id=run_id,
                status="queued",
                workspace=workspace,
                source_id=None,
                source_path=ingest_request["path"],
                recursive=ingest_request["recursive"],
                started_at=None,
                finished_at=None,
                error=None,
                status_history=[
                    _workspace_ingest_status_event("queued", "任务已排队", job.created_at),
                ],
            ),
            "run_status": "queued",
            "run_id": run_id,
        },
        ensure_ascii=False,
    )
    agent_run = create_agent_run(
        db,
        user_id=user.id,
        workspace_id=workspace.id,
        source_type="workspace_ingest",
        source_id=job.id,
        title=f"录入工作区知识库：{workspace.name}",
        status="queued",
    )
    add_agent_event(
        db,
        agent_run,
        event_type="queued",
        title="工作区录入任务已排队",
        detail=_workspace_ingest_request_detail(workspace, ingest_request),
        status="queued",
        payload={"workspace_id": workspace.id, "workspace_name": workspace.name, **ingest_request},
    )
    notify_user(
        db,
        user.id,
        category="workspace",
        severity="info",
        title="工作区知识库录入已排队",
        content=f"{workspace.name}：后台正在处理{_workspace_ingest_request_label(ingest_request)}，完成后会再次通知你。",
        action_status="pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id, "ingest_job_id": job.id},
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(_run_workspace_knowledge_ingest_job, job.id)
    return _serialize_ingest_job(db, job)


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
    return _serialize_ingest_job(db, job)


@router.get("/{workspace_id}/knowledge/graph", response_model=WorkspaceKnowledgeGraphResponse)
def workspace_knowledge_graph(
    workspace_id: int,
    focus: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_can_open_workspace(db, user, workspace)
    scope = _workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = scope["derived_path"]
    if not isinstance(derived_path, Path):
        raise HTTPException(status_code=500, detail="工作区 GBrain 路径配置错误")
    graph = build_source_graph(
        source_id,
        derived_path=derived_path,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
    )
    _write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_graph_view",
        _audit_detail(
            workspace.id,
            "knowledge/graph",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            nodes=len(graph.get("nodes") or []),
            edges=len(graph.get("edges") or []),
            events=len(graph.get("events") or []),
        ),
    )
    db.commit()
    return WorkspaceKnowledgeGraphResponse(
        ok=bool(graph.get("ok")),
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_kind=workspace.workspace_kind,
        source_id=source_id,
        source_scope=str(scope["source_scope"]),
        intelligence_kind=str(scope["intelligence_kind"]),
        derived_path=str(graph.get("derived_path") or derived_path),
        focus=focus,
        entity_type=entity_type,
        nodes=list(graph.get("nodes") or []),
        edges=list(graph.get("edges") or []),
        events=list(graph.get("events") or []),
        profile_cards=_workspace_profile_cards(graph),
        stats=graph.get("stats") if isinstance(graph.get("stats"), dict) else None,
        warnings=[str(item) for item in graph.get("warnings") or []],
    )


@router.get("/{workspace_id}/knowledge/entity-merge-candidates", response_model=WorkspaceEntityMergeCandidatesResponse)
def workspace_entity_merge_candidates(
    workspace_id: int,
    focus: str | None = Query(default=None),
    limit: int = Query(default=80, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    if not _is_workspace_admin(db, user, workspace_id):
        raise HTTPException(status_code=403, detail="仅系统管理员或工作区管理员可查看实体候选")
    scope = _workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = scope["derived_path"]
    if not isinstance(derived_path, Path):
        raise HTTPException(status_code=500, detail="工作区 GBrain 路径配置错误")
    result = build_entity_merge_candidates(source_id, derived_path=derived_path, focus=focus, limit=limit)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidates_view",
        _audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            candidates=len(result.get("candidates") or []),
        ),
    )
    db.commit()
    return WorkspaceEntityMergeCandidatesResponse(
        ok=bool(result.get("ok")),
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_kind=workspace.workspace_kind,
        source_id=source_id,
        source_scope=str(scope["source_scope"]),
        derived_path=str(result.get("derived_path") or derived_path),
        focus=focus,
        candidates=list(result.get("candidates") or []),
        stats=result.get("stats") if isinstance(result.get("stats"), dict) else None,
        warnings=[str(item) for item in result.get("warnings") or []],
    )


@router.post("/{workspace_id}/knowledge/entity-merge-candidates/action")
def workspace_entity_merge_candidate_action(
    workspace_id: int,
    request: WorkspaceEntityMergeActionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    if not _is_workspace_admin(db, user, workspace_id):
        raise HTTPException(status_code=403, detail="仅系统管理员或工作区管理员可处理实体候选")
    if request.action not in {"create_entity_page", "dismiss", "record_alias", "apply_relink_changes"}:
        raise HTTPException(status_code=400, detail="实体候选操作不合法")
    scope = _workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = scope["derived_path"]
    if not isinstance(derived_path, Path):
        raise HTTPException(status_code=500, detail="工作区 GBrain 路径配置错误")
    result = apply_entity_merge_candidate_action(
        source_id,
        request.candidate_id,
        request.action,
        derived_path=derived_path,
        actor=user.username,
    )
    sync_result: dict | None = None
    if result.get("ok") and result.get("status") in {
        "created",
        "already_exists",
        "alias_recorded",
        "alias_already_exists",
        "relink_applied",
    }:
        sync_result = GBrainAdapter().sync_source(source_id=source_id, repo_path=derived_path, no_pull=True)
        result["sync"] = sync_result
    _write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidate_action",
        _audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates/action",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            action=request.action,
            status=result.get("status"),
            candidate_id=request.candidate_id[:160],
            sync=(sync_result or {}).get("status") or "",
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选操作失败")
    return result


@router.get("/{workspace_id}/knowledge/entity-merge-candidates/preview")
def workspace_entity_merge_candidate_preview(
    workspace_id: int,
    candidate_id: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    if not _is_workspace_admin(db, user, workspace_id):
        raise HTTPException(status_code=403, detail="仅系统管理员或工作区管理员可预览实体候选")
    scope = _workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = scope["derived_path"]
    if not isinstance(derived_path, Path):
        raise HTTPException(status_code=500, detail="工作区 GBrain 路径配置错误")
    result = build_entity_merge_candidate_preview(source_id, candidate_id, derived_path=derived_path)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidate_preview",
        _audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates/preview",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            status=result.get("status"),
            candidate_id=candidate_id[:160],
            changes=((result.get("stats") or {}).get("planned_relink_changes") or 0),
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选预览失败")
    return result


@router.get("/{workspace_id}/knowledge/graph/native-context")
def workspace_native_graph_context(
    workspace_id: int,
    slug: str = Query(..., min_length=1),
    depth: int = Query(default=2, ge=1, le=10),
    direction: str = Query(default="both"),
    link_type: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_can_open_workspace(db, user, workspace)
    scope = _workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    result = GBrainAdapter().graph_context(
        slug,
        source_id=source_id,
        depth=depth,
        direction=direction,
        link_type=link_type,
    )
    _write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_native_graph_context",
        _audit_detail(
            workspace.id,
            "knowledge/graph/native-context",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            slug=slug[:160],
            status=result.get("status"),
        ),
    )
    db.commit()
    return result


def _normalize_workspace_ingest_request(
    db: Session,
    workspace: Workspace,
    user: User,
    req: WorkspaceKnowledgeIngestRequest | None,
) -> dict:
    requested_path = (req.path if req else "").replace("\\", "/").strip("/")
    recursive = True if req is None else bool(req.recursive)
    root = _workspace_file_root(workspace)
    rel = _safe_relative_path(requested_path) if requested_path else Path()
    _ensure_not_trash_path(rel)
    target = _resolve_workspace_child(root, rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail="录入路径不存在")
    rel_path = target.relative_to(root).as_posix()
    if rel_path == ".":
        rel_path = ""
    is_file = target.is_file()
    is_directory = target.is_dir()
    if not is_file and not is_directory:
        raise HTTPException(status_code=400, detail="录入路径不是文件或文件夹")

    is_admin = _is_workspace_admin(db, user, workspace.id)
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


def _workspace_ingest_request_label(request: dict) -> str:
    path = str(request.get("path") or "")
    if not path:
        return "当前工作区资料"
    if request.get("target_type") == "file":
        return f"文件「{path}」"
    return f"文件夹「{path}」"


def _workspace_ingest_request_detail(workspace: Workspace, request: dict) -> str:
    mode = "递归录入" if request.get("recursive") else "单文件录入"
    return f"{workspace.name}：{mode} {_workspace_ingest_request_label(request)}"


def _workspace_ingest_request_from_job(job: WorkspaceIngestJob) -> dict:
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


def _compile_project_workspace_sources_for_request(workspace: Workspace, source_path: str, recursive: bool) -> dict:
    try:
        return compile_project_workspace_sources(workspace, source_path=source_path, recursive=recursive)
    except TypeError:
        if source_path or not recursive:
            raise
        return compile_project_workspace_sources(workspace)


def _compile_customer_workspace_sources_for_request(workspace: Workspace, source_path: str, recursive: bool) -> dict:
    try:
        return compile_customer_workspace_sources(workspace, source_path=source_path, recursive=recursive)
    except TypeError:
        if source_path or not recursive:
            raise
        return compile_customer_workspace_sources(workspace)


WORKSPACE_INGEST_RUN_STATUSES = {
    "queued",
    "preprocessing",
    "gbrain_ready",
    "sync_pending",
    "synced",
    "failed",
    "pending_capability",
    "ignored",
}


def _new_workspace_ingest_run_id(workspace: Workspace) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"workspace-{workspace.id}-{stamp}-{uuid.uuid4().hex[:8]}"


def _workspace_ingest_job_run_id(job: WorkspaceIngestJob) -> str:
    return f"workspace-ingest-job-{job.id}"


def _workspace_ingest_run_id_from_job(job: WorkspaceIngestJob) -> str:
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
    return _workspace_ingest_job_run_id(job)


def _workspace_ingest_status_event(status: str, message: str = "", at: datetime | None = None) -> dict:
    normalized = status if status in WORKSPACE_INGEST_RUN_STATUSES else "failed"
    return {
        "status": normalized,
        "message": message,
        "at": serialize_datetime_utc(at or datetime.now(timezone.utc)),
    }


def _workspace_ingest_run_payload(
    *,
    run_id: str,
    status: str,
    workspace: Workspace | None,
    source_id: str | None,
    source_path: str,
    recursive: bool,
    started_at: datetime | None,
    finished_at: datetime | None,
    error: str | None,
    status_history: list[dict],
) -> dict:
    normalized = status if status in WORKSPACE_INGEST_RUN_STATUSES else "failed"
    return {
        "run_id": run_id,
        "status": normalized,
        "workspace_id": getattr(workspace, "id", None),
        "workspace_kind": getattr(workspace, "workspace_kind", None),
        "workspace_name": getattr(workspace, "name", ""),
        "source_id": source_id,
        "source_path": source_path,
        "recursive": recursive,
        "started_at": serialize_datetime_utc(started_at) if started_at else None,
        "finished_at": serialize_datetime_utc(finished_at) if finished_at else None,
        "error": error or None,
        "status_history": status_history,
    }


def _derive_workspace_ingest_run_status(
    *,
    compiled_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    skipped_files: int,
    sync_ok: bool,
    ok: bool,
) -> str:
    if failed_files > 0:
        return "failed"
    if compiled_files > 0 and not sync_ok:
        return "sync_pending"
    if compiled_files > 0 and ok:
        return "synced"
    if pending_extractor_capability_files > 0 or pending_transcription_files > 0:
        return "pending_capability"
    if not ok:
        return "failed"
    if skipped_files > 0:
        return "ignored"
    return "ignored"


def _workspace_ingest_run_status_label(status: str) -> str:
    return {
        "queued": "任务已排队",
        "preprocessing": "正在预处理源文件",
        "gbrain_ready": "已生成 GBrain-ready Markdown",
        "sync_pending": "GBrain 同步待处理",
        "synced": "GBrain 同步完成",
        "failed": "录入失败",
        "pending_capability": "等待预处理能力补齐",
        "ignored": "已忽略或无可处理文件",
    }.get(status, status)


def _workspace_ingest_item_run_status(item: dict, *, sync_ok: bool) -> str:
    status = str(item.get("status") or "")
    if status == "compiled":
        return "synced" if sync_ok else "sync_pending"
    if status in {"pending_extractor_capability", "pending_transcription"} or status.startswith("pending_"):
        return "pending_capability"
    if status == "failed":
        return "failed"
    if status in {"skipped", "ignored"}:
        return "ignored"
    return "failed" if status else "ignored"


def _workspace_ingest_manifest_name(workspace: Workspace) -> str:
    if workspace.workspace_kind == "customer":
        return CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME
    return PROJECT_INGEST_MANIFEST_NAME


def _finalize_workspace_ingest_manifest(
    workspace: Workspace,
    manifest: dict | None,
    *,
    run_id: str,
    run_status: str,
    source_path: str,
    recursive: bool,
    started_at: datetime,
    finished_at: datetime,
    status_history: list[dict],
    sync_ok: bool,
    gbrain_sync_status: str | None,
    gbrain_error: str | None,
    gbrain_think_status: str | None,
) -> None:
    if not isinstance(manifest, dict):
        return
    source_id = str(manifest.get("source_id") or "")
    run_payload = _workspace_ingest_run_payload(
        run_id=run_id,
        status=run_status,
        workspace=workspace,
        source_id=source_id,
        source_path=source_path,
        recursive=recursive,
        started_at=started_at,
        finished_at=finished_at,
        error=gbrain_error,
        status_history=status_history,
    )
    manifest["run_id"] = run_id
    manifest["run_status"] = run_status
    manifest["run"] = run_payload
    manifest["status_history"] = status_history
    manifest["sync"] = {
        "ok": bool(sync_ok),
        "status": gbrain_sync_status,
        "error": gbrain_error,
        "think_status": gbrain_think_status,
    }
    for item in manifest.get("items") or []:
        if not isinstance(item, dict):
            continue
        item["preprocess_status"] = str(item.get("status") or "")
        item["source_hash"] = item.get("source_hash") or item.get("source_sha256")
        if item.get("target_file"):
            item["gbrain_ready_file"] = item.get("gbrain_ready_file") or item["target_file"]
            item["output_file"] = item.get("output_file") or item["target_file"]
        item_run_status = _workspace_ingest_item_run_status(item, sync_ok=sync_ok)
        item["run_status"] = item_run_status
        item["sync_status"] = item_run_status if item_run_status in {"synced", "sync_pending"} else "not_applicable"
        item["model_profile"] = item.get("model_profile") or item.get("extractor_profile") or "not_applicable"
        item["skill_version"] = (
            item.get("skill_version")
            or item.get("preprocessor_version")
            or item.get("extractor_profile")
            or item.get("content_kind")
            or "workspace-ingest-v1"
        )
        item["prompt_version"] = item.get("prompt_version") or item.get("extractor_prompt_version") or "not_applicable"

    manifests_path = manifest.get("manifests_path")
    runs_path = manifest.get("runs_path")
    try:
        run_path = None
        if runs_path:
            run_path = Path(str(runs_path)) / f"{run_id}.json"
            manifest["run_manifest_path"] = str(run_path.resolve())
        if manifests_path:
            path = Path(str(manifests_path)) / _workspace_ingest_manifest_name(workspace)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if run_path is not None:
            run_path.parent.mkdir(parents=True, exist_ok=True)
            run_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        manifest["run_manifest_write_error"] = str(exc)


def _execute_workspace_knowledge_ingest(
    db: Session,
    workspace: Workspace,
    actor_user_id: int,
    *,
    source_path: str = "",
    recursive: bool = True,
    run_id: str | None = None,
    initial_status_history: list[dict] | None = None,
) -> dict:
    run_id = run_id or _new_workspace_ingest_run_id(workspace)
    started_at = datetime.now(timezone.utc)
    status_history = list(initial_status_history or [])
    if not any(item.get("status") == "preprocessing" for item in status_history if isinstance(item, dict)):
        status_history.append(_workspace_ingest_status_event("preprocessing", "开始预处理源文件", started_at))
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
    gbrain_think_status = None
    gbrain_error = None
    gbrain_think_ok = True
    manifest = None
    run_status = "preprocessing"
    if workspace.workspace_kind == "project":
        manifest = _compile_project_workspace_sources_for_request(workspace, source_path, recursive)
        summary = manifest.get("summary") or {}
        compiled_files = int(summary.get("compiled", 0) or 0)
        pending_extractor_capability_files = int(summary.get("pending_extractor_capability", 0) or 0)
        pending_transcription_files = int(summary.get("pending_transcription", 0) or 0)
        skipped_files = int(summary.get("skipped", 0) or 0)
        failed_files = int(summary.get("failed", 0) or 0)
        gbrain_source_id = str(manifest.get("source_id") or "")
        source_ok = True
        if compiled_files > 0:
            status_history.append(_workspace_ingest_status_event("gbrain_ready", "已生成 GBrain-ready Markdown"))
            adapter = GBrainAdapter()
            source_result = adapter.ensure_project_source(workspace)
            source_ok = bool(source_result.get("ok"))
            gbrain_status = str((source_result.get("source") or {}).get("status") or source_result.get("registration", {}).get("status") or "")
            if source_ok:
                sync_result = adapter.sync_project_source(workspace, no_pull=True)
                gbrain_sync_status = str(sync_result.get("status") or "")
                if sync_result.get("status") != "ok":
                    gbrain_error = str(sync_result.get("error") or "GBrain project source sync failed")
                elif gbrain_source_id:
                    settings = getattr(adapter, "settings", None)
                    if settings is None or not hasattr(adapter, "ensure_think_source_client"):
                        gbrain_think_status = "not_checked"
                    elif not settings.think_enabled:
                        gbrain_think_status = "disabled"
                    elif not settings.think_source_scope_verified:
                        gbrain_think_status = "source_scope_unverified"
                    elif not settings.think_project_clients_enabled:
                        gbrain_think_status = "project_clients_disabled"
                    else:
                        think_client_result = adapter.ensure_think_source_client(gbrain_source_id)
                        gbrain_think_status = str(think_client_result.get("status") or "")
                        if not think_client_result.get("ok") and not gbrain_error:
                            gbrain_think_ok = False
                            gbrain_error = str(
                                think_client_result.get("error")
                                or "GBrain project think OAuth client preparation failed"
                            )
            else:
                gbrain_error = str(source_result.get("registration", {}).get("error") or "")
        else:
            gbrain_status = "not_required_no_compiled_files"
            gbrain_sync_status = "not_required_no_compiled_files"
            gbrain_think_status = "not_required_no_compiled_files"
        sync_ok = compiled_files == 0 or gbrain_sync_status == "ok"
        ok = bool(failed_files == 0 and source_ok and sync_ok and gbrain_think_ok)
        run_status = _derive_workspace_ingest_run_status(
            compiled_files=compiled_files,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            skipped_files=skipped_files,
            sync_ok=sync_ok,
            ok=ok,
        )
        status_history.append(_workspace_ingest_status_event(run_status, _workspace_ingest_run_status_label(run_status)))
        _finalize_workspace_ingest_manifest(
            workspace,
            manifest,
            run_id=run_id,
            run_status=run_status,
            source_path=source_path,
            recursive=recursive,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status_history=status_history,
            sync_ok=sync_ok,
            gbrain_sync_status=gbrain_sync_status,
            gbrain_error=gbrain_error,
            gbrain_think_status=gbrain_think_status,
        )
        indexed = _update_workspace_file_rag_statuses_from_manifest(db, workspace, manifest, sync_ok, actor_user_id)
        rag_status = _overall_project_ingest_status(
            ok=ok,
            indexed_files=indexed,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            skipped_files=skipped_files,
        )
    elif workspace.workspace_kind == "customer":
        manifest = _compile_customer_workspace_sources_for_request(workspace, source_path, recursive)
        summary = manifest.get("summary") or {}
        compiled_files = int(summary.get("compiled", 0) or 0)
        pending_extractor_capability_files = int(summary.get("pending_extractor_capability", 0) or 0)
        pending_transcription_files = int(summary.get("pending_transcription", 0) or 0)
        skipped_files = int(summary.get("skipped", 0) or 0)
        failed_files = int(summary.get("failed", 0) or 0)
        gbrain_source_id = str(manifest.get("source_id") or "")
        source_ok = True
        if compiled_files > 0:
            status_history.append(_workspace_ingest_status_event("gbrain_ready", "已生成 GBrain-ready Markdown"))
            adapter = GBrainAdapter()
            source_result = adapter.ensure_customer_source(workspace)
            source_ok = bool(source_result.get("ok"))
            gbrain_status = str((source_result.get("source") or {}).get("status") or source_result.get("registration", {}).get("status") or "")
            if source_ok:
                sync_result = adapter.sync_customer_source(workspace, no_pull=True)
                gbrain_sync_status = str(sync_result.get("status") or "")
                if sync_result.get("status") != "ok":
                    gbrain_error = str(sync_result.get("error") or "GBrain customer source sync failed")
                elif gbrain_source_id:
                    settings = getattr(adapter, "settings", None)
                    if settings is None or not hasattr(adapter, "ensure_think_source_client"):
                        gbrain_think_status = "not_checked"
                    elif not settings.think_enabled:
                        gbrain_think_status = "disabled"
                    elif not settings.think_source_scope_verified:
                        gbrain_think_status = "source_scope_unverified"
                    elif not settings.think_project_clients_enabled:
                        gbrain_think_status = "customer_clients_disabled"
                    else:
                        think_client_result = adapter.ensure_think_source_client(gbrain_source_id)
                        gbrain_think_status = str(think_client_result.get("status") or "")
                        if not think_client_result.get("ok") and not gbrain_error:
                            gbrain_think_ok = False
                            gbrain_error = str(
                                think_client_result.get("error")
                                or "GBrain customer think OAuth client preparation failed"
                            )
            else:
                gbrain_error = str(source_result.get("registration", {}).get("error") or "")
        else:
            gbrain_status = "not_required_no_compiled_files"
            gbrain_sync_status = "not_required_no_compiled_files"
            gbrain_think_status = "not_required_no_compiled_files"
        sync_ok = compiled_files == 0 or gbrain_sync_status == "ok"
        ok = bool(failed_files == 0 and source_ok and sync_ok and gbrain_think_ok)
        run_status = _derive_workspace_ingest_run_status(
            compiled_files=compiled_files,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            skipped_files=skipped_files,
            sync_ok=sync_ok,
            ok=ok,
        )
        status_history.append(_workspace_ingest_status_event(run_status, _workspace_ingest_run_status_label(run_status)))
        _finalize_workspace_ingest_manifest(
            workspace,
            manifest,
            run_id=run_id,
            run_status=run_status,
            source_path=source_path,
            recursive=recursive,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            status_history=status_history,
            sync_ok=sync_ok,
            gbrain_sync_status=gbrain_sync_status,
            gbrain_error=gbrain_error,
            gbrain_think_status=gbrain_think_status,
        )
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
        run_status = "failed"
        gbrain_status = "not_applicable_private_workspace"
        gbrain_sync_status = "not_applicable_private_workspace"
        gbrain_error = "该工作区类型不进入 GBrain 知识库"
        status_history.append(_workspace_ingest_status_event(run_status, gbrain_error))
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
            gbrain_think_status=gbrain_think_status,
            failed_files=failed_files,
            pending_extractor_capability_files=pending_extractor_capability_files,
            pending_transcription_files=pending_transcription_files,
            pending_reviews_created=pending_reviews_created,
            ingest_path=source_path,
            ingest_recursive=recursive,
        ),
    )
    if workspace.workspace_kind in {"project", "customer"}:
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
        "ingest_path": source_path,
        "ingest_recursive": recursive,
        "gbrain_source_id": gbrain_source_id,
        "gbrain_status": gbrain_status,
        "gbrain_sync_status": gbrain_sync_status,
        "gbrain_think_status": gbrain_think_status,
        "gbrain_error": gbrain_error,
        "run_status": run_status,
        "run_id": run_id,
        "run": manifest.get("run") if isinstance(manifest, dict) else None,
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
        workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
        ingest_request = _workspace_ingest_request_from_job(job)
        run_id = _workspace_ingest_run_id_from_job(job)
        initial_history = [
            _workspace_ingest_status_event("queued", "任务已排队", job.created_at),
            _workspace_ingest_status_event("preprocessing", "开始预处理源文件", job.started_at),
        ]
        job.result_json = json.dumps(
            {
                "request": ingest_request,
                "run": _workspace_ingest_run_payload(
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
        agent_run = _get_or_create_workspace_ingest_agent_run(db, job, workspace)
        agent_run.status = "running"
        add_agent_event(
            db,
            agent_run,
            event_type="started",
            title="开始处理工作区资料",
            detail=_workspace_ingest_request_detail(workspace, ingest_request) if workspace else "",
            status="running",
            payload={"workspace_id": job.workspace_id, **ingest_request},
        )
        db.commit()

        if not workspace:
            raise ValueError("workspace no longer exists")
        payload = _execute_workspace_knowledge_ingest(
            db,
            workspace,
            job.requested_by,
            source_path=str(ingest_request.get("path") or ""),
            recursive=bool(ingest_request.get("recursive", True)),
            run_id=run_id,
            initial_status_history=initial_history,
        )
        job.status = "succeeded" if payload.get("ok") else "failed"
        job.result_json = json.dumps(payload, ensure_ascii=False)
        job.error_message = str(payload.get("gbrain_error") or "")
        job.finished_at = datetime.now(timezone.utc)
        add_agent_event(
            db,
            agent_run,
            event_type="result",
            title="工作区知识库录入完成" if payload.get("ok") else "工作区知识库录入未完成",
            detail=_workspace_ingest_summary_text(payload),
            status="completed" if payload.get("ok") else "failed",
            payload=_workspace_ingest_result_payload(payload),
        )
        finish_agent_run(
            db,
            agent_run,
            status="completed" if payload.get("ok") else "failed",
            result=_workspace_ingest_result_payload(payload),
            error_message=str(payload.get("gbrain_error") or ""),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            workspace = db.query(Workspace).filter(Workspace.id == job.workspace_id).first()
            request = _workspace_ingest_request_from_job(job)
            run_id = _workspace_ingest_run_id_from_job(job)
            history = [
                _workspace_ingest_status_event("queued", "任务已排队", job.created_at),
                _workspace_ingest_status_event("preprocessing", "开始预处理源文件", job.started_at),
                _workspace_ingest_status_event("failed", str(exc), job.finished_at),
            ]
            job.result_json = json.dumps(
                {
                    "request": request,
                    "run": _workspace_ingest_run_payload(
                        run_id=run_id,
                        status="failed",
                        workspace=workspace,
                        source_id=None,
                        source_path=str(request.get("path") or ""),
                        recursive=bool(request.get("recursive", True)),
                        started_at=job.started_at,
                        finished_at=job.finished_at,
                        error=str(exc),
                        status_history=history,
                    ),
                    "run_status": "failed",
                    "run_id": run_id,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
            agent_run = _get_or_create_workspace_ingest_agent_run(db, job, workspace)
            add_agent_event(
                db,
                agent_run,
                event_type="error",
                title="工作区知识库录入失败",
                detail=str(exc),
                status="failed",
                payload={"workspace_id": job.workspace_id},
            )
            finish_agent_run(db, agent_run, status="failed", error_message=str(exc))
            notify_user(
                db,
                job.requested_by,
                category="workspace",
                severity="warning",
                title="工作区知识库录入失败",
                content=f"{workspace.name if workspace else '项目'}：后台录入任务失败，原因：{exc}",
                action_status="pending",
                action_kind="open_workspace",
                action_payload={"workspace_id": job.workspace_id, "ingest_job_id": job.id},
            )
            db.commit()
    finally:
        db.close()


def _get_or_create_workspace_ingest_agent_run(
    db: Session,
    job: WorkspaceIngestJob,
    workspace: Workspace | None,
):
    run = _find_workspace_ingest_agent_run(db, job)
    if run:
        return run
    return create_agent_run(
        db,
        user_id=job.requested_by,
        workspace_id=job.workspace_id,
        source_type="workspace_ingest",
        source_id=job.id,
        title=f"录入工作区知识库：{workspace.name if workspace else job.workspace_id}",
        status=job.status,
    )


def _serialize_workspace_ingest_agent_run(db: Session, job: WorkspaceIngestJob) -> dict | None:
    run = _find_workspace_ingest_agent_run(db, job)
    return serialize_agent_run(db, run)


def _find_workspace_ingest_agent_run(db: Session, job: WorkspaceIngestJob):
    return (
        db.query(AgentRun)
        .filter(
            AgentRun.source_type == "workspace_ingest",
            AgentRun.source_id == str(job.id),
            AgentRun.user_id == job.requested_by,
        )
        .order_by(AgentRun.id.desc())
        .first()
    )


def _write_immediate_workspace_ingest_agent_run(
    db: Session,
    workspace: Workspace,
    user_id: int,
    payload: dict,
):
    run = create_agent_run(
        db,
        user_id=user_id,
        workspace_id=workspace.id,
        source_type="workspace_ingest",
        source_id=f"sync:{workspace.id}:{datetime.now(timezone.utc).timestamp()}",
        title=f"录入工作区知识库：{workspace.name}",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="started",
        title="开始处理工作区资料",
        detail=workspace.name,
        status="completed",
        payload={"workspace_id": workspace.id},
    )
    add_agent_event(
        db,
        run,
        event_type="result",
        title="工作区知识库录入完成" if payload.get("ok") else "工作区知识库录入未完成",
        detail=_workspace_ingest_summary_text(payload),
        status="completed" if payload.get("ok") else "failed",
        payload=_workspace_ingest_result_payload(payload),
    )
    return finish_agent_run(
        db,
        run,
        status="completed" if payload.get("ok") else "failed",
        result=_workspace_ingest_result_payload(payload),
        error_message=str(payload.get("gbrain_error") or ""),
    )


def _workspace_ingest_result_payload(payload: dict) -> dict:
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    return {
        "workspace_id": payload.get("workspace_id"),
        "indexed_files": payload.get("indexed_files", 0),
        "compiled_files": payload.get("compiled_files", 0),
        "pending_extractor_capability_files": payload.get("pending_extractor_capability_files", 0),
        "pending_transcription_files": payload.get("pending_transcription_files", 0),
        "failed_files": payload.get("failed_files", 0),
        "gbrain_source_id": payload.get("gbrain_source_id"),
        "gbrain_sync_status": payload.get("gbrain_sync_status"),
        "rag_status": payload.get("rag_status"),
        "run_id": payload.get("run_id"),
        "run_status": payload.get("run_status"),
        "run": manifest.get("run"),
        "manifest_summary": manifest.get("summary"),
    }


def _workspace_ingest_summary_text(payload: dict) -> str:
    run_status = payload.get("run_status") or payload.get("rag_status") or "unknown"
    return (
        f"状态 {run_status}，"
        f"已入库 {payload.get('indexed_files', 0)} 个，"
        f"已编译 {payload.get('compiled_files', 0)} 个，"
        f"待能力补齐 {payload.get('pending_extractor_capability_files', 0)} 个，"
        f"待转写 {payload.get('pending_transcription_files', 0)} 个，"
        f"失败 {payload.get('failed_files', 0)} 个"
    )


def _serialize_ingest_job(db: Session, job: WorkspaceIngestJob) -> WorkspaceKnowledgeIngestJobResponse:
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
        agent_run=_serialize_workspace_ingest_agent_run(db, job),
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
            rag_status="new",
            updated_at=now,
        )
        _record_file_signature(meta, source_path)
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
            meta.rag_status = "synced" if sync_ok else "sync_pending"
            source_path = (root / meta.relative_path).resolve()
            if source_path.exists() and source_path.is_file():
                _record_file_signature(meta, source_path)
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
        if meta.rag_status in {"indexed", "synced"}:
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
        title = "工作区知识库录入完成"
        severity = "success"
    else:
        title = "工作区知识库录入未完成"
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

    _ensure_workspace_admin(db, user, workspace_id)
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
    if req.is_hidden is not None:
        if workspace.workspace_kind == "user":
            raise HTTPException(status_code=400, detail="个人工作台不支持隐藏项目设置")
        workspace.is_hidden = req.is_hidden

    db.commit()
    db.refresh(workspace)
    return _workspace_response(db, workspace, user=user)


@router.get("/{workspace_id}/member-candidates", response_model=list[WorkspaceMemberCandidateResponse])
def list_workspace_member_candidates(
    workspace_id: int,
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    text = q.strip().lower()
    member_roles = {
        member.user_id: member.role
        for member in db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
    }
    users_query = db.query(User).filter(User.is_active == True)
    if text:
        needle = f"%{text}%"
        users_query = users_query.filter(
            or_(
                User.username.ilike(needle),
                User.nickname.ilike(needle),
                User.work_group.ilike(needle),
            )
        )
    users = users_query.order_by(User.username.asc()).limit(limit).all()
    return [
        WorkspaceMemberCandidateResponse(
            user_id=item.id,
            username=item.username,
            nickname=item.nickname,
            work_group=item.work_group,
            role=item.role,
            is_member=item.id in member_roles,
            member_role=member_roles.get(item.id),
        )
        for item in users
    ]


@router.get("/{workspace_id}/group-candidates", response_model=list[WorkspaceGroupCandidateResponse])
def list_workspace_group_candidates(
    workspace_id: int,
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    authorized = set(_workspace_access_groups(db, workspace_id))
    groups: dict[str, WorkspaceGroupCandidateResponse] = {}
    for (group_name,) in db.query(User.work_group).filter(User.work_group != "").distinct().all():
        normalized = _normalize_group_name(group_name)
        if normalized:
            groups[normalized] = WorkspaceGroupCandidateResponse(
                group_name=normalized,
                source="user",
                is_authorized=normalized in authorized,
            )
    for group_name in authorized:
        groups[group_name] = WorkspaceGroupCandidateResponse(
            group_name=group_name,
            source=groups.get(group_name).source if group_name in groups else "workspace",
            is_authorized=True,
        )
    text = q.strip().lower()
    items = [
        item
        for item in groups.values()
        if not text or text in item.group_name.lower()
    ]
    return sorted(items, key=lambda item: (not item.is_authorized, item.group_name.lower()))[:limit]


@router.post("/{workspace_id}/members", response_model=MemberResponse)
def upsert_workspace_member(
    workspace_id: int,
    req: UpsertWorkspaceMemberRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    role = _validate_workspace_member_role(req.role)
    target_user = _resolve_member_target_user(db, req)
    member = _workspace_membership(db, target_user.id, workspace_id)
    action = "workspace_member_update" if member else "workspace_member_invite"
    if member:
        member.role = role
    else:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=target_user.id, role=role)
        db.add(member)
    db.flush()
    _write_workspace_audit(
        db,
        user.id,
        action,
        _audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user.id, role=role),
    )
    notify_user(
        db,
        target_user.id,
        category="workspace",
        severity="info",
        title="工作区权限已更新",
        content=f"{workspace.name}：你已被设置为{'工作区管理员' if role == 'admin' else '成员'}。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:member:{target_user.id}:{role}",
    )
    db.commit()
    db.refresh(member)
    db.refresh(target_user)
    return _serialize_workspace_member(member, target_user)


@router.put("/{workspace_id}/members/{target_user_id}", response_model=MemberResponse)
def update_workspace_member_role(
    workspace_id: int,
    target_user_id: int,
    req: UpdateWorkspaceMemberRoleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    role = _validate_workspace_member_role(req.role)
    member = _workspace_membership(db, target_user_id, workspace_id)
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member.role == "admin" and role != "admin" and _local_workspace_admin_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一名工作区管理员")
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    member.role = role
    _write_workspace_audit(
        db,
        user.id,
        "workspace_member_role_update",
        _audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user_id, role=role),
    )
    notify_user(
        db,
        target_user.id,
        category="workspace",
        severity="info",
        title="工作区角色已更新",
        content=f"{workspace.name}：你的角色已变更为{'工作区管理员' if role == 'admin' else '成员'}。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:role:{target_user.id}:{role}",
    )
    db.commit()
    db.refresh(member)
    return _serialize_workspace_member(member, target_user)


@router.delete("/{workspace_id}/members/{target_user_id}")
def remove_workspace_member(
    workspace_id: int,
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    member = _workspace_membership(db, target_user_id, workspace_id)
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member.role == "admin" and _local_workspace_admin_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一名工作区管理员")
    db.delete(member)
    _write_workspace_audit(
        db,
        user.id,
        "workspace_member_remove",
        _audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user_id),
    )
    notify_user(
        db,
        target_user_id,
        category="workspace",
        severity="info",
        title="工作区访问权限已移除",
        content=f"{workspace.name}：你已不再是该工作区成员。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:remove:{target_user_id}",
    )
    db.commit()
    return {"ok": True}


@router.post("/{workspace_id}/groups", response_model=WorkspaceGroupResponse)
def upsert_workspace_group(
    workspace_id: int,
    req: UpsertWorkspaceGroupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    group_name = _normalize_group_name(req.group_name)
    if not group_name:
        raise HTTPException(status_code=400, detail="组别不能为空")
    existing = (
        db.query(WorkspaceGroupAccess)
        .filter(WorkspaceGroupAccess.workspace_id == workspace_id, WorkspaceGroupAccess.group_name == group_name)
        .first()
    )
    if not existing:
        db.add(WorkspaceGroupAccess(workspace_id=workspace_id, group_name=group_name))
        _write_workspace_audit(
            db,
            user.id,
            "workspace_group_access_add",
            _audit_detail(workspace_id, actor_id=user.id, group_name=group_name),
        )
        db.commit()
    return WorkspaceGroupResponse(group_name=group_name)


@router.delete("/{workspace_id}/groups/{group_name}")
def remove_workspace_group(
    workspace_id: int,
    group_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    _ensure_mutable_membership_workspace(workspace)
    _ensure_workspace_admin(db, user, workspace_id)

    normalized = _normalize_group_name(group_name)
    db.query(WorkspaceGroupAccess).filter(
        WorkspaceGroupAccess.workspace_id == workspace_id,
        WorkspaceGroupAccess.group_name == normalized,
    ).delete()
    _write_workspace_audit(
        db,
        user.id,
        "workspace_group_access_remove",
        _audit_detail(workspace_id, actor_id=user.id, group_name=normalized),
    )
    db.commit()
    return {"ok": True}


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

    if user.role == "admin" and workspace.workspace_kind != "user":
        return {"ok": True, "message": "系统管理员无需加入即可访问"}
    if workspace.workspace_kind == "project" and not workspace.is_hidden:
        return {"ok": True, "message": "开放项目无需加入即可访问"}
    if workspace.workspace_kind in {"project", "customer"} and _has_workspace_group_access(db, user, workspace_id):
        return {"ok": True, "message": "你的组别已获授权访问"}

    raise HTTPException(status_code=403, detail="受限工作区只能通过工作区管理员添加人员或组别授权")


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

    if not _is_workspace_admin(db, user, workspace_id):
        raise HTTPException(status_code=403, detail="仅项目管理员可删除")

    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id
    ).delete()
    db.query(WorkspaceGroupAccess).filter(
        WorkspaceGroupAccess.workspace_id == workspace_id
    ).delete()
    db.delete(workspace)
    db.commit()
    return {"ok": True}


def _ensure_member(db: Session, user_id: int, workspace_id: int):
    member = _workspace_membership(db, user_id, workspace_id)
    if member:
        return member
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.role == "admin":
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if workspace and workspace.workspace_kind != "user":
            return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="admin")
    if user:
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if workspace and workspace.workspace_kind == "project":
            if not workspace.is_hidden or _has_workspace_group_access(db, user, workspace_id):
                return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")
        if workspace and workspace.workspace_kind == "customer" and _has_workspace_group_access(db, user, workspace_id):
            return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")
    if not member:
        raise HTTPException(status_code=403, detail="你尚未加入该工作区")
    return member

