from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.shared.time.schemas import UTCDateTimeModel
from api.auth import get_current_user, pwd_context
from core.gbrain_citation_fixer_jobs import (
    TERMINAL_JOB_STATUSES,
    load_citation_fixer_job_state,
    record_citation_fixer_job,
)
from app.features.auth.system_accounts import SYSTEM_ADMIN_USERNAME, ensure_system_admin, is_system_admin_user
from core.gbrain import GBrainAdapter
from core.knowledge_sources import approve_knowledge_review_to_gbrain
from app.features.notifications.service import notify_gbrain_maintenance_event
from app.features.skills.runner import SkillRunner
from models import get_db
from models.agent_run import AgentEvent, AgentRun
from models.attachment import SessionAttachment
from models.audit_log import AuditLog
from models.distillation import DistillationSuggestion
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.message import ChatMessage
from models.notification import Notification
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember
from models.workspace_ingest_job import WorkspaceIngestJob
from app.features.knowledge.quality.report import list_reports, load_report, report_summary_to_text

router = APIRouter(prefix="/admin", tags=["admin"])
WORKSPACES_ROOT = Path(__file__).resolve().parent.parent / "workspace_data"
ANSWER_CORRECTION_REVIEW_PREFIX = "gbrain_answer_correction:"
GBRAIN_THINK_REVIEW_PREFIX = "gbrain_think_review:"
RESERVED_FIXTURE_USERNAMES = {"workspace", "member", "other", "system-admin"}


class AdminUserResponse(UTCDateTimeModel):
    id: int
    username: str
    role: str
    nickname: str
    avatar: str
    work_group: str = ""
    is_active: bool
    is_system_account: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class AdminUserCandidateResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    work_group: str = ""
    role: str
    is_active: bool
    is_system_account: bool = False


class AdminGroupCandidateResponse(BaseModel):
    group_name: str
    user_count: int = 0


class CreateAdminUserRequest(BaseModel):
    username: str
    password: str
    role: str = "employee"
    nickname: str = ""
    work_group: str = ""


class UpdateAdminUserRequest(BaseModel):
    role: str | None = None
    nickname: str | None = None
    work_group: str | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    password: str


class DeleteAdminUserResponse(BaseModel):
    ok: bool
    deleted_user_id: int
    deleted_username: str


class AuditLogResponse(UTCDateTimeModel):
    id: int
    user_id: int
    action: str
    detail: str
    token_cost: int | None
    success: bool
    created_at: datetime

    class Config:
        from_attributes = True


class KnowledgeReviewResponse(UTCDateTimeModel):
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


class ReviewCitationFixerRequest(BaseModel):
    page_slug: str | None = None
    notes: str | None = None
    allowed_slug_prefixes: list[str] | None = None
    max_turns: int = 30


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


def _write_admin_audit(db: Session, user_id: int, action: str, detail: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=True))


def _unlink_if_file(raw_path: str) -> None:
    if not raw_path:
        return
    try:
        path = Path(raw_path)
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        return


def _remove_user_workspace_storage(workspace: Workspace) -> None:
    if workspace.workspace_kind != "user" or not workspace.storage_path:
        return
    try:
        root = (WORKSPACES_ROOT / "user").resolve()
        path = Path(workspace.storage_path).resolve()
        if path.exists() and path.is_dir() and path.is_relative_to(root):
            shutil.rmtree(path)
    except OSError:
        return


