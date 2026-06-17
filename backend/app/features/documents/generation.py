from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.features.documents.formats import normalize_output_format
from app.features.documents.renderer import render_document
from app.features.documents.email_draft import email_draft_payload
from app.features.notifications.service import notify_file_generated
from models.generated_file import GeneratedFile


def safe_document_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip()[:40] or "Project_R 生成文件"
    return re.sub(r"[\\/:*?\"<>|]", "_", title)


def generated_file_payload(
    file_id: str,
    filename: str,
    mime_type: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": file_id,
        "filename": filename,
        "mime_type": mime_type,
        "download_url": f"/documents/{file_id}/download",
    }
    email_payload = email_draft_payload(metadata, title=filename, content="")
    if email_payload:
        payload["email_draft"] = email_payload
    return payload


def create_generated_file(
    db: Session,
    user_id: int,
    session_id: int | None,
    user_prompt: str,
    content: str,
    *,
    output_format: str,
    generated_files_root: Path,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    format_spec = normalize_output_format(output_format)
    file_id = str(uuid.uuid4())
    title = safe_document_title(user_prompt)
    filename = f"{title}{format_spec.extension}"
    output_path = generated_files_root / str(user_id) / f"{file_id}{format_spec.extension}"
    if format_spec.key == "eml":
        email_payload = email_draft_payload(metadata, title=title, content=content)
        metadata = {"email_draft": email_payload} if email_payload else metadata
    render_document(format_spec.key, title, content, output_path, metadata=metadata)
    generated = GeneratedFile(
        id=file_id,
        user_id=user_id,
        session_id=session_id,
        filename=filename,
        path=str(output_path),
        mime_type=format_spec.mime_type,
    )
    db.add(generated)
    notify_file_generated(db, user_id=user_id, file_id=file_id, filename=filename, session_id=session_id)
    db.flush()
    return generated_file_payload(file_id, filename, format_spec.mime_type, metadata=metadata)
