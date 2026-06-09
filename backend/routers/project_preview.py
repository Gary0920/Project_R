from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import FileResponse, JSONResponse, Response

from api.deps import get_current_user, get_db
from core.project_citation import guess_file_kind_from_source
from models.user import User

router = APIRouter(prefix="/api/projects/{workspace_id}/preview", tags=["project-preview"])


BACKEND_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DATA = BACKEND_DIR / "workspace_data"


MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".eml": "message/rfc822",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
}

PREVIEW_TYPES: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
    ".docx": "text",
    ".xlsx": "sheet_table",
    ".xls": "sheet_table",
    ".eml": "email",
    ".mp4": "media",
    ".mp3": "media",
    ".wav": "media",
    ".m4a": "media",
    ".md": "markdown",
    ".txt": "text",
    ".csv": "sheet_table",
}


def _resolve_preview_path(workspace_id: int, encoded_path: str) -> Path | None:
    """Resolve an encoded relative path to an actual file on disk.

    Only allows files under the workspace's storage_path.
    """
    try:
        rel_path = urllib.parse.unquote(encoded_path)
    except Exception:
        return None

    # Prevent path traversal
    if ".." in rel_path.split("/") or ".." in rel_path.split("\\"):
        return None

    # Resolve workspace directory
    # Note: workspace_data/project/{brand}/{slug}/...
    project_dir = WORKSPACE_DATA / "project"
    if not project_dir.exists():
        return None

    for workspace_dir in project_dir.iterdir():
        if not workspace_dir.is_dir():
            continue
        for slug_dir in workspace_dir.iterdir():
            if not slug_dir.is_dir():
                continue
            candidate = (slug_dir / rel_path).resolve()
            try:
                if candidate.is_relative_to(slug_dir.resolve()) and candidate.exists() and candidate.is_file():
                    return candidate
            except (OSError, ValueError):
                continue
    return None


@router.get("/{encoded_path:path}")
def preview_file(
    workspace_id: int,
    encoded_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview a source file from the project workspace.

    Returns file metadata and a raw-file serving URL.
    """
    file_path = _resolve_preview_path(workspace_id, encoded_path)
    if file_path is None or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = file_path.suffix.lower()
    mime_type = MIME_MAP.get(suffix, "application/octet-stream")
    preview_type = PREVIEW_TYPES.get(suffix, "unknown")
    file_kind = guess_file_kind_from_source(file_path.name)
    file_size = file_path.stat().st_size

    if preview_type == "pdf":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "pdf",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
            },
        })
    elif preview_type == "image":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "image",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
                "width": None,
                "height": None,
            },
        })
    elif preview_type == "text":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "text",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
            },
        })
    elif preview_type == "email":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "email",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
            },
        })
    elif preview_type == "sheet_table":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "sheet_table",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
            },
        })
    elif preview_type == "media":
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "media",
                "url": f"/api/projects/{workspace_id}/raw/{encoded_path}",
            },
        })
    elif preview_type == "markdown":
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            content = ""
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {
                "type": "markdown",
                "content": content,
            },
        })
    else:
        return JSONResponse({
            "file": str(file_path.relative_to(WORKSPACE_DATA.parent)),
            "file_kind": file_kind,
            "size": file_size,
            "mime_type": mime_type,
            "preview": {"type": "unknown"},
        })
