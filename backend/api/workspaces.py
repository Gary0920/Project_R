import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.agents.events import serialize_agent_run
from app.features.knowledge.gbrain import (
    GBrainAdapter,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.notifications.service import (
    notify_user,
    notify_workspace_bulk_delete_risk,
    notify_workspace_joined,
)
from app.features.documents.workspace_save import save_generated_file_to_workspace as _save_generated_file_to_workspace
from app.features.workspaces.audit import (
    audit_detail as _audit_detail,
    mark_workspace_rag_pending as _mark_workspace_rag_pending,
    raise_with_audit as _raise_with_audit,
    write_workspace_audit as _write_workspace_audit,
    write_workspace_file_agent_run as _write_workspace_file_agent_run,
)
from app.features.workspaces import catalog as workspace_catalog
from app.features.workspaces import knowledge_graph as workspace_knowledge_graph_feature
from app.features.workspaces.knowledge_ingest_api import (
    enqueue_workspace_knowledge_ingest_job,
    execute_immediate_workspace_knowledge_ingest,
    normalize_workspace_ingest_request,
    run_workspace_knowledge_ingest_job,
    serialize_ingest_job,
)
from app.features.workspaces import management as workspace_management
from app.features.workspaces.schemas import (
    CopyWorkspacePathRequest,
    CreateWorkspaceFolderRequest,
    CreateWorkspaceRequest,
    MemberResponse,
    MoveWorkspacePathRequest,
    RenameWorkspacePathRequest,
    RestoreWorkspaceFileRequest,
    SaveAttachmentToWorkspaceRequest,
    SaveGeneratedFileToWorkspaceRequest,
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
from app.features.workspaces.files.attachments import save_attachment_to_workspace as _save_attachment_to_workspace
from app.features.workspaces.files import browser as workspace_file_browser
from app.features.workspaces.files import lifecycle as workspace_file_lifecycle
from app.features.workspaces.files import paths as workspace_file_paths
from app.features.workspaces.files import uploads as workspace_file_uploads
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
from app.features.workspaces.responses import workspace_response as _workspace_response
from app.features.workspaces.files.service import (
    DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS,
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
from models import get_db
from models.workspace import Workspace, WorkspaceMember, WorkspaceFile
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
    return workspace_catalog.create_workspace(
        db,
        req,
        user,
        normalize_workspace_kind=_normalize_workspace_kind,
        ensure_crm_workspace=_ensure_crm_workspace,
        workspace_response=_workspace_response,
        normalize_brand=_normalize_brand,
        slugify_name=_slugify,
        candidate_storage_path=_candidate_storage_path,
        workspaces_root=WORKSPACES_ROOT,
        find_existing_project_folder=_find_existing_project_folder,
        register_existing_project_folder=_register_existing_project_folder,
        ensure_storage_path=_ensure_storage_path,
    )


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_catalog.list_workspaces(
        db,
        user,
        ensure_default_workspace=ensure_default_workspace,
        sync_project_folders=_sync_project_folders,
        ensure_crm_workspace=_ensure_crm_workspace,
        normalize_group_name=_normalize_group_name,
        can_open_workspace=_can_open_workspace,
        workspace_response=_workspace_response,
        crm_workspace_slug=CRM_WORKSPACE_SLUG,
    )


@router.get("/search")
def search_workspaces(
    q: str = Query(default=""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    brand: str | None = None,
):
    return workspace_catalog.search_workspaces(
        db,
        q,
        user,
        brand,
        sync_project_folders=_sync_project_folders,
        ensure_crm_workspace=_ensure_crm_workspace,
        normalize_brand=_normalize_brand,
        normalize_group_name=_normalize_group_name,
        can_open_workspace=_can_open_workspace,
        is_workspace_admin=_is_workspace_admin,
        customer_brand=CUSTOMER_BRAND,
        crm_workspace_slug=CRM_WORKSPACE_SLUG,
    )


@router.get("/{workspace_id}", response_model=WorkspaceDetailResponse)
def get_workspace(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_catalog.get_workspace(
        db,
        workspace_id,
        user,
        can_open_workspace=_can_open_workspace,
        ensure_member=_ensure_member,
        is_workspace_admin=_is_workspace_admin,
        workspace_access_groups=_workspace_access_groups,
    )


@router.get("/{workspace_id}/files", response_model=WorkspaceFilesResponse)
def list_workspace_files(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    include_deleted: bool = False,
):
    return workspace_file_browser.list_workspace_files(
        db,
        workspace_id,
        user,
        include_deleted,
        ensure_member=_ensure_member,
        ensure_storage_path=_ensure_storage_path,
        build_deleted_file_items=_build_deleted_file_items,
        build_file_tree=_build_file_tree,
        display_user_names=_display_user_names,
    )


@router.get("/{workspace_id}/files/content")
def get_workspace_file_content(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_browser.get_workspace_file_content(
        db,
        workspace_id,
        path,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        resolve_workspace_child=_resolve_workspace_child,
    )


@router.post("/{workspace_id}/files/upload", response_model=WorkspaceMultiUploadResponse)
async def upload_workspace_files(
    workspace_id: int,
    directory: str = Form(default=""),
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await workspace_file_uploads.upload_workspace_files(
        db,
        workspace_id,
        directory,
        files,
        user,
        ensure_member=_ensure_member,
        upload_limit_for=_upload_limit_for,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        safe_name=_safe_name,
        resolve_conflict_path=_resolve_conflict_path,
        raise_with_audit=_raise_with_audit,
        audit_detail=_audit_detail,
        upsert_workspace_file=_upsert_workspace_file,
        write_workspace_audit=_write_workspace_audit,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.post("/{workspace_id}/files", response_model=WorkspaceFileMutationResponse)
def upload_workspace_file(
    workspace_id: int,
    req: UploadWorkspaceFileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_uploads.upload_workspace_file(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        upload_limit_for=_upload_limit_for,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        safe_name=_safe_name,
        resolve_workspace_child=_resolve_workspace_child,
        resolve_conflict_path=_resolve_conflict_path,
        raise_with_audit=_raise_with_audit,
        audit_detail=_audit_detail,
        upsert_workspace_file=_upsert_workspace_file,
        write_workspace_audit=_write_workspace_audit,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.post("/{workspace_id}/folders", response_model=WorkspaceFileMutationResponse)
def create_workspace_folder(
    workspace_id: int,
    req: CreateWorkspaceFolderRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_browser.create_workspace_folder(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        safe_name=_safe_name,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


# ── Meeting sub-router ───────────────────────────────────────────────────
from app.features.workspaces.meetings.routes import router as meeting_router

router.include_router(meeting_router)

# Backward-compatible re-exports for tests that access meeting symbols via api.workspaces
from app.features.workspaces.meetings import utils as _meeting_utils  # noqa: E402, F401
from app.features.workspaces.meetings.routes import (  # noqa: E402, F401
    MEETING_TYPES,
    _validate_meeting_folder,
    _write_meeting_meta,
    create_meeting_folder,
    generate_meeting_minutes_and_actions,
    get_meeting_speakers,
    ingest_meeting_to_gbrain,
    preflight_meeting_media_transcribe,
    retry_meeting_operation,
    save_meeting_speaker_map,
    save_meeting_term_corrections,
    save_meeting_transcript,
    save_meeting_transcript_from_file,
    transcribe_meeting_media,
)
_read_meeting_meta = _meeting_utils.read_meeting_meta
_read_file_safe = _meeting_utils.read_file_safe
_write_meeting_meta = _meeting_utils.write_meeting_meta
_acquire_meeting_run_lock = _meeting_utils.acquire_meeting_run_lock
_release_meeting_run_lock = _meeting_utils.release_meeting_run_lock
_next_version_number = _meeting_utils.next_version_number
_parse_speakers_from_transcript = _meeting_utils.parse_speakers_from_transcript
_build_speaker_map_markdown = _meeting_utils.build_speaker_map_markdown
_build_term_corrections_markdown = _meeting_utils.build_term_corrections_markdown
_speaker_timeline_rows = _meeting_utils.speaker_timeline_rows
from app.features.workspaces.schemas import (  # noqa: E402, F401
    CreateMeetingFolderRequest,
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
    SaveMeetingTranscriptRequest,
    SaveMeetingTranscriptResponse,
    SaveSpeakerMapRequest,
    SaveTermCorrectionsRequest,
    SpeakerMapItem,
    SpeakerMapResponse,
    TermCorrectionItem,
    TermCorrectionsResponse,
)
from app.features.workspaces.files.service import MEETING_SUBDIRS, meeting_parent_path  # noqa: E402, F401
# ── End meeting sub-router ───────────────────────────────────────────────


@router.delete("/{workspace_id}/files", response_model=WorkspaceFileMutationResponse)
def delete_workspace_file(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_lifecycle.delete_workspace_file(
        db,
        workspace_id,
        path,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        resolve_workspace_child=_resolve_workspace_child,
        member_can_mutate_file=_member_can_mutate_file,
        raise_with_audit=_raise_with_audit,
        audit_detail=_audit_detail,
        upsert_workspace_file=_upsert_workspace_file,
        trash_target=_trash_target,
        mark_workspace_rag_pending=_mark_workspace_rag_pending,
        write_workspace_audit=_write_workspace_audit,
        notify_user=notify_user,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.post("/{workspace_id}/files/restore", response_model=WorkspaceFileMutationResponse)
def restore_workspace_file(
    workspace_id: int,
    req: RestoreWorkspaceFileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_lifecycle.restore_workspace_file(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        resolve_workspace_child=_resolve_workspace_child,
        raise_with_audit=_raise_with_audit,
        audit_detail=_audit_detail,
        record_file_signature=_record_file_signature,
        mark_workspace_rag_pending=_mark_workspace_rag_pending,
        write_workspace_audit=_write_workspace_audit,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.delete("/{workspace_id}/files/permanent", response_model=WorkspaceFileMutationResponse)
def permanently_delete_workspace_file(
    workspace_id: int,
    file_id: int = Query(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_lifecycle.permanently_delete_workspace_file(
        db,
        workspace_id,
        file_id,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        resolve_workspace_child=_resolve_workspace_child,
        member_can_restore_file=_member_can_restore_file,
        raise_with_audit=_raise_with_audit,
        audit_detail=_audit_detail,
        mark_workspace_rag_pending=_mark_workspace_rag_pending,
        write_workspace_audit=_write_workspace_audit,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.delete("/{workspace_id}/files/trash", response_model=WorkspaceTrashClearResponse)
def clear_workspace_trash(
    workspace_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_lifecycle.clear_workspace_trash(
        db,
        workspace_id,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        resolve_workspace_child=_resolve_workspace_child,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        notify_workspace_bulk_delete_risk=notify_workspace_bulk_delete_risk,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


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
    response = _save_attachment_to_workspace(
        db,
        workspace=workspace,
        user=user,
        req=req,
        storage_config=_storage_config(),
    )
    db.commit()
    return response


@router.post("/{workspace_id}/generated-files/save", response_model=WorkspaceFileMutationResponse)
def save_generated_file_to_workspace(
    workspace_id: int,
    req: SaveGeneratedFileToWorkspaceRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    _ensure_member(db, user.id, workspace_id)
    result = _save_generated_file_to_workspace(
        db,
        workspace=workspace,
        user=user,
        generated_file_id=req.generated_file_id,
        conflict_strategy=req.conflict_strategy,
        storage_config=_storage_config(),
    )
    db.commit()
    return WorkspaceFileMutationResponse(**result)


@router.delete("/{workspace_id}/folders", response_model=WorkspaceFileMutationResponse)
def delete_workspace_folder(
    workspace_id: int,
    path: str = Query(..., min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_paths.delete_workspace_folder(
        db,
        workspace_id,
        path,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        is_template_root=_is_template_root,
        resolve_workspace_child=_resolve_workspace_child,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.put("/{workspace_id}/paths/rename", response_model=WorkspaceFileMutationResponse)
def rename_workspace_path(
    workspace_id: int,
    req: RenameWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_paths.rename_workspace_path(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        is_template_root=_is_template_root,
        resolve_workspace_child=_resolve_workspace_child,
        safe_name=_safe_name,
        member_can_mutate_file=_member_can_mutate_file,
        sync_file_descendant_paths=_sync_file_descendant_paths,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.post("/{workspace_id}/paths/move", response_model=WorkspaceFileMutationResponse)
def move_workspace_path(
    workspace_id: int,
    req: MoveWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_paths.move_workspace_path(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        is_template_root=_is_template_root,
        resolve_workspace_child=_resolve_workspace_child,
        member_can_mutate_file=_member_can_mutate_file,
        resolve_conflict_path=_resolve_conflict_path,
        sync_file_descendant_paths=_sync_file_descendant_paths,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


@router.post("/{workspace_id}/paths/copy", response_model=WorkspaceFileMutationResponse)
def copy_workspace_path(
    workspace_id: int,
    req: CopyWorkspacePathRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return workspace_file_paths.copy_workspace_path(
        db,
        workspace_id,
        req,
        user,
        ensure_member=_ensure_member,
        workspace_file_root=_workspace_file_root,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        is_template_root=_is_template_root,
        resolve_workspace_child=_resolve_workspace_child,
        resolve_conflict_path=_resolve_conflict_path,
        create_copied_file_metadata=_create_copied_file_metadata,
        copy_descendant_file_metadata=_copy_descendant_file_metadata,
        write_workspace_audit=_write_workspace_audit,
        audit_detail=_audit_detail,
        write_workspace_file_agent_run=_write_workspace_file_agent_run,
        serialize_agent_run=serialize_agent_run,
    )


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
    ingest_request = normalize_workspace_ingest_request(db, workspace, user, req, storage_config=_storage_config())
    payload = execute_immediate_workspace_knowledge_ingest(db, workspace, user, ingest_request)
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
    ingest_request = normalize_workspace_ingest_request(db, workspace, user, req, storage_config=_storage_config())
    job = enqueue_workspace_knowledge_ingest_job(db, workspace, user, ingest_request)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_workspace_knowledge_ingest_job, job.id)
    return serialize_ingest_job(db, job)


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
    return serialize_ingest_job(db, job)


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
    return workspace_knowledge_graph_feature.workspace_knowledge_graph(
        db,
        workspace=workspace,
        user=user,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
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
    return workspace_knowledge_graph_feature.workspace_entity_merge_candidates(
        db,
        workspace=workspace,
        user=user,
        focus=focus,
        limit=limit,
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
    return workspace_knowledge_graph_feature.workspace_entity_merge_candidate_action(
        db,
        workspace=workspace,
        user=user,
        request=request,
        adapter_cls=GBrainAdapter,
    )


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
    return workspace_knowledge_graph_feature.workspace_entity_merge_candidate_preview(
        db,
        workspace=workspace,
        user=user,
        candidate_id=candidate_id,
    )


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
    return workspace_knowledge_graph_feature.workspace_native_graph_context(
        db,
        workspace=workspace,
        user=user,
        slug=slug,
        depth=depth,
        direction=direction,
        link_type=link_type,
        adapter_cls=GBrainAdapter,
    )


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
