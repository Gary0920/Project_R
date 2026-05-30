from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from api.auth import get_current_user
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
from models import get_db
from models.audit_log import AuditLog
from models.attachment import SessionAttachment
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.message import ChatMessage
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User
from models.workspace import WorkspaceMember

router = APIRouter(prefix="/chat", tags=["chat"])
HISTORY_LIMIT = 20
logger = logging.getLogger(__name__)
KNOWLEDGE_COMMAND_PREFIX = "/query"
KNOWLEDGE_THINK_COMMAND_PREFIX = "/think"
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
        return value.isoformat() + "Z"

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
    stream: bool = False
    thinking: bool = False
    system_prompt: str | None = None


class RegenerateMessageRequest(BaseModel):
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
    system_prompt: str | None = None
    temperature: float = Field(default=0.9, ge=0, le=2)


class EditMessageRequest(BaseModel):
    content: str
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
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


class AttachmentResponse(BaseModel):
    id: int
    session_id: int
    original_name: str
    content_type: str
    size: int
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat() + "Z"

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
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat() + "Z"

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
        return value.isoformat() + "Z"

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
        _ensure_workspace_member(db, user.id, req.workspace_id)
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
    try:
        llm_response = get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=req.system_prompt,
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
        rag_used=target.rag_used,
        sources_json=target.sources_json,
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
    try:
        llm_response = get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=req.system_prompt,
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
        rag_used=False,
        sources_json="[]",
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
        _ensure_workspace_member(db, user.id, req.workspace_id)
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
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")

    selected_attachments = _load_selected_session_attachments(db, user.id, session_id, req.files)
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

    forced_knowledge, knowledge_query, use_gbrain_think = _parse_knowledge_command(content)
    intent = classify_intent(knowledge_query)
    effective_intent = IntentType.RAG_QUERY if forced_knowledge else intent.intent
    reduce_knowledge_context = _should_reduce_knowledge_context(req.selected_prompt_id, forced_knowledge)
    if reduce_knowledge_context and effective_intent == IntentType.RAG_QUERY:
        effective_intent = IntentType.CHAT

    active_skill_response = None
    if effective_intent != IntentType.DOCUMENT_GENERATION and not req.selected_skill:
        active_skill_response = _continue_active_skill_run(db, user.id, session_id, content)
    if active_skill_response:
        return _write_skill_assistant_response(db, user.id, session, user_message.id, content, active_skill_response)

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
            return _write_skill_assistant_response(db, user.id, session, user_message.id, content, skill_response)
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
            return _write_skill_assistant_response(db, user.id, session, user_message.id, content, skill_response)

    if forced_knowledge and use_gbrain_think:
        return _run_gbrain_think_response(db, user.id, session, user_message.id, content, knowledge_query)

    try:
        llm_client = get_llm_client(requested_model)
    except LLMConfigurationError as exc:
        _write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc

    selected_image_attachments = [attachment for attachment in selected_attachments if _is_image_attachment(attachment)]
    selected_audio_video_attachments = [
        attachment for attachment in selected_attachments if _is_audio_video_attachment(attachment)
    ]
    supports_vision = bool(getattr(getattr(llm_client, "settings", None), "supports_vision", False))
    if selected_image_attachments and not supports_vision:
        detail = "当前模型不支持图片理解，请切换到支持图像输入的 MiMo 模型后再发送。"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    if selected_audio_video_attachments:
        detail = "当前版本暂未接入视频/音频附件理解，请先改用图片或可提取文本的附件。"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    try:
        vision_images = _load_vision_image_inputs(selected_image_attachments) if selected_image_attachments else []
    except HTTPException as exc:
        detail = str(exc.detail)
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, detail)
        raise
    if vision_images:
        llm_messages = _attach_vision_images_to_latest_user_message(
            llm_messages,
            vision_images,
            getattr(llm_client.settings, "provider", ""),
        )
    knowledge_sources = _search_knowledge_sources(
        db,
        knowledge_query,
        effective_intent,
        session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    response_sources = _serialize_sources(knowledge_sources)
    attachment_context = _load_attachment_context_from_attachments(selected_attachments, supports_vision=bool(vision_images))
    system_prompt = _compose_system_prompt(
        req.system_prompt,
        knowledge_sources,
        effective_intent,
        attachment_context,
        reduce_knowledge_context,
    )

    try:
        llm_response = llm_client.complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        _write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        _write_chat_audit(db, user.id, session_id, content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    usage = llm_response.usage
    generated_file = None
    if effective_intent == IntentType.DOCUMENT_GENERATION:
        generated_file = _create_generated_docx(db, user.id, session_id, content, llm_response.text)
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
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)

    _write_chat_audit(
        db,
        user.id,
        session_id,
        content,
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
    )


@router.post("/sessions/{session_id}/attachments/upload", response_model=AttachmentResponse)
async def upload_session_attachment(
    session_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    )


def _store_session_attachment(
    db: Session,
    user: User,
    session_id: int,
    filename: str,
    content_type: str,
    content: bytes,
) -> SessionAttachment:
    return session_attachments.store_session_attachment(
        db,
        user,
        session_id,
        filename,
        _safe_content_type(content_type, filename),
        content,
        attachment_dir=_attachment_dir,
    )


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
def list_session_attachments(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_user_session(db, user.id, session_id)
    return session_attachments.list_session_attachments(db, user.id, session_id)


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


def _ensure_workspace_member(db: Session, user_id: int, workspace_id: int) -> None:
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not member:
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


def _message_to_response_dict(db: Session, message: ChatMessage) -> dict:
    versions = _message_versions(db, message)
    feedback = _load_latest_message_feedback(message)
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
                "created_at": version.created_at,
            }
            for version in versions
        ],
        "feedback_rating": feedback.get("rating") if feedback else None,
        "feedback_comment": feedback.get("comment") if feedback else None,
        "sources": message.sources,
        "created_at": message.created_at,
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
    payload = [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
        if message.content
    ]
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
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
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
    return [
        {"role": message.role, "content": message.content}
        for message in reversed(messages)
        if message.content
    ]


