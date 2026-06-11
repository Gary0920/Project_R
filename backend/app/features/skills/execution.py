import os
from pathlib import Path

from sqlalchemy.orm import Session

from core.notification_service import notify_skill_completed, notify_skill_failed
from app.features.skills.dispatcher import SkillDispatchError, SkillDispatcher
from models.generated_file import GeneratedFile
from models.skill_run import SkillRun

BASE_DIR = Path(__file__).resolve().parents[3]
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

    dispatcher = SkillDispatcher()
    try:
        before_status = run.status
        run = dispatcher.execute(db, run, generated_root=GENERATED_FILES_ROOT)
        if run.status == before_status:
            return run
        db.flush()
        generated = db.get(GeneratedFile, run.generated_file_id) if run.generated_file_id else None
        if run.status == "completed" and generated:
            notify_skill_completed(
                db,
                run_id=run.id,
                user_id=run.user_id,
                filename=generated.filename,
                file_id=generated.id,
            )
    except SkillDispatchError as exc:
        run.status = "failed"
        notify_skill_failed(db, run_id=run.id, user_id=run.user_id, skill_name=run.skill_name, reason=str(exc)[:240])
    except Exception as exc:
        run.status = "failed"
        notify_skill_failed(db, run_id=run.id, user_id=run.user_id, skill_name=run.skill_name, reason=str(exc)[:240])
    db.commit()
    db.refresh(run)
    return run
