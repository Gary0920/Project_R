from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.utils import serialize_datetime_utc
from app.features.agents.events import serialize_agent_run
from app.features.chat.access import (
    ensure_workspace_access as _ensure_workspace_access,
    get_user_session as _get_user_session,
)
from app.features.chat.audio_transcription_skill import (
    run_audio_transcription_skill_response as _run_audio_transcription_skill_response,
)
from app.features.chat.audio_attachments import (
    is_audio_attachment as _is_audio_attachment,
    is_video_attachment as _is_video_attachment,
)
from app.features.chat.audio_understanding import (
    transcribe_audio_attachments_for_chat as _transcribe_audio_attachments_for_chat,
)
from app.features.chat import feedback_api as chat_feedback_api
from app.features.chat import stream_service as chat_stream
from app.features.chat.export_service import export_session as _export_session
from app.features.chat.intent import IntentType, classify_intent
from app.features.chat.context_trace import (
    build_context_trace,
    generated_file_context,
    gbrain_think_trace,
    safe_trace_list,
    skill_context_extra,
)
from app.features.chat.document_generation import (
    create_generated_output_file as _create_generated_output_file_base,
    write_document_generation_agent_run as _write_document_generation_agent_run_base,
)
from app.features.chat.gbrain_agent_run import write_gbrain_think_agent_run as _write_gbrain_think_agent_run_base
from app.features.chat.message_serialization import (
    attachment_only_prompt as _attachment_only_prompt,
    attachment_to_response_dict as _attachment_to_response_dict,
    message_attachments as _message_attachments,
    message_to_response_dict as _message_to_response_dict_base,
)
from app.features.chat.skill_agent_run import write_skill_agent_run as _write_skill_agent_run_base
from app.features.chat.skill_text import (
    extract_skill_inputs as _extract_skill_inputs,
    missing_input_fields_text as _missing_input_fields_text,
    missing_input_instruction as _missing_input_instruction,
)
from app.features.chat.skill_policy import (
    chat_text_skill_input_payload as _chat_text_skill_input_payload,
    compose_skill_base_prompt as _compose_skill_base_prompt,
    ensure_llm_chat_text_skill_allowed as _ensure_llm_chat_text_skill_allowed,
    load_skill_prompt as _load_skill_prompt_base,
    skill_outputs_chat_text as _skill_outputs_chat_text,
)
from app.features.chat.vision import attach_vision_images_to_latest_user_message as _attach_vision_images_to_latest_user_message
from app.features.chat.web_search_context import (
    maybe_run_web_search as _maybe_run_web_search_base,
    run_web_search_skill as _run_web_search_skill_base,
    web_search_context_extra as _web_search_context_extra,
)
from app.features.chat.schemas import (
    ChatSourceResponse,
    CreateAttachmentRequest,
    CreateSessionRequest,
    EditMessageRequest,
    GBrainThinkReviewRequest,
    GBrainThinkReviewResponse,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
    MessageListResponse,
    MessageResponse,
    RegenerateMessageRequest,
    RestoreMessagesRequest,
    SearchResultResponse,
    SendMessageRequest,
    SessionDetailResponse,
    SessionResponse,
    TransformTextRequest,
    TransformTextResponse,
    UpdateSessionRequest,
)
from app.features.chat.send_message_service import SendMessagePorts, send_message_use_case
from app.features.chat.transform_service import transform_chat_text
from app.shared.llm.client import LLMConfigurationError, LLMProviderError, get_llm_client
from app.features.chat import attachments as session_attachments
from app.features.chat.attachment_routes import router as attachment_router, create_session_attachment, delete_session_attachment, get_session_attachment_content, list_session_attachments, upload_session_attachment
from app.features.chat.constants import (
    ANSWER_CORRECTION_RATING_THRESHOLD,
    ANSWER_CORRECTION_REVIEW_PREFIX,
    GBRAIN_THINK_REVIEW_PREFIX,
    GENERATED_FILES_ROOT,
    GLOBAL_BASE_PROMPT_PATH,
    MESSAGE_FEEDBACK_ROOT,
    SESSION_ATTACHMENT_CLEANUP_INTERVAL,
)
from app.features.chat.knowledge_sources import KNOWLEDGE_SOURCES
from app.features.chat.message_routes import router as message_router, activate_message_version, edit_message, exclude_message_context, regenerate_message, restore_excluded_messages
from app.features.chat.internal import (
    agent_status_for_skill_status as _agent_status_for_skill_status,
    bind_attachments_to_message as _bind_attachments_to_message,
    build_llm_messages as _build_llm_messages,
    build_llm_messages_before as _build_llm_messages_before,
    cleanup_inactive_session_attachments,
    cleanup_inactive_session_attachments_if_due,
    compose_system_prompt as _compose_system_prompt,
    delete_session_attachments as _delete_session_attachments,
    ensure_version_group as _ensure_version_group,
    exclude_active_messages_after as _exclude_active_messages_after,
    is_image_attachment as _is_image_attachment,
    load_attachment_context as _load_attachment_context,
    load_attachment_context_from_attachments as _load_attachment_context_from_attachments,
    load_global_base_prompt as _load_global_base_prompt,
    load_selected_session_attachments as _load_selected_session_attachments,
    load_vision_image_inputs as _load_vision_image_inputs,
    message_llm_content as _message_llm_content,
    message_pair_delete_targets as _message_pair_delete_targets,
    message_query as _message_query,
    message_to_response_dict as _message_to_response_dict_core,
    next_version_index as _next_version_index,
    normalize_vision_image_media_type as _normalize_vision_image_media_type,
    parse_knowledge_command as _parse_knowledge_command,
    safe_event_detail as _safe_event_detail,
    serialize_sources as _serialize_sources,
    set_active_version as _set_active_version,
    write_chat_audit as _write_chat_audit,
    write_failed_assistant_message as _write_failed_assistant_message,
    write_gbrain_think_agent_run as _write_gbrain_think_agent_run,
    write_skill_agent_run as _write_skill_agent_run,
)
from app.features.chat.response_helpers import (
    run_chat_text_skill_by_name as _run_chat_text_skill_by_name_core,
    run_gbrain_think_response as _run_gbrain_think_response_core,
)
from app.features.chat.skill_dispatch import (
    continue_active_skill_run as _continue_active_skill_run_core,
    start_skill_run_by_name as _start_skill_run_by_name_core,
    start_skill_run_from_chat as _start_skill_run_from_chat_core,
    write_skill_assistant_response as _write_skill_assistant_response_core,
)
from app.features.skills.execution import execute_ready_run, generated_file_payload
from app.features.skills.runner import SkillRunner, run_to_dict
from app.features.prompts.system_prompt import (
    DOCUMENT_GENERATION_PROMPT,
    FORMAT_GUIDANCE_PROMPT,
    TEXT_TRANSFORMATION_PROMPT_IDS,
    compose_system_prompt,
    should_reduce_knowledge_context,
)
from models import SessionLocal, get_db
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.message import ChatMessage
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User

