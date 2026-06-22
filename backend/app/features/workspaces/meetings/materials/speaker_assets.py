from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.workspaces.audit import audit_detail, write_workspace_audit
from app.features.workspaces.files.service import resolve_workspace_child, safe_relative_path
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.meetings.io import write_numbered_latest_markdown
from app.features.workspaces.meetings.utils import (
    build_speaker_map_markdown,
    build_term_corrections_markdown,
    next_version_number,
    parse_speakers_from_transcript,
    read_file_safe,
    speaker_timeline_rows,
)
from app.features.workspaces.schemas import (
    MeetingSpeakersResponse,
    SaveSpeakerMapRequest,
    SaveTermCorrectionsRequest,
    SpeakerMapResponse,
    TermCorrectionsResponse,
)
from models.user import User
from models.workspace import Workspace


def detect_meeting_speakers(workspace: Workspace, root: Path, folder_path: str) -> MeetingSpeakersResponse:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持此操作")

    folder_dir = resolve_workspace_child(root, safe_relative_path(folder_path))
    transcript_path = folder_dir / "02-转录文本" / "transcript-latest.md"
    if not transcript_path.exists():
        raise HTTPException(status_code=400, detail="转录文件不存在")

    text = transcript_path.read_text(encoding="utf-8")
    speakers = parse_speakers_from_transcript(text)
    return MeetingSpeakersResponse(ok=True, detected_speakers=speakers)


def save_meeting_speaker_map_asset(
    db: Session,
    user: User,
    workspace_id: int,
    root: Path,
    req: SaveSpeakerMapRequest,
) -> SpeakerMapResponse:
    folder_dir = resolve_workspace_child(root, safe_relative_path(req.folder_path))
    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    author_name = user.nickname or user.username
    transcript_text = read_file_safe(folder_dir / "02-转录文本" / "transcript-latest.md")
    timeline_rows = speaker_timeline_rows(transcript_text)
    md = build_speaker_map_markdown(req.speakers, author_name, now_ts, timeline_rows)

    speaker_map_files = write_numbered_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        prefix="speaker-map",
        latest_filename="speaker-map-latest.md",
        content=md,
        next_version_number=next_version_number,
    )

    upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        speaker_map_files.version_rel,
        speaker_map_files.version_path.name,
        "text/markdown",
        len(md.encode("utf-8")),
        speaker_map_files.version_path,
    )
    upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        speaker_map_files.latest_rel,
        "speaker-map-latest.md",
        "text/markdown",
        len(md.encode("utf-8")),
        speaker_map_files.latest_path,
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_speaker_map_save",
        audit_detail(workspace_id, req.folder_path, actor_id=user.id, gbrain_ingest=False),
    )
    db.commit()
    return SpeakerMapResponse(ok=True, meeting_folder_path=req.folder_path, speaker_map_path=speaker_map_files.latest_rel, gbrain_ingest=False)


def save_meeting_term_corrections_asset(
    db: Session,
    user: User,
    workspace_id: int,
    root: Path,
    req: SaveTermCorrectionsRequest,
) -> TermCorrectionsResponse:
    folder_dir = resolve_workspace_child(root, safe_relative_path(req.folder_path))
    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    md = build_term_corrections_markdown(req.corrections, now_ts)

    corrections_files = write_numbered_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        prefix="term-corrections",
        latest_filename="term-corrections-latest.md",
        content=md,
        next_version_number=next_version_number,
    )

    upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        corrections_files.version_rel,
        corrections_files.version_path.name,
        "text/markdown",
        len(md.encode("utf-8")),
        corrections_files.version_path,
    )
    upsert_workspace_file(
        db,
        workspace_id,
        user.id,
        corrections_files.latest_rel,
        "term-corrections-latest.md",
        "text/markdown",
        len(md.encode("utf-8")),
        corrections_files.latest_path,
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_term_corrections_save",
        audit_detail(workspace_id, req.folder_path, actor_id=user.id, gbrain_ingest=False),
    )
    db.commit()
    return TermCorrectionsResponse(ok=True, meeting_folder_path=req.folder_path, corrections_path=corrections_files.latest_rel, gbrain_ingest=False)
