from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import logging
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.knowledge_sources import WORKSPACE_TEXT_EXTENSIONS
from models.attachment import SessionAttachment
from models.session import ChatSession
from models.user import User

ATTACHMENT_TEXT_EXTENSIONS = WORKSPACE_TEXT_EXTENSIONS | {
    ".xml",
    ".ini",
    ".toml",
}
ATTACHMENT_TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
    "application/javascript",
    "application/typescript",
}
VISION_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_ATTACHMENT_CONTEXT_CHARS = 12000
SESSION_ATTACHMENT_RETENTION_DAYS = 3

AttachmentDirResolver = Callable[[Session, User, int], Path]


def safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    name = re.sub(r"[^\w一-鿿.\-()（）\[\]【】 ]", "_", name)
    return name[:120] or "attachment.txt"


def safe_content_type(content_type: str | None, filename: str) -> str:
    normalized = (content_type or "").strip().lower()
    if not normalized or normalized == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(filename)
        normalized = guessed or "application/octet-stream"
    return normalized[:128]


def resolve_attachment_dir(
    db: Session,
    user: User,
    session_id: int,
    *,
    fallback_root: Path,
    default_workspace_resolver: Callable[[Session, User], object | None] | None = None,
    logger: logging.Logger | None = None,
) -> Path:
    if default_workspace_resolver is not None:
        try:
            workspace = default_workspace_resolver(db, user)
            storage_path = getattr(workspace, "storage_path", "")
            if storage_path:
                return Path(storage_path) / "对话文件" / str(session_id)
        except Exception:
            if logger:
                logger.exception("Failed to resolve default workspace attachment directory")
    return fallback_root / str(user.id) / str(session_id)


