from datetime import datetime, timedelta, timezone
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.utils import serialize_datetime_utc
from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run, serialize_agent_run
from app.features.chat.access import (
    ensure_workspace_access as _ensure_workspace_access,
    get_user_session as _get_user_session,
)
from app.features.chat import attachment_api as chat_attachment_api
from app.features.chat import feedback_api as chat_feedback_api
from app.features.chat.intent import IntentType, classify_intent
from app.features.chat.context_trace import (
    build_context_trace,
    generated_file_context,
    gbrain_think_trace,
    safe_trace_list,
    skill_context_extra,
)
from app.features.chat.document_generation import (
    create_generated_docx as _create_generated_docx_base,
    safe_document_title as _safe_document_title,
    write_document_generation_agent_run as _write_document_generation_agent_run_base,
)
from app.features.chat.message_serialization import (
    attachment_only_prompt as _attachment_only_prompt,
    attachment_to_response_dict as _attachment_to_response_dict,
    message_attachments as _message_attachments,
    message_to_response_dict as _message_to_response_dict_base,
)
from app.features.chat.skill_text import (
    extract_skill_inputs as _extract_skill_inputs,
    format_audio_transcription_reply as _format_audio_transcription_reply,
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
    ActivateMessageVersionResponse,
    AttachmentResponse,
    ChatSourceResponse,
    CreateAttachmentRequest,
    CreateSessionRequest,
    EditMessageRequest,
    EditMessageResponse,
    GBrainThinkReviewRequest,
    GBrainThinkReviewResponse,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
    MessageListResponse,
    MessageResponse,
    RegenerateMessageRequest,
    RegenerateMessageResponse,
    RestoreMessagesRequest,
    RestoreMessagesResponse,
    SearchResultResponse,
    SendMessageRequest,
    SessionDetailResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from app.features.knowledge.sources import KnowledgeSources
from app.shared.llm.client import LLMConfigurationError, LLMProviderError, get_llm_client
from app.features.chat import attachments as session_attachments
from app.features.skills.execution import execute_ready_run, generated_file_payload
from app.features.skills.runner import SkillRunner, run_to_dict
from app.features.prompts.system_prompt import (
    DOCUMENT_GENERATION_PROMPT,
    FORMAT_GUIDANCE_PROMPT,
    TEXT_TRANSFORMATION_PROMPT_IDS,
    compose_system_prompt,
    should_reduce_knowledge_context,
)
from models import get_db
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
BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_ATTACHMENTS_ROOT = BASE_DIR / "session_attachments"
GLOBAL_BASE_PROMPT_PATH = BASE_DIR / "prompt_presets" / "global-base-prompt.md"
MAX_ATTACHMENT_BYTES = 256 * 1024
MAX_ATTACHMENT_UPLOAD_MB = 20
MAX_ATTACHMENT_UPLOAD_BYTES = MAX_ATTACHMENT_UPLOAD_MB * 1024 * 1024
MAX_ATTACHMENT_CONTEXT_CHARS = session_attachments.MAX_ATTACHMENT_CONTEXT_CHARS
VISION_IMAGE_MIME_TYPES = session_attachments.VISION_IMAGE_MIME_TYPES
SESSION_ATTACHMENT_RETENTION_DAYS = session_attachments.SESSION_ATTACHMENT_RETENTION_DAYS
SESSION_ATTACHMENT_CLEANUP_INTERVAL = timedelta(hours=6)
ATTACHMENT_TEXT_EXTENSIONS = session_attachments.ATTACHMENT_TEXT_EXTENSIONS
ATTACHMENT_TEXT_MIME_TYPES = session_attachments.ATTACHMENT_TEXT_MIME_TYPES
GENERATED_FILES_ROOT = Path(os.getenv("GENERATED_FILES_PATH", str(BASE_DIR / "generated_files")))
MESSAGE_FEEDBACK_ROOT = Path(
    os.getenv("MESSAGE_FEEDBACK_PATH", str(BASE_DIR / "feedback_data" / "message_ratings"))
)
ANSWER_CORRECTION_REVIEW_PREFIX = "gbrain_answer_correction:message:"
GBRAIN_THINK_REVIEW_PREFIX = "gbrain_think_review:message:"
ANSWER_CORRECTION_RATING_THRESHOLD = 2
KNOWLEDGE_SOURCES = KnowledgeSources()


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
    return q.order_by(ChatSession.is_pinned.desc(), ChatSession.updated_at.desc()).all()


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


@router.delete("/sessions/{session_id}/messages/{message_id}")
def exclude_message_context(
    session_id: int,
    message_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    message = (
        _message_query(db, user.id, session_id)
        .filter(ChatMessage.id == message_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")

    affected_messages = _message_pair_delete_targets(db, user.id, session_id, message)
    affected_ids = [item.id for item in affected_messages]
    groups = {item.version_group_id for item in affected_messages if item.version_group_id}
    if groups:
        affected_messages.extend(
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user.id,
                ChatMessage.version_group_id.in_(groups),
            )
            .all()
        )
    for item in affected_messages:
        item.is_excluded = True
        item.active_version = False
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="exclude_message_context",
            detail=f"排除会话 {session_id} 中消息 {message_id} 对应问答: {affected_ids}",
            success=True,
        )
    )
    db.commit()
    return {"ok": True, "excluded_message_ids": affected_ids}


@router.post("/sessions/{session_id}/messages/restore", response_model=RestoreMessagesResponse)
def restore_excluded_messages(
    session_id: int,
    req: RestoreMessagesRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    requested_ids = {int(message_id) for message_id in req.message_ids if int(message_id) > 0}
    if not requested_ids:
        raise HTTPException(status_code=400, detail="缺少可恢复的消息")

    messages = (
        _message_query(db, user.id, session_id, include_excluded=True, include_inactive=True)
        .filter(ChatMessage.id.in_(requested_ids))
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="可恢复的消息不存在")

    groups = {message.version_group_id for message in messages if message.version_group_id}
    related_versions: list[ChatMessage] = []
    if groups:
        related_versions = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.user_id == user.id,
                ChatMessage.version_group_id.in_(groups),
            )
            .all()
        )

    for item in [*messages, *related_versions]:
        item.is_excluded = False
        if item.id in requested_ids:
            item.active_version = True
        elif item.version_group_id in groups:
            item.active_version = False
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="restore_message_context",
            detail=f"恢复会话 {session_id} 消息: {sorted(requested_ids)}",
            success=True,
        )
    )
    db.commit()

    restored = (
        _message_query(db, user.id, session_id)
        .filter(ChatMessage.id.in_(requested_ids))
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    return {
        "ok": True,
        "restored_message_ids": [message.id for message in restored],
        "messages": [_message_to_response_dict(db, message) for message in restored],
    }


@router.post(
    "/sessions/{session_id}/messages/{message_id}/regenerate",
    response_model=RegenerateMessageResponse,
)
def regenerate_message(
    session_id: int,
    message_id: int,
    req: RegenerateMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    target = (
        _message_query(db, user.id, session_id)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "assistant")
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="可重生成的回答不存在")

    llm_messages = _build_llm_messages_before(db, user.id, session_id, target.id)
    if not llm_messages:
        raise HTTPException(status_code=400, detail="缺少可用于重生成的上文")

    requested_model = req.model_profile or req.provider or target.provider
    web_search_query = next(
        (str(message.get("content") or "") for message in reversed(llm_messages) if message.get("role") == "user"),
        target.content,
    )
    web_sources, web_search_context, web_search_trace = _maybe_run_web_search(
        web_search_query,
        req.web_search,
    )
    response_sources = _serialize_sources(web_sources)
    system_prompt = req.system_prompt
    if req.web_search:
        system_prompt = _compose_system_prompt(
            req.system_prompt,
            [],
            IntentType.CHAT,
            "",
            False,
            web_search_context=web_search_context,
        )
    try:
        llm_response = get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
            temperature=req.temperature,
        )
    except LLMConfigurationError as exc:
        _write_chat_audit(db, user.id, session_id, target.content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _write_chat_audit(db, user.id, session_id, target.content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    group_id = _ensure_version_group(target)
    next_index = _next_version_index(db, target)
    target.active_version = False
    excluded_ids = _exclude_active_messages_after(db, user.id, session_id, target.id)
    usage = llm_response.usage
    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=user.id,
        role="assistant",
        content=llm_response.text,
        provider=llm_response.provider,
        model=llm_response.model,
        token_input=usage.get("input_tokens", 0),
        token_output=usage.get("output_tokens", 0),
        token_total=llm_response.token_cost,
        status="success",
        rag_used=bool(response_sources) if req.web_search else target.rag_used,
        sources_json=json.dumps(response_sources, ensure_ascii=False) if req.web_search else target.sources_json,
        context_json=json.dumps(
            build_context_trace(
                session=session,
                req=req,
                attachments=[],
                sources=response_sources,
                intent=IntentType.CHAT,
                provider=llm_response.provider,
                model=llm_response.model,
                requested_model=requested_model,
                extra=_web_search_context_extra(web_search_trace),
            ),
            ensure_ascii=False,
        )
        if req.web_search
        else "{}",
        version_group_id=group_id,
        version_index=next_index,
        active_version=True,
        created_at=target.created_at,
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="regenerate_message",
            detail=f"重生成会话 {session_id} 回答 {message_id}，版本 {next_index}",
            token_cost=llm_response.token_cost,
            success=True,
        )
    )
    db.commit()
    db.refresh(assistant_message)
    return {
        "ok": True,
        "assistant_message": _message_to_response_dict(db, assistant_message),
        "excluded_message_ids": excluded_ids,
        "usage": usage,
    }


