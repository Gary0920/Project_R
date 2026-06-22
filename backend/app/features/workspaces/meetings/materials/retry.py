from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.meetings.generation import generate_meeting_markdowns
from app.features.workspaces.meetings.io import (
    notify_meeting_run_finished,
    read_auxiliary_summaries,
    upsert_generated_meeting_file_metadata,
    write_generated_meeting_markdowns,
)
from app.features.workspaces.meetings.markdown import (
    append_partial_transcript_generation_notice,
    build_transcript_markdown,
    failed_transcript_reason,
    transcript_metadata_value,
    transcript_status_value,
)
from app.features.workspaces.meetings.utils import (
    SUPPORTED_MEDIA_EXTENSIONS,
    acquire_meeting_run_lock,
    meeting_run_lock_path,
    next_version_number,
    read_file_safe,
    read_meeting_meta,
    release_meeting_run_lock,
)
from app.features.workspaces.schemas import MeetingRetryRequest, MeetingRetryResponse
from models.user import User
from models.workspace import Workspace


def retry_meeting_operation_asset(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_dir: Path,
    req: MeetingRetryRequest,
) -> MeetingRetryResponse:
    lock_path = meeting_run_lock_path(root, folder_dir)
    if lock_path.exists():
        raise HTTPException(status_code=409, detail="当前会议已有处理中任务，请等待完成后再操作")

    if req.operation == "transcribe":
        return _retry_media_transcription(db, user, workspace, root, folder_dir, req)
    if req.operation == "generate_minutes":
        return _retry_minutes_generation(db, user, workspace, root, folder_dir, req)
    raise HTTPException(status_code=400, detail=f"不支持的重试操作：{req.operation}")


