"""会话导出服务 — 在内存中组装 Markdown 或 JSON 格式的完整对话记录。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from models.attachment import SessionAttachment
from models.message import ChatMessage
from models.session import ChatSession
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

ExportFormat = Literal["markdown", "json"]

EXPORT_MAX_MESSAGES = 200               # 单次导出最大消息数
# SQLite length() 返回字符数，非 ASCII（如 CJK）UTF-8 可达 3 倍。
# 因此字符上限按 10M 字符设 → 实际字节上限约 10-30 MB。
EXPORT_MAX_TOTAL_CHARS = 10 * 1024 * 1024
EXPORT_MAX_PER_MESSAGE_CHARS = 2 * 1024 * 1024


def _format_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def _parse_json_field(value: str, default: object = None) -> object:
    if not value or value in ("[]", "{}", '""'):
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def _sources_markdown(msg: ChatMessage) -> str:
    sources = _parse_json_field(msg.sources_json)
    if not sources or not isinstance(sources, list) or len(sources) == 0:
        return ""
    lines: list[str] = ["", "> 引用来源:"]
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            continue
        title = src.get("source_title") or src.get("title") or src.get("path") or f"来源 {i + 1}"
        section = src.get("section_path") or ""
        excerpt = ""
        if isinstance(src.get("content"), str) and src["content"].strip():
            excerpt = src["content"].strip()[:200]
            excerpt = excerpt.replace("\n", " ").replace("\r", "")
        lines.append(f"> [{i + 1}] {title}{(' / ' + section) if section else ''}")
        if excerpt:
            lines.append(f">     {excerpt}")
    lines.append("")
    return "\n".join(lines)


def _load_attachment_names(db: DBSession, message_id: int) -> list[str]:
    stmt = (
        select(SessionAttachment.original_name)
        .where(SessionAttachment.message_id == message_id)
        .order_by(SessionAttachment.id.asc())
    )
    return [row[0] for row in db.execute(stmt).all()]


def _build_content_text(msg: ChatMessage, attachment_names: list[str]) -> str:
    parts: list[str] = []
    if msg.content:
        parts.append(msg.content)
    for name in attachment_names:
        parts.append(f"[附件: {name}]")
    return "\n".join(parts) if parts else "(空)"


def _build_markdown(session: ChatSession, messages: list[tuple[ChatMessage, list[str]]]) -> str:
    lines: list[str] = []
    lines.append(f"# {session.title or '对话'}")
    lines.append("")
    for msg, attachment_names in messages:
        ts = _format_time(msg.created_at)
        if msg.role == "user":
            lines.append(f"**用户** ({ts}):")
        elif msg.role == "assistant":
            lines.append(f"**助手** ({ts}):")
        else:
            lines.append(f"**{msg.role}** ({ts}):")
        lines.append("")
        lines.append(_build_content_text(msg, attachment_names))
        if msg.role == "assistant":
            lines.append(_sources_markdown(msg))
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _build_json(session: ChatSession, messages: list[tuple[ChatMessage, list[str]]]) -> str:
    data: dict = {
        "title": session.title or "对话",
        "created_at": _format_time(session.created_at),
        "updated_at": _format_time(session.updated_at),
        "message_count": len(messages),
        "messages": [
            {
                "role": msg.role,
                "content": msg.content or "",
                "timestamp": _format_time(msg.created_at),
                "model": msg.model,
                "provider": msg.provider,
                "status": msg.status,
                "token_input": msg.token_input,
                "token_output": msg.token_output,
                "token_total": msg.token_total,
                "sources": _parse_json_field(msg.sources_json, []),
                "context_trace": _parse_json_field(msg.context_json, None),
                "version_group_id": msg.version_group_id,
                "attachments": attachment_names,
            }
            for msg, attachment_names in messages
        ],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _estimate_export_size(db: DBSession, session_id: int, user_id: int) -> tuple[int, int]:
    """返回 (消息数, 内容总字符数)。

    SQLite length() 返回字符数，非 ASCII（如 CJK 中文）UTF-8 编码可达 3 倍字节。
    此上限已做保守校准（见 EXPORT_MAX_TOTAL_CHARS），用作预检快速拒绝。
    """
    base_filter = (
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
        ChatMessage.is_excluded == False,
        ChatMessage.active_version == True,
    )
    count = db.query(func.count(ChatMessage.id)).filter(*base_filter).scalar() or 0
    if count == 0:
        return 0, 0
    total_chars = (
        db.query(
            func.sum(func.length(ChatMessage.content))
            + func.sum(func.length(ChatMessage.sources_json))
            + func.sum(func.length(ChatMessage.context_json))
        )
        .filter(*base_filter)
        .scalar()
        or 0
    )
    return count, total_chars


def _load_messages(db: DBSession, session_id: int, user_id: int) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.user_id == user_id,
            ChatMessage.is_excluded == False,
            ChatMessage.active_version == True,
        )
        .order_by(ChatMessage.id.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _load_all_attachment_names(
    db: DBSession, message_ids: list[int], *, session_id: int, user_id: int
) -> dict[int, list[str]]:
    """批量加载多条消息的附件名，避免 N+1 查询。

    与 message_serialization.message_attachments 保持一致，按 session_id + user_id + message_id 过滤。
    """
    if not message_ids:
        return {}
    stmt = (
        select(SessionAttachment.message_id, SessionAttachment.original_name)
        .where(
            SessionAttachment.message_id.in_(message_ids),
            SessionAttachment.session_id == session_id,
            SessionAttachment.user_id == user_id,
        )
        .order_by(SessionAttachment.id.asc())
    )
    result: dict[int, list[str]] = {mid: [] for mid in message_ids}
    for row in db.execute(stmt).all():
        result.setdefault(row[0], []).append(row[1])
    return result


def _check_per_message_limit(
    db: DBSession, session_id: int, user_id: int
) -> None:
    """检查是否存在超过单条上限的消息，若有则提前拒绝。"""
    base_filter = (
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
        ChatMessage.is_excluded == False,
        ChatMessage.active_version == True,
    )
    oversized = (
        db.query(ChatMessage.id)
        .filter(
            *base_filter,
            func.length(ChatMessage.content) > EXPORT_MAX_PER_MESSAGE_CHARS,
        )
        .first()
    )
    if oversized is not None:
        raise HTTPException(
            status_code=413,
            detail="会话中存在单条消息内容过大，无法导出。",
        )


def export_session(
    db: DBSession,
    session: ChatSession,
    format: ExportFormat,
    user_id: int,
) -> tuple[str, str]:
    """返回 (filename, content)。不写文件系统，纯内存组装。

    安全限制（通过 SQL 聚合预先检查，避免无谓 I/O）：
    - EXPORT_MAX_MESSAGES：超过此数量的会话拒绝导出。
    - EXPORT_MAX_TOTAL_CHARS：内容总字符数超过此上限时拒绝导出。
      （SQLite length() 返回字符数，CJK 等非 ASCII 实际字节数会更大，此上限已做保守校准。）
    - EXPORT_MAX_PER_MESSAGE_CHARS：单条消息超过此字符数时拒绝导出。
    """
    # 安全防护：在加载实际数据前检查大小
    msg_count, total_chars = _estimate_export_size(db, session.id, user_id)

    if msg_count > EXPORT_MAX_MESSAGES:
        raise HTTPException(
            status_code=413,
            detail=f"会话包含 {msg_count} 条消息，超过导出上限 {EXPORT_MAX_MESSAGES} 条。",
        )
    if total_chars > EXPORT_MAX_TOTAL_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"会话内容约 {total_chars // (1024*1024)} MB（字符数），超过导出上限 {EXPORT_MAX_TOTAL_CHARS // (1024*1024)} MB。",
        )
    _check_per_message_limit(db, session.id, user_id)

    raw_messages = _load_messages(db, session.id, user_id)

    # 批量加载附件名，避免 N+1 查询；按 session_id + user_id 过滤保持所有权边界
    message_ids = [msg.id for msg in raw_messages]
    attachment_map = _load_all_attachment_names(db, message_ids, session_id=session.id, user_id=user_id)
    messages = [(msg, attachment_map.get(msg.id, [])) for msg in raw_messages]

    if format == "markdown":
        content = _build_markdown(session, messages)
        filename = f"{session.title or '对话'}.md"
    elif format == "json":
        content = _build_json(session, messages)
        filename = f"{session.title or '对话'}.json"
    else:
        raise ValueError(f"不支持的导出格式: {format}")

    return filename, content
