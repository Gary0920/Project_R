from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from api.agent_models import AgentRunResponse
from api.auth import get_current_user
from core.time_utils import serialize_datetime_utc
from core.agent_events import add_agent_event, create_agent_run, finish_agent_run, get_agent_run_for_message, serialize_agent_run
from core.notification_service import notify_file_generated, notify_knowledge_review_pending
from core.intent import IntentType, classify_intent
from core.doc_renderer import render_docx
from core.knowledge_sources import KnowledgeSources
from core.llm import LLMConfigurationError, LLMProviderError, get_llm_client
from core import session_attachments
from core.skill_execution import execute_ready_run, generated_file_payload
from core.skill_runner import SkillRunner, run_to_dict
from core.system_prompt import (
    DOCUMENT_GENERATION_PROMPT,
    FORMAT_GUIDANCE_PROMPT,
    TEXT_TRANSFORMATION_PROMPT_IDS,
    compose_system_prompt,
    should_reduce_knowledge_context,
)
from core.web_search import (
    WEB_SEARCH_SKILL_NAME,
    WebSearchResponse,
    format_web_search_prompt,
    search_web,
    web_results_to_sources,
)
from models import get_db
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.message import ChatMessage
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User
from models.workspace import Workspace, WorkspaceGroupAccess, WorkspaceMember

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
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_last_session_attachment_cleanup_at: datetime | None = None
KNOWLEDGE_SOURCES = KnowledgeSources()


class CreateSessionRequest(BaseModel):
    title: str = "新对话"
    workspace_id: int | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    workspace_id: int | None = None
    is_pinned: bool | None = None


class SessionResponse(BaseModel):
    id: int
    title: str
    workspace_id: int | None = None
    is_archived: bool = False
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    message_count: int


class SendMessageRequest(BaseModel):
    content: str
    files: list[str] = []
    provider: str | None = None
    model_profile: str | None = None
    selected_skill: str | None = None
    selected_prompt_id: str | None = None
    force_knowledge_query: bool = False
    stream: bool = False
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None


class RegenerateMessageRequest(BaseModel):
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None
    temperature: float = Field(default=0.9, ge=0, le=2)


class EditMessageRequest(BaseModel):
    content: str
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None


class MessageFeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class RestoreMessagesRequest(BaseModel):
    message_ids: list[int] = Field(default_factory=list)


class ChatSourceResponse(BaseModel):
    file: str
    source_title: str
    section_path: str
    content: str
    score: float
    source_file: str | None = None
    derived_file: str | None = None
    source_line: int | None = None
    source_page: int | None = None
    source_locator: str | None = None


class CreateAttachmentRequest(BaseModel):
    filename: str
    content: str
    content_type: str = "text/plain"
    source_scope: str = "session_upload"
    source_label: str = "会话临时上传"
    authorization_status: str = "uploaded"


class AttachmentResponse(BaseModel):
    id: int
    session_id: int
    message_id: int | None = None
    original_name: str
    content_type: str
    size: int
    source_scope: str = "session_upload"
    source_label: str = "会话临时上传"
    authorization_status: str = "uploaded"
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    provider: str | None
    model: str | None
    token_input: int | None
    token_output: int | None
    token_total: int | None
    status: str
    error_message: str | None
    rag_used: bool = False
    is_excluded: bool = False
    version_group_id: str | None = None
    version_index: int = 1
    version_count: int = 1
    active_version: bool = True
    versions: list["MessageVersionResponse"] = Field(default_factory=list)
    feedback_rating: int | None = None
    feedback_comment: str | None = None
    sources: list[ChatSourceResponse] = Field(default_factory=list)
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    generated_file: dict[str, Any] | None = None
    skill_run: dict[str, Any] | None = None
    agent_run: AgentRunResponse | None = None
    context_trace: dict = Field(default_factory=dict)
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class MessageVersionResponse(BaseModel):
    id: int
    content: str
    provider: str | None = None
    model: str | None = None
    version_index: int = 1
    active_version: bool = True
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class RegenerateMessageResponse(BaseModel):
    ok: bool
    assistant_message: MessageResponse
    excluded_message_ids: list[int] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class EditMessageResponse(BaseModel):
    ok: bool
    user_message: MessageResponse
    assistant_message: MessageResponse
    excluded_message_ids: list[int] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class ActivateMessageVersionResponse(BaseModel):
    ok: bool
    message: MessageResponse


class MessageFeedbackResponse(BaseModel):
    ok: bool
    feedback_id: str
    rating: int
    comment: str
    created_at: str
    knowledge_review_id: int | None = None
    knowledge_review_status: str | None = None


class GBrainThinkReviewRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class GBrainThinkReviewResponse(BaseModel):
    ok: bool
    knowledge_review_id: int
    knowledge_review_status: str
    created: bool