def store_session_attachment(
    db: Session,
    user: User,
    session_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    *,
    attachment_dir: AttachmentDirResolver,
    source_scope: str = "session_upload",
    source_label: str = "会话临时上传",
    authorization_status: str = "uploaded",
) -> SessionAttachment:
    storage_dir = attachment_dir(db, user, session_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / (
        f"{int(datetime.now(timezone.utc).timestamp() * 1000)}-"
        f"{uuid.uuid4().hex[:8]}-{filename}"
    )
    stored_path.write_bytes(content)

    attachment = SessionAttachment(
        session_id=session_id,
        user_id=user.id,
        original_name=filename,
        stored_path=str(stored_path),
        content_type=safe_content_type(content_type, filename),
        size=len(content),
        source_scope=safe_source_scope(source_scope),
        source_label=safe_source_label(source_label),
        authorization_status=safe_authorization_status(authorization_status),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _optional_text(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return value


def safe_source_scope(value: str | None) -> str:
    normalized = _optional_text(value, "session_upload").strip().lower()
    if normalized in {"local_private", "session_upload", "project", "company"}:
        return normalized
    return "session_upload"


def safe_source_label(value: str | None) -> str:
    label = _optional_text(value, "").strip()
    return label[:80] or "会话临时上传"


def safe_authorization_status(value: str | None) -> str:
    normalized = _optional_text(value, "uploaded").strip().lower()
    if normalized in {"pending", "authorized", "uploaded"}:
        return normalized
    return "uploaded"


def list_session_attachments(db: Session, user_id: int, session_id: int) -> list[SessionAttachment]:
    return (
        db.query(SessionAttachment)
        .filter(SessionAttachment.session_id == session_id, SessionAttachment.user_id == user_id)
        .order_by(SessionAttachment.created_at.desc(), SessionAttachment.id.desc())
        .all()
    )


def delete_session_attachment(db: Session, user_id: int, session_id: int, attachment_id: int) -> None:
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
    path = Path(attachment.stored_path)
    if path.exists():
        path.unlink()
    db.delete(attachment)
    db.commit()


def load_selected_session_attachments(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> list[SessionAttachment]:
    ids: list[int] = []
    for raw_id in attachment_ids:
        try:
            ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []

    return (
        db.query(SessionAttachment)
        .filter(
            SessionAttachment.session_id == session_id,
            SessionAttachment.user_id == user_id,
            SessionAttachment.id.in_(ids),
        )
        .order_by(SessionAttachment.id.asc())
        .all()
    )


def load_attachment_context(
    attachments: list[SessionAttachment],
    *,
    supports_vision: bool,
    max_chars: int = MAX_ATTACHMENT_CONTEXT_CHARS,
    logger: logging.Logger | None = None,
) -> str:
    chunks: list[str] = []
    remaining = max_chars
    for attachment in attachments:
        if remaining <= 0:
            break
        chunk, consumed = attachment_context_chunk(
            attachment,
            remaining,
            supports_vision=supports_vision,
            logger=logger,
        )
        if not chunk:
            continue
        remaining -= consumed
        chunks.append(chunk)
    return "\n\n".join(chunks)


def attachment_context_chunk(
    attachment: SessionAttachment,
    remaining: int,
    *,
    supports_vision: bool,
    logger: logging.Logger | None = None,
) -> tuple[str, int]:
    path = Path(attachment.stored_path)
    if not path.exists():
        return "", 0

    header = attachment_context_header(attachment)
    if is_text_attachment(attachment):
        content = read_attachment_text(path, remaining)
        if content:
            return f"{header}\n{content}", len(content)

    if is_pdf_attachment(attachment):
        content = read_pdf_attachment_text(path, remaining, logger=logger)
        if content:
            return f"{header}\nPDF 文本摘录：\n{content}", len(content)
        message = (
            f"{header}\n该 PDF 暂未提取到可用文本；如果它是扫描件或图片型 PDF，"
            "当前聊天链路只能看到附件元数据，不能直接读取页面图像内容。"
        )
        return message, min(len(message), remaining)

    if is_image_attachment(attachment):
        details = image_attachment_details(path)
        if supports_vision:
            message = (
                f"{header}\n该附件是图片。{details}"
                "当前模型支持图像输入，本轮会直接读取图片内容；"
                "回答时请结合图片本身与用户问题。"
            )
        else:
            message = (
                f"{header}\n该附件是图片。{details}"
                "当前聊天链路已保存图片文件，但当前模型未接入视觉理解或 OCR；"
                "如果用户要求分析图片，请明确说明当前只能看到附件元数据。"
            )
        return message, min(len(message), remaining)

    message = (
        f"{header}\n该附件为二进制文件，已作为会话临时附件保存；"
        "当前聊天链路只能看到文件名、类型和大小，不能直接解析其正文内容。"
    )
    return message, min(len(message), remaining)


def attachment_context_header(attachment: SessionAttachment) -> str:
    return (
        f"[会话附件] {attachment.original_name}"
        f"（{attachment.content_type or 'application/octet-stream'}，{format_bytes(attachment.size)}）"
    )


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / 1024 / 1024:.1f}MB"


def is_text_attachment(attachment: SessionAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    suffix = Path(attachment.original_name).suffix.lower()
    return (
        content_type.startswith("text/")
        or content_type in ATTACHMENT_TEXT_MIME_TYPES
        or suffix in ATTACHMENT_TEXT_EXTENSIONS
    )


def is_pdf_attachment(attachment: SessionAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    return content_type == "application/pdf" or Path(attachment.original_name).suffix.lower() == ".pdf"


def is_image_attachment(attachment: SessionAttachment) -> bool:
    return (attachment.content_type or "").lower().startswith("image/")


def is_audio_video_attachment(attachment: SessionAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    return content_type.startswith("audio/") or content_type.startswith("video/")


def load_vision_image_inputs(
    attachments: list[SessionAttachment],
    *,
    allowed_mime_types: set[str] = VISION_IMAGE_MIME_TYPES,
) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for attachment in attachments:
        path = Path(attachment.stored_path)
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"图片附件不存在：{attachment.original_name}")
        media_type = normalize_vision_image_media_type(attachment, allowed_mime_types=allowed_mime_types)
        try:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"图片附件读取失败：{attachment.original_name}") from exc
        images.append({"media_type": media_type, "data": data})
    return images


def normalize_vision_image_media_type(
    attachment: SessionAttachment,
    *,
    allowed_mime_types: set[str] = VISION_IMAGE_MIME_TYPES,
) -> str:
    media_type = (attachment.content_type or "").split(";", 1)[0].strip().lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type in allowed_mime_types:
        return media_type
    raise HTTPException(
        status_code=400,
        detail=f"暂不支持该图片格式：{attachment.original_name}（{attachment.content_type}）",
    )


def read_attachment_text(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()[:limit]
    except OSError:
        return ""


def read_pdf_attachment_text(path: Path, limit: int, *, logger: logging.Logger | None = None) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        if logger:
            logger.warning("pypdf is not available; PDF attachment text extraction skipped")
        return ""

    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        used = 0
        for page in reader.pages[:20]:
            if used >= limit:
                break
            text = (page.extract_text() or "").strip()
            if not text:
                continue
            excerpt = text[: limit - used]
            parts.append(excerpt)
            used += len(excerpt)
        return "\n\n".join(parts).strip()
    except Exception as exc:
        if logger:
            logger.warning("Failed to extract PDF attachment text from %s: %s", path, exc)
        return ""


def image_attachment_details(path: Path) -> str:
    try:
        from PIL import Image
    except Exception:
        return ""

    try:
        with Image.open(path) as image:
            width, height = image.size
            return f"图片尺寸：{width}x{height}px。"
    except Exception:
        return ""


def delete_session_attachments(db: Session, user_id: int, session_id: int) -> None:
    attachments = (
        db.query(SessionAttachment)
        .filter(SessionAttachment.session_id == session_id, SessionAttachment.user_id == user_id)
        .all()
    )
    for attachment in attachments:
        path = Path(attachment.stored_path)
        if path.exists():
            path.unlink()
        db.delete(attachment)


def cleanup_inactive_session_attachments(
    db: Session | None = None,
    *,
    retention_days: int = SESSION_ATTACHMENT_RETENTION_DAYS,
    logger: logging.Logger | None = None,
) -> int:
    owns_session = db is None
    if db is None:
        from models import SessionLocal

        db = SessionLocal()

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    try:
        attachments = (
            db.query(SessionAttachment)
            .join(ChatSession, ChatSession.id == SessionAttachment.session_id)
            .filter(ChatSession.updated_at < cutoff)
            .all()
        )
        for attachment in attachments:
            path = Path(attachment.stored_path)
            if path.exists():
                try:
                    path.unlink()
                except OSError as exc:
                    if logger:
                        logger.warning("Failed to delete inactive session attachment %s: %s", path, exc)
            db.delete(attachment)
        db.commit()
        return len(attachments)
    except Exception:
        db.rollback()
        if logger:
            logger.exception("Failed to clean inactive session attachments")
        return 0
    finally:
        if owns_session:
            db.close()
