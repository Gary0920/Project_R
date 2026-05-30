from datetime import datetime
import os
from pathlib import Path
from typing import Any
import uuid

from sqlalchemy.orm import Session

from core.notification_service import notify_skill_completed, notify_skill_failed
from core.skill_runner import run_to_dict
from core.tag_printing import render_tag_printing_xlsx
from models.generated_file import GeneratedFile
from models.skill_run import SkillRun

BASE_DIR = Path(__file__).resolve().parent.parent
GENERATED_FILES_ROOT = Path(os.getenv("GENERATED_FILES_PATH", str(BASE_DIR / "generated_files")))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def generated_file_payload(db: Session, file_id: str | None) -> dict[str, str] | None:
    if not file_id:
        return None
    file_record = db.get(GeneratedFile, file_id)
    return {
        "id": file_id,
        "filename": file_record.filename if file_record else "",
        "mime_type": file_record.mime_type if file_record else XLSX_MIME,
        "download_url": f"/documents/{file_id}/download",
    }


def execute_ready_run(db: Session, run: SkillRun) -> SkillRun:
    if run.status != "ready" or run.generated_file_id:
        return run
    if run.skill_name != "tag-printing":
        return run

    inputs = run_to_dict(run)["inputs"]
    try:
        file_id = str(uuid.uuid4())
        project_code = _safe_filename_part(inputs.get("project_code"))
        filename = f"tag-printing_{project_code}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
        output_path = GENERATED_FILES_ROOT / str(run.user_id) / f"{file_id}.xlsx"
        render_tag_printing_xlsx(
            project_name=str(inputs.get("project_name") or ""),
            project_code=str(inputs.get("project_code") or ""),
            label_items=inputs.get("label_items"),
            output_path=output_path,
        )
        generated = GeneratedFile(
            id=file_id,
            user_id=run.user_id,
            session_id=run.session_id,
            filename=filename,
            path=str(output_path),
            mime_type=XLSX_MIME,
        )
        db.add(generated)
        run.generated_file_id = file_id
        run.status = "completed"
        notify_skill_completed(db, run_id=run.id, user_id=run.user_id, filename=filename, file_id=file_id)
    except Exception as exc:
        run.status = "failed"
        notify_skill_failed(db, run_id=run.id, user_id=run.user_id, skill_name=run.skill_name, reason=str(exc)[:240])
    db.commit()
    db.refresh(run)
    return run


def _safe_filename_part(value: Any) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or "").strip())
    return text.strip("-")[:80] or "untitled"
