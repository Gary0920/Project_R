import json
import re
import base64
import binascii
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.utils import serialize_datetime_utc
from app.features.agents.events import serialize_agent_run
from app.features.knowledge.gbrain import (
    GBrainAdapter,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.knowledge.gbrain.customer_sources import CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME, compile_customer_workspace_sources
from app.features.knowledge.gbrain.graph import (
    apply_entity_merge_candidate_action,
    build_entity_merge_candidate_preview,
    build_entity_merge_candidates,
    build_source_graph,
)
from app.features.knowledge.gbrain.project_ingest import PROJECT_INGEST_MANIFEST_NAME, compile_project_workspace_sources
from app.features.notifications.service import (
    notify_user,
    notify_workspace_bulk_delete_risk,
    notify_workspace_joined,
)
from app.features.workspaces.audit import (
    audit_detail as _audit_detail,
    mark_workspace_rag_pending as _mark_workspace_rag_pending,
    raise_with_audit as _raise_with_audit,
    write_workspace_audit as _write_workspace_audit,
    write_workspace_file_agent_run as _write_workspace_file_agent_run,
)
from app.features.workspaces.gbrain_graph import (
    workspace_gbrain_graph_scope as _workspace_gbrain_graph_scope,
    workspace_profile_cards as _workspace_profile_cards,
)
from app.features.workspaces.knowledge_ingest_api import (
    compile_customer_workspace_sources_for_request as _compile_customer_workspace_sources_for_request_core,
    compile_project_workspace_sources_for_request as _compile_project_workspace_sources_for_request_core,
    execute_workspace_knowledge_ingest as _execute_workspace_knowledge_ingest_core,
    new_workspace_ingest_run_id as _new_workspace_ingest_run_id_core,
    normalize_workspace_ingest_request as _normalize_workspace_ingest_request_core,
    run_workspace_knowledge_ingest_job as _run_workspace_knowledge_ingest_job_core,
    serialize_ingest_job as _serialize_ingest_job_core,
)
from app.features.workspaces import management as workspace_management
from app.features.workspaces.schemas import (
    CopyWorkspacePathRequest,
    CreateMeetingFolderRequest,
    CreateWorkspaceFolderRequest,
    CreateWorkspaceRequest,
    DetectedSpeaker,
    MediaTranscribePreflightRequest,
    MediaTranscribePreflightResponse,
    MediaTranscribeResponse,
    MeetingFolderResponse,
    MeetingGenerateRequest,
    MeetingGenerateResponse,
    MeetingIngestRequest,
    MeetingIngestResponse,
    MeetingRetryRequest,
    MeetingRetryResponse,
    MeetingSpeakersResponse,
    MemberResponse,
    MoveWorkspacePathRequest,
    RenameWorkspacePathRequest,
    RestoreWorkspaceFileRequest,
    SaveAttachmentToWorkspaceRequest,
    SaveMeetingTranscriptRequest,
    SaveMeetingTranscriptResponse,
    SaveSpeakerMapRequest,
    SaveTermCorrectionsRequest,
    SpeakerMapItem,
    SpeakerMapResponse,
    TermCorrectionItem,
    TermCorrectionsResponse,
    UpdateWorkspaceMemberRoleRequest,
    UpdateWorkspaceRequest,
    UploadWorkspaceFileRequest,
    UpsertWorkspaceGroupRequest,
    UpsertWorkspaceMemberRequest,
    WorkspaceDetailResponse,
    WorkspaceEntityMergeActionRequest,
    WorkspaceEntityMergeCandidatesResponse,
    WorkspaceFileItemResponse,
    WorkspaceFileMutationResponse,
    WorkspaceFilesResponse,
    WorkspaceGroupCandidateResponse,
    WorkspaceGroupResponse,
    WorkspaceKnowledgeGraphResponse,
    WorkspaceKnowledgeIngestJobResponse,
    WorkspaceKnowledgeIngestRequest,
    WorkspaceKnowledgeRefreshResponse,
    WorkspaceMemberCandidateResponse,
    WorkspaceMultiUploadResponse,
    WorkspaceResponse,
    WorkspaceTrashClearResponse,
)
from app.features.workspaces.files.signature import (
    record_file_signature as _record_file_signature,
)
from app.features.workspaces.files.storage import (
    WorkspaceStorageConfig,
    candidate_storage_path,
    ensure_not_trash_path,
    ensure_storage_path,
    normalize_brand,
    normalize_workspace_kind,
    safe_username,
    slugify,
    workspace_file_root,
)
from app.features.workspaces.files.tree import (
    build_deleted_file_items as _build_deleted_file_items,
    build_file_tree as _build_file_tree,
    copy_descendant_file_metadata as _copy_descendant_file_metadata,
    create_copied_file_metadata as _create_copied_file_metadata,
    display_user_names as _display_user_names,
    sync_file_descendant_paths as _sync_file_descendant_paths,
    upsert_workspace_file as _upsert_workspace_file,
)
from app.features.workspaces.permissions import (
    can_open_workspace as _can_open_workspace,
    ensure_can_open_workspace as _ensure_can_open_workspace,
    ensure_member as _ensure_member,
    is_workspace_admin as _is_workspace_admin,
    normalize_group_name as _normalize_group_name,
    workspace_access_groups as _workspace_access_groups,
)
from app.features.workspaces.registry import (
    ensure_crm_workspace,
    ensure_default_workspace as ensure_default_workspace_core,
    find_existing_project_folder,
    register_existing_project_folder,
    sync_project_folders,
)
from app.features.workspaces.ingest.agent_runs import (
    create_queued_workspace_ingest_agent_run,
    write_immediate_workspace_ingest_agent_run as _write_immediate_workspace_ingest_agent_run,
)
from app.features.workspaces.ingest.jobs import (
    mark_workspace_ingest_job_queued,
    workspace_ingest_job_run_id as _workspace_ingest_job_run_id,
    workspace_ingest_request_label as _workspace_ingest_request_label,
)
from app.features.workspaces.ingest.notifications import (
    notify_workspace_ingest_queued,
)
from app.features.workspaces.meetings.io import (
    extract_text_from_docx as _extract_text_from_docx,
    notify_meeting_run_finished as _notify_meeting_run_finished,
    read_auxiliary_summaries as _read_auxiliary_summaries,
    workspace_file_uploader as _workspace_file_uploader,
)
from app.features.workspaces.meetings.markdown import (
    MEETING_SYSTEM_PROMPT as _MEETING_SYSTEM_PROMPT,
    build_actions_prompt as _build_actions_prompt,
    build_fallback_actions as _build_fallback_actions,
    build_fallback_minutes as _build_fallback_minutes,
    build_minutes_prompt as _build_minutes_prompt,
    build_transcript_markdown as _build_transcript_markdown,
    compose_gbrain_ready_meeting as _gbrain_ready_compose,
    escape_markdown_table_cell as _escape_pipe,
    failed_transcript_reason as _failed_transcript_reason,
    partial_transcript_notice as _partial_transcript_notice,
    transcript_metadata_value as _transcript_metadata_value,
    transcript_source_label as _transcript_source_label,
    transcript_status_value as _transcript_status_value,
)
from app.features.workspaces.meetings.utils import (
    SUPPORTED_MEDIA_EXTENSIONS as _SUPPORTED_MEDIA_EXTENSIONS,
    acquire_meeting_run_lock as _acquire_meeting_run_lock,
    build_speaker_map_markdown as _build_speaker_map_markdown,
    build_term_corrections_markdown as _build_term_corrections_markdown,
    duration_minutes as _duration_minutes,
    estimate_media_info as _estimate_media_info,
    next_version_number as _next_version_number,
    parse_speakers_from_transcript as _parse_speakers_from_transcript,
    read_file_safe as _read_file_safe,
    read_meeting_meta as _read_meeting_meta,
    release_meeting_run_lock as _release_meeting_run_lock,
    size_mb as _size_mb,
    speaker_timeline_rows as _speaker_timeline_rows,
    write_meeting_meta as _write_meeting_meta,
)
from app.features.workspaces.files.service import (
    DEFAULT_UNFILED_DIR,
    DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS,
    DEFAULT_WORKSPACE_DIRS,
    MAX_WORKSPACE_ADMIN_UPLOAD_BYTES,
    MAX_WORKSPACE_ADMIN_UPLOAD_MB,
    MAX_WORKSPACE_UPLOAD_BYTES,
    MAX_WORKSPACE_UPLOAD_MB,
    MEETING_SUBDIRS,
    is_template_root as _is_template_root,
    make_meeting_folder_name,
    meeting_folder_collision_free,
    meeting_parent_path,
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


MEETING_TYPES = [
    "项目统筹会",
    "客户沟通会",
    "技术交底",
    "现场协调",
    "内部复盘",
    "培训分享",
    "其他",
]


def _storage_config() -> WorkspaceStorageConfig:
    return WorkspaceStorageConfig(
        workspaces_root=WORKSPACES_ROOT,
        project_root_name=PROJECT_ROOT_NAME,
        customer_root_name=CUSTOMER_ROOT_NAME,
        project_brands=PROJECT_BRANDS,
        customer_brand=CUSTOMER_BRAND,
        crm_workspace_slug=CRM_WORKSPACE_SLUG,
        crm_raw_dir=CRM_RAW_DIR,
    )


def _slugify(name: str) -> str:
    return slugify(name)


def _safe_username(username: str) -> str:
    return safe_username(username)


def _normalize_brand(brand: str) -> str:
    return normalize_brand(brand, _storage_config())


def _normalize_workspace_kind(kind: str | None, brand: str | None = None) -> str:
    return normalize_workspace_kind(kind, brand, _storage_config())


def _ensure_not_trash_path(path: Path) -> None:
    ensure_not_trash_path(path)


def _ensure_storage_path(workspace: Workspace, *, create_user_scaffold: bool = False) -> str:
    return ensure_storage_path(workspace, _storage_config(), create_user_scaffold=create_user_scaffold)


def _workspace_file_root(workspace: Workspace) -> Path:
    return workspace_file_root(workspace, _storage_config())


def _candidate_storage_path(slug: str, brand: str, workspace_kind: str = "project") -> Path:
    return candidate_storage_path(slug, brand, workspace_kind, _storage_config())


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


def ensure_default_workspace(db: Session, user: User) -> Workspace:
    return ensure_default_workspace_core(db, user)


def _find_existing_project_folder(brand: str, slug: str, name: str | None = None) -> Path | None:
    return find_existing_project_folder(brand, slug, name, _storage_config())


def _register_existing_project_folder(
    db: Session,
    user: User,
    brand: str,
    project_dir: Path,
    *,
    add_member: bool = False,
) -> Workspace | None:
    return register_existing_project_folder(db, user, brand, project_dir, _storage_config(), add_member=add_member)


def _ensure_crm_workspace(db: Session, user: User, *, add_member: bool = False) -> Workspace:
    return ensure_crm_workspace(
        db,
        user,
        _storage_config(),
        crm_workspace_name=CRM_WORKSPACE_NAME,
        add_member=add_member,
    )


def _sync_project_folders(db: Session, user: User) -> None:
    sync_project_folders(db, user, _storage_config())


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


# ── Meeting endpoints ────────────────────────────────────────────────────

@router.post("/{workspace_id}/meetings/folder", response_model=MeetingFolderResponse)
def create_meeting_folder(
    workspace_id: int,
    req: CreateMeetingFolderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a single-meeting folder structure inside the workspace."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持创建会议文件夹")
    if req.meeting_type not in MEETING_TYPES:
        raise HTTPException(status_code=400, detail=f"会议类型不合法，可选值：{', '.join(MEETING_TYPES)}")

    root = _workspace_file_root(workspace)

    # Determine parent directory for meetings
    parent_rel_str = meeting_parent_path(workspace.workspace_kind)
    parent_rel = _safe_relative_path(parent_rel_str)
    _ensure_not_trash_path(parent_rel)
    parent = _resolve_workspace_child(root, parent_rel)
    parent.mkdir(parents=True, exist_ok=True)

    # Parse optional meeting time
    meeting_dt: datetime | None = None
    if req.meeting_time:
        try:
            meeting_dt = datetime.fromisoformat(req.meeting_time)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="会议时间格式不合法，请使用 ISO-8601")

    folder_name = make_meeting_folder_name(meeting_dt, req.topic)
    meeting_dir = meeting_folder_collision_free(parent, folder_name)
    meeting_dir.mkdir(parents=True, exist_ok=True)

    created_dirs: list[str] = []
    for sub in MEETING_SUBDIRS:
        sub_dir = meeting_dir / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(sub_dir.relative_to(root).as_posix())

    meeting_rel = meeting_dir.relative_to(root).as_posix()
    created_dirs.insert(0, meeting_rel)

    # Write meeting metadata
    _write_meeting_meta(
        meeting_dir,
        topic=req.topic,
        meeting_time=req.meeting_time,
        meeting_type=req.meeting_type,
    )

    _write_workspace_audit(
        db,
        user.id,
        "meeting_folder_create",
        _audit_detail(
            workspace_id,
            meeting_rel,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=meeting_rel,
            created_dirs=created_dirs,
            gbrain_ingest=False,
        ),
    )
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_folder_create",
        title="创建会议文件夹",
        path=meeting_rel,
        detail=f"会议：{req.topic}",
    )
    db.commit()
    return MeetingFolderResponse(
        ok=True,
        meeting_folder_path=meeting_rel,
        created_dirs=created_dirs,
        created_files=[],
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
    )