def _retry_media_transcription(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_dir: Path,
    req: MeetingRetryRequest,
) -> MeetingRetryResponse:
    transcript_latest = folder_dir / "02-转录文本" / "transcript-latest.md"
    if transcript_latest.exists():
        text = transcript_latest.read_text(encoding="utf-8")
        if not failed_transcript_reason(text):
            raise HTTPException(status_code=400, detail="转录已成功完成，无需重试。如需重新转录请先删除旧转录文件。")

    raw_dir = folder_dir / "01-原始资料"
    if not raw_dir.exists() or not raw_dir.is_dir():
        raise HTTPException(status_code=400, detail="原始资料目录不存在，无法重试转录。请重新上传音视频文件。")

    media_files = [
        child for child in sorted(raw_dir.iterdir())
        if child.is_file() and child.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
    ]
    if not media_files:
        raise HTTPException(status_code=400, detail="原始资料中没有音视频文件，无法重试转录。请重新上传。")

    media_path = max(media_files, key=lambda p: p.stat().st_mtime)
    lock_path = acquire_meeting_run_lock(root, folder_dir, operation="media_transcribe_retry", user_id=user.id)

    try:
        from app.features.preprocessing.media_transcription import load_media_transcription_options, transcribe_media_to_markdown
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
        release_meeting_run_lock(lock_path)

    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    if transcription_status != "failed":
        final_md = build_transcript_markdown(
            transcript_text,
            datetime.now(timezone.utc),
            input_type=media_path.suffix.lstrip("."),
            original_filename=media_path.name,
            transcription_status=transcription_status,
            warnings=warnings_list,
        )
    else:
        final_md = transcript_text

    transcript_version = next_version_number(transcript_dir, "transcript")
    version_path = transcript_dir / f"transcript-v{transcript_version}.md"
    version_path.write_text(final_md, encoding="utf-8")
    latest_path = transcript_dir / "transcript-latest.md"
    latest_path.write_text(final_md, encoding="utf-8")

    version_rel = version_path.relative_to(root).as_posix()
    latest_rel = latest_path.relative_to(root).as_posix()

    upsert_workspace_file(db, workspace.id, user.id, version_rel, f"transcript-v{transcript_version}.md", "text/markdown", len(final_md.encode("utf-8")), version_path)
    upsert_workspace_file(db, workspace.id, user.id, latest_rel, "transcript-latest.md", "text/markdown", len(final_md.encode("utf-8")), latest_path)

    write_workspace_audit(
        db,
        user.id,
        "meeting_media_transcribe_retry",
        audit_detail(workspace.id, req.folder_path, actor_id=user.id, media_file=str(media_path), transcript=latest_rel, status=transcription_status, segments=segment_count),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_media_transcribe_retry",
        title="重试会议音视频转录",
        path=req.folder_path,
        detail=f"转录重试：{media_path.name}（{segment_count}段，{transcription_status}）",
        status="failed" if transcription_status == "failed" else "completed",
    )
    notify_meeting_run_finished(
        db,
        workspace=workspace,
        actor_user_id=user.id,
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


def _retry_minutes_generation(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_dir: Path,
    req: MeetingRetryRequest,
) -> MeetingRetryResponse:
    transcript_latest = folder_dir / "02-转录文本" / "transcript-latest.md"
    if not transcript_latest.exists():
        raise HTTPException(status_code=400, detail="转录文件不存在，无法重试生成纪要")

    transcript_text = transcript_latest.read_text(encoding="utf-8")
    failed_reason = failed_transcript_reason(transcript_text)
    if failed_reason:
        raise HTTPException(status_code=400, detail=f"转录未成功，需要先重试转录。原因：{failed_reason}")

    speaker_map_text = read_file_safe(folder_dir / "02-转录文本" / "speaker-map-latest.md")
    term_corrections_text = read_file_safe(folder_dir / "02-转录文本" / "term-corrections-latest.md")
    original_filename = transcript_metadata_value(transcript_text, "原始文件名")
    auxiliary_summaries_text = read_auxiliary_summaries(folder_dir, source_filename=original_filename)
    transcription_status = transcript_status_value(transcript_text)

    lock_path = acquire_meeting_run_lock(root, folder_dir, operation="generate_minutes_retry", user_id=user.id)

    try:
        minutes_version = next_version_number(folder_dir / "04-会议纪要", "minutes")
        actions_version = next_version_number(folder_dir / "05-行动项", "actions")
        (folder_dir / "04-会议纪要").mkdir(parents=True, exist_ok=True)
        (folder_dir / "05-行动项").mkdir(parents=True, exist_ok=True)

        generation = generate_meeting_markdowns(
            transcript_text=transcript_text,
            speaker_map_text=speaker_map_text,
            term_corrections_text=term_corrections_text,
            auxiliary_summaries_text=auxiliary_summaries_text,
            meeting_type=read_meeting_meta(folder_dir).get("meeting_type", ""),
        )
        minutes_md = generation.minutes_md
        actions_md = generation.actions_md
        model_used = generation.model_used
        token_cost = generation.token_cost
    finally:
        release_meeting_run_lock(lock_path)

    minutes_md = append_partial_transcript_generation_notice(minutes_md, transcription_status)

    generated_files = write_generated_meeting_markdowns(
        root=root,
        minutes_dir=folder_dir / "04-会议纪要",
        actions_dir=folder_dir / "05-行动项",
        minutes_version=minutes_version,
        actions_version=actions_version,
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
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_minutes_generate_retry",
        audit_detail(
            workspace.id,
            req.folder_path,
            actor_id=user.id,
            created_files=[
                generated_files.minutes_version_rel,
                generated_files.minutes_latest_rel,
                generated_files.actions_version_rel,
                generated_files.actions_latest_rel,
            ],
            model=model_used,
            token_cost=token_cost,
        ),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_minutes_generate_retry",
        title="重试生成会议纪要与行动项",
        path=req.folder_path,
        detail=f"纪要重试：minutes-v{minutes_version}.md / actions-v{actions_version}.md（{model_used}）",
    )
    notify_meeting_run_finished(
        db,
        workspace=workspace,
        actor_user_id=user.id,
        folder_path=req.folder_path,
        title="会议纪要重试生成完成",
        status="completed" if transcription_status != "partial" else "partial",
        detail=f"{req.folder_path} 已重新生成 minutes-v{minutes_version}.md / actions-v{actions_version}.md",
    )
    db.commit()
    return MeetingRetryResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        operation=req.operation,
        status="completed" if transcription_status != "partial" else "partial",
        message=f"重新生成纪要与行动项（v{minutes_version}），模型：{model_used}，token：{token_cost}",
        agent_run=serialize_agent_run(db, agent_run),
    )