@router.put("/sessions/{session_id}/messages/{message_id}/edit", response_model=EditMessageResponse)
def edit_message(
    session_id: int,
    message_id: int,
    req: EditMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    target = (
        _message_query(db, user.id, session_id)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "user")
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="可编辑的提问不存在")

    llm_messages = _build_llm_messages_before(
        db,
        user.id,
        session_id,
        target.id,
        extra_tail=[{"role": "user", "content": content}],
    )
    requested_model = req.model_profile or req.provider
    web_sources, web_search_context, web_search_trace = _maybe_run_web_search(
        content,
        req.web_search,
    )
    response_sources = _serialize_sources(web_sources)
    system_prompt = req.system_prompt
    if req.web_search:
        system_prompt = _compose_system_prompt(
            req.system_prompt,
            [],
            IntentType.CHAT,
            "",
            False,
            web_search_context=web_search_context,
        )
    try:
        llm_response = get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        _write_chat_audit(db, user.id, session_id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _write_chat_audit(db, user.id, session_id, content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    group_id = _ensure_version_group(target)
    next_index = _next_version_index(db, target)
    target.active_version = False
    excluded_ids = _exclude_active_messages_after(db, user.id, session_id, target.id)
    user_message = ChatMessage(
        session_id=session_id,
        user_id=user.id,
        role="user",
        content=content,
        status="success",
        version_group_id=group_id,
        version_index=next_index,
        active_version=True,
        created_at=target.created_at,
    )
    usage = llm_response.usage
    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=user.id,
        role="assistant",
        content=llm_response.text,
        provider=llm_response.provider,
        model=llm_response.model,
        token_input=usage.get("input_tokens", 0),
        token_output=usage.get("output_tokens", 0),
        token_total=llm_response.token_cost,
        status="success",
        rag_used=bool(response_sources),
        sources_json=json.dumps(response_sources, ensure_ascii=False),
        context_json=json.dumps(
            build_context_trace(
                session=session,
                req=req,
                attachments=[],
                sources=response_sources,
                intent=IntentType.CHAT,
                provider=llm_response.provider,
                model=llm_response.model,
                requested_model=requested_model,
                extra=_web_search_context_extra(web_search_trace),
            ),
            ensure_ascii=False,
        )
        if req.web_search
        else "{}",
        version_group_id=str(uuid.uuid4()),
    )
    db.add(user_message)
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="edit_message_branch",
            detail=f"编辑会话 {session_id} 提问 {message_id}，新版本 {next_index}，排除后续 {excluded_ids}",
            token_cost=llm_response.token_cost,
            success=True,
        )
    )
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    return {
        "ok": True,
        "user_message": _message_to_response_dict(db, user_message),
        "assistant_message": _message_to_response_dict(db, assistant_message),
        "excluded_message_ids": excluded_ids,
        "usage": usage,
    }


