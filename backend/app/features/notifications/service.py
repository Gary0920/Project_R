from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid
from typing import Any, Iterable

from sqlalchemy.orm import Session

from models.notification import Notification
from models.user import User
from models.workspace import Workspace, WorkspaceMember

CATEGORIES = {"system", "task", "workspace", "approval", "risk"}
SEVERITIES = {"info", "success", "warning", "critical"}
ACTION_STATUSES = {"none", "pending", "done", "dismissed"}
ACTION_KINDS = {"", "open_session", "open_workspace", "open_skill_run", "download_file", "open_admin_review", "open_settings"}

LONG_RETENTION_DAYS = 180
DEFAULT_RETENTION_DAYS = 90


def _validate(value: str, allowed: set[str], field: str) -> str:
    if value not in allowed:
        raise ValueError(f"Invalid notification {field}: {value}")
    return value


def _payload_json(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))


def _default_expires_at(category: str, severity: str) -> datetime:
    days = LONG_RETENTION_DAYS if category == "risk" or severity == "critical" else DEFAULT_RETENTION_DAYS
    return datetime.now(timezone.utc) + timedelta(days=days)


def make_event_key(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4()}"


def notify_user(
    db: Session,
    user_id: int,
    *,
    category: str,
    severity: str,
    title: str,
    content: str = "",
    action_status: str = "none",
    action_kind: str = "",
    action_payload: dict[str, Any] | None = None,
    event_key: str | None = None,
    link: str = "",
    legacy_type: str | None = None,
    expires_at: datetime | None = None,
) -> Notification:
    category = _validate(category, CATEGORIES, "category")
    severity = _validate(severity, SEVERITIES, "severity")
    action_status = _validate(action_status, ACTION_STATUSES, "action_status")
    action_kind = _validate(action_kind, ACTION_KINDS, "action_kind")
    resolved_event_key = event_key or make_event_key(category)
    if event_key:
        existing = (
            db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.event_key == resolved_event_key)
            .first()
        )
        if existing:
            existing.type = legacy_type or category
            existing.category = category
            existing.severity = severity
            existing.title = title[:256]
            existing.content = content
            existing.is_read = False
            existing.action_status = action_status
            existing.action_kind = action_kind
            existing.action_payload_json = _payload_json(action_payload)
            existing.link = link[:512]
            existing.expires_at = expires_at or _default_expires_at(category, severity)
            return existing
    notification = Notification(
        user_id=user_id,
        type=legacy_type or category,
        category=category,
        severity=severity,
        title=title[:256],
        content=content,
        is_read=False,
        action_status=action_status,
        action_kind=action_kind,
        action_payload_json=_payload_json(action_payload),
        event_key=resolved_event_key,
        link=link[:512],
        expires_at=expires_at or _default_expires_at(category, severity),
    )
    db.add(notification)
    return notification


def notify_users(
    db: Session,
    user_ids: Iterable[int],
    *,
    category: str,
    severity: str,
    title: str,
    content: str = "",
    action_status: str = "none",
    action_kind: str = "",
    action_payload: dict[str, Any] | None = None,
    event_key: str | None = None,
    link: str = "",
    legacy_type: str | None = None,
) -> list[Notification]:
    unique_user_ids = list(dict.fromkeys(int(user_id) for user_id in user_ids))
    if not unique_user_ids:
        return []
    key = event_key or make_event_key(category)
    return [
        notify_user(
            db,
            user_id,
            category=category,
            severity=severity,
            title=title,
            content=content,
            action_status=action_status,
            action_kind=action_kind,
            action_payload=action_payload,
            event_key=key,
            link=link,
            legacy_type=legacy_type,
        )
        for user_id in unique_user_ids
    ]


def system_admin_ids(db: Session) -> list[int]:
    return [
        user.id
        for user in db.query(User).filter(User.role == "admin", User.is_active == True).all()
    ]


def workspace_member_ids(db: Session, workspace_id: int) -> list[int]:
    return [
        user_id
        for (user_id,) in db.query(WorkspaceMember.user_id)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id, User.is_active == True)
        .all()
    ]


def workspace_admin_ids(db: Session, workspace_id: int) -> list[int]:
    return [
        user_id
        for (user_id,) in db.query(WorkspaceMember.user_id)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role == "admin",
            User.is_active == True,
        )
        .all()
    ]


def notify_system_admins(
    db: Session,
    *,
    category: str,
    severity: str,
    title: str,
    content: str = "",
    action_status: str = "none",
    action_kind: str = "",
    action_payload: dict[str, Any] | None = None,
    event_key: str | None = None,
) -> list[Notification]:
    return notify_users(
        db,
        system_admin_ids(db),
        category=category,
        severity=severity,
        title=title,
        content=content,
        action_status=action_status,
        action_kind=action_kind,
        action_payload=action_payload,
        event_key=event_key,
    )


def notify_workspace_admins(
    db: Session,
    workspace_id: int,
    *,
    category: str,
    severity: str,
    title: str,
    content: str = "",
    action_status: str = "none",
    action_kind: str = "open_workspace",
    action_payload: dict[str, Any] | None = None,
    event_key: str | None = None,
) -> list[Notification]:
    return notify_users(
        db,
        workspace_admin_ids(db, workspace_id),
        category=category,
        severity=severity,
        title=title,
        content=content,
        action_status=action_status,
        action_kind=action_kind,
        action_payload=action_payload or {"workspace_id": workspace_id},
        event_key=event_key,
    )