router = APIRouter(prefix="/chat", tags=["chat"])
HISTORY_LIMIT = 20
logger = logging.getLogger(__name__)
KNOWLEDGE_COMMAND_PREFIX = "/query"
FILE_COMMAND_FORMATS = {
    "/doc": "docx",
    "/word": "docx",
    "/md": "markdown",
    "/markdown": "markdown",
    "/txt": "txt",
    "/xlsx": "xlsx",
    "/excel": "xlsx",
    "/ppt": "pptx",
    "/pptx": "pptx",
    "/pdf": "pdf",
    "/eml": "eml",
    "/email": "eml",
}
# Local path constants (API-layer specific, not used by feature modules)
BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_ATTACHMENTS_ROOT = BASE_DIR / "session_attachments"
MAX_ATTACHMENT_BYTES = 256 * 1024
MAX_ATTACHMENT_UPLOAD_MB = 20
MAX_ATTACHMENT_UPLOAD_BYTES = MAX_ATTACHMENT_UPLOAD_MB * 1024 * 1024
# Re-exports from feature layer (kept for backward compatibility within this file)
MAX_ATTACHMENT_CONTEXT_CHARS = session_attachments.MAX_ATTACHMENT_CONTEXT_CHARS
VISION_IMAGE_MIME_TYPES = session_attachments.VISION_IMAGE_MIME_TYPES
SESSION_ATTACHMENT_RETENTION_DAYS = session_attachments.SESSION_ATTACHMENT_RETENTION_DAYS
ATTACHMENT_TEXT_EXTENSIONS = session_attachments.ATTACHMENT_TEXT_EXTENSIONS
ATTACHMENT_TEXT_MIME_TYPES = session_attachments.ATTACHMENT_TEXT_MIME_TYPES
router.include_router(message_router)
router.include_router(attachment_router)