@router.post(
    "/sessions/{session_id}/messages/{message_id}/versions/{version_id}/activate",
    response_model=ActivateMessageVersionResponse,
)
def activate_message_version(
    session_id: int,
    message_id: int,
    version_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    current = (
        _message_query(db, user.id, session_id, include_inactive=True)
        .filter(ChatMessage.id == message_id)
        .first()
    )
    selected = (
        _message_query(db, user.id, session_id, include_inactive=True)
        .filter(ChatMessage.id == version_id)
        .first()
    )
    if not current or not selected:
        raise HTTPException(status_code=404, detail="消息版本不存在")
    if not current.version_group_id or current.version_group_id != selected.version_group_id:
        raise HTTPException(status_code=400, detail="消息版本不属于同一组")

    _set_active_version(db, selected)
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="activate_message_version",
            detail=f"切换会话 {session_id} 消息 {message_id} 到版本 {version_id}",
            success=True,
        )
    )
    db.commit()
    db.refresh(selected)
    return {"ok": True, "message": _message_to_response_dict(db, selected)}


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


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: int,
    req: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_user_session(db, user.id, session_id)
    content = req.content.strip()
    selected_attachments = _load_selected_session_attachments(db, user.id, session_id, req.files)
    if not content and not selected_attachments:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    requested_model = req.model_profile or req.provider

    user_message = ChatMessage(
        session_id=session_id,
        user_id=user.id,
        role="user",
        content=content,
        status="success",
        version_group_id=str(uuid.uuid4()),
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)
    _bind_attachments_to_message(db, selected_attachments, user_message)

    forced_knowledge, knowledge_query = _parse_knowledge_command(content)
    if req.force_knowledge_query:
        forced_knowledge = True
        knowledge_query = content
    llm_user_content = content or _attachment_only_prompt(selected_attachments)
    query_content = knowledge_query or llm_user_content
    intent = classify_intent(query_content)
    effective_intent = IntentType.RAG_QUERY if forced_knowledge else intent.intent
    reduce_knowledge_context = _should_reduce_knowledge_context(req.selected_prompt_id, forced_knowledge)
    if reduce_knowledge_context and effective_intent == IntentType.RAG_QUERY:
        effective_intent = IntentType.CHAT

    active_skill_response = None
    if effective_intent != IntentType.DOCUMENT_GENERATION and not req.selected_skill:
        active_skill_response = _continue_active_skill_run(db, user.id, session_id, llm_user_content)
    if active_skill_response:
        return _write_skill_assistant_response(
            db,
            user.id,
            session,
            user_message.id,
            content,
            active_skill_response,
            context_trace=build_context_trace(
                session=session,
                req=req,
                attachments=selected_attachments,
                sources=[],
                intent=effective_intent,
                provider="project_r",
                model="skill_runner",
                requested_model=requested_model,
                extra=skill_context_extra(active_skill_response),
            ),
        )

    llm_messages = _build_llm_messages(db, user.id, session_id)
    if req.selected_skill and effective_intent != IntentType.DOCUMENT_GENERATION:
        chat_text_response = _run_chat_text_skill_by_name(
            db,
            user,
            session,
            user_message.id,
            content,
            req,
            effective_intent,
            req.selected_skill,
        )
        if chat_text_response:
            return chat_text_response
        skill_response = _start_skill_run_by_name(db, user.id, session_id, req.selected_skill)
        if skill_response:
            return _write_skill_assistant_response(
                db,
                user.id,
                session,
                user_message.id,
                content,
                skill_response,
                context_trace=build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=skill_context_extra(skill_response),
                ),
            )
    if effective_intent == IntentType.SKILL_TRIGGER:
        matched_skill = SkillRunner.get().match_skill(content)
        if matched_skill:
            chat_text_response = _run_chat_text_skill_by_name(
                db,
                user,
                session,
                user_message.id,
                content,
                req,
                effective_intent,
                matched_skill["skill"]["name"],
            )
            if chat_text_response:
                return chat_text_response
        skill_response = _start_skill_run_from_chat(db, user.id, session_id, content)
        if skill_response:
            return _write_skill_assistant_response(
                db,
                user.id,
                session,
                user_message.id,
                content,
                skill_response,
                context_trace=build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=skill_context_extra(skill_response),
                ),
            )

    if forced_knowledge:
        return _run_gbrain_think_response(
            db,
            user.id,
            session,
            user_message.id,
            content,
            query_content,
        )

    selected_image_attachments = [attachment for attachment in selected_attachments if _is_image_attachment(attachment)]
    selected_audio_video_attachments = [
        attachment for attachment in selected_attachments if _is_audio_video_attachment(attachment)
    ]
    if selected_audio_video_attachments and not req.selected_skill:
        matched_skill = SkillRunner.get().match_skill(content)
        if matched_skill and matched_skill["skill"]["name"] == "audio-transcription":
            chat_text_response = _run_chat_text_skill_by_name(
                db,
                user,
                session,
                user_message.id,
                content,
                req,
                IntentType.SKILL_TRIGGER,
                "audio-transcription",
            )
            if chat_text_response:
                return chat_text_response

    try:
        llm_client = get_llm_client(requested_model)
    except LLMConfigurationError as exc:
        _write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc

    supports_vision = bool(getattr(getattr(llm_client, "settings", None), "supports_vision", False))
    if selected_image_attachments and not supports_vision:
        detail = "当前模型不支持图片理解，请切换到支持图像输入的 MiMo 模型后再发送。"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    if selected_audio_video_attachments:
        detail = "当前版本暂未接入视频/音频附件理解，请先改用图片或可提取文本的附件。"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    try:
        vision_images = _load_vision_image_inputs(selected_image_attachments) if selected_image_attachments else []
    except HTTPException as exc:
        detail = str(exc.detail)
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise
    if vision_images:
        llm_messages = _attach_vision_images_to_latest_user_message(
            llm_messages,
            vision_images,
            getattr(llm_client.settings, "provider", ""),
        )
    knowledge_sources = _search_knowledge_sources(
        db,
        query_content,
        effective_intent,
        session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    web_sources, web_search_context, web_search_trace = _maybe_run_web_search(
        query_content,
        req.web_search,
        source_start_index=len(knowledge_sources) + 1,
    )
    response_sources = _serialize_sources([*knowledge_sources, *web_sources])
    attachment_context = _load_attachment_context_from_attachments(selected_attachments, supports_vision=bool(vision_images))
    system_prompt = _compose_system_prompt(
        req.system_prompt,
        knowledge_sources,
        effective_intent,
        attachment_context,
        reduce_knowledge_context,
        web_search_context=web_search_context,
    )

    try:
        llm_response = llm_client.complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        _write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    usage = llm_response.usage
    generated_file = None
    if effective_intent == IntentType.DOCUMENT_GENERATION:
        generated_file = _create_generated_docx(db, user.id, session_id, content, llm_response.text)
    context_trace = build_context_trace(
        session=session,
        req=req,
        attachments=selected_attachments,
        sources=response_sources,
        intent=effective_intent,
        provider=llm_response.provider,
        model=llm_response.model,
        requested_model=requested_model,
        reduce_knowledge_context=reduce_knowledge_context,
        extra={
            "generated_file": generated_file_context(generated_file),
            **_web_search_context_extra(web_search_trace),
        },
    )
    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=user.id,
        role="assistant",
        content=llm_response.text,
        provider=llm_response.provider,
        model=llm_response.model,
        token_input=usage.get("input_tokens", 0),
        token_output=usage.get("output_tokens", 0),
        token_total=llm_response.token_cost,
        status="success",
        rag_used=bool(response_sources),
        sources_json=json.dumps(response_sources, ensure_ascii=False),
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    agent_run = None
    if generated_file:
        agent_run = _write_document_generation_agent_run(
            db,
            user_id=user.id,
            session=session,
            message_id=assistant_message.id,
            user_prompt=content,
            generated_file=generated_file,
        )
        db.commit()

    _write_chat_audit(
        db,
        user.id,
        session_id,
        llm_user_content,
        True,
        f"provider={llm_response.provider}, model={llm_response.model}, key_index={llm_response.key_index}",
        token_cost=llm_response.token_cost,
    )

    return {
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
        "reply": llm_response.text,
        "provider": llm_response.provider,
        "model": llm_response.model,
        "key_index": llm_response.key_index,
        "usage": llm_response.usage,
        "intent": effective_intent.value,
        "sources": response_sources,
        "generated_file": generated_file,
        "skill_run": None,
        "user_attachments": [_attachment_to_response_dict(attachment) for attachment in selected_attachments],
        "agent_run": serialize_agent_run(db, agent_run),
        "context_trace": context_trace,
    }


@router.post("/sessions/{session_id}/attachments", response_model=AttachmentResponse)
def create_session_attachment(
    session_id: int,
    req: CreateAttachmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_attachment_api.create_session_attachment(
        db,
        session_id,
        req,
        user,
        max_attachment_bytes=MAX_ATTACHMENT_BYTES,
        attachment_root=SESSION_ATTACHMENTS_ROOT,
        logger=logger,
    )


@router.post("/sessions/{session_id}/attachments/upload", response_model=AttachmentResponse)
async def upload_session_attachment(
    session_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    source_scope: str = Form("session_upload"),
    source_label: str = Form("会话临时上传"),
    authorization_status: str = Form("uploaded"),
):
    return await chat_attachment_api.upload_session_attachment(
        db,
        session_id,
        file,
        user,
        source_scope=source_scope,
        source_label=source_label,
        authorization_status=authorization_status,
        max_upload_bytes=MAX_ATTACHMENT_UPLOAD_BYTES,
        max_upload_mb=MAX_ATTACHMENT_UPLOAD_MB,
        attachment_root=SESSION_ATTACHMENTS_ROOT,
        logger=logger,
    )


def _store_session_attachment(
    db: Session,
    user: User,
    session_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    source_scope: str = "session_upload",
    source_label: str = "会话临时上传",
    authorization_status: str = "uploaded",
) -> SessionAttachment:
    return chat_attachment_api.store_session_attachment(
        db,
        user,
        session_id,
        filename,
        content_type,
        content,
        attachment_root=SESSION_ATTACHMENTS_ROOT,
        logger=logger,
        source_scope=source_scope,
        source_label=source_label,
        authorization_status=authorization_status,
    )


def _get_user_session_attachment(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_id: int,
) -> SessionAttachment:
    return chat_attachment_api.get_user_session_attachment(db, user_id, session_id, attachment_id)


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
def list_session_attachments(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_attachment_api.list_session_attachments(db, session_id, user)


@router.get("/sessions/{session_id}/attachments/{attachment_id}/content")
def get_session_attachment_content(
    session_id: int,
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_attachment_api.get_session_attachment_content(db, session_id, attachment_id, user)


@router.delete("/sessions/{session_id}/attachments/{attachment_id}")
def delete_session_attachment(
    session_id: int,
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return chat_attachment_api.delete_session_attachment(db, session_id, attachment_id, user)


def _message_query(
    db: Session,
    user_id: int,
    session_id: int,
    include_excluded: bool = False,
    include_inactive: bool = False,
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


def _message_pair_delete_targets(
    db: Session,
    user_id: int,
    session_id: int,
    message: ChatMessage,
) -> list[ChatMessage]:
    visible = (
        _message_query(db, user_id, session_id)
        .filter(ChatMessage.id >= message.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )
    if not visible:
        return [message]
    if message.role != "user":
        return [message]

    targets: list[ChatMessage] = []
    for item in visible:
        if item.id != message.id and item.role == "user":
            break
        targets.append(item)
    return targets or [message]


def _ensure_version_group(message: ChatMessage) -> str:
    if not message.version_group_id:
        message.version_group_id = str(uuid.uuid4())
    if not message.version_index:
        message.version_index = 1
    return message.version_group_id


def _next_version_index(db: Session, message: ChatMessage) -> int:
    group_id = _ensure_version_group(message)
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


def _message_to_response_dict(db: Session, message: ChatMessage) -> dict:
    return _message_to_response_dict_base(db, message, feedback_root=MESSAGE_FEEDBACK_ROOT)


def _build_llm_messages_before(
    db: Session,
    user_id: int,
    session_id: int,
    before_message_id: int,
    extra_tail: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    messages = (
        _message_query(db, user_id, session_id)
        .filter(
            ChatMessage.status == "success",
            ChatMessage.role.in_(["user", "assistant"]),
            ChatMessage.id < before_message_id,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    payload = []
    for message in reversed(messages):
        content = _message_llm_content(db, message)
        if content:
            payload.append({"role": message.role, "content": content})
    if extra_tail:
        payload.extend(extra_tail)
    return payload


def _exclude_active_messages_after(
    db: Session,
    user_id: int,
    session_id: int,
    message_id: int,
) -> list[int]:
    affected = (
        _message_query(db, user_id, session_id)
        .filter(ChatMessage.id > message_id)
        .order_by(ChatMessage.id.asc())
        .all()
    )
    affected_ids = [message.id for message in affected]
    groups = {message.version_group_id for message in affected if message.version_group_id}
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
    for message in [*affected, *related_versions]:
        message.is_excluded = True
        message.active_version = False
    return affected_ids


def _set_active_version(db: Session, selected: ChatMessage) -> None:
    group_id = _ensure_version_group(selected)
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


def _build_llm_messages(db: Session, user_id: int, session_id: int) -> list[dict[str, str]]:
    messages = (
        _message_query(db, user_id, session_id)
        .filter(ChatMessage.status == "success", ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    payload = []
    for message in reversed(messages):
        content = _message_llm_content(db, message)
        if content:
            payload.append({"role": message.role, "content": content})
    return payload


def _message_llm_content(db: Session, message: ChatMessage) -> str:
    if message.content:
        return message.content
    if message.role != "user":
        return ""
    return _attachment_only_prompt(_message_attachments(db, message))


def _bind_attachments_to_message(
    db: Session,
    attachments: list[SessionAttachment],
    message: ChatMessage,
) -> None:
    if not attachments:
        return
    for attachment in attachments:
        attachment.message_id = message.id
    db.commit()
    for attachment in attachments:
        db.refresh(attachment)


def _parse_knowledge_command(content: str) -> tuple[bool, str]:
    stripped = content.strip()
    if stripped == KNOWLEDGE_COMMAND_PREFIX:
        return True, stripped
    if stripped.startswith(f"{KNOWLEDGE_COMMAND_PREFIX} "):
        query = stripped[len(KNOWLEDGE_COMMAND_PREFIX) :].strip()
        return True, query or stripped
    return False, stripped


def _load_attachment_context(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> str:
    return chat_attachment_api.load_attachment_context(
        db,
        user_id,
        session_id,
        attachment_ids,
        supports_vision=False,
        max_chars=MAX_ATTACHMENT_CONTEXT_CHARS,
        logger=logger,
    )


def _load_selected_session_attachments(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> list[SessionAttachment]:
    return chat_attachment_api.load_selected_session_attachments(db, user_id, session_id, attachment_ids)


def _load_attachment_context_from_attachments(
    attachments: list[SessionAttachment],
    *,
    supports_vision: bool,
) -> str:
    return chat_attachment_api.load_attachment_context_from_attachments(
        attachments,
        supports_vision=supports_vision,
        max_chars=MAX_ATTACHMENT_CONTEXT_CHARS,
        logger=logger,
    )


def _is_image_attachment(attachment: SessionAttachment) -> bool:
    return chat_attachment_api.is_image_attachment(attachment)


def _is_audio_video_attachment(attachment: SessionAttachment) -> bool:
    return chat_attachment_api.is_audio_video_attachment(attachment)


def _load_vision_image_inputs(attachments: list[SessionAttachment]) -> list[dict[str, str]]:
    return chat_attachment_api.load_vision_image_inputs(
        attachments,
        allowed_mime_types=VISION_IMAGE_MIME_TYPES,
    )


def _normalize_vision_image_media_type(attachment: SessionAttachment) -> str:
    return chat_attachment_api.normalize_vision_image_media_type(
        attachment,
        allowed_mime_types=VISION_IMAGE_MIME_TYPES,
    )


def _delete_session_attachments(db: Session, user_id: int, session_id: int) -> None:
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


def _create_generated_docx(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
) -> dict:
    return _create_generated_docx_base(
        db,
        user_id,
        session_id,
        user_prompt,
        content,
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


def _write_skill_agent_run(
    db: Session,
    *,
    user_id: int,
    session: ChatSession,
    message_id: int,
    skill_response: dict,
):
    skill_run = skill_response.get("skill_run") or {}
    generated_file = skill_response.get("generated_file")
    status = _agent_status_for_skill_status(str(skill_run.get("status") or "running"))
    skill_name = str(skill_run.get("skill_name") or "skill")
    display_name = str(((skill_run.get("skill") or {}).get("display_name")) or skill_name)
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="skill",
        source_id=str(skill_run.get("id") or ""),
        title=f"运行 Skill：{display_name}",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="skill_selected",
        title="已选择业务 Skill",
        detail=display_name,
        status="completed",
        payload={"skill_name": skill_name, "skill_run_id": skill_run.get("id")},
    )
    dispatch = skill_run.get("dispatch") or {}
    dispatch_steps = dispatch.get("steps") or []
    if dispatch:
        add_agent_event(
            db,
            run,
            event_type="execution_plan",
            title="读取 Skill 执行计划",
            detail=str(dispatch.get("mode") or "manual"),
            status="completed",
            payload={
                "mode": dispatch.get("mode"),
                "risk_level": dispatch.get("risk_level"),
                "requires_confirmation": dispatch.get("requires_confirmation"),
                "allowed_tools": dispatch.get("allowed_tools") or [],
                "steps": dispatch_steps,
            },
        )
    missing_inputs = skill_run.get("missing_inputs") or []
    if missing_inputs:
        skill_name = skill_run.get("skill_name") or ""
        field_detail = _missing_input_instruction(str(skill_name), missing_inputs)

        add_agent_event(
            db,
            run,
            event_type="input_request",
            title=f"等待用户补充参数（还需要 {len(missing_inputs)} 个字段）",
            detail=field_detail or f"还需要 {len(missing_inputs)} 个字段",
            status="waiting",
            payload={"missing_inputs": missing_inputs},
        )
    elif generated_file:
        if dispatch_steps:
            for step in dispatch_steps:
                add_agent_event(
                    db,
                    run,
                    event_type="tool_call",
                    title=str(step.get("label") or step.get("tool") or "执行 Skill 工具"),
                    detail=str(step.get("tool") or ""),
                    status="completed",
                    payload={
                        "tool": step.get("tool"),
                        "step_id": step.get("id"),
                        "risk_level": step.get("risk_level"),
                    },
                )
        else:
            add_agent_event(
                db,
                run,
                event_type="tool_call",
                title="执行 Skill 并生成文件",
                detail=str(generated_file.get("filename") or ""),
                status="completed",
                payload={"generated_file": generated_file},
            )
        add_agent_event(
            db,
            run,
            event_type="result",
            title="Skill 产物已生成",
            detail=str(generated_file.get("filename") or ""),
            status="completed",
            payload={"generated_file": generated_file},
        )
    else:
        if dispatch_steps:
            for step in dispatch_steps:
                add_agent_event(
                    db,
                    run,
                    event_type="tool_call",
                    title=str(step.get("label") or step.get("tool") or "执行 Skill 工具"),
                    detail=str(step.get("tool") or ""),
                    status=status,
                    payload={
                        "tool": step.get("tool"),
                        "step_id": step.get("id"),
                        "risk_level": step.get("risk_level"),
                        "skill_status": skill_run.get("status"),
                    },
                )
        else:
            add_agent_event(
                db,
                run,
                event_type="tool_call",
                title="执行 Skill",
                detail=_safe_event_detail(skill_response.get("reply") or ""),
                status=status,
                payload={"skill_status": skill_run.get("status")},
            )
        if status == "completed":
            add_agent_event(
                db,
                run,
                event_type="result",
                title="Skill 输出已生成",
                detail=_safe_event_detail(skill_response.get("reply") or ""),
                status="completed",
                payload={"output_type": "chat_text"},
            )
    result = {"skill_run": skill_run}
    if generated_file:
        result["generated_file"] = generated_file
    return finish_agent_run(db, run, status=status, result=result)


def _write_gbrain_think_agent_run(
    db: Session,
    *,
    user_id: int,
    session: ChatSession,
    message_id: int,
    query: str,
    think_result: dict,
    response_sources: list[dict],
):
    ok = bool(think_result.get("ok"))
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="gbrain_think",
        source_id=str(think_result.get("source_id") or ""),
        title="GBrain Think 知识推理",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="context_trace",
        title="限定知识库 Source",
        detail=str(think_result.get("source_id") or session.workspace_id or "company-wiki"),
        status="completed",
        payload={"workspace_id": session.workspace_id, "source_id": think_result.get("source_id")},
    )
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title="调用 GBrain think",
        detail=_safe_event_detail(query),
        status="completed" if ok else "failed",
        payload={
            "model": think_result.get("model"),
            "status": think_result.get("status"),
            "source_count": len(response_sources),
            "gaps": safe_trace_list((think_result.get("metadata") or {}).get("gaps") if isinstance(think_result.get("metadata"), dict) else []),
            "conflicts": safe_trace_list((think_result.get("metadata") or {}).get("conflicts") if isinstance(think_result.get("metadata"), dict) else []),
            "warnings": safe_trace_list((think_result.get("metadata") or {}).get("warnings") if isinstance(think_result.get("metadata"), dict) else []),
        },
    )
    if response_sources:
        add_agent_event(
            db,
            run,
            event_type="citation",
            title="整理引用来源",
            detail=f"{len(response_sources)} 个来源",
            status="completed",
            payload={"sources": response_sources[:8]},
        )
    error_message = "" if ok else str(think_result.get("error") or think_result.get("status") or "GBrain think unavailable")
    return finish_agent_run(
        db,
        run,
        status="completed" if ok else "failed",
        result={
            "model": think_result.get("model"),
            "source_id": think_result.get("source_id"),
            "source_count": len(response_sources),
            "gbrain_think": gbrain_think_trace(think_result),
        },
        error_message=error_message,
    )


def _agent_status_for_skill_status(status: str) -> str:
    if status in {"completed", "failed"}:
        return status
    if status == "collecting_inputs":
        return "waiting"
    return "running"


def _safe_event_detail(value: object, limit: int = 240) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _start_skill_run_from_chat(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    runner = SkillRunner.get()
    match = runner.match_skill(content)
    if not match:
        return None
    return _start_skill_run_by_name(db, user_id, session_id, match["skill"]["name"])


def _start_skill_run_by_name(db: Session, user_id: int, session_id: int, skill_name: str) -> dict | None:
    runner = SkillRunner.get()
    skill = runner.get_skill(skill_name)
    if not skill:
        return None
    run = runner.start_run(db, skill.name, user_id=user_id, session_id=session_id)
    missing = run_to_dict(run, skill)["missing_inputs"]
    if missing:
        instruction = _missing_input_instruction(skill.name, missing)
        fields = _missing_input_fields_text(missing)
        reply = (
            f"已识别到业务 Skill：{skill.display_name}，但还不能开始执行。\n\n"
            f"请补充以下信息：\n{fields}\n\n"
            f"下一步操作：\n```text\n{instruction}\n```"
        )
    else:
        reply = f"已识别到业务 Skill：{skill.display_name}，信息已齐全，可以继续执行。"
    return {
        "reply": reply,
        "skill_run": run_to_dict(run, skill),
        "generated_file": generated_file_payload(db, run.generated_file_id),
    }


def _continue_active_skill_run(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    run = (
        db.query(SkillRun)
        .filter(
            SkillRun.user_id == user_id,
            SkillRun.session_id == session_id,
            SkillRun.status == "collecting_inputs",
        )
        .order_by(SkillRun.id.desc())
        .first()
    )
    if not run:
        return None
    runner = SkillRunner.get()
    skill = runner.get_skill(run.skill_name)
    if not skill:
        return None
    current = run_to_dict(run, skill)
    extracted = _extract_skill_inputs(content, current["missing_inputs"])
    if not extracted:
        fields = _missing_input_fields_text(current["missing_inputs"])
        instruction = _missing_input_instruction(run.skill_name, current["missing_inputs"])
        return {
            "reply": (
                f"我还没有识别到可写入 {skill.display_name} 的字段。\n\n"
                f"请按下面字段补充：\n{fields}\n\n"
                f"下一步操作：\n```text\n{instruction}\n```"
            ),
            "skill_run": current,
            "generated_file": generated_file_payload(db, run.generated_file_id),
        }

    run = runner.submit_input(db, run, extracted)
    run = execute_ready_run(db, run)
    payload = run_to_dict(run, skill)
    if run.status == "completed":
        reply = f"{skill.display_name} 已生成完成，可以下载结果文件。"
    else:
        fields = _missing_input_fields_text(payload["missing_inputs"])
        instruction = _missing_input_instruction(run.skill_name, payload["missing_inputs"])
        reply = (
            f"已记录补充信息，还需要：\n{fields}\n\n"
            f"下一步操作：\n```text\n{instruction}\n```"
        )
    return {
        "reply": reply,
        "skill_run": payload,
        "generated_file": generated_file_payload(db, run.generated_file_id),
    }


def _write_skill_assistant_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    skill_response: dict,
    context_trace: dict | None = None,
) -> dict:
    context_trace = context_trace or {}
    assistant_message = ChatMessage(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content=skill_response["reply"],
        provider="project_r",
        model="skill_runner",
        token_input=0,
        token_output=0,
        token_total=0,
        status="success",
        rag_used=False,
        sources_json="[]",
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    agent_run = _write_skill_agent_run(
        db,
        user_id=user_id,
        session=session,
        message_id=assistant_message.id,
        skill_response=skill_response,
    )
    db.commit()
    _write_chat_audit(
        db,
        user_id,
        session.id,
        content,
        True,
        f"skill_run={skill_response['skill_run']['skill_name']}",
        token_cost=0,
    )
    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message.id,
        "reply": skill_response["reply"],
        "provider": "project_r",
        "model": "skill_runner",
        "key_index": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "intent": IntentType.SKILL_TRIGGER.value,
        "sources": [],
        "generated_file": skill_response.get("generated_file"),
        "skill_run": skill_response["skill_run"],
        "agent_run": serialize_agent_run(db, agent_run),
        "context_trace": context_trace,
    }


def _run_gbrain_think_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    knowledge_query: str,
) -> dict:
    think_result = KNOWLEDGE_SOURCES.think(db, knowledge_query, workspace_id=session.workspace_id)
    response_sources = _serialize_sources(think_result.get("sources", []))
    ok = bool(think_result.get("ok"))
    context_trace = build_context_trace(
        session=session,
        req=None,
        attachments=[],
        sources=response_sources,
        intent=IntentType.RAG_QUERY,
        provider="gbrain",
        model=str(think_result.get("model") or ("think" if ok else "think-unavailable")),
        requested_model="gbrain_think",
        extra={
            "knowledge_query": knowledge_query,
            "gbrain_source_id": think_result.get("source_id"),
            "gbrain_status": think_result.get("status"),
            "gbrain_think": gbrain_think_trace(think_result),
        },
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content=str(think_result.get("reply") or ""),
        provider="gbrain",
        model=str(think_result.get("model") or ("think" if ok else "think-unavailable")),
        token_input=0,
        token_output=0,
        token_total=0,
        status="success",
        rag_used=bool(response_sources),
        sources_json=json.dumps(response_sources, ensure_ascii=False),
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            user_id=user_id,
            action="chat",
            detail=(
                f"会话 {session.id}: {content[:50]}... | "
                f"gbrain_think status={think_result.get('status')} source_id={think_result.get('source_id')}"
            ),
            token_cost=0,
            success=ok,
        )
    )
    db.commit()
    db.refresh(assistant_message)
    agent_run = _write_gbrain_think_agent_run(
        db,
        user_id=user_id,
        session=session,
        message_id=assistant_message.id,
        query=knowledge_query,
        think_result=think_result,
        response_sources=response_sources,
    )
    db.commit()
    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message.id,
        "reply": assistant_message.content,
        "provider": "gbrain",
        "model": assistant_message.model,
        "key_index": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "intent": IntentType.RAG_QUERY.value,
        "sources": response_sources,
        "generated_file": None,
        "skill_run": None,
        "agent_run": serialize_agent_run(db, agent_run),
        "context_trace": context_trace,
    }


_AUDIO_VIDEO_EXTS: set[str] = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".mp4", ".mov", ".avi", ".wmv", ".mkv", ".webm",
}


def _find_audio_attachments(attachments: list[SessionAttachment]) -> list[SessionAttachment]:
    """Filter attachments to only audio/video files."""
    return [
        a for a in attachments
        if a.stored_path and Path(a.stored_path).suffix.lower() in _AUDIO_VIDEO_EXTS
    ]


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
    runner = SkillRunner.get()
    skill = runner.get_skill(skill_name)
    if not skill or not _skill_outputs_chat_text(skill):
        return None
    _ensure_llm_chat_text_skill_allowed(skill)

    input_payload = _chat_text_skill_input_payload(skill, content)
    run = runner.start_run(db, skill.name, user_id=user.id, session_id=session.id, inputs=input_payload)
    run.status = "completed"
    db.commit()
    db.refresh(run)

    # ── Audio transcription special path ────────────────────────────
    if skill_name == "audio-transcription":
        from app.features.preprocessing.tools.media_transcription import (
            run_media_transcription_tool,
            MediaTranscriptionToolInput,
        )

        selected_attachments = _load_selected_session_attachments(db, user.id, session.id, req.files)
        audio_attachments = _find_audio_attachments(selected_attachments)

        if not audio_attachments:
            instruction = _missing_input_instruction(
                "audio-transcription",
                [{"name": "audio_source", "label": "音频或视频文件"}],
            )
            skill_response = {
                "reply": (
                    "还不能开始录音转文字，因为当前消息没有可处理的音频/视频附件。\n\n"
                    f"下一步操作：\n```text\n{instruction}\n```"
                ),
                "skill_run": run_to_dict(run, skill),
                "generated_file": None,
            }
            return _write_skill_assistant_response(
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
        if len(audio_attachments) > 1:
            reply_extra = "\n\n> 注意：检测到多个音频文件，只处理第一个。"
        else:
            reply_extra = ""

        try:
            tool_result = run_media_transcription_tool(
                MediaTranscriptionToolInput(media_path=audio_path)
            )
            reply = _format_audio_transcription_reply(tool_result.text, reply_extra=reply_extra)
        except Exception as exc:
            reply = f"转录失败：{exc}\n\n请检查音频文件是否有效。"

        skill_response = {
            "reply": reply,
            "skill_run": run_to_dict(run, skill),
            "generated_file": None,
        }
        return _write_skill_assistant_response(
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

    # ── End audio transcription special path ─────────────────────────

    reduce_knowledge_context = _should_reduce_knowledge_context(req.selected_prompt_id, False)
    knowledge_sources = _search_knowledge_sources(
        db,
        content,
        intent,
        session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    web_sources, web_search_context, web_search_trace = _maybe_run_web_search(
        content,
        req.web_search,
        source_start_index=len(knowledge_sources) + 1,
    )
    response_sources = _serialize_sources([*knowledge_sources, *web_sources])
    selected_attachments = _load_selected_session_attachments(db, user.id, session.id, req.files)
    attachment_context = _load_attachment_context_from_attachments(selected_attachments, supports_vision=False)
    skill_prompt = _load_skill_prompt(skill)
    system_prompt = _compose_system_prompt(
        _compose_skill_base_prompt(req.system_prompt, skill.display_name, skill_prompt),
        knowledge_sources,
        intent,
        attachment_context,
        reduce_knowledge_context,
        web_search_context=web_search_context,
    )
    requested_model = req.model_profile or req.provider

    try:
        llm_response = get_llm_client(requested_model).complete(
            _build_llm_messages(db, user.id, session.id),
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        _write_failed_assistant_message(db, user.id, session.id, str(exc), requested_model)
        _write_chat_audit(db, user.id, session.id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _write_failed_assistant_message(db, user.id, session.id, detail, requested_model)
        _write_chat_audit(db, user.id, session.id, content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    usage = llm_response.usage
    skill_payload = run_to_dict(run, skill)
    context_trace = build_context_trace(
        session=session,
        req=req,
        attachments=selected_attachments,
        sources=response_sources,
        intent=IntentType.SKILL_TRIGGER,
        provider=llm_response.provider,
        model=llm_response.model,
        requested_model=requested_model,
        reduce_knowledge_context=reduce_knowledge_context,
        extra={
            **skill_context_extra({"skill_run": skill_payload}),
            **_web_search_context_extra(web_search_trace),
        },
    )
    assistant_message = ChatMessage(
        session_id=session.id,
        user_id=user.id,
        role="assistant",
        content=llm_response.text,
        provider=llm_response.provider,
        model=llm_response.model,
        token_input=usage.get("input_tokens", 0),
        token_output=usage.get("output_tokens", 0),
        token_total=llm_response.token_cost,
        status="success",
        rag_used=bool(response_sources),
        sources_json=json.dumps(response_sources, ensure_ascii=False),
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    agent_run = _write_skill_agent_run(
        db,
        user_id=user.id,
        session=session,
        message_id=assistant_message.id,
        skill_response={
            "reply": llm_response.text,
            "skill_run": skill_payload,
            "generated_file": None,
        },
    )
    db.commit()

    _write_chat_audit(
        db,
        user.id,
        session.id,
        content,
        True,
        f"skill_run={skill.name}, provider={llm_response.provider}, model={llm_response.model}, key_index={llm_response.key_index}",
        token_cost=llm_response.token_cost,
    )

    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message.id,
        "reply": llm_response.text,
        "provider": llm_response.provider,
        "model": llm_response.model,
        "key_index": llm_response.key_index,
        "usage": usage,
        "intent": IntentType.SKILL_TRIGGER.value,
        "sources": response_sources,
        "generated_file": None,
        "skill_run": skill_payload,
        "agent_run": serialize_agent_run(db, agent_run),
        "context_trace": context_trace,
    }


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


def _serialize_sources(rag_sources: list[dict]) -> list[dict]:
    return [
        {
            "file": source.get("file", ""),
            "source_title": source.get("source_title", ""),
            "section_path": source.get("section_path", ""),
            "content": str(source.get("content", ""))[:600],
            "score": float(source.get("score", 0.0)),
            "source_file": source.get("source_file"),
            "derived_file": source.get("derived_file"),
            "source_line": source.get("source_line"),
            "source_page": source.get("source_page"),
            "source_locator": source.get("source_locator"),
        }
        for source in rag_sources
    ]


def _compose_system_prompt(
    base_prompt: str | None,
    rag_sources: list[dict],
    intent: IntentType | None = None,
    attachment_context: str = "",
    reduce_knowledge_context: bool = False,
    *,
    web_search_context: str = "",
) -> str | None:
    return compose_system_prompt(
        base_prompt,
        rag_sources,
        intent=intent,
        attachment_context=attachment_context,
        reduce_knowledge_context=reduce_knowledge_context,
        global_base_prompt=_load_global_base_prompt(),
        web_search_context=web_search_context,
    )


def _load_global_base_prompt() -> str:
    try:
        return GLOBAL_BASE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _write_failed_assistant_message(
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


def _write_chat_audit(
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
