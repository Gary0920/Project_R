from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.utils import serialize_datetime_utc
from models import get_db
from models.distillation import DistillationSuggestion
from models.notification import Notification
from models.user import User
from models.workspace import WorkspaceMember

router = APIRouter(prefix="/distillation", tags=["distillation"])


class SuggestionResponse(BaseModel):
    id: int
    workspace_id: int
    session_id: int | None
    title: str
    content: str
    status: str
    reviewer_id: int | None
    created_at: str  # ISO string
    reviewed_at: str | None

    class Config:
        from_attributes = True


class ReviewRequest(BaseModel):
    status: str  # "approved" or "rejected"
    review_comment: str = ""


@router.get("/suggestions", response_model=list[SuggestionResponse])
def list_pending_suggestions(
    workspace_id: int = Query(default=...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_admin(db, user.id, workspace_id)
    suggestions = (
        db.query(DistillationSuggestion)
        .filter(
            DistillationSuggestion.workspace_id == workspace_id,
            DistillationSuggestion.status == "pending",
        )
        .order_by(DistillationSuggestion.created_at.desc())
        .all()
    )
    return [
        SuggestionResponse(
            id=s.id,
            workspace_id=s.workspace_id,
            session_id=s.session_id,
            title=s.title,
            content=s.content,
            status=s.status,
            reviewer_id=s.reviewer_id,
            created_at=serialize_datetime_utc(s.created_at),
            reviewed_at=serialize_datetime_utc(s.reviewed_at) if s.reviewed_at else None,
        )
        for s in suggestions
    ]


@router.post("/suggestions/{suggestion_id}/review")
def review_suggestion(
    suggestion_id: int,
    req: ReviewRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suggestion = (
        db.query(DistillationSuggestion)
        .filter(DistillationSuggestion.id == suggestion_id)
        .first()
    )
    if not suggestion:
        raise HTTPException(status_code=404, detail="建议不存在")

    _ensure_admin(db, user.id, suggestion.workspace_id)

    if req.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status 必须是 approved 或 rejected")

    suggestion.status = req.status
    suggestion.reviewer_id = user.id
    suggestion.review_comment = req.review_comment
    suggestion.reviewed_at = datetime.now(timezone.utc)

    if req.status == "approved":
        _write_knowledge_file(suggestion)

    db.commit()
    return {"ok": True}


def _write_knowledge_file(suggestion):
    """Write approved distillation to the workspace knowledge base."""
    from pathlib import Path
    import json

    from models.workspace import Workspace
    from models import SessionLocal

    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.id == suggestion.workspace_id).first()
        if not workspace or not workspace.storage_path:
            return

        kb_dir = Path(workspace.storage_path) / "knowledge_base"
        kb_dir.mkdir(parents=True, exist_ok=True)

        safe_title = suggestion.title.strip().replace("/", "-").replace("\\", "-") or "distilled"
        file_path = kb_dir / f"{safe_title}.md"

        header = f"# {suggestion.title}\n\n"
        header += f"> 来源: 会话 #{suggestion.session_id} | 审批人: {suggestion.reviewer_id}\n"
        header += f"> 生成时间: {serialize_datetime_utc(suggestion.created_at)}\n\n"
        header += suggestion.content

        file_path.write_text(header, encoding="utf-8")
    finally:
        db.close()


def _ensure_admin(db: Session, user_id: int, workspace_id: int):
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.role == "admin",
        )
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="仅项目管理员可操作")