class RestoreMessagesResponse(BaseModel):
    ok: bool
    restored_message_ids: list[int] = Field(default_factory=list)
    messages: list[MessageResponse] = Field(default_factory=list)


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class SearchResultResponse(SessionResponse):
    matched_message: str | None = None


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
            _build_context_trace(
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
            _build_context_trace(
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
    session = _get_user_session(db, user.id, session_id)
    message = (
        _message_query(db, user.id, session_id, include_inactive=True)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "assistant")
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="可评分的回答不存在")
    comment = req.comment.strip()[:2000]
    feedback = _write_message_feedback(user, message, req.rating, comment)
    correction_review = _maybe_create_answer_correction_review(
        db,
        user=user,
        session=session,
        message=message,
        rating=req.rating,
        comment=comment,
        feedback_id=feedback["feedback_id"],
    )
    db.add(
        AuditLog(
            user_id=user.id,
            action="message_feedback",
            detail=(
                f"会话 {session_id} 回答 {message_id} 评分 {req.rating}/5"
                + (f"，生成知识纠错审核 {correction_review.id}" if correction_review else "")
            ),
            success=True,
        )
    )
    db.commit()
    return {
        "ok": True,
        "feedback_id": feedback["feedback_id"],
        "rating": req.rating,
        "comment": comment,
        "created_at": feedback["created_at"],
        "knowledge_review_id": correction_review.id if correction_review else None,
        "knowledge_review_status": correction_review.status if correction_review else None,
    }


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
    session = _get_user_session(db, user.id, session_id)
    message = (
        _message_query(db, user.id, session_id, include_inactive=True)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "assistant")
        .first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="可提交审核的 GBrain 回答不存在")
    review, created = _create_gbrain_think_review(
        db,
        user=user,
        session=session,
        message=message,
        note=req.note.strip()[:2000],
    )
    if not review:
        raise HTTPException(status_code=400, detail="该回答没有可提交审核的 GBrain 缺口、冲突或警告")
    db.add(
        AuditLog(
            user_id=user.id,
            action="gbrain_think_review_submit",
            detail=f"会话 {session_id} 回答 {message_id} 提交 GBrain gap/conflict 审核 {review.id}",
            success=True,
        )
    )
    db.commit()
    return {
        "ok": True,
        "knowledge_review_id": review.id,
        "knowledge_review_status": review.status,
        "created": created,
    }


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
            context_trace=_build_context_trace(
                session=session,
                req=req,
                attachments=selected_attachments,
                sources=[],
                intent=effective_intent,
                provider="project_r",
                model="skill_runner",
                requested_model=requested_model,
                extra=_skill_context_extra(active_skill_response),
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
                context_trace=_build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=_skill_context_extra(skill_response),
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
                context_trace=_build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=_skill_context_extra(skill_response),
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
    context_trace = _build_context_trace(
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
            "generated_file": _generated_file_context(generated_file),
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
    _get_user_session(db, user.id, session_id)
    filename = _safe_filename(req.filename)
    content_bytes = req.content.encode("utf-8")
    if len(content_bytes) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=400, detail="附件不能超过 256KB")

    return _store_session_attachment(
        db,
        user,
        session_id,
        filename,
        req.content_type,
        content_bytes,
        source_scope=req.source_scope,
        source_label=req.source_label,
        authorization_status=req.authorization_status,
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
    _get_user_session(db, user.id, session_id)
    filename = _safe_filename(file.filename or "attachment")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="附件内容为空")
    if len(content) > MAX_ATTACHMENT_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"附件不能超过 {MAX_ATTACHMENT_UPLOAD_MB}MB")

    return _store_session_attachment(
        db,
        user,
        session_id,
        filename,
        file.content_type or "application/octet-stream",
        content,
        source_scope=source_scope,
        source_label=source_label,
        authorization_status=authorization_status,
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
    return session_attachments.store_session_attachment(
        db,
        user,
        session_id,
        filename,
        _safe_content_type(content_type, filename),
        content,
        attachment_dir=_attachment_dir,
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
    attachment = (
        db.query(SessionAttachment)
        .filter(
            SessionAttachment.id == attachment_id,
            SessionAttachment.session_id == session_id,
            SessionAttachment.user_id == user_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")
    return attachment


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
def list_session_attachments(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_session(db, user.id, session_id)
    return session_attachments.list_session_attachments(db, user.id, session_id)


@router.get("/sessions/{session_id}/attachments/{attachment_id}/content")
def get_session_attachment_content(
    session_id: int,
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_session(db, user.id, session_id)
    attachment = _get_user_session_attachment(db, user.id, session_id, attachment_id)
    path = Path(attachment.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
    )


@router.delete("/sessions/{session_id}/attachments/{attachment_id}")
def delete_session_attachment(
    session_id: int,
    attachment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_session(db, user.id, session_id)
    session_attachments.delete_session_attachment(db, user.id, session_id, attachment_id)
    return {"ok": True}


def _get_user_session(db: Session, user_id: int, session_id: int) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


def _workspace_membership(db: Session, user_id: int, workspace_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )


def _has_workspace_group_access(db: Session, user: User, workspace_id: int) -> bool:
    group_name = (getattr(user, "work_group", "") or "").strip().lower()
    if not group_name:
        return False
    return bool(
        db.query(WorkspaceGroupAccess)
        .filter(
            WorkspaceGroupAccess.workspace_id == workspace_id,
            WorkspaceGroupAccess.group_name == group_name,
        )
        .first()
    )


def _ensure_workspace_access(db: Session, user: User, workspace_id: int) -> None:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id, Workspace.is_archived == False).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    member = _workspace_membership(db, user.id, workspace_id)
    if workspace.workspace_kind == "user":
        if member:
            return
        raise HTTPException(status_code=403, detail="你尚未加入该项目")
    if user.role == "admin":
        return
    if workspace.workspace_kind == "customer":
        if member or _has_workspace_group_access(db, user, workspace_id):
            return
        raise HTTPException(status_code=403, detail="你尚未加入该项目")
    if not workspace.is_hidden:
        return
    if member or _has_workspace_group_access(db, user, workspace_id):
        return
    raise HTTPException(status_code=403, detail="你尚未加入该项目")


def _ensure_workspace_member(db: Session, user_id: int, workspace_id: int) -> None:
    if not _workspace_membership(db, user_id, workspace_id):
        raise HTTPException(status_code=403, detail="你尚未加入该项目")


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


def _message_versions(db: Session, message: ChatMessage) -> list[ChatMessage]:
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


def _attachment_to_response_dict(attachment: SessionAttachment) -> dict:
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


def _message_attachments(db: Session, message: ChatMessage) -> list[SessionAttachment]:
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


def _message_to_response_dict(db: Session, message: ChatMessage) -> dict:
    versions = _message_versions(db, message)
    feedback = _load_latest_message_feedback(message)
    attachments = _message_attachments(db, message)
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
        "feedback_rating": feedback.get("rating") if feedback else None,
        "feedback_comment": feedback.get("comment") if feedback else None,
        "sources": message.sources,
        "attachments": [_attachment_to_response_dict(attachment) for attachment in attachments],
        "generated_file": agent_result.get("generated_file"),
        "skill_run": agent_result.get("skill_run"),
        "agent_run": serialized_agent_run,
        "context_trace": message.context_trace,
        "created_at": serialize_datetime_utc(message.created_at),
    }


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


def _feedback_message_dir(message: ChatMessage) -> Path:
    return MESSAGE_FEEDBACK_ROOT / f"user_{message.user_id}" / f"session_{message.session_id}" / f"message_{message.id}"


def _write_message_feedback(user: User, message: ChatMessage, rating: int, comment: str) -> dict:
    created_at = datetime.now(timezone.utc)
    feedback_id = f"{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid.uuid4().hex[:8]}"
    payload = {
        "schema_version": 1,
        "feedback_id": feedback_id,
        "created_at": serialize_datetime_utc(created_at),
        "rating": rating,
        "comment": comment,
        "user": {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
        },
        "message": {
            "id": message.id,
            "session_id": message.session_id,
            "role": message.role,
            "provider": message.provider,
            "model": message.model,
            "version_group_id": message.version_group_id,
            "version_index": message.version_index,
            "content_excerpt": message.content[:1200],
        },
        "sources": message.sources,
        "intended_use": "ai_prompt_and_skill_iteration",
    }
    target_dir = _feedback_message_dir(message)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{feedback_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _maybe_create_answer_correction_review(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    rating: int,
    comment: str,
    feedback_id: str,
) -> KnowledgeReview | None:
    if rating > ANSWER_CORRECTION_RATING_THRESHOLD:
        return None
    gbrain_sources = _gbrain_sources_for_message(message)
    if not gbrain_sources:
        return None

    source = f"{ANSWER_CORRECTION_REVIEW_PREFIX}{message.id}"
    question = _previous_user_message_content(db, message)
    content = _build_answer_correction_review_content(
        user=user,
        session=session,
        message=message,
        rating=rating,
        comment=comment,
        feedback_id=feedback_id,
        question=question,
        sources=gbrain_sources,
    )
    review = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
        .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
        .first()
    )
    if review:
        review.content = content
    else:
        review = KnowledgeReview(submitter_id=user.id, content=content, source=source)
        db.add(review)
    db.flush()
    notify_knowledge_review_pending(db, review_id=review.id, source=source)
    return review


def _create_gbrain_think_review(
    db: Session,
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    note: str,
) -> tuple[KnowledgeReview | None, bool]:
    trace = message.context_trace
    gbrain_think = trace.get("gbrain_think") if isinstance(trace.get("gbrain_think"), dict) else {}
    gaps = _safe_trace_list(gbrain_think.get("gaps"))
    conflicts = _safe_trace_list(gbrain_think.get("conflicts"))
    warnings = _safe_trace_list(gbrain_think.get("warnings"))
    if not (gaps or conflicts or warnings):
        return None, False

    source = f"{GBRAIN_THINK_REVIEW_PREFIX}{message.id}"
    content = _build_gbrain_think_review_content(
        user=user,
        session=session,
        message=message,
        note=note,
        question=_previous_user_message_content(db, message),
        sources=_gbrain_sources_for_message(message),
        gbrain_think=gbrain_think,
        gaps=gaps,
        conflicts=conflicts,
        warnings=warnings,
    )
    review = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
        .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
        .first()
    )
    created = review is None
    if review:
        review.content = content
    else:
        review = KnowledgeReview(submitter_id=user.id, content=content, source=source)
        db.add(review)
    db.flush()
    notify_knowledge_review_pending(db, review_id=review.id, source=source)
    return review, created


def _gbrain_sources_for_message(message: ChatMessage) -> list[dict]:
    sources = []
    for source in message.sources:
        if not isinstance(source, dict):
            continue
        file_ref = str(source.get("file") or "")
        source_type = str(source.get("type") or "")
        tags = str(source.get("tags") or "")
        if file_ref.startswith("gbrain:") or source_type.startswith("gbrain") or "gbrain" in tags.lower():
            sources.append(source)
    return sources


def _previous_user_message_content(db: Session, message: ChatMessage) -> str:
    previous = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == message.session_id,
            ChatMessage.user_id == message.user_id,
            ChatMessage.role == "user",
            ChatMessage.id < message.id,
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )
    return previous.content if previous else ""


def _build_answer_correction_review_content(
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    rating: int,
    comment: str,
    feedback_id: str,
    question: str,
    sources: list[dict],
) -> str:
    source_lines = []
    for index, source in enumerate(sources, start=1):
        source_lines.append(
            "\n".join(
                [
                    f"{index}. `{_safe_review_text(str(source.get('file') or 'gbrain'))}`",
                    f"   - 标题 / Title: {_safe_review_text(str(source.get('source_title') or ''))}",
                    f"   - 位置 / Path: {_safe_review_text(str(source.get('section_path') or ''))}",
                    f"   - 摘录 / Excerpt: {_safe_review_text(str(source.get('content') or ''), 500)}",
                ]
            )
        )
    source_block = "\n".join(source_lines)
    comment_text = comment or "用户未填写补充意见。 / No additional user comment."
    question_text = question or "未找到上一条用户问题。 / Previous user question was not found."
    return (
        "# 知识纠错候选 / Knowledge Correction Candidate\n\n"
        "> 本候选来自用户对带 GBrain 引用回答的低分反馈。管理员需要判断问题属于事实错误、来源过期、引用缺失、资料冲突，还是回答组织问题；"
        "审核通过前应改写为可沉淀的中英文对齐知识，不应把未核实反馈直接作为事实。\n\n"
        "> This candidate comes from low-rated feedback on an answer with GBrain citations. Before approval, an administrator must decide whether the issue is a factual error, stale source, missing citation, source conflict, or answer-composition problem, then rewrite it as verified bilingual knowledge.\n\n"
        "## 反馈元数据 / Feedback Metadata\n\n"
        f"- feedback_id: `{feedback_id}`\n"
        f"- rating: {rating}/5\n"
        f"- user: `{user.username}` / `{user.nickname}`\n"
        f"- session_id: {session.id}\n"
        f"- workspace_id: {session.workspace_id if session.workspace_id is not None else 'company-wiki'}\n"
        f"- assistant_message_id: {message.id}\n"
        f"- model: `{message.provider or ''}:{message.model or ''}`\n\n"
        "## 用户反馈 / User Feedback\n\n"
        f"- 中文：{_safe_review_text(comment_text)}\n"
        f"- English: Same user feedback text for review: {_safe_review_text(comment_text)}\n\n"
        "## 原问题 / Original Question\n\n"
        f"{_safe_review_text(question_text, 1200)}\n\n"
        "## 原回答摘录 / Answer Excerpt\n\n"
        f"{_safe_review_text(message.content, 1600)}\n\n"
        "## GBrain 引用来源 / GBrain Citations\n\n"
        f"{source_block}\n\n"
        "## 管理员处理建议 / Admin Triage Guidance\n\n"
        "- 中文：如果只是引用格式或缺少引用，优先后续调用 GBrain citation-fixer；如果是资料冲突，进入 contradiction review；如果是原始知识错误或过期，审核后沉淀修正知识。\n"
        "- English: If the issue is only citation formatting or missing citation, prefer a later GBrain citation-fixer task. If sources conflict, route it to contradiction review. If the underlying knowledge is wrong or stale, approve a verified correction into the knowledge base.\n"
    )


def _build_gbrain_think_review_content(
    *,
    user: User,
    session: ChatSession,
    message: ChatMessage,
    note: str,
    question: str,
    sources: list[dict],
    gbrain_think: dict,
    gaps: list[str],
    conflicts: list[str],
    warnings: list[str],
) -> str:
    source_lines = []
    for index, source in enumerate(sources, start=1):
        source_lines.append(
            "\n".join(
                [
                    f"{index}. `{_safe_review_text(str(source.get('file') or 'gbrain'))}`",
                    f"   - 标题 / Title: {_safe_review_text(str(source.get('source_title') or ''))}",
                    f"   - 位置 / Path: {_safe_review_text(str(source.get('section_path') or ''))}",
                    f"   - 摘录 / Excerpt: {_safe_review_text(str(source.get('content') or ''), 500)}",
                ]
            )
        )
    source_block = "\n".join(source_lines) or "- 无引用来源 / No citation source."
    question_text = question or "未找到上一条用户问题。 / Previous user question was not found."
    note_text = note or "用户未补充说明。 / No additional user note."
    gap_block = "\n".join(f"- {item}" for item in gaps) or "- 无 / None"
    conflict_block = "\n".join(f"- {item}" for item in conflicts) or "- 无 / None"
    warning_block = "\n".join(f"- {item}" for item in warnings) or "- 无 / None"
    diagnostics = gbrain_think.get("diagnostics") if isinstance(gbrain_think.get("diagnostics"), dict) else {}
    return (
        "# GBrain Think 缺口 / 冲突审核候选\n\n"
        "> 本候选来自 GBrain Think 在回答时返回的 gap/conflict/warning。管理员需要判断它是资料缺失、资料冲突、检索范围问题，还是回答组织问题；"
        "审核通过前不得把未核实的 gap/conflict 直接写成事实。\n\n"
        "> This candidate comes from GBrain Think gaps/conflicts/warnings. Before approval, an administrator must decide whether it indicates missing knowledge, conflicting sources, retrieval scope issues, or answer-composition issues. Do not turn unverified gaps/conflicts into facts.\n\n"
        "## 元数据 / Metadata\n\n"
        f"- user: `{user.username}` / `{user.nickname}`\n"
        f"- session_id: {session.id}\n"
        f"- workspace_id: {session.workspace_id if session.workspace_id is not None else 'company-wiki'}\n"
        f"- assistant_message_id: {message.id}\n"
        f"- source_id: `{_safe_review_text(str(gbrain_think.get('source_id') or ''))}`\n"
        f"- status: `{_safe_review_text(str(gbrain_think.get('status') or ''))}`\n"
        f"- model: `{_safe_review_text(str(gbrain_think.get('model') or message.model or ''))}`\n"
        f"- trace_id: `{_safe_review_text(str(diagnostics.get('trace_id') or ''))}`\n\n"
        "## 用户补充 / User Note\n\n"
        f"- 中文：{_safe_review_text(note_text)}\n"
        f"- English: Same user note for review: {_safe_review_text(note_text)}\n\n"
        "## 原问题 / Original Question\n\n"
        f"{_safe_review_text(question_text, 1200)}\n\n"
        "## 原回答摘录 / Answer Excerpt\n\n"
        f"{_safe_review_text(message.content, 1600)}\n\n"
        "## GBrain 缺口 / Gaps\n\n"
        f"{_safe_review_text(gap_block, 1600)}\n\n"
        "## GBrain 冲突 / Conflicts\n\n"
        f"{_safe_review_text(conflict_block, 1600)}\n\n"
        "## GBrain 警告 / Warnings\n\n"
        f"{_safe_review_text(warning_block, 1600)}\n\n"
        "## GBrain 引用来源 / GBrain Citations\n\n"
        f"{source_block}\n\n"
        "## 管理员处理建议 / Admin Triage Guidance\n\n"
        "- 中文：资料缺失时补充经验证知识；资料冲突时进入 contradiction review；引用格式问题可调用 citation-fixer；检索范围问题应先检查 source scope 和权限。\n"
        "- English: Add verified knowledge for real gaps; route source conflicts to contradiction review; use citation-fixer for citation-format issues; check source scope and permissions for retrieval-scope issues.\n"
    )


def _safe_review_text(value: str, limit: int = 2000) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _load_latest_message_feedback(message: ChatMessage) -> dict | None:
    target_dir = _feedback_message_dir(message)
    if not target_dir.exists():
        return None
    files = sorted(target_dir.glob("*.json"), key=lambda path: path.name, reverse=True)
    if not files:
        return None
    try:
        payload = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


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


def _attachment_only_prompt(attachments: list[SessionAttachment]) -> str:
    if not attachments:
        return ""
    names = "、".join(attachment.original_name for attachment in attachments[:6])
    suffix = "等附件" if len(attachments) > 6 else "附件"
    return f"请根据本轮上传的{suffix}回答。附件：{names}"


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


def _safe_filename(filename: str) -> str:
    return session_attachments.safe_filename(filename)


def _safe_content_type(content_type: str | None, filename: str) -> str:
    return session_attachments.safe_content_type(content_type, filename)


def _attachment_dir(db: Session, user: User, session_id: int) -> Path:
    return session_attachments.resolve_attachment_dir(
        db,
        user,
        session_id,
        fallback_root=SESSION_ATTACHMENTS_ROOT,
        logger=logger,
    )


def _load_attachment_context(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> str:
    return _load_attachment_context_from_attachments(
        _load_selected_session_attachments(db, user_id, session_id, attachment_ids),
        supports_vision=False,
    )


def _load_selected_session_attachments(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> list[SessionAttachment]:
    return session_attachments.load_selected_session_attachments(db, user_id, session_id, attachment_ids)


def _load_attachment_context_from_attachments(
    attachments: list[SessionAttachment],
    *,
    supports_vision: bool,
) -> str:
    return session_attachments.load_attachment_context(
        attachments,
        supports_vision=supports_vision,
        max_chars=MAX_ATTACHMENT_CONTEXT_CHARS,
        logger=logger,
    )


def _attachment_context_chunk(
    attachment: SessionAttachment,
    remaining: int,
    *,
    supports_vision: bool,
) -> tuple[str, int]:
    return session_attachments.attachment_context_chunk(
        attachment,
        remaining,
        supports_vision=supports_vision,
        logger=logger,
    )


def _attachment_context_header(attachment: SessionAttachment) -> str:
    return session_attachments.attachment_context_header(attachment)


def _format_bytes(size: int) -> str:
    return session_attachments.format_bytes(size)


def _is_text_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_text_attachment(attachment)


def _is_pdf_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_pdf_attachment(attachment)


def _is_image_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_image_attachment(attachment)


def _is_audio_video_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_audio_video_attachment(attachment)


def _load_vision_image_inputs(attachments: list[SessionAttachment]) -> list[dict[str, str]]:
    return session_attachments.load_vision_image_inputs(
        attachments,
        allowed_mime_types=VISION_IMAGE_MIME_TYPES,
    )


def _normalize_vision_image_media_type(attachment: SessionAttachment) -> str:
    return session_attachments.normalize_vision_image_media_type(
        attachment,
        allowed_mime_types=VISION_IMAGE_MIME_TYPES,
    )


def _attach_vision_images_to_latest_user_message(
    messages: list[dict],
    images: list[dict[str, str]],
    provider: str,
) -> list[dict]:
    updated = [dict(message) for message in messages]
    for index in range(len(updated) - 1, -1, -1):
        if updated[index].get("role") != "user":
            continue
        content = updated[index].get("content", "")
        text = content if isinstance(content, str) else ""
        updated[index]["content"] = _build_vision_content_blocks(text, images, provider)
        break
    return updated


def _build_vision_content_blocks(
    text: str,
    images: list[dict[str, str]],
    provider: str,
) -> list[dict]:
    blocks: list[dict] = []
    if text:
        blocks.append({"type": "text", "text": text})
    if provider == "claude":
        blocks.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            }
            for image in images
        )
    else:
        blocks.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image['media_type']};base64,{image['data']}"},
            }
            for image in images
        )
    return blocks


