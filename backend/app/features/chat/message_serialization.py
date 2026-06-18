from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.features.agents.events import get_agent_run_for_message, serialize_agent_run
from app.features.chat import feedback_api as chat_feedback_api
from app.shared.time.utils import serialize_datetime_utc
from models.attachment import SessionAttachment
from models.message import ChatMessage


def attachment_to_response_dict(attachment: SessionAttachment) -> dict:
    return {
        "id": attachment.id,
        "session_id": attachment.session_id,
        "message_id": attachment.message_id,
        "original_name": attachment.original_name,
        "content_type": attachment.content_type,
        "size": attachment.size,
        "source_scope": attachment.source_scope,
        "source_label": attachment.source_label,
        "authorization_status": attachment.authorization_status,
        "created_at": serialize_datetime_utc(attachment.created_at),
    }


def message_versions(db: Session, message: ChatMessage) -> list[ChatMessage]:
    if not message.version_group_id:
        return [message]
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == message.session_id,
            ChatMessage.user_id == message.user_id,
            ChatMessage.version_group_id == message.version_group_id,
            ChatMessage.is_excluded == False,
        )
        .order_by(ChatMessage.version_index.asc(), ChatMessage.id.asc())
        .all()
    )


def message_attachments(db: Session, message: ChatMessage) -> list[SessionAttachment]:
    return (
        db.query(SessionAttachment)
        .filter(
            SessionAttachment.session_id == message.session_id,
            SessionAttachment.user_id == message.user_id,
            SessionAttachment.message_id == message.id,
        )
        .order_by(SessionAttachment.created_at.asc(), SessionAttachment.id.asc())
        .all()
    )


def message_to_response_dict(db: Session, message: ChatMessage, *, feedback_root: Path) -> dict:
    versions = message_versions(db, message)
    feedback = chat_feedback_api.load_latest_message_feedback(db, feedback_root, message)
    attachments = message_attachments(db, message)
    agent_run = get_agent_run_for_message(db, message.user_id, message.id)
    serialized_agent_run = serialize_agent_run(db, agent_run)
    agent_result = serialized_agent_run.get("result", {}) if serialized_agent_run else {}
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "provider": message.provider,
        "model": message.model,
        "token_input": message.token_input,
        "token_output": message.token_output,
        "token_total": message.token_total,
        "status": message.status,
        "error_message": message.error_message,
        "rag_used": message.rag_used,
        "is_excluded": message.is_excluded,
        "version_group_id": message.version_group_id,
        "version_index": message.version_index or 1,
        "version_count": len(versions),
        "active_version": message.active_version,
        "versions": [
            {
                "id": version.id,
                "content": version.content,
                "provider": version.provider,
                "model": version.model,
                "version_index": version.version_index or 1,
                "active_version": version.active_version,
                "created_at": serialize_datetime_utc(version.created_at),
            }
            for version in versions
        ],
        "feedback": feedback.get("feedback") if feedback else None,
        "feedback_rating": feedback.get("rating") if feedback else None,
        "feedback_comment": feedback.get("comment") if feedback else None,
        "sources": message.sources,
        "attachments": [attachment_to_response_dict(attachment) for attachment in attachments],
        "generated_file": agent_result.get("generated_file"),
        "skill_run": agent_result.get("skill_run"),
        "agent_run": serialized_agent_run,
        "context_trace": message.context_trace,
        "created_at": serialize_datetime_utc(message.created_at),
    }


def attachment_only_prompt(attachments: list[SessionAttachment]) -> str:
    if not attachments:
        return ""
    names = "、".join(attachment.original_name for attachment in attachments[:6])
    suffix = "等附件" if len(attachments) > 6 else "附件"
    return f"请根据本轮上传的{suffix}回答。附件：{names}"
