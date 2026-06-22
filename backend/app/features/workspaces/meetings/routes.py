"""Meeting route handlers — extracted from api/workspaces.py.

These endpoints were originally inline in the workspaces API router.
They are now mounted as a sub-router under the main workspaces router.

Shared helpers (_ensure_member, _workspace_file_root, etc.) are imported
directly from their feature modules to avoid circular imports.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.workspaces.files.service import (
    resolve_workspace_child as _resolve_workspace_child,
    safe_relative_path as _safe_relative_path,
)
from app.features.workspaces.files.storage import (
    WorkspaceStorageConfig,
    ensure_not_trash_path as _ensure_not_trash_path,
    workspace_file_root,
)
from app.features.workspaces.meetings.materials.folders import (
    MEETING_TYPES,
    create_meeting_folder_for_workspace,
)
from app.features.workspaces.meetings.materials.ingest import (
    ingest_meeting_to_gbrain_asset,
)
from app.features.workspaces.meetings.io import (
    extract_text_from_docx as _extract_text_from_docx,
)
from app.features.workspaces.meetings.materials.media import (
    preflight_media_transcription,
    transcribe_meeting_media_asset,
)
from app.features.workspaces.meetings.materials.retry import (
    retry_meeting_operation_asset,
)
from app.features.workspaces.meetings.materials.speaker_assets import (
    detect_meeting_speakers,
    save_meeting_speaker_map_asset,
    save_meeting_term_corrections_asset,
)
from app.features.workspaces.meetings.materials.transcripts import (
    save_meeting_transcript_asset,
)
from app.features.workspaces.meetings.outputs.generation import (
    generate_meeting_outputs,
)
from app.features.workspaces.meetings.utils import (
    write_meeting_meta as _write_meeting_meta,
)
from app.features.workspaces.meetings.validation import (
    validate_meeting_folder as _validate_meeting_folder_core,
)
from app.features.workspaces.permissions import (
    ensure_member as _ensure_member,
)
from app.features.workspaces.schemas import (
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
from models import SessionLocal, get_db
from models.workspace import Workspace
from models.user import User

router = APIRouter()

# ── Storage config (lazy-imported from api.workspaces for test compat) ─────
def _storage_config() -> WorkspaceStorageConfig:
    from api.workspaces import WORKSPACES_ROOT, PROJECT_BRANDS, CUSTOMER_BRAND, CRM_WORKSPACE_SLUG, CRM_RAW_DIR
    return WorkspaceStorageConfig(
        workspaces_root=WORKSPACES_ROOT,
        project_root_name="project",
        customer_root_name="customer",
        project_brands=PROJECT_BRANDS,
        customer_brand=CUSTOMER_BRAND,
        crm_workspace_slug=CRM_WORKSPACE_SLUG,
        crm_raw_dir=CRM_RAW_DIR,
    )


def _workspace_file_root(workspace: Workspace) -> Path:
    return workspace_file_root(workspace, _storage_config())


# ── Meeting folder helpers (moved from api/workspaces.py) ────────────────

def _validate_meeting_folder(workspace: Workspace, folder_path: str) -> None:
    """Validate that a meeting folder path is within the workspace and not in trash."""
    root = _workspace_file_root(workspace)
    _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
    )


# ── Step 1: Meeting folder ───────────────────────────────────────────────

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

    return create_meeting_folder_for_workspace(
        db=db,
        user=user,
        workspace=workspace,
        root=_workspace_file_root(workspace),
        req=req,
    )


# ── Step 2: Meeting transcript ───────────────────────────────────────────

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
    _folder_rel, folder_dir = _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=req.folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        missing_detail="请选择会议文件夹后保存转录文本",
    )

    return save_meeting_transcript_asset(
        db=db,
        user=user,
        workspace=workspace,
        root=root,
        folder_dir=folder_dir,
        req=req,
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


# ── Step 3: Minutes generation ───────────────────────────────────────────

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
    _folder_rel, folder_dir = _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=req.folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        missing_detail="请选择会议文件夹后生成纪要",
    )

    return generate_meeting_outputs(
        db=db,
        user=user,
        workspace=workspace,
        root=root,
        folder_dir=folder_dir,
        req=req,
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

    _validate_meeting_folder(workspace, folder_path)
    return detect_meeting_speakers(workspace, _workspace_file_root(workspace), folder_path)


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
    return save_meeting_speaker_map_asset(db, user, workspace_id, _workspace_file_root(workspace), req)


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
    return save_meeting_term_corrections_asset(db, user, workspace_id, _workspace_file_root(workspace), req)


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
    return await transcribe_meeting_media_asset(db, user, workspace, _workspace_file_root(workspace), folder_path, file)


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

    return preflight_media_transcription(workspace, req)


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
    folder_rel, folder_dir = _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=req.folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        not_found_detail="请选择完整的会议文件夹",
        missing_detail="请选择完整的会议文件夹",
    )

    return retry_meeting_operation_asset(db, user, workspace, root, folder_dir, req)


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
    return ingest_meeting_to_gbrain_asset(db, user, workspace, _workspace_file_root(workspace), req)
