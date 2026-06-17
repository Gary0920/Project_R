from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.chat import attachment_api as chat_attachment_api
from app.features.chat.schemas import AttachmentResponse, CreateAttachmentRequest
from models import get_db
from models.attachment import SessionAttachment
from models.user import User

router = APIRouter()


def _api():
    import api.chat as chat_api

    return chat_api


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
        max_attachment_bytes=_api().MAX_ATTACHMENT_BYTES,
        attachment_root=_api().SESSION_ATTACHMENTS_ROOT,
        logger=_api().logger,
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
        max_upload_bytes=_api().MAX_ATTACHMENT_UPLOAD_BYTES,
        max_upload_mb=_api().MAX_ATTACHMENT_UPLOAD_MB,
        attachment_root=_api().SESSION_ATTACHMENTS_ROOT,
        logger=_api().logger,
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
        attachment_root=_api().SESSION_ATTACHMENTS_ROOT,
        logger=_api().logger,
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