def _read_attachment_text(path: Path, limit: int) -> str:
    return session_attachments.read_attachment_text(path, limit)


def _read_pdf_attachment_text(path: Path, limit: int) -> str:
    return session_attachments.read_pdf_attachment_text(path, limit, logger=logger)


def _image_attachment_details(path: Path) -> str:
    return session_attachments.image_attachment_details(path)


def _delete_session_attachments(db: Session, user_id: int, session_id: int) -> None:
    session_attachments.delete_session_attachments(db, user_id, session_id)


def cleanup_inactive_session_attachments_if_due(db: Session) -> int:
    global _last_session_attachment_cleanup_at
    now = datetime.now(timezone.utc)
    if (
        _last_session_attachment_cleanup_at is not None
        and now - _last_session_attachment_cleanup_at < SESSION_ATTACHMENT_CLEANUP_INTERVAL
    ):
        return 0
    _last_session_attachment_cleanup_at = now
    return cleanup_inactive_session_attachments(db)


def cleanup_inactive_session_attachments(db: Session | None = None) -> int:
    return session_attachments.cleanup_inactive_session_attachments(
        db,
        retention_days=SESSION_ATTACHMENT_RETENTION_DAYS,
        logger=logger,
    )


def _safe_document_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip()[:40] or "Project_R 生成文档"
    return re.sub(r"[\\/:*?\"<>|]", "_", title)