@router.post("/{workspace_id}/meetings/transcript", response_model=SaveMeetingTranscriptResponse)
def save_meeting_transcript(
    workspace_id: int,
    req: SaveMeetingTranscriptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save pasted meeting text as transcript-v1.md and transcript-latest.md inside an existing meeting folder."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持保存会议转录")

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(req.folder_path)
    _ensure_not_trash_path(folder_rel)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    if not folder_dir.exists() or not folder_dir.is_dir():
        raise HTTPException(status_code=400, detail="会议文件夹不存在")

    # Validate this is a proper meeting folder with all 5 subdirectories
    missing = [sub for sub in MEETING_SUBDIRS if not (folder_dir / sub).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail="请选择会议文件夹后保存转录文本")

    # Enforce parent path whitelist per workspace kind
    expected_parent = meeting_parent_path(workspace.workspace_kind)
    folder_posix = folder_rel.as_posix()
    if folder_posix != expected_parent and not folder_posix.startswith(expected_parent + "/"):
        raise HTTPException(status_code=400, detail=f"会议文件夹必须位于 {expected_parent}/ 下")

    transcript_dir = folder_dir / "02-转录文本"

    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="转录文本不能为空")

    # Build transcript markdown with formal template
    now_utc = datetime.now(timezone.utc)
    transcript_md = _build_transcript_markdown(
        content, now_utc,
        input_type=req.input_type,
        original_filename=req.original_filename,
    )

    # Write transcript-v1.md
    v1_path = _resolve_conflict_path(transcript_dir, "transcript-v1.md", "keep_both")
    if v1_path is None:
        raise HTTPException(status_code=500, detail="无法写入转录文件")
    v1_path.write_text(transcript_md, encoding="utf-8")
    v1_rel = v1_path.relative_to(root).as_posix()

    # Write / overwrite transcript-latest.md
    latest_path = transcript_dir / "transcript-latest.md"
    latest_path.write_text(transcript_md, encoding="utf-8")
    latest_rel = latest_path.relative_to(root).as_posix()

    # Record WorkspaceFile metadata for both files
    _upsert_workspace_file(
        db, workspace_id, user.id, v1_rel,
        "transcript-v1.md", "text/markdown", len(transcript_md.encode("utf-8")), v1_path,
    )
    _upsert_workspace_file(
        db, workspace_id, user.id, latest_rel,
        "transcript-latest.md", "text/markdown", len(transcript_md.encode("utf-8")), latest_path,
    )

    _write_workspace_audit(
        db,
        user.id,
        "meeting_transcript_save",
        _audit_detail(
            workspace_id,
            req.folder_path,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=req.folder_path,
            created_files=[v1_rel, latest_rel],
            gbrain_ingest=False,
        ),
    )
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_transcript_save",
        title="保存会议转录文本",
        path=req.folder_path,
        detail=f"转录：transcript-v1.md, transcript-latest.md",
    )
    db.commit()
    return SaveMeetingTranscriptResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        transcript_v1_path=v1_rel,
        transcript_latest_path=latest_rel,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
    )


