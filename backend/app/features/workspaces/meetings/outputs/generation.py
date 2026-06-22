from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.meetings.generation import generate_meeting_markdowns
from app.features.workspaces.meetings.io import (
    mark_previous_generated_meeting_files_needs_reingest,
    notify_meeting_run_finished,
    read_auxiliary_summaries,
    upsert_generated_meeting_file_metadata,
    workspace_file_uploader,
    write_generated_meeting_markdowns,
)
from app.features.workspaces.meetings.markdown import (
    append_partial_transcript_generation_notice,
    failed_transcript_reason,
    transcript_metadata_value,
    transcript_status_value,
)
from app.features.workspaces.meetings.utils import (
    acquire_meeting_run_lock,
    next_version_number,
    read_file_safe,
    read_meeting_meta,
    release_meeting_run_lock,
)
from app.features.workspaces.schemas import MeetingGenerateRequest, MeetingGenerateResponse
from models.user import User
from models.workspace import Workspace


def generate_meeting_outputs(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_dir: Path,
    req: MeetingGenerateRequest,
) -> MeetingGenerateResponse:
    """Generate meeting minutes and action items for one validated meeting folder."""
    transcript_dir = folder_dir / "02-转录文本"
    transcript_path = transcript_dir / "transcript-latest.md"
    if not transcript_path.exists():
        raise HTTPException(status_code=400, detail="转录文件（transcript-latest.md）不存在，请先保存转录")

    transcript_rel = transcript_path.relative_to(root).as_posix()
    transcript_uploaded_by = workspace_file_uploader(db, workspace.id, transcript_rel)
    transcript_text = transcript_path.read_text(encoding="utf-8")
    if not transcript_text.strip():
        raise HTTPException(status_code=400, detail="转录文件为空")

    failed_reason = failed_transcript_reason(transcript_text)
    if failed_reason:
        raise HTTPException(status_code=400, detail=f"转录未成功，不能生成会议纪要。原因：{failed_reason}")

    transcription_status = transcript_status_value(transcript_text)
    if transcription_status == "partial" and not req.allow_partial:
        raise HTTPException(status_code=400, detail="转录状态为 partial，请确认允许基于成功片段生成纪要后再继续")

    lock_path = acquire_meeting_run_lock(root, folder_dir, operation="generate_minutes", user_id=user.id)

    speaker_map_text = read_file_safe(folder_dir / "02-转录文本" / "speaker-map-latest.md")
    term_corrections_text = read_file_safe(folder_dir / "02-转录文本" / "term-corrections-latest.md")
    original_filename = transcript_metadata_value(transcript_text, "原始文件名")
    auxiliary_summaries_text = read_auxiliary_summaries(folder_dir, source_filename=original_filename)

    minutes_dir = folder_dir / "04-会议纪要"
    actions_dir = folder_dir / "05-行动项"
    minutes_dir.mkdir(parents=True, exist_ok=True)
    actions_dir.mkdir(parents=True, exist_ok=True)

    minutes_ver = next_version_number(minutes_dir, "minutes")
    actions_ver = next_version_number(actions_dir, "actions")

    if not req.regenerate:
        if (minutes_dir / "minutes-latest.md").exists() or (actions_dir / "actions-latest.md").exists():
            raise HTTPException(
                status_code=409,
                detail="已存在纪要与行动项。如需重新生成，请设置 regenerate=True 或先删除已有文件",
            )

    try:
        generation = generate_meeting_markdowns(
            transcript_text=transcript_text,
            speaker_map_text=speaker_map_text,
            term_corrections_text=term_corrections_text,
            auxiliary_summaries_text=auxiliary_summaries_text,
            meeting_type=read_meeting_meta(folder_dir).get("meeting_type", ""),
        )
    finally:
        release_meeting_run_lock(lock_path)

    minutes_md = append_partial_transcript_generation_notice(generation.minutes_md, transcription_status)
    actions_md = generation.actions_md
    total_tokens = generation.token_input + generation.token_output

    generated_files = write_generated_meeting_markdowns(
        root=root,
        minutes_dir=minutes_dir,
        actions_dir=actions_dir,
        minutes_version=minutes_ver,
        actions_version=actions_ver,
        minutes_md=minutes_md,
        actions_md=actions_md,
    )

    upsert_generated_meeting_file_metadata(
        workspace_id=workspace.id,
        user_id=user.id,
        generated_files=generated_files,
        minutes_md=minutes_md,
        actions_md=actions_md,
        upsert_workspace_file=lambda workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path: upsert_workspace_file(
            db, workspace_id_arg, user_id_arg, rel_path, filename, mime_type, size, path
        ),
        rag_status="partial" if transcription_status == "partial" else "not_ingested",
    )
    mark_previous_generated_meeting_files_needs_reingest(
        db,
        workspace_id=workspace.id,
        root=root,
        minutes_dir=minutes_dir,
        actions_dir=actions_dir,
        generated_files=generated_files,
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_minutes_generate",
        audit_detail(
            workspace.id,
            req.folder_path,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=req.folder_path,
            input_files=[{"path": transcript_rel, "uploaded_by": transcript_uploaded_by}],
            run_by=user.id,
            created_files=[
                generated_files.minutes_version_rel,
                generated_files.minutes_latest_rel,
                generated_files.actions_version_rel,
                generated_files.actions_latest_rel,
            ],
            model=generation.model_used,
            token_cost=total_tokens,
            transcription_status=transcription_status,
            gbrain_ingest=False,
        ),
    )
    agent_run = write_workspace_file_agent_run(
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
    notify_meeting_run_finished(
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
        minutes_v_path=generated_files.minutes_version_rel,
        minutes_latest_path=generated_files.minutes_latest_rel,
        actions_v_path=generated_files.actions_version_rel,
        actions_latest_path=generated_files.actions_latest_rel,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
        model_used=generation.model_used,
        token_cost=total_tokens,
    )
