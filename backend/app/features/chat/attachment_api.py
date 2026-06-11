from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.features.chat import attachments as session_attachments
from app.features.chat.access import get_user_session
from app.features.chat.schemas import CreateAttachmentRequest
from models.attachment import SessionAttachment
from models.user import User

_last_session_attachment_cleanup_at: datetime | None = None


def create_session_attachment(
    db: Session,
    session_id: int,
    req: CreateAttachmentRequest,
    user: User,
    *,
    max_attachment_bytes: int,
    attachment_root: Path,
    logger: logging.Logger,
) -> SessionAttachment:
    get_user_session(db, user.id, session_id)
    filename = safe_filename(req.filename)
    content_bytes = req.content.encode("utf-8")
    if len(content_bytes) > max_attachment_bytes:
        raise HTTPException(status_code=400, detail="附件不能超过 256KB")

    return store_session_attachment(
        db,
        user,
        session_id,
        filename,
        req.content_type,
        content_bytes,
        attachment_root=attachment_root,
        logger=logger,
        source_scope=req.source_scope,
        source_label=req.source_label,
        authorization_status=req.authorization_status,
    )


async def upload_session_attachment(
    db: Session,
    session_id: int,
    file: UploadFile,
    user: User,
    *,
    source_scope: str,
    source_label: str,
    authorization_status: str,
    max_upload_bytes: int,
    max_upload_mb: int,
    attachment_root: Path,
    logger: logging.Logger,
) -> SessionAttachment:
    get_user_session(db, user.id, session_id)
    filename = safe_filename(file.filename or "attachment")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="附件内容为空")
    if len(content) > max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"附件不能超过 {max_upload_mb}MB")

    return store_session_attachment(
        db,
        user,
        session_id,
        filename,
        file.content_type or "application/octet-stream",
        content,
        attachment_root=attachment_root,
        logger=logger,
        source_scope=source_scope,
        source_label=source_label,
        authorization_status=authorization_status,
    )


def store_session_attachment(
    db: Session,
    user: User,
    session_id: int,
    filename: str,
    content_type: str,
    content: bytes,
    *,
    attachment_root: Path,
    logger: logging.Logger,
    source_scope: str = "session_upload",
    source_label: str = "会话临时上传",
    authorization_status: str = "uploaded",
) -> SessionAttachment:
    return session_attachments.store_session_attachment(
        db,
        user,
        session_id,
        filename,
        safe_content_type(content_type, filename),
        content,
        attachment_dir=lambda db_arg, user_arg, session_id_arg: attachment_dir(
            db_arg,
            user_arg,
            session_id_arg,
            attachment_root=attachment_root,
            logger=logger,
        ),
        source_scope=source_scope,
        source_label=source_label,
        authorization_status=authorization_status,
    )


def get_user_session_attachment(
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


def list_session_attachments(db: Session, session_id: int, user: User) -> list[SessionAttachment]:
    get_user_session(db, user.id, session_id)
    return session_attachments.list_session_attachments(db, user.id, session_id)


def get_session_attachment_content(
    db: Session,
    session_id: int,
    attachment_id: int,
    user: User,
) -> FileResponse:
    get_user_session(db, user.id, session_id)
    attachment = get_user_session_attachment(db, user.id, session_id, attachment_id)
    path = Path(attachment.stored_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_name,
    )


def delete_session_attachment(db: Session, session_id: int, attachment_id: int, user: User) -> dict:
    get_user_session(db, user.id, session_id)
    session_attachments.delete_session_attachment(db, user.id, session_id, attachment_id)
    return {"ok": True}


def safe_filename(filename: str) -> str:
    return session_attachments.safe_filename(filename)


def safe_content_type(content_type: str | None, filename: str) -> str:
    return session_attachments.safe_content_type(content_type, filename)


def attachment_dir(db: Session, user: User, session_id: int, *, attachment_root: Path, logger: logging.Logger) -> Path:
    return session_attachments.resolve_attachment_dir(
        db,
        user,
        session_id,
        fallback_root=attachment_root,
        logger=logger,
    )


def load_attachment_context(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
    *,
    supports_vision: bool,
    max_chars: int,
    logger: logging.Logger,
) -> str:
    return load_attachment_context_from_attachments(
        load_selected_session_attachments(db, user_id, session_id, attachment_ids),
        supports_vision=supports_vision,
        max_chars=max_chars,
        logger=logger,
    )


def load_selected_session_attachments(
    db: Session,
    user_id: int,
    session_id: int,
    attachment_ids: list[str],
) -> list[SessionAttachment]:
    return session_attachments.load_selected_session_attachments(db, user_id, session_id, attachment_ids)


def load_attachment_context_from_attachments(
    attachments: list[SessionAttachment],
    *,
    supports_vision: bool,
    max_chars: int,
    logger: logging.Logger,
) -> str:
    return session_attachments.load_attachment_context(
        attachments,
        supports_vision=supports_vision,
        max_chars=max_chars,
        logger=logger,
    )


def load_vision_image_inputs(attachments: list[SessionAttachment], *, allowed_mime_types: set[str]) -> list[dict[str, str]]:
    return session_attachments.load_vision_image_inputs(attachments, allowed_mime_types=allowed_mime_types)


def normalize_vision_image_media_type(attachment: SessionAttachment, *, allowed_mime_types: set[str]) -> str:
    return session_attachments.normalize_vision_image_media_type(attachment, allowed_mime_types=allowed_mime_types)


def is_image_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_image_attachment(attachment)


def is_audio_video_attachment(attachment: SessionAttachment) -> bool:
    return session_attachments.is_audio_video_attachment(attachment)


def delete_session_attachments(db: Session, user_id: int, session_id: int) -> None:
    session_attachments.delete_session_attachments(db, user_id, session_id)


def cleanup_inactive_session_attachments_if_due(
    db: Session,
    *,
    cleanup_interval: timedelta,
    retention_days: int,
    logger: logging.Logger,
) -> int:
    global _last_session_attachment_cleanup_at
    now = datetime.now(timezone.utc)
    if (
        _last_session_attachment_cleanup_at is not None
        and now - _last_session_attachment_cleanup_at < cleanup_interval
    ):
        return 0
    _last_session_attachment_cleanup_at = now
    return cleanup_inactive_session_attachments(db, retention_days=retention_days, logger=logger)


def cleanup_inactive_session_attachments(
    db: Session | None = None,
    *,
    retention_days: int,
    logger: logging.Logger,
) -> int:
    return session_attachments.cleanup_inactive_session_attachments(
        db,
        retention_days=retention_days,
        logger=logger,
    )
