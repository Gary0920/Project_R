"""Chat response helper functions — extracted from api/chat.py.

Verbatim extraction: no GBrain code changes, no behavioral changes.
Monkeypatch-sensitive dependencies (KNOWLEDGE_SOURCES, etc.) are
injected as callbacks by thin wrappers in api/chat.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.features.agents.events import serialize_agent_run
from app.features.chat.context_trace import build_context_trace, gbrain_think_trace
from app.features.chat.intent import IntentType
from app.features.skills.runner import SkillRunner, run_to_dict
from models.audit_log import AuditLog
from models.message import ChatMessage
from models.session import ChatSession


def run_gbrain_think_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    knowledge_query: str,
    *,
    knowledge_sources: Any,
    serialize_sources_fn: Any,
    write_gbrain_think_agent_run_fn: Any,
) -> dict:
    """Run a GBrain Think query and write the response as a ChatMessage.

    Args:
        knowledge_sources: KNOWLEDGE_SOURCES instance (injected by wrapper).
        serialize_sources_fn: _serialize_sources function (injected).
        write_gbrain_think_agent_run_fn: _write_gbrain_think_agent_run wrapper (injected).
    """
    think_result = knowledge_sources.think(db, knowledge_query, workspace_id=session.workspace_id)
    response_sources = serialize_sources_fn(think_result.get("sources", []))
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
    agent_run = write_gbrain_think_agent_run_fn(
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


def run_chat_text_skill_by_name(
    db: Session,
    user: Any,
    session: ChatSession,
    user_message_id: int,
    content: str,
    req: Any,
    intent: IntentType,
    skill_name: str,
    *,
    # Callbacks injected by api/chat.py wrapper
    skill_outputs_chat_text: Any,
    ensure_llm_chat_text_skill_allowed: Any,
    chat_text_skill_input_payload: Any,
    run_audio_transcription_skill_response: Any,
    load_selected_session_attachments: Any,
    write_skill_assistant_response: Any,
    should_reduce_knowledge_context: Any,
    search_knowledge_sources: Any,
    maybe_run_web_search: Any,
    serialize_sources: Any,
    load_attachment_context_from_attachments: Any,
    load_skill_prompt: Any,
    compose_system_prompt: Any,
    compose_skill_base_prompt: Any,
    get_llm_client: Any,
    build_llm_messages: Any,
    write_failed_assistant_message: Any,
    write_chat_audit: Any,
    write_skill_agent_run: Any,
    serialize_agent_run: Any,
    build_context_trace: Any,
    skill_context_extra: Any,
    web_search_context_extra: Any,
    LLMConfigurationError: Any,
    LLMProviderError: Any,
) -> dict | None:
    """Run a chat text skill: start a run, call LLM, write the response.

    Verbatim extraction from api/chat.py. All dependencies are injected
    via callbacks to support monkeypatching and avoid circular imports.
    """
    runner = SkillRunner.get()
    skill = runner.get_skill(skill_name)
    if not skill or not skill_outputs_chat_text(skill):
        return None
    ensure_llm_chat_text_skill_allowed(skill)

    input_payload = chat_text_skill_input_payload(skill, content)
    run = runner.start_run(db, skill.name, user_id=user.id, session_id=session.id, inputs=input_payload)
    run.status = "completed"
    db.commit()
    db.refresh(run)

    if skill_name == "audio-transcription":
        return run_audio_transcription_skill_response(
            db, user, session, user_message_id, content, req,
            run, skill,
            load_selected_attachments=load_selected_session_attachments,
            write_skill_response=write_skill_assistant_response,
        )

    reduce_knowledge_context = should_reduce_knowledge_context(req.selected_prompt_id, False)
    knowledge_sources = search_knowledge_sources(
        db, content, intent, session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    web_sources, web_search_context, web_search_trace = maybe_run_web_search(
        content, req.web_search,
        source_start_index=len(knowledge_sources) + 1,
    )
    response_sources = serialize_sources([*knowledge_sources, *web_sources])
    selected_attachments = load_selected_session_attachments(db, user.id, session.id, req.files)
    attachment_context = load_attachment_context_from_attachments(selected_attachments, supports_vision=False)
    skill_prompt = load_skill_prompt(skill)
    system_prompt = compose_system_prompt(
        compose_skill_base_prompt(req.system_prompt, skill.display_name, skill_prompt),
        knowledge_sources, intent, attachment_context,
        reduce_knowledge_context,
        web_search_context=web_search_context,
    )
    requested_model = req.model_profile or req.provider

    try:
        llm_response = get_llm_client(requested_model).complete(
            build_llm_messages(db, user.id, session.id),
            system_prompt=system_prompt,
            thinking=req.thinking,
        )
    except LLMConfigurationError as exc:
        write_failed_assistant_message(db, user.id, session.id, str(exc), requested_model)
        write_chat_audit(db, user.id, session.id, content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except LLMProviderError as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        write_failed_assistant_message(db, user.id, session.id, detail, requested_model)
        write_chat_audit(db, user.id, session.id, content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    usage = llm_response.usage
    skill_payload = run_to_dict(run, skill)
    context_trace = build_context_trace(
        session=session, req=req, attachments=selected_attachments,
        sources=response_sources, intent=IntentType.SKILL_TRIGGER,
        provider=llm_response.provider, model=llm_response.model,
        requested_model=requested_model,
        reduce_knowledge_context=reduce_knowledge_context,
        extra={
            **skill_context_extra({"skill_run": skill_payload}),
            **web_search_context_extra(web_search_trace),
        },
    )
    assistant_message = ChatMessage(
        session_id=session.id, user_id=user.id, role="assistant",
        content=llm_response.text, provider=llm_response.provider,
        model=llm_response.model,
        token_input=usage.get("input_tokens", 0),
        token_output=usage.get("output_tokens", 0),
        token_total=llm_response.token_cost,
        status="success", rag_used=bool(response_sources),
        sources_json=json.dumps(response_sources, ensure_ascii=False),
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    agent_run = write_skill_agent_run(
        db, user_id=user.id, session=session,
        message_id=assistant_message.id,
        skill_response={
            "reply": llm_response.text,
            "skill_run": skill_payload,
            "generated_file": None,
        },
    )
    db.commit()

    write_chat_audit(
        db, user.id, session.id, content, True,
        f"skill_run={skill.name}, provider={llm_response.provider}, "
        f"model={llm_response.model}, key_index={llm_response.key_index}",
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
