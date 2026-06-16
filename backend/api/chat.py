from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from app.features.chat import attachment_api as chat_attachment_api
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
}
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
    document_format, document_prompt = _parse_file_generation_command(content)
    if req.force_knowledge_query:
        forced_knowledge = True
        knowledge_query = content
    llm_user_content = document_prompt or content or _attachment_only_prompt(selected_attachments)
    query_content = knowledge_query or llm_user_content
    intent = classify_intent(query_content)
    effective_intent = IntentType.DOCUMENT_GENERATION if document_format else IntentType.RAG_QUERY if forced_knowledge else intent.intent
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
    if document_format and document_prompt and llm_messages:
        llm_messages[-1] = {**llm_messages[-1], "content": document_prompt}
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

    if req.stream:
        # ============================================================
        # 流式分支：返回 SSE StreamingResponse
        # ============================================================
        ctx_trace = build_context_trace(
            session=session,
            req=req,
            attachments=selected_attachments,
            sources=response_sources,
            intent=effective_intent,
            provider="streaming",
            model=requested_model,
            requested_model=requested_model,
            reduce_knowledge_context=reduce_knowledge_context,
            extra={
                **_web_search_context_extra(web_search_trace),
            },
        )
        return StreamingResponse(
            chat_stream.generate_sse_stream(
                llm_client=llm_client,
                llm_messages=llm_messages,
                system_prompt=system_prompt,
                thinking=req.thinking,
                temperature=req.temperature,
                session_factory=SessionLocal,
                session_id=session.id,
                user_id=user.id,
                requested_model=requested_model,
                sources_json=json.dumps(response_sources, ensure_ascii=False),
                context_json=json.dumps(ctx_trace, ensure_ascii=False),
                rag_used=bool(response_sources),
                llm_user_content=llm_user_content,
                user_message_id=user_message.id,
                user_attachments_json=json.dumps(
                    [_attachment_to_response_dict(a) for a in selected_attachments],
                    ensure_ascii=False,
                ),
                intent=effective_intent.value,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        llm_response = llm_client.complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
            temperature=req.temperature,
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
        generated_file = _create_generated_file(
            db,
            user.id,
            session_id,
            document_prompt or content,
            llm_response.text,
            output_format=document_format or "docx",
        )
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


from app.features.chat.internal import (
    message_query as _message_query,
    message_pair_delete_targets as _message_pair_delete_targets,
    ensure_version_group as _ensure_version_group,
    next_version_index as _next_version_index,
    build_llm_messages_before as _build_llm_messages_before,
    exclude_active_messages_after as _exclude_active_messages_after,
    set_active_version as _set_active_version,
    build_llm_messages as _build_llm_messages,
    message_llm_content as _message_llm_content,
    bind_attachments_to_message as _bind_attachments_to_message,
    parse_knowledge_command as _parse_knowledge_command,
    load_attachment_context as _load_attachment_context,
    load_selected_session_attachments as _load_selected_session_attachments,
    load_attachment_context_from_attachments as _load_attachment_context_from_attachments,
    is_image_attachment as _is_image_attachment,
    is_audio_video_attachment as _is_audio_video_attachment,
    load_vision_image_inputs as _load_vision_image_inputs,
    normalize_vision_image_media_type as _normalize_vision_image_media_type,
    delete_session_attachments as _delete_session_attachments,
    cleanup_inactive_session_attachments_if_due,
    cleanup_inactive_session_attachments,
)
from app.features.chat.internal import (
    message_to_response_dict as _message_to_response_dict_core,
)


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


from app.features.chat.internal import (
    write_skill_agent_run as _write_skill_agent_run,
    write_gbrain_think_agent_run as _write_gbrain_think_agent_run,
    agent_status_for_skill_status as _agent_status_for_skill_status,
    safe_event_detail as _safe_event_detail,
)
from app.features.chat.skill_dispatch import (
    start_skill_run_from_chat as _start_skill_run_from_chat_core,
    start_skill_run_by_name as _start_skill_run_by_name_core,
    continue_active_skill_run as _continue_active_skill_run_core,
    write_skill_assistant_response as _write_skill_assistant_response_core,
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



from app.features.chat.response_helpers import (
    run_gbrain_think_response as _run_gbrain_think_response_core,
)


def _run_gbrain_think_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    knowledge_query: str,
) -> dict:
    return _run_gbrain_think_response_core(
        db, user_id, session, user_message_id, content, knowledge_query,
        knowledge_sources=KNOWLEDGE_SOURCES,
        serialize_sources_fn=_serialize_sources,
        write_gbrain_think_agent_run_fn=_write_gbrain_think_agent_run,
    )



from app.features.chat.response_helpers import (
    run_chat_text_skill_by_name as _run_chat_text_skill_by_name_core,
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


from app.features.chat.internal import (
    serialize_sources as _serialize_sources,
    compose_system_prompt as _compose_system_prompt,
    load_global_base_prompt as _load_global_base_prompt,
    write_failed_assistant_message as _write_failed_assistant_message,
    write_chat_audit as _write_chat_audit,
)