def _cleanup_user_before_delete(db: Session, *, target: User, replacement_user_id: int) -> dict[str, int]:
    target_id = target.id
    counts: dict[str, int] = {}

    session_ids = [
        item.id
        for item in db.query(ChatSession.id).filter(ChatSession.user_id == target_id).all()
    ]
    agent_run_ids = [
        item.id
        for item in db.query(AgentRun.id).filter(AgentRun.user_id == target_id).all()
    ]
    if agent_run_ids:
        counts["agent_events"] = db.query(AgentEvent).filter(AgentEvent.run_id.in_(agent_run_ids)).delete(synchronize_session=False)
    counts["agent_runs"] = db.query(AgentRun).filter(AgentRun.user_id == target_id).delete(synchronize_session=False)

    attachments = db.query(SessionAttachment).filter(SessionAttachment.user_id == target_id).all()
    for attachment in attachments:
        _unlink_if_file(attachment.stored_path)
        db.delete(attachment)
    counts["session_attachments"] = len(attachments)

    counts["skill_runs"] = db.query(SkillRun).filter(SkillRun.user_id == target_id).delete(synchronize_session=False)

    generated_files = db.query(GeneratedFile).filter(GeneratedFile.user_id == target_id).all()
    for generated in generated_files:
        _unlink_if_file(generated.path)
        db.delete(generated)
    counts["generated_files"] = len(generated_files)

    if session_ids:
        counts["distillation_session_links"] = (
            db.query(DistillationSuggestion)
            .filter(DistillationSuggestion.session_id.in_(session_ids))
            .update({"session_id": None}, synchronize_session=False)
        )
        counts["chat_messages"] = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id.in_(session_ids))
            .delete(synchronize_session=False)
        )
    else:
        counts["distillation_session_links"] = 0
        counts["chat_messages"] = 0
    counts["chat_messages"] += db.query(ChatMessage).filter(ChatMessage.user_id == target_id).delete(synchronize_session=False)
    counts["chat_sessions"] = db.query(ChatSession).filter(ChatSession.user_id == target_id).delete(synchronize_session=False)

    counts["notifications"] = db.query(Notification).filter(Notification.user_id == target_id).delete(synchronize_session=False)
    counts["audit_logs"] = db.query(AuditLog).filter(AuditLog.user_id == target_id).delete(synchronize_session=False)
    counts["distillation_suggested"] = (
        db.query(DistillationSuggestion)
        .filter(DistillationSuggestion.suggested_by == target_id)
        .update({"suggested_by": None}, synchronize_session=False)
    )
    counts["distillation_reviewed"] = (
        db.query(DistillationSuggestion)
        .filter(DistillationSuggestion.reviewer_id == target_id)
        .update({"reviewer_id": None}, synchronize_session=False)
    )
    counts["knowledge_submitter_reassigned"] = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.submitter_id == target_id)
        .update({"submitter_id": replacement_user_id}, synchronize_session=False)
    )
    counts["knowledge_reviewer_cleared"] = (
        db.query(KnowledgeReview)
        .filter(KnowledgeReview.reviewer_id == target_id)
        .update({"reviewer_id": None}, synchronize_session=False)
    )
    counts["workspace_ingest_jobs_reassigned"] = (
        db.query(WorkspaceIngestJob)
        .filter(WorkspaceIngestJob.requested_by == target_id)
        .update({"requested_by": replacement_user_id}, synchronize_session=False)
    )

    default_workspaces = (
        db.query(Workspace)
        .filter(Workspace.created_by == target_id, Workspace.workspace_kind == "user", Workspace.is_default == True)
        .all()
    )
    for workspace in default_workspaces:
        _remove_user_workspace_storage(workspace)
        db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == workspace.id).delete(synchronize_session=False)
        db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace.id).delete(synchronize_session=False)
        db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.workspace_id == workspace.id).delete(synchronize_session=False)
        db.delete(workspace)
    counts["default_workspaces"] = len(default_workspaces)
    if default_workspaces:
        db.flush()

    counts["workspace_files_uploaded_reassigned"] = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.uploaded_by == target_id)
        .update({"uploaded_by": replacement_user_id}, synchronize_session=False)
    )
    counts["workspace_files_deleted_reassigned"] = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.deleted_by == target_id)
        .update({"deleted_by": replacement_user_id}, synchronize_session=False)
    )
    counts["workspaces_created_reassigned"] = (
        db.query(Workspace)
        .filter(Workspace.created_by == target_id)
        .update({"created_by": replacement_user_id}, synchronize_session=False)
    )

    memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == target_id).all()
    for membership in memberships:
        workspace_id = membership.workspace_id
        db.delete(membership)
        db.flush()
        remaining = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
        if not remaining:
            db.add(WorkspaceMember(workspace_id=workspace_id, user_id=replacement_user_id, role="admin"))
        elif not any(item.role == "admin" for item in remaining):
            remaining[0].role = "admin"
    counts["workspace_memberships"] = len(memberships)

    return counts


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    ensure_system_admin(db)
    return db.query(User).order_by(User.created_at.desc(), User.id.desc()).all()


