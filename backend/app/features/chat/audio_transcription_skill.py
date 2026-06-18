"""Audio transcription skill helper — extracted from _run_chat_text_skill_by_name."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.chat.audio_attachments import find_audio_attachments
from app.features.chat.context_trace import (
    build_context_trace,
    skill_context_extra,
)
from app.features.chat.intent import IntentType
from app.features.chat.skill_text import (
    format_audio_transcription_reply,
    missing_input_instruction,
)
from app.features.skills.runner import run_to_dict


def run_audio_transcription_skill_response(
    db: Session,
    user: Any,
    session: Any,
    user_message_id: int,
    content: str,
    req: Any,
    run: Any,
    skill: Any,
    *,
    load_selected_attachments: Callable[..., Any],
    write_skill_response: Callable[..., Any],
) -> dict[str, Any]:
    """Handle the audio-transcription special path within a chat text skill run.

    Loads session attachments, finds audio files, runs media transcription,
    and returns the complete skill response dict.

    Returns the same shape as _run_chat_text_skill_by_name for the
    audio-transcription case.
    """
    from app.features.preprocessing.tools.media_transcription import (  # noqa: PLC0415
        MediaTranscriptionToolInput,
        run_media_transcription_tool,
    )

    selected_attachments = load_selected_attachments(db, user.id, session.id, req.files)
    audio_attachments = find_audio_attachments(selected_attachments)

    if not audio_attachments:
        instruction = missing_input_instruction(
            "audio-transcription",
            [{"name": "audio_source", "label": "音频或视频文件"}],
        )
        skill_response: dict[str, Any] = {
            "reply": (
                "还不能开始录音转文字，因为当前消息没有可处理的音频附件。\n\n"
                f"下一步操作：\n```text\n{instruction}\n```"
            ),
            "skill_run": run_to_dict(run, skill),
            "generated_file": None,
        }
        return write_skill_response(
            db,
            user.id,
            session,
            user_message_id,
            content,
            skill_response,
            context_trace=build_context_trace(
                session=session,
                req=req,
                attachments=selected_attachments,
                sources=[],
                intent=IntentType.SKILL_TRIGGER,
                provider="project_r",
                model="audio-transcription",
                requested_model=req.model_profile or req.provider,
                extra=skill_context_extra(skill_response),
            ),
        )

    audio_path = Path(audio_attachments[0].stored_path)
    reply_extra = (
        "\n\n> 注意：检测到多个音频文件，只处理第一个。"
        if len(audio_attachments) > 1
        else ""
    )

    try:
        tool_result = run_media_transcription_tool(
            MediaTranscriptionToolInput(media_path=audio_path)
        )
        reply = format_audio_transcription_reply(tool_result.text, reply_extra=reply_extra)
    except Exception as exc:
        reply = f"转录失败：{exc}\n\n请检查音频文件是否有效。"

    skill_response = {
        "reply": reply,
        "skill_run": run_to_dict(run, skill),
        "generated_file": None,
    }
    return write_skill_response(
        db,
        user.id,
        session,
        user_message_id,
        content,
        skill_response,
        context_trace=build_context_trace(
            session=session,
            req=req,
            attachments=selected_attachments,
            sources=[],
            intent=IntentType.SKILL_TRIGGER,
            provider="project_r",
            model="audio-transcription",
            requested_model=req.model_profile or req.provider,
            extra=skill_context_extra(skill_response),
        ),
    )