@router.post("/{workspace_id}/meetings/transcript/file", response_model=SaveMeetingTranscriptResponse)
async def save_meeting_transcript_from_file(
    workspace_id: int,
    folder_path: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a TXT/MD/DOCX file as meeting transcript source."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持保存会议转录")

    filename = (file.filename or "untitled").strip()
    lower = filename.lower()

    # Determine input type and extract text
    content: str
    input_type: str
    if lower.endswith(".docx"):
        content_bytes = await file.read()
        content = _extract_text_from_docx(content_bytes, filename)
        input_type = "docx"
    elif lower.endswith(".txt"):
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")
        input_type = "txt"
    elif lower.endswith(".md") or lower.endswith(".markdown"):
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")
        input_type = "md"
    else:
        raise HTTPException(status_code=400, detail="仅支持 TXT / MD / DOCX 格式的转录文件")

    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空，无法生成转录")

    # Delegate to the same logic as the paste endpoint
    return save_meeting_transcript(
        workspace_id,
        SaveMeetingTranscriptRequest(
            folder_path=folder_path,
            content=content,
            input_type=input_type,
            original_filename=filename,
        ),
        user,
        db,
    )


# ── Helper ───────────────────────────────────────────────────────────────

@router.post("/{workspace_id}/meetings/generate", response_model=MeetingGenerateResponse)
def generate_meeting_minutes_and_actions(
    workspace_id: int,
    req: MeetingGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate meeting minutes and action items from transcript via LLM."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持生成会议纪要")
    if workspace.workspace_kind not in ("project", "customer"):
        raise HTTPException(status_code=400, detail="不支持的工作区类型")

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(req.folder_path)
    _ensure_not_trash_path(folder_rel)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    if not folder_dir.exists() or not folder_dir.is_dir():
        raise HTTPException(status_code=400, detail="会议文件夹不存在")

    # Validate meeting folder structure
    missing = [sub for sub in MEETING_SUBDIRS if not (folder_dir / sub).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail="请选择会议文件夹后生成纪要")

    # Enforce parent path whitelist
    expected_parent = meeting_parent_path(workspace.workspace_kind)
    folder_posix = folder_rel.as_posix()
    if folder_posix != expected_parent and not folder_posix.startswith(expected_parent + "/"):
        raise HTTPException(status_code=400, detail=f"会议文件夹必须位于 {expected_parent}/ 下")

    # Read transcript
    transcript_dir = folder_dir / "02-转录文本"
    transcript_path = transcript_dir / "transcript-latest.md"
    if not transcript_path.exists():
        raise HTTPException(status_code=400, detail="转录文件（transcript-latest.md）不存在，请先保存转录")
    transcript_rel = transcript_path.relative_to(root).as_posix()
    transcript_uploaded_by = _workspace_file_uploader(db, workspace_id, transcript_rel)
    transcript_text = transcript_path.read_text(encoding="utf-8")
    if not transcript_text.strip():
        raise HTTPException(status_code=400, detail="转录文件为空")
    failed_reason = _failed_transcript_reason(transcript_text)
    if failed_reason:
        raise HTTPException(status_code=400, detail=f"转录未成功，不能生成会议纪要。原因：{failed_reason}")
    transcription_status = _transcript_status_value(transcript_text)
    if transcription_status == "partial" and not req.allow_partial:
        raise HTTPException(status_code=400, detail="转录状态为 partial，请确认允许基于成功片段生成纪要后再继续")
    lock_path = _acquire_meeting_run_lock(root, folder_dir, operation="generate_minutes", user_id=user.id)

    # Read optional speaker map and term corrections
    speaker_map_path = folder_dir / "02-转录文本" / "speaker-map-latest.md"
    speaker_map_text = _read_file_safe(speaker_map_path)
    term_corrections_path = folder_dir / "02-转录文本" / "term-corrections-latest.md"
    term_corrections_text = _read_file_safe(term_corrections_path)
    original_filename = _transcript_metadata_value(transcript_text, "原始文件名")
    auxiliary_summaries_text = _read_auxiliary_summaries(folder_dir, source_filename=original_filename)

    # Determine version numbers
    minutes_dir = folder_dir / "04-会议纪要"
    actions_dir = folder_dir / "05-行动项"
    minutes_dir.mkdir(parents=True, exist_ok=True)
    actions_dir.mkdir(parents=True, exist_ok=True)

    minutes_ver = _next_version_number(minutes_dir, "minutes")
    actions_ver = _next_version_number(actions_dir, "actions")

    # If regenerate is False and already exists, don't overwrite
    if not req.regenerate:
        if (minutes_dir / "minutes-latest.md").exists() or (actions_dir / "actions-latest.md").exists():
            raise HTTPException(
                status_code=409,
                detail="已存在纪要与行动项。如需重新生成，请设置 regenerate=True 或先删除已有文件",
            )

    try:
        # LLM generation
        from app.shared.llm.client import get_llm_client

        minutes_md: str = ""
        actions_md: str = ""
        token_input: int = 0
        token_output: int = 0
        model_used: str = "template-fallback"

        meeting_type = _read_meeting_meta(folder_dir).get("meeting_type", "")

        _minutes_prompt = _build_minutes_prompt(
            transcript_text,
            speaker_map_text,
            term_corrections_text,
            auxiliary_summaries_text,
            meeting_type=meeting_type,
        )
        _actions_prompt = _build_actions_prompt(
            transcript_text,
            speaker_map_text,
            term_corrections_text,
            auxiliary_summaries_text,
        )

        client = get_llm_client("deepseek-flash")
        model_used = "deepseek-flash"

        # Generate minutes
        minutes_response = client.complete(
            [{"role": "user", "content": _minutes_prompt}],
            system_prompt=_MEETING_SYSTEM_PROMPT,
            temperature=0.3,
        )
        minutes_md = minutes_response.text.strip() if minutes_response.text else ""
        if minutes_response.usage:
            token_input += minutes_response.usage.get("input_tokens", 0)
            token_output += minutes_response.usage.get("output_tokens", 0)

        # Generate actions
        actions_response = client.complete(
            [{"role": "user", "content": _actions_prompt}],
            system_prompt=_MEETING_SYSTEM_PROMPT,
            temperature=0.3,
        )
        actions_md = actions_response.text.strip() if actions_response.text else ""
        if actions_response.usage:
            token_input += actions_response.usage.get("input_tokens", 0)
            token_output += actions_response.usage.get("output_tokens", 0)

    except HTTPException:
        raise
    except Exception as exc:
        # If LLM fails, fall back to template-based generation
        model_used = "template-fallback"
        from app.shared.time.utils import serialize_datetime_utc
        now_ts = serialize_datetime_utc(datetime.now(timezone.utc))
        minutes_md = _build_fallback_minutes(transcript_text, now_ts, str(exc))
        actions_md = _build_fallback_actions(now_ts)

    finally:
        _release_meeting_run_lock(lock_path)

    if transcription_status == "partial":
        partial_block = (
            "\n\n> 转录状态：partial。以下纪要和行动项仅基于已成功转录片段生成。"
            "缺失片段可能导致结论不完整，请人工复核。\n"
        )
        if "转录状态：partial" not in minutes_md:
            minutes_md = minutes_md.rstrip() + partial_block

    # Save minutes
    minutes_v_path = minutes_dir / f"minutes-v{minutes_ver}.md"
    minutes_v_path.write_text(minutes_md, encoding="utf-8")
    minutes_v_rel = minutes_v_path.relative_to(root).as_posix()

    minutes_latest_path = minutes_dir / "minutes-latest.md"
    minutes_latest_path.write_text(minutes_md, encoding="utf-8")
    minutes_latest_rel = minutes_latest_path.relative_to(root).as_posix()

    # Save actions
    actions_v_path = actions_dir / f"actions-v{actions_ver}.md"
    actions_v_path.write_text(actions_md, encoding="utf-8")
    actions_v_rel = actions_v_path.relative_to(root).as_posix()

    actions_latest_path = actions_dir / "actions-latest.md"
    actions_latest_path.write_text(actions_md, encoding="utf-8")
    actions_latest_rel = actions_latest_path.relative_to(root).as_posix()

    # Record WorkspaceFile metadata
    _upsert_workspace_file(
        db, workspace_id, user.id, minutes_v_rel,
        f"minutes-v{minutes_ver}.md", "text/markdown", len(minutes_md.encode("utf-8")), minutes_v_path,
    ).rag_status = "partial" if transcription_status == "partial" else "not_ingested"
    # Mark previously synced files as needs_reingest
    for prefix_dir, prefix_name in [(minutes_dir, "minutes"), (actions_dir, "actions")]:
        if not prefix_dir.exists():
            continue
        for child in prefix_dir.iterdir():
            if child.is_file() and child.name.startswith(prefix_name) and child != minutes_v_path and child != minutes_latest_path:
                cr = child.relative_to(root).as_posix()
                cmeta = db.query(WorkspaceFile).filter(
                    WorkspaceFile.workspace_id == workspace_id,
                    WorkspaceFile.relative_path == cr).first()
                if cmeta and cmeta.rag_status in ("synced", "gbrain_ready", "sync_pending"):
                    cmeta.rag_status = "needs_reingest"

    _upsert_workspace_file(
        db, workspace_id, user.id, minutes_latest_rel,
        "minutes-latest.md", "text/markdown", len(minutes_md.encode("utf-8")), minutes_latest_path,
    ).rag_status = "partial" if transcription_status == "partial" else "not_ingested"
    _upsert_workspace_file(
        db, workspace_id, user.id, actions_v_rel,
        f"actions-v{actions_ver}.md", "text/markdown", len(actions_md.encode("utf-8")), actions_v_path,
    ).rag_status = "partial" if transcription_status == "partial" else "not_ingested"
    _upsert_workspace_file(
        db, workspace_id, user.id, actions_latest_rel,
        "actions-latest.md", "text/markdown", len(actions_md.encode("utf-8")), actions_latest_path,
    ).rag_status = "partial" if transcription_status == "partial" else "not_ingested"

    total_tokens = token_input + token_output

    _write_workspace_audit(
        db,
        user.id,
        "meeting_minutes_generate",
        _audit_detail(
            workspace_id,
            req.folder_path,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=req.folder_path,
            input_files=[{"path": transcript_rel, "uploaded_by": transcript_uploaded_by}],
            run_by=user.id,
            created_files=[minutes_v_rel, minutes_latest_rel, actions_v_rel, actions_latest_rel],
            model=model_used,
            token_cost=total_tokens,
            transcription_status=transcription_status,
            gbrain_ingest=False,
        ),
    )
    agent_run = _write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_minutes_generate",
        title="生成会议纪要与行动项",
        path=req.folder_path,
        detail=f"纪要：minutes-v{minutes_ver}.md, actions-v{actions_ver}.md",
        status="completed" if transcription_status != "partial" else "completed",
        result={"transcription_status": transcription_status},
    )
    _notify_meeting_run_finished(
        db,
        workspace=workspace,
        actor_user_id=user.id,
        folder_path=req.folder_path,
        title="会议纪要生成完成" if transcription_status != "partial" else "会议纪要基于部分转录生成",
        status="completed" if transcription_status != "partial" else "partial",
        detail=f"{req.folder_path} 已生成 minutes-v{minutes_ver}.md / actions-v{actions_ver}.md",
    )
    db.commit()
    return MeetingGenerateResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        minutes_v_path=minutes_v_rel,
        minutes_latest_path=minutes_latest_rel,
        actions_v_path=actions_v_rel,
        actions_latest_path=actions_latest_rel,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
        model_used=model_used,
        token_cost=total_tokens,
    )


