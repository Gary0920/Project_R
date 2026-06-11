from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.features.documents.renderer import render_docx
from app.features.notifications.service import notify_file_generated
from models.generated_file import GeneratedFile


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def safe_document_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text).strip()[:40] or "Project_R 生成文档"
    return re.sub(r"[\\/:*?\"<>|]", "_", title)


def create_generated_docx(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
    *,
    generated_files_root: Path,
) -> dict:
    file_id = str(uuid.uuid4())
    title = safe_document_title(user_prompt)
    filename = f"{title}.docx"
    output_path = generated_files_root / str(user_id) / f"{file_id}.docx"
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
