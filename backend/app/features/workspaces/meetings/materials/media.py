from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.service import resolve_conflict_path, resolve_workspace_child, safe_name, safe_relative_path
from app.features.workspaces.files.tree import upsert_workspace_file
from app.features.workspaces.meetings.io import notify_meeting_run_finished, write_versioned_latest_markdown
from app.features.workspaces.meetings.markdown import build_transcript_markdown
from app.features.workspaces.meetings.utils import (
    SUPPORTED_MEDIA_EXTENSIONS,
    acquire_meeting_run_lock,
    duration_minutes,
    estimate_media_info,
    release_meeting_run_lock,
)
from app.features.workspaces.schemas import MediaTranscribePreflightRequest, MediaTranscribePreflightResponse, MediaTranscribeResponse
from models.user import User
from models.workspace import Workspace


def preflight_media_transcription(workspace: Workspace, req: MediaTranscribePreflightRequest) -> MediaTranscribePreflightResponse:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持音视频转录")

    ext = Path(req.filename).suffix.lower()
    if ext not in SUPPORTED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持音视频格式：{', '.join(sorted(SUPPORTED_MEDIA_EXTENSIONS))}")

    info = estimate_media_info(req.size_bytes, req.filename)
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


async def transcribe_meeting_media_asset(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    folder_path: str,
    file: UploadFile,
) -> MediaTranscribeResponse:
    filename = (file.filename or "recording").strip()
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_MEDIA_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"仅支持音视频格式：{', '.join(sorted(SUPPORTED_MEDIA_EXTENSIONS))}")

    folder_dir = resolve_workspace_child(root, safe_relative_path(folder_path))
    lock_path = acquire_meeting_run_lock(root, folder_dir, operation="media_transcribe", user_id=user.id)

    try:
        raw_dir = folder_dir / "01-原始资料"
        raw_dir.mkdir(parents=True, exist_ok=True)
        media_path = resolve_conflict_path(raw_dir, safe_name(filename), "keep_both")
        if media_path is None:
            raise HTTPException(status_code=500, detail="无法保存媒体文件")

        content_bytes = await file.read()
        media_path.write_bytes(content_bytes)
        media_rel = media_path.relative_to(root).as_posix()

        duration_min = duration_minutes(media_path)
        if duration_min is not None and duration_min > 30:
            pass

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
        release_meeting_run_lock(lock_path)

    transcript_dir = folder_dir / "02-转录文本"
    transcript_dir.mkdir(parents=True, exist_ok=True)

    if transcription_status == "failed":
        final_md = transcript_text
    else:
        final_md = build_transcript_markdown(
            transcript_text,
            datetime.now(timezone.utc),
            input_type=ext.lstrip("."),
            original_filename=filename,
            transcription_status=transcription_status,
            warnings=warnings_list,
        )

    transcript_files = write_versioned_latest_markdown(
        root=root,
        target_dir=transcript_dir,
        version_filename="transcript-v1.md",
        latest_filename="transcript-latest.md",
        content=final_md,
        resolve_conflict_path=resolve_conflict_path,
        error_detail="无法写入转录文件",
    )

    media_meta = upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        media_rel,
        filename,
        file.content_type or "application/octet-stream",
        len(content_bytes),
        media_path,
    )
    media_meta.rag_status = "pending_transcription" if transcription_status == "failed" else "not_ingested"
    version_meta = upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        transcript_files.version_rel,
        "transcript-v1.md",
        "text/markdown",
        len(final_md.encode("utf-8")),
        transcript_files.version_path,
    )
    latest_meta = upsert_workspace_file(
        db,
        workspace.id,
        user.id,
        transcript_files.latest_rel,
        "transcript-latest.md",
        "text/markdown",
        len(final_md.encode("utf-8")),
        transcript_files.latest_path,
    )
    transcript_rag_status = "failed" if transcription_status == "failed" else "partial" if transcription_status == "partial" else "not_ingested"
    version_meta.rag_status = transcript_rag_status
    latest_meta.rag_status = transcript_rag_status

    write_workspace_audit(
        db,
        user.id,
        "meeting_media_transcribe",
        audit_detail(
            workspace.id,
            folder_path,
            actor_id=user.id,
            media_file=media_rel,
            transcript=transcript_files.version_rel,
            status=transcription_status,
            segments=segment_count,
            gbrain_ingest=False,
        ),
        success=transcription_status != "failed",
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_media_transcribe",
        title="会议音视频转录",
        path=folder_path,
        detail=f"转录：{filename}（{segment_count}段，{transcription_status}）",
        status="failed" if transcription_status == "failed" else "completed",
    )
    notify_meeting_run_finished(
        db,
        workspace=workspace,
        actor_user_id=user.id,
        folder_path=folder_path,
        title="会议音视频转录完成" if transcription_status != "failed" else "会议音视频转录失败",
        status="partial" if transcription_status == "partial" else "failed" if transcription_status == "failed" else "completed",
        detail=f"{filename}：{transcription_status}，生成 {transcript_files.latest_rel}",
    )
    db.commit()
    return MediaTranscribeResponse(
        ok=True,
        meeting_folder_path=folder_path,
        media_path=media_rel,
        transcript_v1_path=transcript_files.version_rel,
        transcript_latest_path=transcript_files.latest_rel,
        transcription_status=transcription_status,
        segment_count=segment_count,
        warnings=warnings_list,
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
        token_cost=token_cost,
    )