# ── Step 4: Speaker map & term corrections ───────────────────────────────

@router.get("/{workspace_id}/meetings/speakers", response_model=MeetingSpeakersResponse)
def get_meeting_speakers(
    workspace_id: int,
    folder_path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse detected speakers from the transcript."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持此操作")
    _validate_meeting_folder(workspace, folder_path)

    root = _workspace_file_root(workspace)
    folder_dir = _resolve_workspace_child(root, _safe_relative_path(folder_path))

    transcript_path = folder_dir / "02-转录文本" / "transcript-latest.md"
    if not transcript_path.exists():
        raise HTTPException(status_code=400, detail="转录文件不存在")

    text = transcript_path.read_text(encoding="utf-8")
    speakers = _parse_speakers_from_transcript(text)
    return MeetingSpeakersResponse(ok=True, detected_speakers=speakers)


@router.post("/{workspace_id}/meetings/speaker-map", response_model=SpeakerMapResponse)
def save_meeting_speaker_map(
    workspace_id: int,
    req: SaveSpeakerMapRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save speaker mapping as speaker-map-latest.md."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    _validate_meeting_folder(workspace, req.folder_path)

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(req.folder_path)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    author_name = user.nickname or user.username

    # Version numbering
    ver = _next_version_number(transcript_dir, "speaker-map")

    transcript_text = _read_file_safe(folder_dir / "02-转录文本" / "transcript-latest.md")
    timeline_rows = _speaker_timeline_rows(transcript_text)
    md = _build_speaker_map_markdown(req.speakers, author_name, now_ts, timeline_rows)

    v_path = transcript_dir / f"speaker-map-v{ver}.md"
    v_path.write_text(md, encoding="utf-8")
    latest_path = transcript_dir / "speaker-map-latest.md"
    latest_path.write_text(md, encoding="utf-8")

    v_rel = v_path.relative_to(root).as_posix()
    latest_rel = latest_path.relative_to(root).as_posix()

    _upsert_workspace_file(db, workspace_id, user.id, v_rel,
                           f"speaker-map-v{ver}.md", "text/markdown", len(md.encode("utf-8")), v_path)
    _upsert_workspace_file(db, workspace_id, user.id, latest_rel,
                           "speaker-map-latest.md", "text/markdown", len(md.encode("utf-8")), latest_path)

    _write_workspace_audit(db, user.id, "meeting_speaker_map_save",
                           _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                         gbrain_ingest=False))
    db.commit()
    return SpeakerMapResponse(ok=True, meeting_folder_path=req.folder_path,
                               speaker_map_path=latest_rel, gbrain_ingest=False)


@router.post("/{workspace_id}/meetings/term-corrections", response_model=TermCorrectionsResponse)
def save_meeting_term_corrections(
    workspace_id: int,
    req: SaveTermCorrectionsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save term corrections as term-corrections-latest.md."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    _validate_meeting_folder(workspace, req.folder_path)

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(req.folder_path)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ver = _next_version_number(transcript_dir, "term-corrections")

    md = _build_term_corrections_markdown(req.corrections, now_ts)

    v_path = transcript_dir / f"term-corrections-v{ver}.md"
    v_path.write_text(md, encoding="utf-8")
    latest_path = transcript_dir / "term-corrections-latest.md"
    latest_path.write_text(md, encoding="utf-8")

    v_rel = v_path.relative_to(root).as_posix()
    latest_rel = latest_path.relative_to(root).as_posix()

    _upsert_workspace_file(db, workspace_id, user.id, v_rel,
                           f"term-corrections-v{ver}.md", "text/markdown", len(md.encode("utf-8")), v_path)
    _upsert_workspace_file(db, workspace_id, user.id, latest_rel,
                           "term-corrections-latest.md", "text/markdown", len(md.encode("utf-8")), latest_path)

    _write_workspace_audit(db, user.id, "meeting_term_corrections_save",
                           _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                         gbrain_ingest=False))
    db.commit()
    return TermCorrectionsResponse(ok=True, meeting_folder_path=req.folder_path,
                                    corrections_path=latest_rel, gbrain_ingest=False)


def _validate_meeting_folder(workspace: "Workspace", folder_path: str) -> None:
    """Shared validation: check that folder_path is a valid meeting folder."""
    from app.features.workspaces.files.service import MEETING_SUBDIRS, meeting_parent_path
    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(folder_path)
    _ensure_not_trash_path(folder_rel)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    if not folder_dir.exists() or not folder_dir.is_dir():
        raise HTTPException(status_code=400, detail="会议文件夹不存在")
    missing = [sub for sub in MEETING_SUBDIRS if not (folder_dir / sub).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail="请选择会议文件夹")
    expected_parent = meeting_parent_path(workspace.workspace_kind)
    folder_posix = folder_rel.as_posix()
    if folder_posix != expected_parent and not folder_posix.startswith(expected_parent + "/"):
        raise HTTPException(status_code=400, detail=f"会议文件夹必须位于 {expected_parent}/ 下")


