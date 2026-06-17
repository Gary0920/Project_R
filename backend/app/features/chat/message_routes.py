from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.chat.access import get_user_session as _get_user_session
from app.features.chat.intent import IntentType
from app.features.chat.context_trace import build_context_trace
from app.features.chat.internal import (
    build_llm_messages_before as _build_llm_messages_before,
    ensure_version_group as _ensure_version_group,
    exclude_active_messages_after as _exclude_active_messages_after,
    message_pair_delete_targets as _message_pair_delete_targets,
    message_query as _message_query,
    next_version_index as _next_version_index,
    set_active_version as _set_active_version,
)
from app.features.chat.schemas import (
    ActivateMessageVersionResponse,
    EditMessageRequest,
    EditMessageResponse,
    RegenerateMessageRequest,
    RegenerateMessageResponse,
    RestoreMessagesRequest,
    RestoreMessagesResponse,
)
from app.features.chat.web_search_context import web_search_context_extra as _web_search_context_extra
from app.shared.llm.client import LLMConfigurationError, LLMProviderError
from models import get_db
from models.audit_log import AuditLog
from models.message import ChatMessage
from models.user import User

router = APIRouter()


def _api():
    import api.chat as chat_api

    return chat_api


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
        "messages": [_api()._message_to_response_dict(db, message) for message in restored],
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
    web_sources, web_search_context, web_search_trace = _api()._maybe_run_web_search(
        web_search_query,
        req.web_search,
    )
    response_sources = _api()._serialize_sources(web_sources)
    system_prompt = req.system_prompt
    if req.web_search:
        system_prompt = _api()._compose_system_prompt(
            req.system_prompt,
            [],
            IntentType.CHAT,
            "",
            False,
            web_search_context=web_search_context,
        )
    try:
        llm_response = _api().get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
            temperature=req.temperature,
        )
    except LLMConfigurationError as exc:
        _api()._write_chat_audit(db, user.id, session_id, target.content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _api()._write_chat_audit(db, user.id, session_id, target.content, False, detail)
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
        "assistant_message": _api()._message_to_response_dict(db, assistant_message),
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
    web_sources, web_search_context, web_search_trace = _api()._maybe_run_web_search(
        content,
        req.web_search,
    )
    response_sources = _api()._serialize_sources(web_sources)
    system_prompt = req.system_prompt
    if req.web_search:
        system_prompt = _api()._compose_system_prompt(
            req.system_prompt,
            [],
            IntentType.CHAT,
            "",
            False,
            web_search_context=web_search_context,
        )
    try:
        llm_response = _api().get_llm_client(requested_model).complete(
            llm_messages,
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        _api()._write_chat_audit(db, user.id, session_id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        _api()._write_chat_audit(db, user.id, session_id, content, False, detail)
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
        "user_message": _api()._message_to_response_dict(db, user_message),
        "assistant_message": _api()._message_to_response_dict(db, assistant_message),
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
    return {"ok": True, "message": _api()._message_to_response_dict(db, selected)}


