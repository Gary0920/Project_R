from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.features.chat.context_trace import generated_file_context
from app.features.chat.intent import IntentType
from app.features.chat.schemas import SendMessageRequest
from app.features.skills.runner import SkillRunner
from models.message import ChatMessage
from models.user import User


@dataclass(frozen=True)
class SendMessagePorts:
    get_user_session: Callable[..., Any]
    load_selected_session_attachments: Callable[..., Any]
    bind_attachments_to_message: Callable[..., Any]
    parse_knowledge_command: Callable[..., Any]
    parse_file_generation_command: Callable[..., Any]
    attachment_only_prompt: Callable[..., Any]
    classify_intent: Callable[..., Any]
    should_reduce_knowledge_context: Callable[..., Any]
    continue_active_skill_run: Callable[..., Any]
    write_skill_assistant_response: Callable[..., Any]
    build_context_trace: Callable[..., Any]
    skill_context_extra: Callable[..., Any]
    build_llm_messages: Callable[..., Any]
    run_chat_text_skill_by_name: Callable[..., Any]
    start_skill_run_by_name: Callable[..., Any]
    start_skill_run_from_chat: Callable[..., Any]
    run_gbrain_think_response: Callable[..., Any]
    is_image_attachment: Callable[..., Any]
    is_audio_attachment: Callable[..., Any]
    is_video_attachment: Callable[..., Any]
    transcribe_audio_attachments_for_chat: Callable[..., Any]
    get_llm_client: Callable[..., Any]
    write_failed_assistant_message: Callable[..., Any]
    write_chat_audit: Callable[..., Any]
    load_vision_image_inputs: Callable[..., Any]
    attach_vision_images_to_latest_user_message: Callable[..., Any]
    search_knowledge_sources: Callable[..., Any]
    maybe_run_web_search: Callable[..., Any]
    serialize_sources: Callable[..., Any]
    load_attachment_context_from_attachments: Callable[..., Any]
    compose_system_prompt: Callable[..., Any]
    web_search_context_extra: Callable[..., Any]
    generate_sse_stream: Callable[..., Any]
    session_factory: Callable[..., Session]
    attachment_to_response_dict: Callable[..., Any]
    create_generated_file: Callable[..., Any]
    write_document_generation_agent_run: Callable[..., Any]
    serialize_agent_run: Callable[..., Any]
    llm_configuration_error: type[Exception]
    llm_provider_error: type[Exception]


