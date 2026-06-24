"""Internal chat helper functions — extracted from api/chat.py.

These helper functions are used by chat route handlers.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.features.chat import attachment_api as chat_attachment_api
from app.features.chat.attachments import (
    MAX_ATTACHMENT_CONTEXT_CHARS,
    SESSION_ATTACHMENT_RETENTION_DAYS,
    VISION_IMAGE_MIME_TYPES,
)
from app.features.chat.constants import (
    BACKEND_ROOT,
    MESSAGE_FEEDBACK_ROOT,
    SESSION_ATTACHMENT_CLEANUP_INTERVAL,
)
from app.features.chat.gbrain_agent_run import (
    write_gbrain_think_agent_run as _write_gbrain_think_agent_run_base,
)
from app.features.chat.intent import IntentType
from app.features.chat.knowledge_sources import KNOWLEDGE_SOURCES
from app.features.chat.message_serialization import (
    attachment_only_prompt as _attachment_only_prompt,
    message_attachments as _message_attachments,
    message_to_response_dict as _message_to_response_dict_base,
)
from app.features.chat.skill_agent_run import (
    write_skill_agent_run as _write_skill_agent_run_base,
)
from app.features.chat.skill_text import (
    missing_input_instruction as _missing_input_instruction,
)
from app.features.prompts import system_prompt as _system_prompt
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.message import ChatMessage
from models.session import ChatSession

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


# ── Message query / versioning ──────────────────────────────────────────

def message_query(
    db: Session, user_id: int, session_id: int,
    include_excluded: bool = False, include_inactive: bool = False,
):
    query = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
    )
    if not include_excluded:
        query = query.filter(ChatMessage.is_excluded == False)
    if not include_inactive:
        query = query.filter(ChatMessage.active_version == True)
    return query


def message_pair_delete_targets(
    db: Session, user_id: int, session_id: int, message: ChatMessage,
) -> list[ChatMessage]:
    visible = (
        message_query(db, user_id, session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    if not visible:
        return [message]

    target_index = next((index for index, item in enumerate(visible) if item.id == message.id), -1)
    if target_index < 0:
        return [message]

    turn_start = target_index
    while turn_start > 0 and visible[turn_start].role != "user":
        turn_start -= 1

    targets: list[ChatMessage] = []
    for index in range(turn_start, len(visible)):
        item = visible[index]
        if index != turn_start and item.role == "user":
            break
        targets.append(item)
    return targets or [message]


def ensure_version_group(message: ChatMessage) -> str:
    if not message.version_group_id:
        message.version_group_id = str(uuid.uuid4())
    if not message.version_index:
        message.version_index = 1
    return message.version_group_id


def next_version_index(db: Session, message: ChatMessage) -> int:
    group_id = ensure_version_group(message)
    versions = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == message.session_id,
            ChatMessage.user_id == message.user_id,
            ChatMessage.version_group_id == group_id,
        )
        .all()
    )
    return max((item.version_index or 1 for item in versions), default=1) + 1


def message_to_response_dict(db: Session, message: ChatMessage, feedback_root: Path | None = None) -> dict:
    if feedback_root is None:
        feedback_root = MESSAGE_FEEDBACK_ROOT
    return _message_to_response_dict_base(db, message, feedback_root=feedback_root)


def build_llm_messages_before(
    db: Session, user_id: int, session_id: int,
    before_message_id: int,
    extra_tail: list[dict[str, str]] | None = None,
    history_limit: int = HISTORY_LIMIT,
) -> list[dict[str, str]]:
    messages = (
        message_query(db, user_id, session_id)
        .filter(
            ChatMessage.status == "success",
            ChatMessage.role.in_(["user", "assistant"]),
            ChatMessage.id < before_message_id,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(history_limit)
        .all()
    )
    payload = []
    for message in reversed(messages):
        content = message_llm_content(db, message)
        if content:
            payload.append({"role": message.role, "content": content})
    if extra_tail:
        payload.extend(extra_tail)
    return payload


def exclude_active_messages_after(
    db: Session, user_id: int, session_id: int, message_id: int,
) -> list[int]:
    affected = (
        message_query(db, user_id, session_id)
        .filter(ChatMessage.id > message_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    affected_ids = [m.id for m in affected]
    groups = {m.version_group_id for m in affected if m.version_group_id}
    related_versions: list[ChatMessage] = []
    if groups:
        related_versions = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user_id,
                ChatMessage.version_group_id.in_(groups),
            )
            .all()
        )
    for m in [*affected, *related_versions]:
        m.is_excluded = True
        m.active_version = False
    return affected_ids


def set_active_version(db: Session, selected: ChatMessage) -> None:
    group_id = ensure_version_group(selected)
    versions = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == selected.session_id,
            ChatMessage.user_id == selected.user_id,
            ChatMessage.version_group_id == group_id,
            ChatMessage.is_excluded == False,
        )
        .all()
    )
    for version in versions:
        version.active_version = version.id == selected.id


def build_llm_messages(
    db: Session, user_id: int, session_id: int,
    history_limit: int = HISTORY_LIMIT,
) -> list[dict[str, str]]:
    messages = (
        message_query(db, user_id, session_id)
        .filter(ChatMessage.status == "success", ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(history_limit)
        .all()
    )
    payload = []
    for message in reversed(messages):
        content = message_llm_content(db, message)
        if content:
            payload.append({"role": message.role, "content": content})
    return payload


def message_llm_content(db: Session, message: ChatMessage) -> str:
    if message.content:
        return message.content
    if message.role != "user":
        return ""
    return _attachment_only_prompt(_message_attachments(db, message))


def bind_attachments_to_message(
    db: Session, attachments: list[SessionAttachment], message: ChatMessage,
) -> None:
    if not attachments:
        return
    for attachment in attachments:
        attachment.message_id = message.id
    db.commit()
    for attachment in attachments:
        db.refresh(attachment)


def parse_knowledge_command(content: str, prefix: str = "/query") -> tuple[bool, str]:
    stripped = content.strip()
    if stripped == prefix:
        return True, stripped
    if stripped.startswith(f"{prefix} "):
        query = stripped[len(prefix):].strip()
        return True, query or stripped
    return False, stripped


# ── Attachment loading wrappers ──────────────────────────────────────────

def load_attachment_context(
    db: Session, user_id: int, session_id: int, attachment_ids: list[str],
) -> str:
    return chat_attachment_api.load_attachment_context(
        db, user_id, session_id, attachment_ids,
        supports_vision=False, max_chars=MAX_ATTACHMENT_CONTEXT_CHARS, logger=logger,
    )


def load_selected_session_attachments(
    db: Session, user_id: int, session_id: int, attachment_ids: list[str],
) -> list[SessionAttachment]:
    return chat_attachment_api.load_selected_session_attachments(db, user_id, session_id, attachment_ids)


def load_attachment_context_from_attachments(
    attachments: list[SessionAttachment], *, supports_vision: bool,
) -> str:
    return chat_attachment_api.load_attachment_context_from_attachments(
        attachments, supports_vision=supports_vision, max_chars=MAX_ATTACHMENT_CONTEXT_CHARS, logger=logger,
    )


def is_image_attachment(attachment: SessionAttachment) -> bool:
    return chat_attachment_api.is_image_attachment(attachment)


def is_audio_video_attachment(attachment: SessionAttachment) -> bool:
    return chat_attachment_api.is_audio_video_attachment(attachment)


def load_vision_image_inputs(attachments: list[SessionAttachment]) -> list[dict[str, str]]:
    return chat_attachment_api.load_vision_image_inputs(attachments, allowed_mime_types=VISION_IMAGE_MIME_TYPES)


def normalize_vision_image_media_type(attachment: SessionAttachment) -> str:
    return chat_attachment_api.normalize_vision_image_media_type(attachment, allowed_mime_types=VISION_IMAGE_MIME_TYPES)


# ── Agent run wrappers ──────────────────────────────────────────────────

def write_skill_agent_run(
    db: Session, *, user_id: int, session: ChatSession, message_id: int, skill_response: dict,
):
    return _write_skill_agent_run_base(
        db, user_id=user_id, session=session, message_id=message_id,
        skill_response=skill_response,
        safe_event_detail=safe_event_detail,
        missing_input_instruction=_missing_input_instruction,
        agent_status_for_skill_status=agent_status_for_skill_status,
    )


def write_gbrain_think_agent_run(
    db: Session, *, user_id: int, session: ChatSession, message_id: int,
    query: str, think_result: dict, response_sources: list[dict],
):
    return _write_gbrain_think_agent_run_base(
        db, user_id=user_id, session=session, message_id=message_id,
        query=query, think_result=think_result, response_sources=response_sources,
        safe_event_detail=safe_event_detail,
    )


def agent_status_for_skill_status(status: str) -> str:
    if status in {"completed", "failed"}:
        return status
    if status == "collecting_inputs":
        return "waiting"
    return "running"


def safe_event_detail(value: object, limit: int = 240) -> str:
    s = str(value)
    return (s[:limit] + "...") if len(s) > limit else s


# ── Document generation wrappers ─────────────────────────────────────────

def create_generated_docx(
    db: Session, user_id: int, session_id: int, prompt: str, content: str, title: str,
) -> Any:
    from app.features.chat.document_generation import create_generated_docx as _base
    return _base(db, user_id=user_id, session_id=session_id, prompt=prompt, content=content, title=title)


def write_document_generation_agent_run(
    db: Session, user_id: int, session_id: int, doc_id: int, title: str, model: str,
) -> Any:
    from app.features.chat.document_generation import write_document_generation_agent_run as _base
    return _base(db, user_id=user_id, session_id=session_id, doc_id=doc_id, title=title, model=model)


# ── Source serialization ────────────────────────────────────────────────

def serialize_sources(rag_sources: list[dict]) -> list[dict]:
    return [
        {
            "file": source.get("file", ""),
            "source_title": source.get("source_title", ""),
            "section_path": source.get("section_path", ""),
            "content": str(source.get("content", ""))[:600],
            "score": float(source.get("score", 0.0)),
            "source_file": source.get("source_file"),
            "derived_file": source.get("derived_file"),
            "display_title": source.get("display_title"),
            "evidence_excerpt": str(source.get("evidence_excerpt") or "")[:1200] or None,
            "original_source_file": source.get("original_source_file"),
            "locator_label": source.get("locator_label"),
            "metadata_only": bool(source.get("metadata_only")) if source.get("metadata_only") is not None else None,
            "page_slug": source.get("page_slug"),
            "row_num": source.get("row_num"),
            "source_id": source.get("source_id"),
            "source_slug": source.get("source_slug"),
            "source_line": source.get("source_line"),
            "source_page": source.get("source_page"),
            "source_locator": source.get("source_locator"),
        }
        for source in rag_sources
    ]


# ── System prompt composition ────────────────────────────────────────────

def load_global_base_prompt() -> str:
    # Lazy import so tests can monkey-patch constants.GLOBAL_BASE_PROMPT_PATH
    from app.features.chat.constants import GLOBAL_BASE_PROMPT_PATH as _path
    try:
        return _path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def compose_system_prompt(
    base_prompt: str | None,
    rag_sources: list[dict],
    intent: IntentType | None = None,
    attachment_context: str = "",
    reduce_knowledge_context: bool = False,
    *,
    web_search_context: str = "",
) -> str | None:
    return _system_prompt.compose_system_prompt(
        base_prompt,
        rag_sources,
        intent=intent,
        attachment_context=attachment_context,
        reduce_knowledge_context=reduce_knowledge_context,
        global_base_prompt=load_global_base_prompt(),
        web_search_context=web_search_context,
    )


# ── Error handling helpers ──────────────────────────────────────────────

def write_failed_assistant_message(
    db: Session,
    user_id: int,
    session_id: int,
    error_message: str,
    provider: str | None,
) -> None:
    db.add(
        ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content="AI 服务暂时不可用，请稍后重试。",
            provider=provider,
            status="failed",
            error_message=error_message[:1000],
            version_group_id=str(uuid.uuid4()),
        )
    )
    db.commit()


def write_chat_audit(
    db: Session,
    user_id: int,
    session_id: int,
    content: str,
    success: bool,
    detail: str,
    token_cost: int | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action="chat",
            detail=f"会话 {session_id}: {content[:50]}... | {detail}",
            token_cost=token_cost,
            success=success,
        )
    )
    db.commit()


# ── Skill / search wrappers ────────────────────────────────────────────

def load_skill_prompt(skill, base_dir: Path | None = None) -> str:
    from app.features.chat.skill_policy import load_skill_prompt as _base
    return _base(skill, base_dir=base_dir or BACKEND_ROOT)


def search_workspace_sources(db: Session, workspace_id: int | None, content: str) -> list[dict]:
    return KNOWLEDGE_SOURCES.search_workspace_sources(db, workspace_id, content)


def should_reduce_knowledge_context(selected_prompt_id: str | None, forced_knowledge: bool) -> bool:
    from app.features.prompts.system_prompt import should_reduce_knowledge_context as _base
    return _base(selected_prompt_id, forced_knowledge)


def search_knowledge_sources(
    db: Session,
    content: str,
    intent: Any,
    workspace_id: int | None,
    *,
    reduce_knowledge_context: bool = False,
) -> list[dict]:
    return KNOWLEDGE_SOURCES.search(
        db,
        content,
        workspace_id=workspace_id,
        forced_company_query=intent == IntentType.RAG_QUERY,
        reduce_knowledge_context=reduce_knowledge_context,
    )


# ── Attachment helpers (thin wrappers around chat_attachment_api) ────────

def delete_session_attachments(db: Session, user_id: int, session_id: int) -> None:
    chat_attachment_api.delete_session_attachments(db, user_id, session_id)


def cleanup_inactive_session_attachments_if_due(db: Session) -> int:
    return chat_attachment_api.cleanup_inactive_session_attachments_if_due(
        db,
        cleanup_interval=SESSION_ATTACHMENT_CLEANUP_INTERVAL,
        retention_days=SESSION_ATTACHMENT_RETENTION_DAYS,
        logger=logger,
    )


def cleanup_inactive_session_attachments(db: Session | None = None) -> int:
    return chat_attachment_api.cleanup_inactive_session_attachments(
        db,
        retention_days=SESSION_ATTACHMENT_RETENTION_DAYS,
        logger=logger,
    )