def _create_generated_docx(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
) -> dict:
    file_id = str(uuid.uuid4())
    title = _safe_document_title(user_prompt)
    filename = f"{title}.docx"
    output_path = GENERATED_FILES_ROOT / str(user_id) / f"{file_id}.docx"
    render_docx(title, content, output_path)
    generated = GeneratedFile(
        id=file_id,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        path=str(output_path),
        mime_type=DOCX_MIME,
    )
    db.add(generated)
    notify_file_generated(db, user_id=user_id, file_id=file_id, filename=filename, session_id=session_id)
    return {
        "id": file_id,
        "filename": filename,
        "mime_type": DOCX_MIME,
        "download_url": f"/documents/{file_id}/download",
    }


def _build_context_trace(
    *,
    session: ChatSession,
    req: SendMessageRequest | None,
    attachments: list[SessionAttachment],
    sources: list[dict],
    intent: IntentType,
    provider: str | None,
    model: str | None,
    requested_model: str | None = None,
    reduce_knowledge_context: bool = False,
    extra: dict | None = None,
) -> dict:
    system_prompt = getattr(req, "system_prompt", None) if req else None
    return {
        "schema_version": 1,
        "workspace_id": session.workspace_id,
        "intent": intent.value if isinstance(intent, IntentType) else str(intent),
        "model": {
            "provider": provider,
            "model": model,
            "requested_model": requested_model,
            "thinking": bool(getattr(req, "thinking", False)) if req else False,
            "web_search": bool(getattr(req, "web_search", False)) if req else False,
        },
        "prompt": {
            "selected_prompt_id": getattr(req, "selected_prompt_id", None) if req else None,
            "selected_skill": getattr(req, "selected_skill", None) if req else None,
            "system_prompt_provided": bool(system_prompt and system_prompt.strip()),
            "system_prompt_preview": _trace_preview(system_prompt, 220),
        },
        "attachments": [_attachment_trace_dict(attachment) for attachment in attachments],
        "knowledge": {
            "reduce_context": reduce_knowledge_context,
            "source_count": len(sources),
            "sources": [_source_trace_dict(source, index) for index, source in enumerate(sources[:12], start=1)],
        },
        **(extra or {}),
    }


