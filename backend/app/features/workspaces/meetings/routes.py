"""Meeting route handlers — extracted from api/workspaces.py.

These endpoints were originally inline in the workspaces API router.
They are now mounted as a sub-router under the main workspaces router.

Shared helpers (_ensure_member, _workspace_file_root, etc.) are imported
directly from their feature modules to avoid circular imports.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.agents.events import serialize_agent_run
from app.features.knowledge.gbrain import (
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.workspaces.audit import (
    audit_detail as _audit_detail,
    write_workspace_audit as _write_workspace_audit,
    write_workspace_file_agent_run as _write_workspace_file_agent_run,
)
from app.features.workspaces.files.service import (
    MEETING_SUBDIRS,
    make_meeting_folder_name,
    meeting_folder_collision_free,
    meeting_parent_path,
    resolve_conflict_path as _resolve_conflict_path,
    resolve_workspace_child as _resolve_workspace_child,
    safe_name as _safe_name,
    safe_relative_path as _safe_relative_path,
)
from app.features.workspaces.files.storage import (
    WorkspaceStorageConfig,
    ensure_not_trash_path as _ensure_not_trash_path,
    workspace_file_root,
)
from app.features.workspaces.files.tree import (
    upsert_workspace_file as _upsert_workspace_file,
)
from app.features.workspaces.meetings.generation import (
    generate_meeting_markdowns as _generate_meeting_markdowns,
)
from app.features.workspaces.meetings.io import (
    extract_text_from_docx as _extract_text_from_docx,
    notify_meeting_run_finished as _notify_meeting_run_finished,
    mark_previous_generated_meeting_files_needs_reingest as _mark_previous_generated_meeting_files_needs_reingest,
    read_auxiliary_summaries as _read_auxiliary_summaries,
    upsert_generated_meeting_file_metadata as _upsert_generated_meeting_file_metadata,
    write_numbered_latest_markdown as _write_numbered_latest_markdown,
    write_generated_meeting_markdowns as _write_generated_meeting_markdowns,
    write_versioned_latest_markdown as _write_versioned_latest_markdown,
    workspace_file_uploader as _workspace_file_uploader,
)
from app.features.workspaces.meetings.markdown import (
    append_partial_transcript_generation_notice as _append_partial_transcript_generation_notice,
    build_transcript_markdown as _build_transcript_markdown,
    compose_gbrain_ready_meeting as _gbrain_ready_compose,
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
    meeting_run_lock_path as _meeting_run_lock_path,
    next_version_number as _next_version_number,
    parse_speakers_from_transcript as _parse_speakers_from_transcript,
    read_file_safe as _read_file_safe,
    read_meeting_meta as _read_meeting_meta,
    release_meeting_run_lock as _release_meeting_run_lock,
    speaker_timeline_rows as _speaker_timeline_rows,
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
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember
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

MEETING_TYPES = [
    "项目统筹会",
    "客户沟通会",
    "技术交底",
    "现场协调",
    "内部复盘",
    "培训分享",
    "其他",
]


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
    folder_rel, folder_dir = _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=req.folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        missing_detail="请选择会议文件夹后保存转录文本",
    )

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

    transcript_files = _write_versioned_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        version_filename="transcript-v1.md",
        latest_filename="transcript-latest.md",
        content=transcript_md,
        resolve_conflict_path=_resolve_conflict_path,
        error_detail="无法写入转录文件",
    )
    v1_path = transcript_files.version_path
    v1_rel = transcript_files.version_rel
    latest_path = transcript_files.latest_path
    latest_rel = transcript_files.latest_rel

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
    folder_rel, folder_dir = _validate_meeting_folder_core(
        workspace_kind=workspace.workspace_kind,
        root=root,
        folder_path=req.folder_path,
        safe_relative_path=_safe_relative_path,
        ensure_not_trash_path=_ensure_not_trash_path,
        resolve_workspace_child=_resolve_workspace_child,
        missing_detail="请选择会议文件夹后生成纪要",
    )

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
        generation = _generate_meeting_markdowns(
            transcript_text=transcript_text,
            speaker_map_text=speaker_map_text,
            term_corrections_text=term_corrections_text,
            auxiliary_summaries_text=auxiliary_summaries_text,
            meeting_type=_read_meeting_meta(folder_dir).get("meeting_type", ""),
        )
    finally:
        _release_meeting_run_lock(lock_path)

    minutes_md = generation.minutes_md
    actions_md = generation.actions_md
    model_used = generation.model_used
    token_input = generation.token_input
    token_output = generation.token_output
    minutes_md = _append_partial_transcript_generation_notice(minutes_md, transcription_status)

    generated_files = _write_generated_meeting_markdowns(
        root=root,
        minutes_dir=minutes_dir,
        actions_dir=actions_dir,
        minutes_version=minutes_ver,
        actions_version=actions_ver,
        minutes_md=minutes_md,
        actions_md=actions_md,
    )
    minutes_v_path = generated_files.minutes_version_path
    minutes_v_rel = generated_files.minutes_version_rel
    minutes_latest_path = generated_files.minutes_latest_path
    minutes_latest_rel = generated_files.minutes_latest_rel
    actions_v_path = generated_files.actions_version_path
    actions_v_rel = generated_files.actions_version_rel
    actions_latest_path = generated_files.actions_latest_path
    actions_latest_rel = generated_files.actions_latest_rel

    _upsert_generated_meeting_file_metadata(
        workspace_id=workspace_id,
        user_id=user.id,
        generated_files=generated_files,
        minutes_md=minutes_md,
        actions_md=actions_md,
        upsert_workspace_file=lambda workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path: _upsert_workspace_file(
            db, workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path
        ),
        rag_status="partial" if transcription_status == "partial" else "not_ingested",
    )
    _mark_previous_generated_meeting_files_needs_reingest(
        db,
        workspace_id=workspace_id,
        root=root,
        minutes_dir=minutes_dir,
        actions_dir=actions_dir,
        generated_files=generated_files,
    )

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

    transcript_text = _read_file_safe(folder_dir / "02-转录文本" / "transcript-latest.md")
    timeline_rows = _speaker_timeline_rows(transcript_text)
    md = _build_speaker_map_markdown(req.speakers, author_name, now_ts, timeline_rows)

    speaker_map_files = _write_numbered_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        prefix="speaker-map",
        latest_filename="speaker-map-latest.md",
        content=md,
        next_version_number=_next_version_number,
    )

    _upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        speaker_map_files.version_rel,
        speaker_map_files.version_path.name,
        "text/markdown",
        len(md.encode("utf-8")),
        speaker_map_files.version_path,
    )
    _upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        speaker_map_files.latest_rel,
        "speaker-map-latest.md",
        "text/markdown",
        len(md.encode("utf-8")),
        speaker_map_files.latest_path,
    )

    _write_workspace_audit(db, user.id, "meeting_speaker_map_save",
                           _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                         gbrain_ingest=False))
    db.commit()
    return SpeakerMapResponse(ok=True, meeting_folder_path=req.folder_path,
                               speaker_map_path=speaker_map_files.latest_rel, gbrain_ingest=False)


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

    md = _build_term_corrections_markdown(req.corrections, now_ts)

    corrections_files = _write_numbered_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        prefix="term-corrections",
        latest_filename="term-corrections-latest.md",
        content=md,
        next_version_number=_next_version_number,
    )

    _upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        corrections_files.version_rel,
        corrections_files.version_path.name,
        "text/markdown",
        len(md.encode("utf-8")),
        corrections_files.version_path,
    )
    _upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        corrections_files.latest_rel,
        "term-corrections-latest.md",
        "text/markdown",
        len(md.encode("utf-8")),
        corrections_files.latest_path,
    )

    _write_workspace_audit(db, user.id, "meeting_term_corrections_save",
                           _audit_detail(workspace_id, req.folder_path, actor_id=user.id,
                                         gbrain_ingest=False))
    db.commit()
    return TermCorrectionsResponse(ok=True, meeting_folder_path=req.folder_path,
                                    corrections_path=corrections_files.latest_rel, gbrain_ingest=False)


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

    transcript_files = _write_versioned_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        version_filename="transcript-v1.md",
        latest_filename="transcript-latest.md",
        content=final_md,
        resolve_conflict_path=_resolve_conflict_path,
        error_detail="无法写入转录文件",
    )
    v1_path = transcript_files.version_path
    v1_rel = transcript_files.version_rel
    latest_path = transcript_files.latest_path
    latest_rel = transcript_files.latest_rel

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

            generation = _generate_meeting_markdowns(
                transcript_text=transcript_text,
                speaker_map_text=speaker_map_text,
                term_corrections_text=term_corrections_text,
                auxiliary_summaries_text=auxiliary_summaries_text,
                meeting_type=_read_meeting_meta(folder_dir).get("meeting_type", ""),
            )
            minutes_md = generation.minutes_md
            actions_md = generation.actions_md
            model_used = generation.model_used
            token_cost = generation.token_cost
        finally:
            _release_meeting_run_lock(lock_path)

        minutes_md = _append_partial_transcript_generation_notice(minutes_md, transcription_status)

        generated_files = _write_generated_meeting_markdowns(
            root=root,
            minutes_dir=folder_dir / "04-会议纪要",
            actions_dir=folder_dir / "05-行动项",
            minutes_version=minutes_ver,
            actions_version=actions_ver,
            minutes_md=minutes_md,
            actions_md=actions_md,
        )
        minutes_v_path = generated_files.minutes_version_path
        minutes_v_rel = generated_files.minutes_version_rel
        minutes_latest_path = generated_files.minutes_latest_path
        minutes_latest_rel = generated_files.minutes_latest_rel
        actions_v_path = generated_files.actions_version_path
        actions_v_rel = generated_files.actions_version_rel
        actions_latest_path = generated_files.actions_latest_path
        actions_latest_rel = generated_files.actions_latest_rel

        _upsert_generated_meeting_file_metadata(
            workspace_id=workspace_id,
            user_id=user.id,
            generated_files=generated_files,
            minutes_md=minutes_md,
            actions_md=actions_md,
            upsert_workspace_file=lambda workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path: _upsert_workspace_file(
                db, workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path
            ),
        )

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
