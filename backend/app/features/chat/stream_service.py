"""SSE 流式传输服务。

本模块负责：
- 组合 system prompt / 知识库上下文 / 附件上下文（复用 api/chat.py 已有 helper）
- 调用 LLMClient.stream() 获取增量块
- 将增量块包装为 SSE 事件
- 流式完成后持久化 assistant message 并返回最终 metadata
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Callable, Generator
from datetime import datetime, timezone

from app.shared.llm.client import LLMClient, StreamResponse
from models.message import ChatMessage
from models.session import ChatSession
from sqlalchemy.orm import Session as DBSession

logger = logging.getLogger(__name__)

SSE_PREFIX = "data: "
SSE_DONE = "data: [STREAM-DONE]"


def sse_event(payload: dict | str) -> str:
    """将 dict 或纯文本转换为 SSE data 行（不含 event: 字段）。"""
    if isinstance(payload, dict):
        return SSE_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n\n"
    return SSE_PREFIX + str(payload) + "\n\n"


def _persist_assistant_message(
    db: DBSession,
    session_id: int,
    user_id: int,
    aggregated: StreamResponse,
    sources_json: str,
    context_json: str,
    rag_used: bool,
) -> ChatMessage:
    """持久化完整的 assistant 消息。"""
    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=aggregated.text,
        provider=aggregated.provider,
        model=aggregated.model,
        token_input=aggregated.usage.get("input_tokens", 0),
        token_output=aggregated.usage.get("output_tokens", 0),
        token_total=aggregated.token_cost,
        status="success",
        rag_used=rag_used,
        sources_json=sources_json,
        context_json=context_json,
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    db.query(ChatSession).filter(ChatSession.id == session_id).update(
        {"updated_at": datetime.now(timezone.utc)}
    )
    db.commit()
    db.refresh(assistant_message)
    return assistant_message


def generate_sse_stream(
    *,
    llm_client: LLMClient,
    llm_messages: list[dict],
    system_prompt: str,
    thinking: bool,
    session_factory: Callable[[], DBSession],
    session_id: int,
    user_id: int,
    requested_model: str,
    sources_json: str,
    context_json: str,
    rag_used: bool,
    temperature: float | None = None,
    llm_user_content: str = "",
    user_message_id: int | None = None,
    user_attachments_json: str = "[]",
    intent: str = "chat",
) -> Generator[str, None, None]:
    """同步生成器，产生 SSE 事件。

    调用方通过 FastAPI StreamingResponse 包装此生成器。
    SSE 事件流格式：
    - data: {"delta": "..."}  增量文本
    - data: {"done":true, "reply":"...", "usage":{...}, "assistant_message_id":...}  最终元数据
    """
    accumulated_text: list[str] = []
    final_response: StreamResponse | None = None
    db = session_factory()

    try:
        stream_gen = llm_client.stream(
            llm_messages,
            system_prompt=system_prompt,
            thinking=thinking,
            temperature=temperature,
        )
    except Exception as exc:
        logger.exception("初始化流式请求失败")
        _write_chat_audit(db, user_id, session_id, llm_user_content, False, str(exc))
        yield sse_event({"error": str(exc)})
        yield SSE_DONE + "\n\n"
        db.close()
        return

    try:
        while True:
            try:
                chunk = next(stream_gen)
            except StopIteration as exc:
                final_response = exc.value  # Generator return value (PEP 380)
                break

            if chunk.text_delta:
                accumulated_text.append(chunk.text_delta)
                yield sse_event({"delta": chunk.text_delta})

        # 流式完成，持久化
        if final_response is None:
            _write_chat_audit(db, user_id, session_id, llm_user_content, False, "stream 未返回汇总")
            yield sse_event({"error": "流式响应未返回汇总信息"})
            yield SSE_DONE + "\n\n"
            return

        assistant_message = _persist_assistant_message(
            db=db,
            session_id=session_id,
            user_id=user_id,
            aggregated=final_response,
            sources_json=sources_json,
            context_json=context_json,
            rag_used=rag_used,
        )

        _write_chat_audit(
            db,
            user_id,
            session_id,
            llm_user_content,
            True,
            f"provider={final_response.provider}, model={final_response.model}, key_index={final_response.key_index}, stream=1",
            token_cost=final_response.token_cost,
        )

        yield sse_event({
            "done": True,
            "reply": final_response.text,
            "provider": final_response.provider,
            "model": final_response.model,
            "key_index": final_response.key_index,
            "usage": final_response.usage,
            "assistant_message_id": assistant_message.id,
            "user_message_id": user_message_id,
            "sources": json.loads(sources_json) if sources_json else [],
            "user_attachments": json.loads(user_attachments_json) if user_attachments_json else [],
            "context_trace": json.loads(context_json) if context_json else None,
            "intent": intent,
        })
        yield SSE_DONE + "\n\n"

    except Exception as exc:
        logger.exception("流式传输过程中异常")
        _write_chat_audit(db, user_id, session_id, llm_user_content, False, f"stream_error: {exc}")
        # 不持久化 partial text（避免截断回复被标记为成功）
        # 始终写入 status="failed" 失败消息
        _write_failed_assistant_message(db, user_id, session_id, str(exc), requested_model)
        yield sse_event({"error": str(exc)})
        yield SSE_DONE + "\n\n"
    finally:
        db.close()


def _write_chat_audit(
    db: DBSession,
    user_id: int,
    session_id: int,
    prompt: str,
    success: bool,
    detail: str,
    token_cost: int = 0,
) -> None:
    from models.audit_log import AuditLog

    db.add(
        AuditLog(
            user_id=user_id,
            action="chat_stream" if success else "chat_stream_failed",
            detail=f"session={session_id}, {detail}, tokens={token_cost}",
            success=success,
        )
    )
    db.commit()


def _write_failed_assistant_message(
    db: DBSession,
    user_id: int,
    session_id: int,
    detail: str,
    requested_model: str,
) -> None:
    """写入 'failed' 状态的 assistant 消息。"""
    from models.message import ChatMessage  # noqa: reimport for clarity
    from models.session import ChatSession  # noqa: reimport for clarity
    from datetime import datetime, timezone  # noqa: reimport for clarity

    assistant_message = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=detail,
        provider="system",
        model=requested_model or "",
        token_input=0,
        token_output=0,
        token_total=0,
        status="failed",
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    db.query(ChatSession).filter(ChatSession.id == session_id).update(
        {"updated_at": datetime.now(timezone.utc)}
    )
    db.commit()