def _attachment_trace_dict(attachment: SessionAttachment) -> dict:
    return {
        "id": attachment.id,
        "session_id": attachment.session_id,
        "message_id": attachment.message_id,
        "name": attachment.original_name,
        "content_type": attachment.content_type,
        "size": attachment.size,
    }


def _source_trace_dict(source: dict, index: int) -> dict:
    return {
        "index": index,
        "file": source.get("file"),
        "source_title": source.get("source_title"),
        "section_path": source.get("section_path"),
        "score": source.get("score"),
        "source_file": source.get("source_file"),
        "source_locator": source.get("source_locator"),
    }


def _safe_trace_list(value: object, *, limit: int = 6, item_limit: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            result.append(text[:item_limit])
    return result


def _gbrain_think_trace(think_result: dict) -> dict:
    metadata = think_result.get("metadata") if isinstance(think_result.get("metadata"), dict) else {}
    gaps = _safe_trace_list(metadata.get("gaps"))
    conflicts = _safe_trace_list(metadata.get("conflicts"))
    warnings = _safe_trace_list(metadata.get("warnings"))
    diagnostics = metadata.get("diagnostics") if isinstance(metadata.get("diagnostics"), dict) else {}
    return {
        "source_id": think_result.get("source_id"),
        "status": think_result.get("status"),
        "model": think_result.get("model"),
        "gap_count": len(metadata.get("gaps") if isinstance(metadata.get("gaps"), list) else []),
        "conflict_count": len(metadata.get("conflicts") if isinstance(metadata.get("conflicts"), list) else []),
        "warning_count": len(metadata.get("warnings") if isinstance(metadata.get("warnings"), list) else []),
        "gaps": gaps,
        "conflicts": conflicts,
        "warnings": warnings,
        "diagnostics": {
            "trace_id": diagnostics.get("trace_id"),
            "pipeline": diagnostics.get("pipeline"),
        },
    }


def _skill_context_extra(skill_response: dict) -> dict:
    skill_run = skill_response.get("skill_run") or {}
    skill = skill_run.get("skill") or {}
    return {
        "skill": {
            "run_id": skill_run.get("id"),
            "skill_name": skill_run.get("skill_name"),
            "display_name": skill.get("display_name"),
            "status": skill_run.get("status"),
            "missing_input_count": len(skill_run.get("missing_inputs") or []),
        },
        "generated_file": _generated_file_context(skill_response.get("generated_file")),
    }


def _generated_file_context(generated_file: dict | None) -> dict | None:
    if not generated_file:
        return None
    return {
        "id": generated_file.get("id"),
        "filename": generated_file.get("filename"),
        "mime_type": generated_file.get("mime_type"),
        "download_url": generated_file.get("download_url"),
    }


def _trace_preview(value: str | None, limit: int = 160) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _write_document_generation_agent_run(
    db: Session,
    *,
    user_id: int,
    session: ChatSession,
    message_id: int,
    user_prompt: str,
    generated_file: dict,
):
    title = f"生成文件：{generated_file.get('filename') or _safe_document_title(user_prompt)}"
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="document_generation",
        source_id=str(generated_file.get("id") or ""),
        title=title,
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="plan",
        title="识别文件生成任务",
        detail=_safe_event_detail(user_prompt),
        status="completed",
    )
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title="渲染 Word 文档",
        detail=str(generated_file.get("filename") or ""),
        status="completed",
        payload={"tool": "document_generation.render_docx", "file_id": generated_file.get("id")},
    )
    add_agent_event(
        db,
        run,
        event_type="result",
        title="文件已生成",
        detail=str(generated_file.get("filename") or ""),
        status="completed",
        payload={"generated_file": generated_file},
    )
    return finish_agent_run(db, run, status="completed", result={"generated_file": generated_file})


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
            "gaps": _safe_trace_list((think_result.get("metadata") or {}).get("gaps") if isinstance(think_result.get("metadata"), dict) else []),
            "conflicts": _safe_trace_list((think_result.get("metadata") or {}).get("conflicts") if isinstance(think_result.get("metadata"), dict) else []),
            "warnings": _safe_trace_list((think_result.get("metadata") or {}).get("warnings") if isinstance(think_result.get("metadata"), dict) else []),
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
            "gbrain_think": _gbrain_think_trace(think_result),
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