def send_message_use_case(
    db: Session,
    session_id: int,
    req: SendMessageRequest,
    user: User,
    *,
    ports: SendMessagePorts,
) -> Any:
    session = ports.get_user_session(db, user.id, session_id)
    content = req.content.strip()
    selected_attachments = ports.load_selected_session_attachments(db, user.id, session_id, req.files)
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
    ports.bind_attachments_to_message(db, selected_attachments, user_message)

    forced_knowledge, knowledge_query = ports.parse_knowledge_command(content)
    document_format, document_prompt = ports.parse_file_generation_command(content)
    if req.force_knowledge_query:
        forced_knowledge = True
        knowledge_query = content
    llm_user_content = document_prompt or content or ports.attachment_only_prompt(selected_attachments)
    query_content = knowledge_query or llm_user_content
    intent = ports.classify_intent(query_content)
    effective_intent = IntentType.DOCUMENT_GENERATION if document_format else IntentType.RAG_QUERY if forced_knowledge else intent.intent
    reduce_knowledge_context = ports.should_reduce_knowledge_context(req.selected_prompt_id, forced_knowledge)
    if reduce_knowledge_context and effective_intent == IntentType.RAG_QUERY:
        effective_intent = IntentType.CHAT

    active_skill_response = None
    if effective_intent != IntentType.DOCUMENT_GENERATION and not req.selected_skill:
        active_skill_response = ports.continue_active_skill_run(db, user.id, session_id, llm_user_content)
    if active_skill_response:
        return ports.write_skill_assistant_response(
            db,
            user.id,
            session,
            user_message.id,
            content,
            active_skill_response,
            context_trace=ports.build_context_trace(
                session=session,
                req=req,
                attachments=selected_attachments,
                sources=[],
                intent=effective_intent,
                provider="project_r",
                model="skill_runner",
                requested_model=requested_model,
                extra=ports.skill_context_extra(active_skill_response),
            ),
        )

    llm_messages = ports.build_llm_messages(db, user.id, session_id)
    if document_format and document_prompt and llm_messages:
        llm_messages[-1] = {**llm_messages[-1], "content": document_prompt}
    if req.selected_skill and effective_intent != IntentType.DOCUMENT_GENERATION:
        chat_text_response = ports.run_chat_text_skill_by_name(
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
        skill_response = ports.start_skill_run_by_name(db, user.id, session_id, req.selected_skill)
        if skill_response:
            return ports.write_skill_assistant_response(
                db,
                user.id,
                session,
                user_message.id,
                content,
                skill_response,
                context_trace=ports.build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=ports.skill_context_extra(skill_response),
                ),
            )
    if effective_intent == IntentType.SKILL_TRIGGER:
        matched_skill = SkillRunner.get().match_skill(content)
        if matched_skill:
            chat_text_response = ports.run_chat_text_skill_by_name(
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
        skill_response = ports.start_skill_run_from_chat(db, user.id, session_id, content)
        if skill_response:
            return ports.write_skill_assistant_response(
                db,
                user.id,
                session,
                user_message.id,
                content,
                skill_response,
                context_trace=ports.build_context_trace(
                    session=session,
                    req=req,
                    attachments=selected_attachments,
                    sources=[],
                    intent=effective_intent,
                    provider="project_r",
                    model="skill_runner",
                    requested_model=requested_model,
                    extra=ports.skill_context_extra(skill_response),
                ),
            )

    if forced_knowledge:
        return ports.run_gbrain_think_response(
            db,
            user.id,
            session,
            user_message.id,
            content,
            query_content,
        )

    selected_image_attachments = [attachment for attachment in selected_attachments if ports.is_image_attachment(attachment)]
    selected_audio_attachments = [
        attachment for attachment in selected_attachments if ports.is_audio_attachment(attachment)
    ]
    selected_video_attachments = [
        attachment for attachment in selected_attachments if ports.is_video_attachment(attachment)
    ]
    if selected_audio_attachments and not req.selected_skill:
        matched_skill = SkillRunner.get().match_skill(content)
        if matched_skill and matched_skill["skill"]["name"] == "audio-transcription":
            chat_text_response = ports.run_chat_text_skill_by_name(
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
        llm_client = ports.get_llm_client(requested_model)
    except ports.llm_configuration_error as exc:
        ports.write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc

    supports_vision = bool(getattr(getattr(llm_client, "settings", None), "supports_vision", False))
    if selected_image_attachments and not supports_vision:
        detail = "当前模型不支持图片理解，请切换到支持图像输入的 MiMo 模型后再发送。"
        ports.write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    if selected_video_attachments:
        detail = "当前版本暂未接入视频附件理解；如需处理会议视频，请使用会议工作流的转写能力。"
        ports.write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=400, detail=detail)
    try:
        vision_images = ports.load_vision_image_inputs(selected_image_attachments) if selected_image_attachments else []
    except HTTPException as exc:
        detail = str(exc.detail)
        ports.write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise
    if vision_images:
        llm_messages = ports.attach_vision_images_to_latest_user_message(
            llm_messages,
            vision_images,
            getattr(llm_client.settings, "provider", ""),
        )
    knowledge_sources = ports.search_knowledge_sources(
        db,
        query_content,
        effective_intent,
        session.workspace_id,
        reduce_knowledge_context=reduce_knowledge_context,
    )
    web_sources, web_search_context, web_search_trace = ports.maybe_run_web_search(
        query_content,
        req.web_search,
        source_start_index=len(knowledge_sources) + 1,
    )
    response_sources = ports.serialize_sources([*knowledge_sources, *web_sources])
    attachment_context = ports.load_attachment_context_from_attachments(
        selected_attachments,
        supports_vision=bool(vision_images),
    )
    audio_understanding = None
    if selected_audio_attachments:
        audio_understanding = ports.transcribe_audio_attachments_for_chat(
            selected_audio_attachments,
            model_profile=req.model_profile,
        )
        if audio_understanding.context:
            attachment_context = "\n\n".join(part for part in [attachment_context, audio_understanding.context] if part)
    system_prompt = ports.compose_system_prompt(
        req.system_prompt,
        knowledge_sources,
        effective_intent,
        attachment_context,
        reduce_knowledge_context,
        web_search_context=web_search_context,
    )

    if req.stream:
        ctx_trace = ports.build_context_trace(
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
                **ports.web_search_context_extra(web_search_trace),
                **audio_understanding_context_extra(audio_understanding),
            },
        )
        return StreamingResponse(
            ports.generate_sse_stream(
                llm_client=llm_client,
                llm_messages=llm_messages,
                system_prompt=system_prompt,
                thinking=req.thinking,
                temperature=req.temperature,
                session_factory=ports.session_factory,
                session_id=session.id,
                user_id=user.id,
                requested_model=requested_model,
                sources_json=json.dumps(response_sources, ensure_ascii=False),
                context_json=json.dumps(ctx_trace, ensure_ascii=False),
                rag_used=bool(response_sources),
                llm_user_content=llm_user_content,
                user_message_id=user_message.id,
                user_attachments_json=json.dumps(
                    [ports.attachment_to_response_dict(a) for a in selected_attachments],
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
    except ports.llm_configuration_error as exc:
        ports.write_failed_assistant_message(db, user.id, session_id, str(exc), requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, str(exc))
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from exc
    except ports.llm_provider_error as exc:
        status_code = 503 if exc.retryable else 502
        detail = f"{exc}"
        if exc.key_index:
            detail = f"{detail}（key_index={exc.key_index}）"
        ports.write_failed_assistant_message(db, user.id, session_id, detail, requested_model)
        ports.write_chat_audit(db, user.id, session_id, llm_user_content, False, detail)
        raise HTTPException(status_code=status_code, detail="AI 服务暂时不可用，请稍后重试") from exc

    usage = llm_response.usage
    generated_file = None
    if effective_intent == IntentType.DOCUMENT_GENERATION:
        generated_file = ports.create_generated_file(
            db,
            user.id,
            session_id,
            document_prompt or content,
            llm_response.text,
            output_format=document_format or "docx",
        )
    context_trace = ports.build_context_trace(
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
            **ports.web_search_context_extra(web_search_trace),
            **audio_understanding_context_extra(audio_understanding),
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
        agent_run = ports.write_document_generation_agent_run(
            db,
            user_id=user.id,
            session=session,
            message_id=assistant_message.id,
            user_prompt=content,
            generated_file=generated_file,
        )
        db.commit()

    ports.write_chat_audit(
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
        "user_attachments": [ports.attachment_to_response_dict(attachment) for attachment in selected_attachments],
        "agent_run": ports.serialize_agent_run(db, agent_run),
        "context_trace": context_trace,
    }


def audio_understanding_context_extra(audio_understanding: Any) -> dict[str, Any]:
    if not audio_understanding:
        return {}
    warnings = list(getattr(audio_understanding, "warnings", []) or [])
    return {
        "audio_understanding": {
            "transcript_count": getattr(audio_understanding, "transcript_count", 0),
            "warning_count": len(warnings),
            "warnings": warnings[:5],
        }
    }