@router.get("/user-candidates", response_model=list[AdminUserCandidateResponse])
def list_user_candidates(
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    ensure_system_admin(db)
    keyword = q.strip()
    query = db.query(User)
    if keyword:
        pattern = f"%{keyword}%"
        query = query.filter(
            (User.username.ilike(pattern))
            | (User.nickname.ilike(pattern))
            | (User.work_group.ilike(pattern))
        )
    users = query.order_by(User.username.asc(), User.id.asc()).limit(limit).all()
    return [
        AdminUserCandidateResponse(
            user_id=item.id,
            username=item.username,
            nickname=item.nickname or item.username,
            work_group=item.work_group or "",
            role=item.role,
            is_active=item.is_active,
            is_system_account=is_system_admin_user(item),
        )
        for item in users
    ]


@router.get("/group-candidates", response_model=list[AdminGroupCandidateResponse])
def list_group_candidates(
    q: str = Query(default=""),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    keyword = q.strip().lower()
    groups: dict[str, int] = {}
    for item in db.query(User.work_group).filter(User.work_group != "").all():
        group_name = (item[0] or "").strip()
        if not group_name:
            continue
        if keyword and keyword not in group_name.lower():
            continue
        groups[group_name] = groups.get(group_name, 0) + 1
    return [
        AdminGroupCandidateResponse(group_name=name, user_count=count)
        for name, count in sorted(groups.items(), key=lambda pair: (-pair[1], pair[0].lower()))[:limit]
    ]


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
    if username.lower() in RESERVED_FIXTURE_USERNAMES:
        raise HTTPException(status_code=400, detail="该用户名保留给自动化测试夹具，不能在真实用户管理中创建")
    if username.lower() == SYSTEM_ADMIN_USERNAME:
        raise HTTPException(status_code=400, detail="系统内置管理员账号已固定，不可创建或覆盖")
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
        work_group=req.work_group.strip(),
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
    if is_system_admin_user(target):
        ensure_system_admin(db)
        raise HTTPException(status_code=400, detail="系统内置管理员账号不可修改")
    if target.id == user.id and req.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前管理员账号")
    if req.role is not None:
        if req.role not in {"admin", "employee"}:
            raise HTTPException(status_code=400, detail="角色不合法")
        target.role = req.role
    if req.nickname is not None:
        target.nickname = req.nickname.strip() or target.username
    if req.work_group is not None:
        target.work_group = req.work_group.strip()
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
    if is_system_admin_user(target):
        ensure_system_admin(db)
        raise HTTPException(status_code=400, detail="系统内置管理员账号密码固定，不可重置")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    target.password_hash = pwd_context.hash(req.password)
    _write_admin_audit(db, user.id, "admin_user_reset_password", target.username)
    db.commit()
    db.refresh(target)
    return target


@router.delete("/users/{target_user_id}", response_model=DeleteAdminUserResponse)
def delete_user(
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    target = db.get(User, target_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if is_system_admin_user(target):
        ensure_system_admin(db)
        raise HTTPException(status_code=400, detail="系统内置管理员账号不可删除")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    if target.role == "admin":
        admin_count = db.query(User).filter(User.role == "admin").count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="不能删除最后一个管理员账号")

    deleted_username = target.username
    cleanup = _cleanup_user_before_delete(db, target=target, replacement_user_id=user.id)
    db.delete(target)
    _write_admin_audit(db, user.id, "admin_user_delete", f"{deleted_username}:{cleanup}")
    db.commit()
    return DeleteAdminUserResponse(ok=True, deleted_user_id=target_user_id, deleted_username=deleted_username)


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


@router.post("/knowledge-reviews/{review_id}/citation-fixer")
def submit_review_citation_fixer(
    review_id: int,
    req: ReviewCitationFixerRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    review = db.get(KnowledgeReview, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="候选知识不存在")
    if not (
        review.source.startswith(ANSWER_CORRECTION_REVIEW_PREFIX)
        or review.source.startswith(GBRAIN_THINK_REVIEW_PREFIX)
    ):
        raise HTTPException(status_code=400, detail="仅 GBrain 回答审核项可提交 citation-fixer")

    page_slug = _normalize_gbrain_page_slug(req.page_slug) or _first_gbrain_citation_slug(review.content)
    if not page_slug:
        raise HTTPException(status_code=400, detail="无法从审核项中定位 GBrain 页面，请手动填写 page_slug")
    existing = _existing_citation_fixer_for_review(review.id)
    if existing:
        return {
            "ok": True,
            "status": "already_tracked",
            "review": _review_payload(review),
            "tracked_job": existing,
        }

    allowed_slug_prefixes = req.allowed_slug_prefixes or [_default_slug_prefix(page_slug)]
    result = GBrainAdapter().submit_citation_fixer(
        page_slug=page_slug,
        review_id=review.id,
        notes=req.notes or f"Submitted from KnowledgeReview #{review.id}: {review.source}",
        allowed_slug_prefixes=allowed_slug_prefixes,
        max_turns=max(1, min(int(req.max_turns or 30), 100)),
    )
    ok = result.get("status") == "ok"
    tracking = record_citation_fixer_job(
        submit_result=result,
        page_slug=page_slug,
        review_id=review.id,
        allowed_slug_prefixes=allowed_slug_prefixes,
        actor=user.username,
    ) if ok else None
    job_id = _gbrain_job_id(result)
    _write_admin_audit(
        db,
        user.id,
        "admin_knowledge_review_citation_fixer",
        f"review_id={review.id}, page_slug={page_slug}, ok={ok}, status={result.get('status')}, job_id={job_id or ''}",
    )
    notify_gbrain_maintenance_event(
        db,
        title="GBrain 引用修复任务已提交" if ok else "GBrain 引用修复任务提交失败",
        content=f"review #{review.id} · page={page_slug} · status={result.get('status') or 'unknown'} · job_id={job_id or '-'}",
        severity="info" if ok else "warning",
        action_status="pending",
    )
    db.commit()
    return {
        "ok": ok,
        "status": result.get("status") or "unknown",
        "review": _review_payload(review),
        "result": result,
        "tracking": tracking,
    }


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


def _first_gbrain_citation_slug(content: str) -> str:
    for match in re.finditer(r"^\s*\d+\.\s+`([^`]+)`", content or "", flags=re.MULTILINE):
        slug = _normalize_gbrain_page_slug(match.group(1))
        if slug:
            return slug
    return ""


def _normalize_gbrain_page_slug(value: str | None) -> str:
    slug = str(value or "").strip().strip("`")
    if not slug or slug.lower() == "gbrain":
        return ""
    slug = slug.replace("\\", "/")
    if slug.endswith(".md"):
        slug = slug[:-3]
    return slug.strip("/")


def _default_slug_prefix(page_slug: str) -> str:
    if "/" not in page_slug:
        return page_slug
    return f"{page_slug.rsplit('/', 1)[0]}/*"


def _existing_citation_fixer_for_review(review_id: int) -> dict | None:
    state = load_citation_fixer_job_state()
    for job in state.get("tracked_jobs") or []:
        if not isinstance(job, dict):
            continue
        if job.get("review_id") != review_id:
            continue
        status = str(job.get("status") or "").lower()
        if status and status not in TERMINAL_JOB_STATUSES:
            return job
    return None


def _gbrain_job_id(result: dict) -> int | None:
    payload = result.get("result") if isinstance(result.get("result"), dict) else {}
    value = payload.get("id") or payload.get("job_id") or result.get("job_id")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _review_payload(review: KnowledgeReview) -> dict:
    return {
        "id": review.id,
        "submitter_id": review.submitter_id,
        "content": review.content,
        "source": review.source,
        "status": review.status,
        "reviewer_id": review.reviewer_id,
        "created_at": review.created_at,
        "reviewed_at": review.reviewed_at,
    }


# ── 8.D Quality Report Endpoints ──────────────────────────────────────


@router.get("/quality/reports")
def list_quality_reports(
    project_slug: str | None = Query(None, description="Filter by project slug"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List quality regression reports (system admin only)."""
    if not is_system_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅系统管理员可查看质量报告")
    return list_reports(project_slug=project_slug, limit=limit)


@router.get("/quality/reports/{run_id}")
def get_quality_report(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a single quality regression report by run_id (system admin only)."""
    if not is_system_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅系统管理员可查看质量报告")

    # Search across all project report dirs
    from pathlib import Path
    BACKEND_DIR = Path(__file__).resolve().parents[1]
    AGGREGATED_DIR = BACKEND_DIR / "workspace_data" / "_preprocessed" / "_quality-reports"
    if not AGGREGATED_DIR.exists():
        raise HTTPException(status_code=404, detail="No quality reports found")

    for project_dir in AGGREGATED_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        report_path = project_dir / f"{run_id}.json"
        if report_path.exists():
            report = load_report(report_path)
            return report

    raise HTTPException(status_code=404, detail=f"Report {run_id} not found")


@router.get("/quality/reports/{run_id}/json")
def download_quality_report_json(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Download the raw JSON of a quality regression report."""
    if not is_system_admin_user(current_user):
        raise HTTPException(status_code=403, detail="仅系统管理员可下载质量报告")

    from pathlib import Path
    BACKEND_DIR = Path(__file__).resolve().parents[1]
    AGGREGATED_DIR = BACKEND_DIR / "workspace_data" / "_preprocessed" / "_quality-reports"
    if not AGGREGATED_DIR.exists():
        raise HTTPException(status_code=404, detail="No quality reports found")

    for project_dir in AGGREGATED_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        report_path = project_dir / f"{run_id}.json"
        if report_path.exists():
            report = load_report(report_path)
            from starlette.responses import JSONResponse
            return JSONResponse(
                content=report,
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'},
            )

    raise HTTPException(status_code=404, detail=f"Report {run_id} not found")


def _parse_date_filter(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} 日期格式不合法") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