def _extract_skill_inputs(content: str, missing_inputs: list[dict]) -> dict:
    extracted: dict[str, str] = {}
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for item in missing_inputs:
        name = str(item.get("name") or "")
        label = str(item.get("label") or name)
        value = _find_labeled_value(lines, name, label)
        if value:
            extracted[name] = value

    if "label_items" in {str(item.get("name") or "") for item in missing_inputs}:
        table_lines = [line for line in lines if "|" in line]
        if len(table_lines) >= 2:
            extracted["label_items"] = "\n".join(table_lines)

    if "template_file" in {str(item.get("name") or "") for item in missing_inputs}:
        lowered = content.lower()
        if "模板" in content or ".xlsx" in lowered or ".xls" in lowered:
            extracted.setdefault("template_file", "default-template")

    return extracted


def _missing_input_fields_text(missing_inputs: list[dict]) -> str:
    fields = [
        f"- {item.get('label') or item.get('name') or '待补充字段'}"
        for item in missing_inputs
    ]
    return "\n".join(fields)


def _missing_input_instruction(skill_name: str, missing_inputs: list[dict]) -> str:
    normalized_skill = str(skill_name or "").strip()
    missing_names = {str(item.get("name") or "").strip() for item in missing_inputs}
    missing_labels = {str(item.get("label") or "").strip() for item in missing_inputs}
    if normalized_skill == "audio-transcription" or "audio_source" in missing_names or "音频或视频文件" in missing_labels:
        return "请先在当前会话上传或从项目文件中引用一个音频/视频文件，然后重新发送“将这段录音转录成文字”。支持 MP3、WAV、M4A、OGG、FLAC、MP4、MOV 等格式。"
    if normalized_skill in ("term-correction", "术语纠错") or "term_corrections" in missing_names:
        return "请提供术语纠正规则，每行一条，例如：LAM Wiki -> LLM Wiki。"
    fields = "、".join(item.get("label") or item.get("name") or "待补充字段" for item in missing_inputs)
    return f"请补充：{fields}。"