# ── Step 5: Media transcription ───────────────────────────────────────────


@router.post("/{workspace_id}/meetings/transcribe/media", response_model=MediaTranscribeResponse)
async def transcribe_meeting_media(
    workspace_id: int,
    folder_path: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload and transcribe meeting audio/video via MiMo V2.5."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持音视频转录")
    _validate_meeting_folder(workspace, folder_path)

    filename = (file.filename or "recording").strip()
    lower = filename.lower()
    ext = Path(filename).suffix.lower()
    if ext not in _SUPPORTED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持音视频格式：{', '.join(sorted(_SUPPORTED_MEDIA_EXTENSIONS))}")

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(folder_path)
    folder_dir = _resolve_workspace_child(root, folder_rel)
    lock_path = _acquire_meeting_run_lock(root, folder_dir, operation="media_transcribe", user_id=user.id)

    try:
        # Save raw media to 01-原始资料/
        raw_dir = folder_dir / "01-原始资料"
        raw_dir.mkdir(parents=True, exist_ok=True)
        media_path = _resolve_conflict_path(raw_dir, _safe_name(filename), "keep_both")
        if media_path is None:
            raise HTTPException(status_code=500, detail="无法保存媒体文件")

        content_bytes = await file.read()
        media_path.write_bytes(content_bytes)
        media_rel = media_path.relative_to(root).as_posix()

        # Warn for long videos > 30 min
        duration_min = _duration_minutes(media_path)
        if duration_min is not None and duration_min > 30:
            pass  # caller/frontend handles confirmation; this is informational

        # Transcribe via app.features.preprocessing.media_transcription
        from app.features.preprocessing.media_transcription import transcribe_media_to_markdown, load_media_transcription_options
        from app.shared.llm.client import get_llm_client

        token_cost = 0
        options = load_media_transcription_options()
        transcription_client = get_llm_client(options.model_profile)
        result = transcribe_media_to_markdown(media_path, options=options, llm_client=transcription_client)
        transcript_text = result.transcript_text
        transcription_status = result.transcription_status
        segment_count = result.segment_count
        warnings_list = list(result.warnings) if result.warnings else []
        if result.token_usage:
            token_cost += result.token_usage.get("input_tokens", 0) + result.token_usage.get("output_tokens", 0)
        if result.refinement_token_usage:
            token_cost += result.refinement_token_usage.get("input_tokens", 0) + result.refinement_token_usage.get("output_tokens", 0)
    except Exception as exc:
        transcription_status = "failed"
        segment_count = 0
        warnings_list = [str(exc)]
        token_cost = 0
        media_rel = media_path.relative_to(root).as_posix() if "media_path" in locals() and media_path.exists() else ""
        content_bytes = content_bytes if "content_bytes" in locals() else b""
        transcript_text = (
            f"# 会议转录文本 - 转录失败\n\n"
            f"**转录状态**：failed\n\n"
            f"**错误**：{exc}\n\n"
            f"请检查媒体文件是否有效，或联系管理员。\n\n"
            f"> **注意**：当前版本仅支持整体重试转录（通过「重试转录」按钮），不支持单片段重跑。\n"
        )
    finally:
        _release_meeting_run_lock(lock_path)

    # Save transcript
    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    # Use the formal template wrapper
    now_utc = datetime.now(timezone.utc)
    if transcription_status == "failed":
        final_md = transcript_text
    else:
        final_md = _build_transcript_markdown(
            transcript_text,
            now_utc,
            input_type=ext.lstrip("."),
            original_filename=filename,
            transcription_status=transcription_status,
            warnings=warnings_list,
        )

    v1_path = _resolve_conflict_path(transcript_dir, "transcript-v1.md", "keep_both")
    if v1_path is None:
        raise HTTPException(status_code=500, detail="无法写入转录文件")
    v1_path.write_text(final_md, encoding="utf-8")
    v1_rel = v1_path.relative_to(root).as_posix()

    latest_path = transcript_dir / "transcript-latest.md"
    latest_path.write_text(final_md, encoding="utf-8")
    latest_rel = latest_path.relative_to(root).as_posix()

    # Record WorkspaceFile metadata
    media_meta = _upsert_workspace_file(db, workspace_id, user.id, media_rel,
                           filename, file.content_type or "application/octet-stream", len(content_bytes), media_path)
    media_meta.rag_status = "pending_transcription" if transcription_status == "failed" else "not_ingested"
    v1_meta = _upsert_workspace_file(db, workspace_id, user.id, v1_rel,
                           "transcript-v1.md", "text/markdown", len(final_md.encode("utf-8")), v1_path)
    latest_meta = _upsert_workspace_file(db, workspace_id, user.id, latest_rel,
                           "transcript-latest.md", "text/markdown", len(final_md.encode("utf-8")), latest_path)
    transcript_rag_status = "failed" if transcription_status == "failed" else "partial" if transcription_status == "partial" else "not_ingested"
    v1_meta.rag_status = transcript_rag_status
    latest_meta.rag_status = transcript_rag_status

    _write_workspace_audit(db, user.id, "meeting_media_transcribe",
                           _audit_detail(workspace_id, folder_path, actor_id=user.id,
                                         media_file=media_rel,
                                         transcript=v1_rel,
                                         status=transcription_status,
                                         segments=segment_count,
                                         gbrain_ingest=False),
                           success=transcription_status != "failed")
    agent_run = _write_workspace_file_agent_run(
        db, user_id=user.id, workspace=workspace,
        source_type="meeting_media_transcribe",
        title="会议音视频转录",
        path=folder_path,
        detail=f"转录：{filename}（{segment_count}段，{transcription_status}）",
        status="failed" if transcription_status == "failed" else "completed",
    )
    _notify_meeting_run_finished(
        db,
        workspace=workspace,
        actor_user_id=user.id,
        folder_path=folder_path,
        title="会议音视频转录完成" if transcription_status != "failed" else "会议音视频转录失败",
        status="partial" if transcription_status == "partial" else "failed" if transcription_status == "failed" else "completed",
        detail=f"{filename}：{transcription_status}，生成 {latest_rel}",
    )
    db.commit()
    return MediaTranscribeResponse(
        ok=True,
        meeting_folder_path=folder_path,
        media_path=media_rel,
        transcript_v1_path=v1_rel,
        transcript_latest_path=latest_rel,
        transcription_status=transcription_status,
        segment_count=segment_count,
        warnings=warnings_list,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
        token_cost=token_cost,
    )


# ── Step 5b: Media preflight ───────────────────────────────────────────────

