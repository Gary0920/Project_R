from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user, pwd_context
from core.gbrain import GBrainAdapter
from core.knowledge_sources import approve_knowledge_review_to_gbrain
from core.skill_runner import SkillRunner
from models import get_db
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.notification import Notification
from models.user import User
from models.workspace import WorkspaceFile

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserResponse(BaseModel):
    id: int
    username: str
    role: str
    nickname: str
    avatar: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CreateAdminUserRequest(BaseModel):
    username: str
    password: str
    role: str = "employee"
    nickname: str = ""


class UpdateAdminUserRequest(BaseModel):
    role: str | None = None
    nickname: str | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    password: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    action: str
    detail: str
    token_cost: int | None
    success: bool
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeReviewResponse(BaseModel):
    id: int
    submitter_id: int
    content: str
    source: str
    status: str
    reviewer_id: int | None
    created_at: datetime
    reviewed_at: datetime | None

    class Config:
        from_attributes = True


class ReviewKnowledgeRequest(BaseModel):
    status: str
    content: str | None = None


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


def _write_admin_audit(db: Session, user_id: int, action: str, detail: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=True))


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    return db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()


@router.post("/users", response_model=AdminUserResponse)
def create_user(
    req: CreateAdminUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if req.role not in {"admin", "employee"}:
        raise HTTPException(status_code=400, detail="角色不合法")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    created = User(
        username=username,
        password_hash=pwd_context.hash(req.password),
        role=req.role,
        nickname=req.nickname.strip() or username,
    )
    db.add(created)
    _write_admin_audit(db, user.id, "admin_user_create", username)
    db.commit()
    db.refresh(created)
    from api.workspaces import ensure_default_workspace

    ensure_default_workspace(db, created)
    return created


@router.put("/users/{target_user_id}", response_model=AdminUserResponse)
def update_user(
    target_user_id: int,
    req: UpdateAdminUserRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    target = db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == user.id and req.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前管理员账号")
    if req.role is not None:
        if req.role not in {"admin", "employee"}:
            raise HTTPException(status_code=400, detail="角色不合法")
        target.role = req.role
    if req.nickname is not None:
        target.nickname = req.nickname.strip() or target.username
    if req.is_active is not None:
        target.is_active = req.is_active
    _write_admin_audit(db, user.id, "admin_user_update", f"{target.username}:{target.role}:{target.is_active}")
    db.commit()
    db.refresh(target)
    return target


@router.post("/users/{target_user_id}/reset-password", response_model=AdminUserResponse)
def reset_user_password(
    target_user_id: int,
    req: ResetPasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    target = db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    target.password_hash = pwd_context.hash(req.password)
    _write_admin_audit(db, user.id, "admin_user_reset_password", target.username)
    db.commit()
    db.refresh(target)
    return target


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def list_audit_logs(
    user_id: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    query = db.query(AuditLog)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= _parse_date_filter(date_from, "date_from"))
    if date_to:
        query = query.filter(AuditLog.created_at <= _parse_date_filter(date_to, "date_to"))
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()


@router.get("/knowledge-reviews", response_model=list[KnowledgeReviewResponse])
def list_knowledge_reviews(
    status: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    query = db.query(KnowledgeReview)
    if status:
        query = query.filter(KnowledgeReview.status == status)
    return query.order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc()).limit(100).all()


@router.post("/knowledge-reviews/{review_id}", response_model=KnowledgeReviewResponse)
def review_knowledge(
    review_id: int,
    req: ReviewKnowledgeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    if req.status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="审核状态不合法")
    review = db.get(KnowledgeReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="候选知识不存在")
    if req.content is not None:
        review.content = req.content.strip()
    if req.status == "approved" and not review.content.strip():
        raise HTTPException(status_code=400, detail="候选知识内容不能为空")
    review.status = req.status
    review.reviewer_id = user.id
    review.reviewed_at = datetime.now(timezone.utc)
    if req.status == "approved":
        _append_approved_knowledge(review, db)
    db.query(Notification).filter(
        Notification.event_key == f"knowledge_review:{review.id}:pending",
        Notification.action_status == "pending",
    ).update({"action_status": "done", "is_read": True}, synchronize_session=False)
    _write_admin_audit(db, user.id, "admin_knowledge_review", f"{review.id}:{req.status}")
    db.commit()
    db.refresh(review)
    return review


@router.get("/templates")
def list_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    skills = SkillRunner.get().list_skills()
    return {
        "items": [
            {
                "skill_name": skill.name,
                "display_name": skill.display_name,
                "outputs": skill.outputs,
                "references": skill.references,
            }
            for skill in skills
        ]
    }


def _append_approved_knowledge(review: KnowledgeReview, db: Session) -> None:
    approval = approve_knowledge_review_to_gbrain(review, db=db)
    if approval.get("scope") == "project" and approval.get("workspace_id"):
        from models.workspace import Workspace

        workspace = db.get(Workspace, int(approval["workspace_id"]))
        sync_result = GBrainAdapter().sync_project_source(workspace, no_pull=True) if workspace else {"status": "not_found"}
        if sync_result.get("status") == "ok" and approval.get("source_file"):
            meta = (
                db.query(WorkspaceFile)
                .filter(
                    WorkspaceFile.workspace_id == int(approval["workspace_id"]),
                    WorkspaceFile.relative_path == str(approval["source_file"]),
                    WorkspaceFile.deleted_at.is_(None),
                )
                .first()
            )
            if meta:
                meta.rag_status = "indexed"
                meta.updated_at = datetime.now(timezone.utc)
        return
    sync_result = GBrainAdapter().sync_source(no_pull=True)
    if sync_result.get("status") not in {"ok", "disabled"}:
        # The approved Markdown is already in derived/. Admin status/refresh can retry sync.
        return


def _parse_date_filter(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} 日期格式不合法") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
