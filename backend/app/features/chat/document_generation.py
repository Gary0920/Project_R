from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run
from app.features.documents.generation import create_generated_file, safe_document_title
from app.features.documents.formats import normalize_output_format


def create_generated_output_file(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
    *,
    output_format: str = "docx",
    generated_files_root: Path,
) -> dict:
    return create_generated_file(
        db,
        user_id,
        session_id,
        user_prompt,
        content,
        output_format=output_format,
        generated_files_root=generated_files_root,
    )


def create_generated_docx(
    db: Session,
    user_id: int,
    session_id: int,
    user_prompt: str,
    content: str,
    *,
    generated_files_root: Path,
) -> dict:
    return create_generated_output_file(
        db,
        user_id,
        session_id,
        user_prompt,
        content,
        output_format="docx",
        generated_files_root=generated_files_root,
    )


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
    mime_type = str(generated_file.get("mime_type") or "")
    output_format = "docx"
    if "markdown" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".md"):
        output_format = "markdown"
    elif "text/plain" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".txt"):
        output_format = "txt"
    elif "spreadsheet" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".xlsx"):
        output_format = "xlsx"
    elif "presentation" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".pptx"):
        output_format = "pptx"
    elif "application/pdf" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".pdf"):
        output_format = "pdf"
    elif "message/rfc822" in mime_type or str(generated_file.get("filename") or "").lower().endswith(".eml"):
        output_format = "eml"
    format_name = normalize_output_format(output_format).display_name
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
        title=f"渲染{format_name}",
        detail=str(generated_file.get("filename") or ""),
        status="completed",
        payload={"tool": f"document_generation.render_{output_format}", "file_id": generated_file.get("id")},
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