@router.post("/{workspace_id}/meetings/transcribe/media/preflight", response_model=MediaTranscribePreflightResponse)
def preflight_meeting_media_transcribe(
    workspace_id: int,
    req: MediaTranscribePreflightRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Estimate media cost/duration before transcription. Does not upload or transcribe."""
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持音视频转录")
    _validate_meeting_folder(workspace, req.folder_path)

    ext = Path(req.filename).suffix.lower()
    if ext not in _SUPPORTED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持音视频格式：{', '.join(sorted(_SUPPORTED_MEDIA_EXTENSIONS))}")

    info = _estimate_media_info(req.size_bytes, req.filename)
    return MediaTranscribePreflightResponse(
        ok=True,
        filename=req.filename,
        size_mb=info["size_mb"],
        estimated_duration_minutes=info["estimated_duration_minutes"],
        is_long_media=info["is_long_media"],
        estimated_segments=info["estimated_segments"],
        estimated_cost_note=info["estimated_cost_note"],
        warnings=info["warnings"],
        model="MiMo V2.5",
    )


# ── Step 5c: Meeting retry ─────────────────────────────────────────────────

@router.post("/{workspace_id}/meetings/retry", response_model=MeetingRetryResponse)
def retry_meeting_operation(
    workspace_id: int,
    req: MeetingRetryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retry a failed meeting operation (transcription or minutes generation).

    Re-runs the same operation after verifying that:
    - The previous run failed
    - No active lock exists
    - The meeting folder still has the necessary input files
    """
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持此操作")
    if workspace.workspace_kind not in ("project", "customer"):
        raise HTTPException(status_code=400, detail="不支持的工作区类型")

    root = _workspace_file_root(workspace)
    folder_rel = _safe_relative_path(req.folder_path)
    _ensure_not_trash_path(folder_rel)
    folder_dir = _resolve_workspace_child(root, folder_rel)

    # Validate this is a meeting folder
    missing = [sub for sub in MEETING_SUBDIRS if not (folder_dir / sub).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail="请选择完整的会议文件夹")

    expected_parent = meeting_parent_path(workspace.workspace_kind)
    folder_posix = folder_rel.as_posix()
    if folder_posix != expected_parent and not folder_posix.startswith(expected_parent + "/"):
        raise HTTPException(status_code=400, detail=f"会议文件夹必须位于 {expected_parent}/ 下")

    lock_path = _meeting_run_lock_path(root, folder_dir)
    if lock_path.exists():
        raise HTTPException(status_code=409, detail="当前会议已有处理中任务，请等待完成后再操作")

    if req.operation == "transcribe":
        # Check for failed transcript
        transcript_latest = folder_dir / "02-转录文本" / "transcript-latest.md"
        if transcript_latest.exists():
            text = transcript_latest.read_text(encoding="utf-8")
            if not _failed_transcript_reason(text):
                raise HTTPException(status_code=400, detail="转录已成功完成，无需重试。如需重新转录请先删除旧转录文件。")

        # Find raw media in 01-原始资料 to re-transcribe
        raw_dir = folder_dir / "01-原始资料"
        if not raw_dir.exists() or not raw_dir.is_dir():
            raise HTTPException(status_code=400, detail="原始资料目录不存在，无法重试转录。请重新上传音视频文件。")

        media_files = [
            child for child in sorted(raw_dir.iterdir())
            if child.is_file() and child.suffix.lower() in _SUPPORTED_MEDIA_EXTENSIONS
        ]
        if not media_files:
            raise HTTPException(status_code=400, detail="原始资料中没有音视频文件，无法重试转录。请重新上传。")

        # Use the first (or most recent) media file
        media_path = max(media_files, key=lambda p: p.stat().st_mtime)
        _acquire_meeting_run_lock(root, folder_dir, operation="media_transcribe_retry", user_id=user.id)

        try:
            from app.features.preprocessing.media_transcription import transcribe_media_to_markdown, load_media_transcription_options
            from app.shared.llm.client import get_llm_client

            token_cost = 0
            options = load_media_transcription_options()
            transcription_client = get_llm_client(options.model_profile)
            result = transcribe_media_to_markdown(media_path, options=options, llm_client=transcription_client)
            transcript_text = result.transcript_text
            transcription_status = result.transcription_status
            segment_count = result.segment_count
            warnings_list = list(result.warnings) if result.warnings else []
            if result.token_usage:
                token_cost += result.token_usage.get("input_tokens", 0) + result.token_usage.get("output_tokens", 0)
            if result.refinement_token_usage:
                token_cost += result.refinement_token_usage.get("input_tokens", 0) + result.refinement_token_usage.get("output_tokens", 0)
        except Exception as exc:
            transcription_status = "failed"
            segment_count = 0
            warnings_list = [str(exc)]
            token_cost = 0
            transcript_text = (
                f"# 会议转录文本 - 转录失败\n\n"
                f"**转录状态**：failed\n\n"
                f"**错误**：{exc}\n\n"
                f"请检查媒体文件是否有效，或联系管理员。\n\n"
                f"> **注意**：当前版本仅支持整体重试转录（通过「重试转录」按钮），不支持单片段重跑。\n"
            )
        finally:
            _release_meeting_run_lock(lock_path)

        # Save transcript (overwrite latest, keep history)
        transcript_dir = folder_dir / "02-转录文本"
        transcript_dir.mkdir(parents=True, exist_ok=True)

        now_utc = datetime.now(timezone.utc)
        if transcription_status != "failed":
            final_md = _build_transcript_markdown(
                transcript_text, now_utc,
                input_type=media_path.suffix.lstrip("."),
                original_filename=media_path.name,
                transcription_status=transcription_status,
                warnings=warnings_list,
            )
        else:
            final_md = transcript_text

        v_ver = _next_version_number(transcript_dir, "transcript")
        v_path = transcript_dir / f"transcript-v{v_ver}.md"
        v_path.write_text(final_md, encoding="utf-8")
        latest_path = transcript_dir / "transcript-latest.md"
        latest_path.write_text(final_md, encoding="utf-8")

        v_rel = v_path.relative_to(root).as_posix()
        latest_rel = latest_path.relative_to(root).as_posix()

        _upsert_workspace_file(db, workspace_id, user.id, v_rel,
                               f"transcript-v{v_ver}.md", "text/markdown", len(final_md.encode("utf-8")), v_path)
        _upsert_workspace_file(db, workspace_id, user.id, latest_rel,
                               "transcript-latest.md", "text/markdown", len(final_md.encode("utf-8")), latest_path)

        _write_workspace_audit(db, user.id, "meeting_media_transcribe_retry",
                               _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                             media_file=str(media_path), transcript=latest_rel,
                                             status=transcription_status, segments=segment_count))
        agent_run = _write_workspace_file_agent_run(
            db, user_id=user.id, workspace=workspace,
            source_type="meeting_media_transcribe_retry",
            title="重试会议音视频转录",
            path=req.folder_path,
            detail=f"转录重试：{media_path.name}（{segment_count}段，{transcription_status}）",
            status="failed" if transcription_status == "failed" else "completed",
        )
        _notify_meeting_run_finished(
            db, workspace=workspace, actor_user_id=user.id,
            folder_path=req.folder_path,
            title="会议音视频转录重试完成" if transcription_status != "failed" else "会议音视频转录重试失败",
            status="partial" if transcription_status == "partial" else "failed" if transcription_status == "failed" else "completed",
            detail=f"{media_path.name}：{transcription_status}，生成 {latest_rel}",
        )
        db.commit()
        return MeetingRetryResponse(
            ok=True,
            meeting_folder_path=req.folder_path,
            operation=req.operation,
            status=transcription_status,
            message=f"转录{'部分完成' if transcription_status == 'partial' else '完成' if transcription_status != 'failed' else '失败'}（{segment_count}段）",
            agent_run=serialize_agent_run(db, agent_run),
        )

    elif req.operation == "generate_minutes":
        # Check for failed or partial minutes
        minutes_latest = folder_dir / "04-会议纪要" / "minutes-latest.md"
        transcript_latest = folder_dir / "02-转录文本" / "transcript-latest.md"
        if not transcript_latest.exists():
            raise HTTPException(status_code=400, detail="转录文件不存在，无法重试生成纪要")

        transcript_text = transcript_latest.read_text(encoding="utf-8")
        failed_reason = _failed_transcript_reason(transcript_text)
        if failed_reason:
            raise HTTPException(status_code=400, detail=f"转录未成功，需要先重试转录。原因：{failed_reason}")

        # Delegate to generate endpoint with regenerate=True (in-process via function call)
        from app.shared.llm.client import get_llm_client

        speaker_map_text = _read_file_safe(folder_dir / "02-转录文本" / "speaker-map-latest.md")
        term_corrections_text = _read_file_safe(folder_dir / "02-转录文本" / "term-corrections-latest.md")
        original_filename = _transcript_metadata_value(transcript_text, "原始文件名")
        auxiliary_summaries_text = _read_auxiliary_summaries(folder_dir, source_filename=original_filename)
        transcription_status = _transcript_status_value(transcript_text)

        lock_path = _acquire_meeting_run_lock(root, folder_dir, operation="generate_minutes_retry", user_id=user.id)

        try:
            minutes_ver = _next_version_number(folder_dir / "04-会议纪要", "minutes")
            actions_ver = _next_version_number(folder_dir / "05-行动项", "actions")
            (folder_dir / "04-会议纪要").mkdir(parents=True, exist_ok=True)
            (folder_dir / "05-行动项").mkdir(parents=True, exist_ok=True)

            try:
                client = get_llm_client("deepseek-flash")
                model_used = "deepseek-flash"
                retry_meeting_type = _read_meeting_meta(folder_dir).get("meeting_type", "")
                minutes_response = client.complete(
                    [{"role": "user", "content": _build_minutes_prompt(transcript_text, speaker_map_text, term_corrections_text, auxiliary_summaries_text, meeting_type=retry_meeting_type)}],
                    system_prompt=_MEETING_SYSTEM_PROMPT,
                    temperature=0.3,
                )
                minutes_md = minutes_response.text.strip() if minutes_response.text else ""
                actions_response = client.complete(
                    [{"role": "user", "content": _build_actions_prompt(transcript_text, speaker_map_text, term_corrections_text, auxiliary_summaries_text)}],
                    system_prompt=_MEETING_SYSTEM_PROMPT,
                    temperature=0.3,
                )
                actions_md = actions_response.text.strip() if actions_response.text else ""
                token_cost = (
                    (minutes_response.usage or {}).get("input_tokens", 0) + (minutes_response.usage or {}).get("output_tokens", 0)
                    + (actions_response.usage or {}).get("input_tokens", 0) + (actions_response.usage or {}).get("output_tokens", 0)
                )
            except Exception as exc:
                model_used = "template-fallback"
                now_ts = serialize_datetime_utc(datetime.now(timezone.utc))
                minutes_md = _build_fallback_minutes(transcript_text, now_ts, str(exc))
                actions_md = _build_fallback_actions(now_ts)
                token_cost = 0
        finally:
            _release_meeting_run_lock(lock_path)

        if transcription_status == "partial":
            partial_block = "\n\n> 转录状态：partial。以下纪要和行动项仅基于已成功转录片段生成。缺失片段可能导致结论不完整，请人工复核。\n"
            if "转录状态：partial" not in minutes_md:
                minutes_md = minutes_md.rstrip() + partial_block

        minutes_v_path = folder_dir / "04-会议纪要" / f"minutes-v{minutes_ver}.md"
        minutes_v_path.write_text(minutes_md, encoding="utf-8")
        minutes_latest_path = folder_dir / "04-会议纪要" / "minutes-latest.md"
        minutes_latest_path.write_text(minutes_md, encoding="utf-8")
        actions_v_path = folder_dir / "05-行动项" / f"actions-v{actions_ver}.md"
        actions_v_path.write_text(actions_md, encoding="utf-8")
        actions_latest_path = folder_dir / "05-行动项" / "actions-latest.md"
        actions_latest_path.write_text(actions_md, encoding="utf-8")

        minutes_v_rel = minutes_v_path.relative_to(root).as_posix()
        minutes_latest_rel = minutes_latest_path.relative_to(root).as_posix()
        actions_v_rel = actions_v_path.relative_to(root).as_posix()
        actions_latest_rel = actions_latest_path.relative_to(root).as_posix()

        _upsert_workspace_file(db, workspace_id, user.id, minutes_v_rel,
                               f"minutes-v{minutes_ver}.md", "text/markdown", len(minutes_md.encode("utf-8")), minutes_v_path)
        _upsert_workspace_file(db, workspace_id, user.id, minutes_latest_rel,
                               "minutes-latest.md", "text/markdown", len(minutes_md.encode("utf-8")), minutes_latest_path)
        _upsert_workspace_file(db, workspace_id, user.id, actions_v_rel,
                               f"actions-v{actions_ver}.md", "text/markdown", len(actions_md.encode("utf-8")), actions_v_path)
        _upsert_workspace_file(db, workspace_id, user.id, actions_latest_rel,
                               "actions-latest.md", "text/markdown", len(actions_md.encode("utf-8")), actions_latest_path)

        _write_workspace_audit(db, user.id, "meeting_minutes_generate_retry",
                               _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                             created_files=[minutes_v_rel, minutes_latest_rel, actions_v_rel, actions_latest_rel],
                                             model=model_used, token_cost=token_cost))
        agent_run = _write_workspace_file_agent_run(
            db, user_id=user.id, workspace=workspace,
            source_type="meeting_minutes_generate_retry",
            title="重试生成会议纪要与行动项",
            path=req.folder_path,
            detail=f"纪要重试：minutes-v{minutes_ver}.md / actions-v{actions_ver}.md（{model_used}）",
        )
        _notify_meeting_run_finished(
            db, workspace=workspace, actor_user_id=user.id,
            folder_path=req.folder_path,
            title="会议纪要重试生成完成",
            status="completed" if transcription_status != "partial" else "partial",
            detail=f"{req.folder_path} 已重新生成 minutes-v{minutes_ver}.md / actions-v{actions_ver}.md",
        )
        db.commit()
        return MeetingRetryResponse(
            ok=True,
            meeting_folder_path=req.folder_path,
            operation=req.operation,
            status="completed" if transcription_status != "partial" else "partial",
            message=f"重新生成纪要与行动项（v{minutes_ver}），模型：{model_used}，token：{token_cost}",
            agent_run=serialize_agent_run(db, agent_run),
        )

    else:
        raise HTTPException(status_code=400, detail=f"不支持的重试操作：{req.operation}")