def _parse_knowledge_command(content: str) -> tuple[bool, str, bool]:
    stripped = content.strip()
    if stripped == KNOWLEDGE_THINK_COMMAND_PREFIX:
        return True, stripped, True
    if stripped.startswith(f"{KNOWLEDGE_THINK_COMMAND_PREFIX} "):
        query = stripped[len(KNOWLEDGE_THINK_COMMAND_PREFIX) :].strip()
        return True, query or stripped, True
    if stripped == KNOWLEDGE_COMMAND_PREFIX:
        return True, stripped, False
    if stripped.startswith(f"{KNOWLEDGE_COMMAND_PREFIX} "):
        query = stripped[len(KNOWLEDGE_COMMAND_PREFIX) :].strip()
        if query.lower() == "--think":
            return True, stripped, True
        if query.lower().startswith("--think "):
            think_query = query[len("--think") :].strip()
            return True, think_query or stripped, True
        return True, query or stripped, False
    return False, stripped, False


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
        default_workspace_resolver=_default_workspace_for_attachment,
        logger=logger,
    )


def _default_workspace_for_attachment(db: Session, user: User):
    from api.workspaces import ensure_default_workspace

    return ensure_default_workspace(db, user)


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
        fields = "\n".join(f"- {item.get('label') or item.get('name')}" for item in missing)
        reply = f"已识别到业务 Skill：{skill.display_name}。\n\n请补充以下信息：\n{fields}"
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
        fields = "\n".join(f"- {item.get('label') or item.get('name')}" for item in current["missing_inputs"])
        return {
            "reply": f"我还没有识别到可写入 {skill.display_name} 的字段。\n\n请按下面字段补充：\n{fields}",
            "skill_run": current,
            "generated_file": generated_file_payload(db, run.generated_file_id),
        }

    run = runner.submit_input(db, run, extracted)
    run = execute_ready_run(db, run)
    payload = run_to_dict(run, skill)
    if run.status == "completed":
        reply = f"{skill.display_name} 已生成完成，可以下载结果文件。"
    else:
        fields = "\n".join(f"- {item.get('label') or item.get('name')}" for item in payload["missing_inputs"])
        reply = f"已记录补充信息，还需要：\n{fields}"
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
) -> dict:
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
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
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
    }


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

    input_payload = _chat_text_skill_input_payload(skill, content)
    run = runner.start_run(db, skill.name, user_id=user.id, session_id=session.id, inputs=input_payload)
    run.status = "completed"
    db.commit()
    db.refresh(run)

    reduce_knowledge_context = _should_reduce_knowledge_context(req.selected_prompt_id, False)
    knowledge_sources = _search_knowledge_sources(
        db,
        content,
        intent,
        session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    response_sources = _serialize_sources(knowledge_sources)
    attachment_context = _load_attachment_context(db, user.id, session.id, req.files)
    skill_prompt = _load_skill_prompt(skill)
    system_prompt = _compose_system_prompt(
        _compose_skill_base_prompt(req.system_prompt, skill.display_name, skill_prompt),
        knowledge_sources,
        intent,
        attachment_context,
        reduce_knowledge_context,
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
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)

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
        "skill_run": run_to_dict(run, skill),
    }


def _skill_outputs_chat_text(skill) -> bool:
    return any(str(output.get("type") or "") == "chat_text" for output in skill.outputs)


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
) -> str | None:
    return compose_system_prompt(
        base_prompt,
        rag_sources,
        intent=intent,
        attachment_context=attachment_context,
        reduce_knowledge_context=reduce_knowledge_context,
        global_base_prompt=_load_global_base_prompt(),
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