def _format_audio_transcription_reply(transcript_text: str, *, reply_extra: str = "") -> str:
    text = (transcript_text or "").strip()
    if not text:
        text = "未识别到可用的转写文本。"
    return (
        "已完成录音转文字。转写内容如下，可直接复制：\n\n"
        f"```text\n{text}\n```"
        f"{reply_extra}"
    )


def _find_labeled_value(lines: list[str], name: str, label: str) -> str | None:
    aliases = {name, label}
    if label.endswith("（每行一个标签）"):
        aliases.add(label.removesuffix("（每行一个标签）"))
    for line in lines:
        for alias in aliases:
            if not alias:
                continue
            pattern = rf"^{re.escape(alias)}\s*[:：=]\s*(.+)$"
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None


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
    context_trace = _build_context_trace(
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
            "gbrain_think": _gbrain_think_trace(think_result),
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
        from core.tools.media_transcription_tool import (
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
                context_trace=_build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=IntentType.SKILL_TRIGGER,
                    provider="project_r",
                    model="audio-transcription",
                    requested_model=req.model_profile or req.provider,
                    extra=_skill_context_extra(skill_response),
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
            context_trace=_build_context_trace(
                session=session,
                req=req,
                attachments=selected_attachments,
                sources=[],
                intent=IntentType.SKILL_TRIGGER,
                provider="project_r",
                model="audio-transcription",
                requested_model=req.model_profile or req.provider,
                extra=_skill_context_extra(skill_response),
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
    context_trace = _build_context_trace(
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
            **_skill_context_extra({"skill_run": skill_payload}),
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


def _skill_outputs_chat_text(skill) -> bool:
    mode = str((skill.execution or {}).get("mode") or "")
    if mode:
        return mode == "llm_chat_text"
    return any(str(output.get("type") or "") == "chat_text" for output in skill.outputs)


def _ensure_llm_chat_text_skill_allowed(skill) -> None:
    mode = str((skill.execution or {}).get("mode") or "")
    if mode != "llm_chat_text":
        return
    allowed_tools = {
        str(tool).strip()
        for tool in ((skill.governance or {}).get("allowed_tools") or (skill.execution or {}).get("allowed_tools") or [])
        if str(tool).strip()
    }
    if "llm.complete" not in allowed_tools:
        raise HTTPException(status_code=500, detail="Skill 执行策略缺少 llm.complete 授权")


def _chat_text_skill_input_payload(skill, content: str) -> dict[str, str]:
    for item in skill.inputs:
        if str(item.get("type") or "") == "text":
            return {str(item.get("name") or "input"): content}
    return {"input": content}


def _load_skill_prompt(skill) -> str:
    skill_file = BASE_DIR / skill.path
    prompt_file = skill_file.parent / "prompt.md"
    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _compose_skill_base_prompt(base_prompt: str | None, display_name: str, skill_prompt: str) -> str:
    parts: list[str] = []
    if base_prompt and base_prompt.strip():
        parts.append(base_prompt.strip())
    parts.append(
        f"当前启用的业务 Skill：{display_name}。"
        "请严格按该 Skill 的目的、输出结构和风险边界处理用户请求。"
    )
    if skill_prompt:
        parts.append("以下是该 Skill 的专用指令：\n\n" + skill_prompt)
    return "\n\n".join(parts)


def _maybe_run_web_search(
    query: str,
    enabled: bool,
    *,
    source_start_index: int = 1,
) -> tuple[list[dict], str, dict | None]:
    if not enabled:
        return [], "", None
    response = _run_web_search_skill(query)
    sources = web_results_to_sources(response)
    prompt = format_web_search_prompt(response, start_index=source_start_index)
    return sources, prompt, _web_search_trace(response, len(sources))


def _run_web_search_skill(query: str) -> WebSearchResponse:
    try:
        return search_web(query)
    except Exception as exc:  # pragma: no cover - defensive guard for provider bugs.
        logger.warning("web search skill failed unexpectedly", exc_info=True)
        return WebSearchResponse(
            query=" ".join(query.split()).strip(),
            provider="unknown",
            warnings=[f"unexpected_error:{type(exc).__name__}"],
        )


def _web_search_trace(response: WebSearchResponse, result_count: int) -> dict:
    return {
        "enabled": True,
        "skill_name": WEB_SEARCH_SKILL_NAME,
        "query": response.query,
        "provider": response.provider,
        "result_count": result_count,
        "warnings": response.warnings,
    }


def _web_search_context_extra(trace: dict | None) -> dict:
    if not trace:
        return {}
    return {"web_search": trace}


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