# ── Step 6: GBrain meeting ingest ────────────────────────────────────────

@router.post("/{workspace_id}/meetings/ingest", response_model=MeetingIngestResponse)
def ingest_meeting_to_gbrain(
    workspace_id: int,
    req: MeetingIngestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compile meeting outputs into a GBrain-ready page and ingest to the workspace source.

    Supports both full meeting ingest (default) and single-file actions-only ingest
    (when single_file_path points to actions-latest.md).
    """
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)

    is_single_file_actions = (
        req.single_file_path is not None
        and req.single_file_path.rstrip("/").endswith("actions-latest.md")
    )

    if is_single_file_actions:
        # Single-file actions-only: skip full meeting folder validation
        pass
    else:
        _validate_meeting_folder(workspace, req.folder_path)

    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id).first()
    is_admin = member and member.role == "admin"
    is_system_admin = user.role == "admin"

    # Permission check
    if workspace.workspace_kind == "customer":
        if not (is_admin or is_system_admin):
            raise HTTPException(status_code=403, detail="仅客户工作区管理员可录入会议资料")
    elif workspace.workspace_kind == "project":
        if not (is_admin or is_system_admin):
            raise HTTPException(status_code=403, detail="仅项目管理员可录入会议文件夹")

    root = _workspace_file_root(workspace)
    folder_dir = _resolve_workspace_child(root, _safe_relative_path(req.folder_path))

    # Determine source scope
    if workspace.workspace_kind == "project":
        from app.features.knowledge.gbrain import project_source_id_for_workspace, project_source_paths_for_workspace
        source_id = project_source_id_for_workspace(workspace)
        paths = project_source_paths_for_workspace(workspace)
        source_scope = "project"
    else:
        from app.features.knowledge.gbrain import customer_source_id_for_workspace, customer_source_paths_for_workspace
        source_id = customer_source_id_for_workspace(workspace)
        paths = customer_source_paths_for_workspace(workspace)
        source_scope = "customer"

    gbrain_ready_dir = paths.get("gbrain_ready", Path(""))
    if isinstance(gbrain_ready_dir, str):
        gbrain_ready_dir = Path(gbrain_ready_dir)
    gbrain_ready_dir.mkdir(parents=True, exist_ok=True)

    ingested: list[str] = []
    skipped: list[str] = []
    warning: str = ""

    if is_single_file_actions:
        # ── Single-file actions-only ingest ──────────────────────────────
        # Only read the actions-latest.md file
        actions_dir = folder_dir / "05-行动项"
        actions_latest = actions_dir / "actions-latest.md"
        if not actions_latest.exists():
            raise HTTPException(status_code=400, detail="行动项文件 actions-latest.md 不存在")

        actions_md = actions_latest.read_text(encoding="utf-8")
        lr = actions_latest.relative_to(root).as_posix()
        ingested.append(lr)

        # Check if full meeting files exist and warn
        has_minutes = (folder_dir / "04-会议纪要" / "minutes-latest.md").exists()
        has_transcript = (folder_dir / "02-转录文本" / "transcript-latest.md").exists()
        if has_minutes and has_transcript:
            warning = "该会议存在完整的纪要和转录文件。建议改为录入完整会议资料以获取更全面的知识上下文。"

        meeting_name = folder_dir.name
        gb_md = _gbrain_ready_compose(
            meeting_name,
            "",
            "",
            actions_md,
            source_scope=source_scope,
            source_context="action_items_only",
        )
        gb_path = _resolve_conflict_path(gbrain_ready_dir, f"{_safe_name(meeting_name)}.md", "keep_both")
        if gb_path is None:
            raise HTTPException(status_code=500, detail="无法写入 GBrain-ready 文件")
        gb_path.write_text(gb_md, encoding="utf-8")

        # Update ingested file status
        imeta = db.query(WorkspaceFile).filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == lr).first()
        if imeta:
            imeta.rag_status = "gbrain_ready"

    else:
        # ── Full meeting ingest (existing behavior) ─────────────────────
        sections = {
            "04-会议纪要": "minutes",
            "02-转录文本": "transcript",
            "05-行动项": "actions",
        }
        collected: dict[str, str] = {}
        for subdir, prefix in sections.items():
            dir_p = folder_dir / subdir
            if not dir_p.exists():
                continue
            latest_path = dir_p / f"{prefix}-latest.md"
            if not latest_path.exists():
                continue
            lr = latest_path.relative_to(root).as_posix()
            ingested.append(lr)
            collected[subdir] = latest_path.read_text(encoding="utf-8")

            # Mark vN files as superseded
            vn_pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.md$", re.IGNORECASE)
            for child in dir_p.iterdir():
                if not child.is_file():
                    continue
                if child.name == f"{prefix}-latest.md":
                    continue
                if vn_pattern.match(child.name):
                    sr = child.relative_to(root).as_posix()
                    skipped.append(sr)
                    sp_meta = db.query(WorkspaceFile).filter(
                        WorkspaceFile.workspace_id == workspace_id,
                        WorkspaceFile.relative_path == sr).first()
                    if sp_meta:
                        sp_meta.rag_status = "skipped_superseded_version"

        if not collected:
            raise HTTPException(status_code=400, detail="没有可录入的会议文件。请先生成纪要和转录。")

        meeting_name = folder_dir.name
        gb_md = _gbrain_ready_compose(
            meeting_name,
            collected.get("04-会议纪要", ""),
            collected.get("02-转录文本", ""),
            collected.get("05-行动项", ""),
            source_scope=source_scope,
            source_context="full_meeting",
        )
        gb_path = _resolve_conflict_path(gbrain_ready_dir, f"{_safe_name(meeting_name)}.md", "keep_both")
        if gb_path is None:
            raise HTTPException(status_code=500, detail="无法写入 GBrain-ready 文件")
        gb_path.write_text(gb_md, encoding="utf-8")

        # Update ingested files' statuses
        for ipath in ingested:
            imeta = db.query(WorkspaceFile).filter(
                WorkspaceFile.workspace_id == workspace_id,
                WorkspaceFile.relative_path == ipath).first()
            if imeta:
                imeta.rag_status = "gbrain_ready"

    _write_workspace_audit(db, user.id, "meeting_gbrain_ingest",
                           _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                         source_id=source_id, source_scope=source_scope,
                                         ingested=ingested, skipped=skipped,
                                         gbrain_ready_path=str(gb_path.resolve()),
                                         gbrain_ready_generated=True,
                                         gbrain_synced=False,
                                         single_file_actions_only=is_single_file_actions,
                                         warning=warning if warning else None))
    agent_run = _write_workspace_file_agent_run(
        db, user_id=user.id, workspace=workspace,
        source_type="meeting_gbrain_ingest",
        title="会议行动项录入 GBrain" if is_single_file_actions else "会议资料录入 GBrain",
        path=req.folder_path,
        detail=f"已生成 {len(ingested)} 个 GBrain-ready 文件，跳过 {len(skipped)} 个旧版本",
    )
    db.commit()
    return MeetingIngestResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        gbrain_ready_path=str(gb_path.resolve()),
        source_id=source_id,
        source_scope=source_scope,
        ingested_files=ingested,
        skipped_files=skipped,
        gbrain_ingest=True,
        agent_run=serialize_agent_run(db, agent_run),
        warning=warning,
    )


# ── End meeting endpoints ────────────────────────────────────────────────


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
    mark_workspace_ingest_job_queued(job, workspace=workspace, ingest_request=ingest_request, run_id=run_id)
    create_queued_workspace_ingest_agent_run(db, job, workspace, ingest_request)
    notify_workspace_ingest_queued(
        db,
        workspace=workspace,
        actor_user_id=user.id,
        job_id=job.id,
        request_label=_workspace_ingest_request_label(ingest_request),
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
    return _normalize_workspace_ingest_request_core(
        db,
        workspace,
        user,
        req,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        is_workspace_admin=_is_workspace_admin,
    )


def _compile_project_workspace_sources_for_request(workspace: Workspace, source_path: str, recursive: bool) -> dict:
    return _compile_project_workspace_sources_for_request_core(
        compile_project_workspace_sources, workspace, source_path, recursive
    )


def _compile_customer_workspace_sources_for_request(workspace: Workspace, source_path: str, recursive: bool) -> dict:
    return _compile_customer_workspace_sources_for_request_core(
        compile_customer_workspace_sources, workspace, source_path, recursive
    )


def _new_workspace_ingest_run_id(workspace: Workspace) -> str:
    return _new_workspace_ingest_run_id_core(workspace)


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
    return _execute_workspace_knowledge_ingest_core(
        db,
        workspace,
        actor_user_id,
        compile_project=compile_project_workspace_sources,
        compile_customer=compile_customer_workspace_sources,
        adapter_factory=GBrainAdapter,
        source_path=source_path,
        recursive=recursive,
        run_id=run_id,
        initial_status_history=initial_status_history,
    )


def _run_workspace_knowledge_ingest_job(job_id: int) -> None:
    return _run_workspace_knowledge_ingest_job_core(
        job_id,
        session_factory=SessionLocal,
        compile_project=compile_project_workspace_sources,
        compile_customer=compile_customer_workspace_sources,
        adapter_factory=GBrainAdapter,
    )


def _serialize_ingest_job(db: Session, job: WorkspaceIngestJob) -> WorkspaceKnowledgeIngestJobResponse:
    return _serialize_ingest_job_core(db, job)


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: int,
    req: UpdateWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.update_workspace(
        db,
        workspace_id,
        req,
        user,
        workspace_response=_workspace_response,
    )


@router.get("/{workspace_id}/member-candidates", response_model=list[WorkspaceMemberCandidateResponse])
def list_workspace_member_candidates(
    workspace_id: int,
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.list_workspace_member_candidates(db, workspace_id, q, limit, user)


@router.get("/{workspace_id}/group-candidates", response_model=list[WorkspaceGroupCandidateResponse])
def list_workspace_group_candidates(
    workspace_id: int,
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=80),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.list_workspace_group_candidates(db, workspace_id, q, limit, user)


@router.post("/{workspace_id}/members", response_model=MemberResponse)
def upsert_workspace_member(
    workspace_id: int,
    req: UpsertWorkspaceMemberRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.upsert_workspace_member(db, workspace_id, req, user)


@router.put("/{workspace_id}/members/{target_user_id}", response_model=MemberResponse)
def update_workspace_member_role(
    workspace_id: int,
    target_user_id: int,
    req: UpdateWorkspaceMemberRoleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.update_workspace_member_role(db, workspace_id, target_user_id, req, user)


@router.delete("/{workspace_id}/members/{target_user_id}")
def remove_workspace_member(
    workspace_id: int,
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.remove_workspace_member(db, workspace_id, target_user_id, user)


@router.post("/{workspace_id}/groups", response_model=WorkspaceGroupResponse)
def upsert_workspace_group(
    workspace_id: int,
    req: UpsertWorkspaceGroupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.upsert_workspace_group(db, workspace_id, req, user)


@router.delete("/{workspace_id}/groups/{group_name}")
def remove_workspace_group(
    workspace_id: int,
    group_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.remove_workspace_group(db, workspace_id, group_name, user)


@router.post("/{workspace_id}/join")
def join_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.join_workspace(db, workspace_id, user)


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_management.delete_workspace(db, workspace_id, user)