@router.post("/sessions", response_model=SessionResponse)
def create_session(
    req: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.workspace_id is not None:
        _ensure_workspace_access(db, user, req.workspace_id)
    session = ChatSession(user_id=user.id, title=req.title, workspace_id=req.workspace_id)
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(
        AuditLog(
            user_id=user.id,
            action="create_session",
            detail=f"创建会话: {session.id}",
            success=True,
        )
    )
    db.commit()
    return session


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    workspace_id: int | None = Query(default=None),
):
    cleanup_inactive_session_attachments_if_due(db)
    q = db.query(ChatSession).filter(
        ChatSession.user_id == user.id,
        ChatSession.is_archived == False,
    )
    if workspace_id:
        q = q.filter(ChatSession.workspace_id == workspace_id)
    sessions = q.order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc()).all()

    if sessions:
        # 单次查询：子查询取每个 session 最新 active 消息
        # 按 created_at DESC, id DESC 排序取最后一条消息，避免版本化消息选错
        all_msgs = (
            db.query(ChatMessage.session_id, ChatMessage.content)
            .filter(
                ChatMessage.session_id.in_([s.id for s in sessions]),
                ChatMessage.is_excluded == False,
                ChatMessage.active_version == True,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .all()
        )
        seen: set[int] = set()
        preview_map: dict[int, str] = {}
        for sid, content in all_msgs:
            if sid in seen:
                continue
            seen.add(sid)
            if content:
                preview_map[sid] = content.replace("\n", " ").strip()[:80]
        for s in sessions:
            s.last_message_preview = preview_map.get(s.id, "")  # type: ignore

    return sessions


@router.get("/sessions/archived", response_model=list[SessionResponse])
def list_archived_sessions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id, ChatSession.is_archived == True)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )


@router.get("/search", response_model=list[SearchResultResponse])
def search_sessions(
    q: str = Query(default="", min_length=1),
    workspace_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pattern = f"%{q.strip()}%"
    session_query = db.query(ChatSession).filter(
        ChatSession.user_id == user.id,
        ChatSession.is_archived == False,
    )
    if workspace_id:
        session_query = session_query.filter(ChatSession.workspace_id == workspace_id)

    sessions = session_query.order_by(ChatSession.updated_at.desc()).all()
    results: list[SearchResultResponse] = []
    for session in sessions:
        matched_message = (
            _message_query(db, user.id, session.id)
            .filter(ChatMessage.content.ilike(pattern))
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .first()
        )
        if q.strip().lower() in session.title.lower() or matched_message:
            results.append(
                SearchResultResponse(
                    id=session.id,
                    title=session.title,
                    workspace_id=session.workspace_id,
                    is_archived=session.is_archived,
                    is_pinned=session.is_pinned,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    matched_message=matched_message.content[:240] if matched_message else None,
                )
            )
    return results

@router.post("/transform", response_model=TransformTextResponse)
def transform_text(
    req: TransformTextRequest,
    user: User = Depends(get_current_user),
):
    try:
        llm_response = transform_chat_text(req, get_llm_client=get_llm_client)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc
    return {
        "ok": True,
        "action": req.action.strip().lower(),
        "text": llm_response.text,
        "provider": llm_response.provider,
        "model": llm_response.model,
        "usage": llm_response.usage,
    }


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    return SessionDetailResponse(
        id=session.id,
        title=session.title,
        workspace_id=session.workspace_id,
        is_archived=session.is_archived,
        is_pinned=session.is_pinned,
        created_at=session.created_at,
        updated_at=session.updated_at,
        message_count=_message_query(db, user.id, session_id).count(),
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    _message_query(db, user.id, session_id, include_excluded=True, include_inactive=True).delete(
        synchronize_session=False
    )
    _delete_session_attachments(db, user.id, session_id)
    db.delete(session)
    db.commit()
    return {"ok": True}


@router.post(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=MessageFeedbackResponse,
)
def submit_message_feedback(
    session_id: int,
    message_id: int,
    req: MessageFeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_feedback_api.submit_message_feedback(
        db,
        session_id,
        message_id,
        req,
        user,
        feedback_root=MESSAGE_FEEDBACK_ROOT,
        answer_correction_rating_threshold=ANSWER_CORRECTION_RATING_THRESHOLD,
        answer_correction_review_prefix=ANSWER_CORRECTION_REVIEW_PREFIX,
    )


@router.post(
    "/sessions/{session_id}/messages/{message_id}/gbrain-think-review",
    response_model=GBrainThinkReviewResponse,
)
def submit_gbrain_think_review(
    session_id: int,
    message_id: int,
    req: GBrainThinkReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_feedback_api.submit_gbrain_think_review(
        db,
        session_id,
        message_id,
        req,
        user,
        gbrain_think_review_prefix=GBRAIN_THINK_REVIEW_PREFIX,
    )


@router.put("/sessions/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: int,
    req: UpdateSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    if req.title is not None:
        title = req.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="会话标题不能为空")
        session.title = title[:256]
    if req.workspace_id is not None:
        _ensure_workspace_access(db, user, req.workspace_id)
        session.workspace_id = req.workspace_id
    if req.is_pinned is not None:
        session.is_pinned = req.is_pinned
    db.commit()
    db.refresh(session)
    return session


@router.post("/sessions/{session_id}/archive")
def archive_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    session.is_archived = True
    db.commit()
    return {"ok": True}


@router.post("/sessions/{session_id}/restore")
def restore_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    session.is_archived = False
    db.commit()
    return {"ok": True}


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
def list_messages(
    session_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_session(db, user.id, session_id)
    query = _message_query(db, user.id, session_id)
    total = query.count()
    items = (
        query.order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return MessageListResponse(
        items=[_message_to_response_dict(db, message) for message in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}/export")
def export_session_route(
    session_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出会话为 Markdown 或 JSON。"""
    session = _get_user_session(db, user.id, session_id)  # 已包含所有权校验
    filename, content = _export_session(db, session, format, user_id=user.id)  # type: ignore
    media_type = "text/markdown" if format == "markdown" else "application/json"
    # 使用 RFC 5987 编码确保非 ASCII 文件名安全，避免 Content-Disposition 参数注入
    # filename*="UTF-8''..." 是现代浏览器标准，`quote` 转义特殊字符
    encoded_filename = quote(filename, safe="")
    # filename="" 作为旧客户端 fallback，仅保留 ASCII 安全字符
    ascii_fallback = re.sub(r'[^\x20-\x7E]', '_', filename)
    ascii_fallback = ascii_fallback.replace('"', "_").replace("\\", "_").replace(";", "_")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}'
        },
    )


def _send_message_ports() -> SendMessagePorts:
    return SendMessagePorts(
        get_user_session=_get_user_session,
        load_selected_session_attachments=_load_selected_session_attachments,
        bind_attachments_to_message=_bind_attachments_to_message,
        parse_knowledge_command=_parse_knowledge_command,
        parse_file_generation_command=_parse_file_generation_command,
        attachment_only_prompt=_attachment_only_prompt,
        classify_intent=classify_intent,
        should_reduce_knowledge_context=_should_reduce_knowledge_context,
        continue_active_skill_run=_continue_active_skill_run,
        write_skill_assistant_response=_write_skill_assistant_response,
        build_context_trace=build_context_trace,
        skill_context_extra=skill_context_extra,
        build_llm_messages=_build_llm_messages,
        run_chat_text_skill_by_name=_run_chat_text_skill_by_name,
        start_skill_run_by_name=_start_skill_run_by_name,
        start_skill_run_from_chat=_start_skill_run_from_chat,
        run_gbrain_think_response=_run_gbrain_think_response,
        is_image_attachment=_is_image_attachment,
        is_audio_attachment=_is_audio_attachment,
        is_video_attachment=_is_video_attachment,
        transcribe_audio_attachments_for_chat=_transcribe_audio_attachments_for_chat,
        get_llm_client=get_llm_client,
        write_failed_assistant_message=_write_failed_assistant_message,
        write_chat_audit=_write_chat_audit,
        load_vision_image_inputs=_load_vision_image_inputs,
        attach_vision_images_to_latest_user_message=_attach_vision_images_to_latest_user_message,
        search_knowledge_sources=_search_knowledge_sources,
        maybe_run_web_search=_maybe_run_web_search,
        serialize_sources=_serialize_sources,
        load_attachment_context_from_attachments=_load_attachment_context_from_attachments,
        compose_system_prompt=_compose_system_prompt,
        web_search_context_extra=_web_search_context_extra,
        generate_sse_stream=chat_stream.generate_sse_stream,
        session_factory=SessionLocal,
        attachment_to_response_dict=_attachment_to_response_dict,
        create_generated_file=_create_generated_file,
        write_document_generation_agent_run=_write_document_generation_agent_run,
        serialize_agent_run=serialize_agent_run,
        llm_configuration_error=LLMConfigurationError,
        llm_provider_error=LLMProviderError,
    )


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: int,
    req: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return send_message_use_case(db, session_id, req, user, ports=_send_message_ports())

def _message_to_response_dict(db: Session, message: ChatMessage) -> dict:
    return _message_to_response_dict_core(db, message, feedback_root=MESSAGE_FEEDBACK_ROOT)

def _parse_file_generation_command(content: str) -> tuple[str | None, str]:
    normalized = content.strip()
    lowered = normalized.lower()
    for command, output_format in FILE_COMMAND_FORMATS.items():
        if lowered == command:
            raise HTTPException(status_code=400, detail="请在文件生成命令后输入要生成的内容要求")
        if lowered.startswith(f"{command} "):
            return output_format, normalized[len(command):].strip()
    return None, ""

def _create_generated_file(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
    *,
    output_format: str,
) -> dict:
    return _create_generated_output_file_base(
        db,
        user_id,
        session_id,
        user_prompt,
        content,
        output_format=output_format,
        generated_files_root=GENERATED_FILES_ROOT,
    )

def _write_document_generation_agent_run(
    db: Session,
    *,
    user_id: int,
    session: ChatSession,
    message_id: int,
    user_prompt: str,
    generated_file: dict,
):
    return _write_document_generation_agent_run_base(
        db,
        user_id=user_id,
        session=session,
        message_id=message_id,
        user_prompt=user_prompt,
        generated_file=generated_file,
        safe_event_detail=_safe_event_detail,
    )


def _start_skill_run_from_chat(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    return _start_skill_run_from_chat_core(db, user_id, session_id, content)


def _start_skill_run_by_name(db: Session, user_id: int, session_id: int, skill_name: str) -> dict | None:
    return _start_skill_run_by_name_core(db, user_id, session_id, skill_name)


def _continue_active_skill_run(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    return _continue_active_skill_run_core(db, user_id, session_id, content)


def _write_skill_assistant_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    skill_response: dict,
    context_trace: dict | None = None,
) -> dict:
    return _write_skill_assistant_response_core(
        db, user_id, session, user_message_id, content, skill_response,
        context_trace=context_trace,
        write_skill_agent_run=_write_skill_agent_run,
        write_chat_audit=_write_chat_audit,
    )




def _run_gbrain_think_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    knowledge_query: str,
    req: SendMessageRequest,
) -> dict:
    return _run_gbrain_think_response_core(
        db,
        user_id,
        session,
        user_message_id,
        content,
        knowledge_query,
        req,
        knowledge_sources=KNOWLEDGE_SOURCES,
        serialize_sources_fn=_serialize_sources,
        write_gbrain_think_agent_run_fn=_write_gbrain_think_agent_run,
        get_llm_client=get_llm_client,
        load_global_base_prompt=_load_global_base_prompt,
        llm_configuration_error=LLMConfigurationError,
        llm_provider_error=LLMProviderError,
    )



def _run_chat_text_skill_by_name(
    db: Session,
    user: User,
    session: ChatSession,
    user_message_id: int,
    content: str,
    req: SendMessageRequest,
    intent: IntentType,
    skill_name: str,
) -> dict | None:
    return _run_chat_text_skill_by_name_core(
        db, user, session, user_message_id, content, req, intent, skill_name,
        skill_outputs_chat_text=_skill_outputs_chat_text,
        ensure_llm_chat_text_skill_allowed=_ensure_llm_chat_text_skill_allowed,
        chat_text_skill_input_payload=_chat_text_skill_input_payload,
        run_audio_transcription_skill_response=_run_audio_transcription_skill_response,
        load_selected_session_attachments=_load_selected_session_attachments,
        write_skill_assistant_response=_write_skill_assistant_response,
        should_reduce_knowledge_context=_should_reduce_knowledge_context,
        search_knowledge_sources=_search_knowledge_sources,
        maybe_run_web_search=_maybe_run_web_search,
        serialize_sources=_serialize_sources,
        load_attachment_context_from_attachments=_load_attachment_context_from_attachments,
        load_skill_prompt=_load_skill_prompt,
        compose_system_prompt=_compose_system_prompt,
        compose_skill_base_prompt=_compose_skill_base_prompt,
        get_llm_client=get_llm_client,
        build_llm_messages=_build_llm_messages,
        write_failed_assistant_message=_write_failed_assistant_message,
        write_chat_audit=_write_chat_audit,
        write_skill_agent_run=_write_skill_agent_run,
        serialize_agent_run=serialize_agent_run,
        build_context_trace=build_context_trace,
        skill_context_extra=skill_context_extra,
        web_search_context_extra=_web_search_context_extra,
        LLMConfigurationError=LLMConfigurationError,
        LLMProviderError=LLMProviderError,
    )
def _load_skill_prompt(skill) -> str:
    return _load_skill_prompt_base(skill, base_dir=BASE_DIR)


def _maybe_run_web_search(
    query: str,
    enabled: bool,
    *,
    source_start_index: int = 1,
) -> tuple[list[dict], str, dict | None]:
    return _maybe_run_web_search_base(
        query,
        enabled,
        source_start_index=source_start_index,
        logger=logger,
        runner=_run_web_search_skill,
    )


def _run_web_search_skill(query: str):
    return _run_web_search_skill_base(query, logger=logger)


def _search_workspace_sources(db: Session, workspace_id: int | None, content: str) -> list[dict]:
    return KNOWLEDGE_SOURCES.search_workspace_sources(db, workspace_id, content)


def _should_reduce_knowledge_context(selected_prompt_id: str | None, forced_knowledge: bool) -> bool:
    return should_reduce_knowledge_context(selected_prompt_id, forced_knowledge)


def _search_knowledge_sources(
    db: Session,
    content: str,
    intent: IntentType,
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



