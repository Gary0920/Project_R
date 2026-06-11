from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run
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


def write_document_generation_agent_run(
    db: Session,
    *,
    user_id: int,
    session: Any,
    message_id: int,
    user_prompt: str,
    generated_file: dict,
    safe_event_detail: Callable[[object], str],
):
    title = f"生成文件：{generated_file.get('filename') or safe_document_title(user_prompt)}"
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="document_generation",
        source_id=str(generated_file.get("id") or ""),
        title=title,
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="plan",
        title="识别文件生成任务",
        detail=safe_event_detail(user_prompt),
        status="completed",
    )
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title="渲染 Word 文档",
        detail=str(generated_file.get("filename") or ""),
        status="completed",
        payload={"tool": "document_generation.render_docx", "file_id": generated_file.get("id")},
    )
    add_agent_event(
        db,
        run,
        event_type="result",
        title="文件已生成",
        detail=str(generated_file.get("filename") or ""),
        status="completed",
        payload={"generated_file": generated_file},
    )
    return finish_agent_run(db, run, status="completed", result={"generated_file": generated_file})