def notify_workspace_members(
    db: Session,
    workspace_id: int,
    *,
    category: str,
    severity: str,
    title: str,
    content: str = "",
    action_status: str = "none",
    action_kind: str = "open_workspace",
    action_payload: dict[str, Any] | None = None,
    event_key: str | None = None,
) -> list[Notification]:
    return notify_users(
        db,
        workspace_member_ids(db, workspace_id),
        category=category,
        severity=severity,
        title=title,
        content=content,
        action_status=action_status,
        action_kind=action_kind,
        action_payload=action_payload or {"workspace_id": workspace_id},
        event_key=event_key,
    )


def notify_skill_completed(db: Session, *, run_id: int, user_id: int, filename: str, file_id: str | None) -> Notification:
    payload: dict[str, Any] = {"run_id": run_id}
    action_kind = "open_skill_run"
    if file_id:
        payload["file_id"] = file_id
        payload["filename"] = filename
        payload["download_url"] = f"/documents/{file_id}/download"
    return notify_user(
        db,
        user_id,
        category="task",
        severity="success",
        title="Skill 已完成",
        content=f"{filename or '生成文件'} 已准备好下载。",
        action_status="none",
        action_kind=action_kind,
        action_payload=payload,
        event_key=f"skill_run:{run_id}:completed",
    )


def notify_skill_blocked(
    db: Session,
    *,
    run_id: int,
    user_id: int,
    skill_name: str,
    missing_count: int,
) -> Notification:
    return notify_user(
        db,
        user_id,
        category="task",
        severity="warning",
        title="Skill 需要补充材料",
        content=f"{skill_name} 还缺少 {missing_count} 项必要信息，请补充后继续执行。",
        action_status="pending",
        action_kind="open_skill_run",
        action_payload={"run_id": run_id},
        event_key=f"skill_run:{run_id}:blocked",
    )


def notify_skill_failed(db: Session, *, run_id: int, user_id: int, skill_name: str, reason: str) -> Notification:
    return notify_user(
        db,
        user_id,
        category="task",
        severity="warning",
        title="Skill 执行失败",
        content=f"{skill_name} 执行失败：{reason or '请检查输入材料后重试。'}",
        action_status="pending",
        action_kind="open_skill_run",
        action_payload={"run_id": run_id},
        event_key=f"skill_run:{run_id}:failed",
    )


def notify_file_generated(db: Session, *, user_id: int, file_id: str, filename: str, session_id: int | None = None) -> Notification:
    payload: dict[str, Any] = {
        "file_id": file_id,
        "filename": filename,
        "download_url": f"/documents/{file_id}/download",
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return notify_user(
        db,
        user_id,
        category="task",
        severity="success",
        title="文件已生成",
        content=f"{filename} 已准备好下载。",
        action_status="none",
        action_kind="download_file",
        action_payload=payload,
        event_key=f"generated_file:{file_id}:ready",
    )


def notify_knowledge_review_pending(db: Session, *, review_id: int, source: str = "") -> list[Notification]:
    return notify_system_admins(
        db,
        category="approval",
        severity="warning",
        title="知识审核提醒",
        content=f"有新的知识候选待审核。来源：{source or 'Project_R'}",
        action_status="pending",
        action_kind="open_admin_review",
        action_payload={"review_id": review_id},
        event_key=f"knowledge_review:{review_id}:pending",
    )


def notify_system_risk_alert(db: Session, *, title: str, content: str, event_key: str | None = None) -> list[Notification]:
    return notify_system_admins(
        db,
        category="risk",
        severity="critical",
        title=title,
        content=content,
        action_status="pending",
        action_kind="open_settings",
        action_payload={"section": "admin"},
        event_key=event_key,
    )


def notify_gbrain_maintenance_event(
    db: Session,
    *,
    title: str,
    content: str = "",
    severity: str = "info",
    action_status: str = "none",
    event_key: str | None = None,
) -> list[Notification]:
    category = "risk" if severity == "critical" else "task"
    return notify_system_admins(
        db,
        category=category,
        severity=severity,
        title=title,
        content=content,
        action_status=action_status,
        action_kind="open_settings",
        action_payload={"section": "admin", "tab": "gbrain"},
        event_key=event_key,
    )


def notify_workspace_joined(db: Session, *, workspace: Workspace, user_id: int) -> Notification:
    return notify_user(
        db,
        user_id,
        category="workspace",
        severity="info",
        title="已加入项目工作区",
        content=f"您已加入 {workspace.name}，可以查看该项目资料和会话。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:join:{user_id}",
    )


def notify_workspace_indexed(db: Session, *, workspace: Workspace, actor_user_id: int, indexed_files: int) -> list[Notification]:
    if indexed_files <= 0:
        return []
    title = "项目资料索引完成"
    content = f"{workspace.name} 的 {indexed_files} 个项目资料已完成索引。"
    event_key = f"workspace:{workspace.id}:indexed:{uuid.uuid4()}"
    recipients = workspace_member_ids(db, workspace.id) if indexed_files >= 10 else [actor_user_id, *workspace_admin_ids(db, workspace.id)]
    return notify_users(
        db,
        recipients,
        category="workspace",
        severity="success",
        title=title,
        content=content,
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=event_key,
    )


def notify_workspace_bulk_delete_risk(db: Session, *, workspace: Workspace, actor_user_id: int, deleted_files: int) -> list[Notification]:
    if deleted_files < 5:
        return []
    actor = db.get(User, actor_user_id)
    return notify_workspace_admins(
        db,
        workspace.id,
        category="risk",
        severity="critical" if deleted_files >= 20 else "warning",
        title="项目文件批量删除提醒",
        content=f"{actor.nickname or actor.username if actor else '用户'} 在 {workspace.name} 中批量删除了 {deleted_files} 个文件，请确认是否为误操作。",
        action_status="pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:bulk_delete:{uuid.uuid4()}",
    )
