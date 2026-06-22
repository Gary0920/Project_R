from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.service import resolve_conflict_path
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.meetings.io import write_versioned_latest_markdown
from app.features.workspaces.meetings.markdown import build_transcript_markdown
from app.features.workspaces.schemas import SaveMeetingTranscriptRequest, SaveMeetingTranscriptResponse
from models.user import User
from models.workspace import Workspace


def save_meeting_transcript_asset(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_dir: Path,
    req: SaveMeetingTranscriptRequest,
) -> SaveMeetingTranscriptResponse:
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="转录文本不能为空")

    transcript_md = build_transcript_markdown(
        content,
        datetime.now(timezone.utc),
        input_type=req.input_type,
        original_filename=req.original_filename,
    )
    transcript_files = write_versioned_latest_markdown(
        root=root,
        target_dir=folder_dir / "02-转录文本",
        version_filename="transcript-v1.md",
        latest_filename="transcript-latest.md",
        content=transcript_md,
        resolve_conflict_path=resolve_conflict_path,
        error_detail="无法写入转录文件",
    )

    upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        transcript_files.version_rel,
        "transcript-v1.md",
        "text/markdown",
        len(transcript_md.encode("utf-8")),
        transcript_files.version_path,
    )
    upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        transcript_files.latest_rel,
        "transcript-latest.md",
        "text/markdown",
        len(transcript_md.encode("utf-8")),
        transcript_files.latest_path,
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_transcript_save",
        audit_detail(
            workspace.id,
            req.folder_path,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=req.folder_path,
            created_files=[transcript_files.version_rel, transcript_files.latest_rel],
            gbrain_ingest=False,
        ),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_transcript_save",
        title="保存会议转录文本",
        path=req.folder_path,
        detail="转录：transcript-v1.md, transcript-latest.md",
    )
    db.commit()
    return SaveMeetingTranscriptResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        transcript_v1_path=transcript_files.version_rel,
        transcript_latest_path=transcript_files.latest_rel,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
    )
