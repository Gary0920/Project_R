from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.notifications.service import notify_user
from models.workspace import Workspace, WorkspaceFile


def extract_text_from_docx(file_bytes: bytes, filename: str = "") -> str:
    import io

    try:
        from docx import Document

        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        text = cell.text.strip()
                        if text:
                            paragraphs.append(text)
        return "\n\n".join(paragraphs)
    except ImportError:
        raise HTTPException(status_code=500, detail="DOCX 解析组件未安装")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"DOCX 文件解析失败：{exc}")


def workspace_file_uploader(db: Session, workspace_id: int, rel_path: str) -> int | None:
    meta = (
        db.query(WorkspaceFile)
        .filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == rel_path,
            WorkspaceFile.deleted_at.is_(None),
        )
        .first()
    )
    return meta.uploaded_by if meta else None


def notify_meeting_run_finished(
    db: Session,
    *,
    workspace: Workspace,
    actor_user_id: int,
    folder_path: str,
    title: str,
    status: str,
    detail: str,
) -> None:
    severity = "success" if status == "completed" else "warning" if status == "partial" else "critical"
    notify_user(
        db,
        actor_user_id,
        category="workspace",
        severity=severity,
        title=title,
        content=f"{workspace.name}：{detail}",
        action_status="none" if status == "completed" else "pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id, "path": folder_path},
        event_key=f"workspace:{workspace.id}:meeting:{folder_path}:{title}:{datetime.now(timezone.utc).timestamp()}",
    )


def filename_match_tokens(filename: str) -> set[str]:
    stem = Path(filename or "").stem.lower()
    raw_tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", stem)
    ignored = {"audio", "video", "meeting", "summary", "transcript", "纪要", "总结", "转录", "会议"}
    return {token for token in raw_tokens if len(token) >= 2 and token not in ignored}


def read_auxiliary_summaries(folder_dir: Path, source_filename: str = "", max_chars: int = 20000) -> str:
    summary_dir = folder_dir / "03-辅助总结"
    if not summary_dir.exists() or not summary_dir.is_dir():
        return ""

    source_tokens = filename_match_tokens(source_filename)
    candidates = [
        child for child in sorted(summary_dir.iterdir(), key=lambda item: item.name.lower())
        if child.is_file() and not child.name.startswith("~$") and child.suffix.lower() in {".md", ".txt", ".docx"}
    ]
    if source_tokens:
        matched = [
            child for child in candidates
            if source_tokens.intersection(filename_match_tokens(child.name))
        ]
        candidates = matched

    sections: list[str] = []
    total = 0
    for child in candidates:
        suffix = child.suffix.lower()
        try:
            if suffix == ".docx":
                text = extract_text_from_docx(child.read_bytes(), child.name)
            else:
                text = child.read_text(encoding="utf-8")
        except Exception as exc:
            sections.append(f"### {child.name}\n\n> 辅助总结读取失败：{exc}")
            continue
        text = text.strip()
        if not text:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        clipped = text[:remaining]
        total += len(clipped)
        suffix_note = "\n\n> 已截断，仅保留前部内容。" if len(text) > len(clipped) else ""
        sections.append(f"### {child.name}\n\n{clipped}{suffix_note}")
    return "\n\n".join(sections)
