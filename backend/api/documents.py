from pathlib import Path
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.features.documents.export_content_service import (
    ExportContentError,
    cleanup_export_temp_file,
    export_content_to_temp_file,
)
from app.features.documents.formats import SUPPORTED_OUTPUT_FORMATS
from app.features.documents.schemas import ExportDocumentRequest
from models import get_db
from models.generated_file import GeneratedFile
from models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])
GENERATED_FILES_TTL_HOURS = int(os.getenv("GENERATED_FILES_TTL_HOURS", "48"))


@router.post("/export")
def export_document_content(
    body: ExportDocumentRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    del user
    try:
        output_path, filename = export_content_to_temp_file(
            content=body.content,
            title=body.title,
            output_format=body.format,
        )
    except ExportContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    format_spec = SUPPORTED_OUTPUT_FORMATS[body.format]
    background_tasks.add_task(cleanup_export_temp_file, output_path)
    return FileResponse(
        output_path,
        media_type=format_spec.mime_type,
        filename=filename,
    )


@router.get("/{file_id}/download")
def download_generated_file(
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    generated = (
        db.query(GeneratedFile)
        .filter(GeneratedFile.id == file_id, GeneratedFile.user_id == user.id)
        .first()
    )
    if not generated:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = Path(generated.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已过期或被清理")
    return FileResponse(
        path,
        media_type=generated.mime_type,
        filename=generated.filename,
    )


@router.post("/cleanup")
def cleanup_generated_files(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=GENERATED_FILES_TTL_HOURS)
    files = db.query(GeneratedFile).all()
    removed = 0
    for generated in files:
        created_at = generated.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        path = Path(generated.path)
        expired = created_at < cutoff
        missing = not path.exists()
        if expired or missing:
            if path.exists():
                path.unlink()
            db.delete(generated)
            removed += 1
    db.commit()
    return {"ok": True, "removed": removed}
