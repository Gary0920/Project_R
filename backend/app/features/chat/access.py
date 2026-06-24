from __future__ import annotations

from sqlalchemy.orm import Session

from app.shared.errors import (
    ResourceNotFoundError,
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
)
from models.session import ChatSession
from models.user import User
from models.workspace import Workspace, WorkspaceGroupAccess, WorkspaceMember


def get_user_session(db: Session, user_id: int, session_id: int) -> ChatSession:
    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise ResourceNotFoundError("会话不存在")
    return session


def workspace_membership(db: Session, user_id: int, workspace_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )


def has_workspace_group_access(db: Session, user: User, workspace_id: int) -> bool:
    group_name = (getattr(user, "work_group", "") or "").strip().lower()
    if not group_name:
        return False
    return bool(
        db.query(WorkspaceGroupAccess)
        .filter(
            WorkspaceGroupAccess.workspace_id == workspace_id,
            WorkspaceGroupAccess.group_name == group_name,
        )
        .first()
    )


def ensure_workspace_access(db: Session, user: User, workspace_id: int) -> None:
    workspace = db.query(Workspace).filter(
        Workspace.id == workspace_id, Workspace.is_archived == False
    ).first()
    if not workspace:
        raise WorkspaceNotFoundError("工作区不存在")
    member = workspace_membership(db, user.id, workspace_id)
    if workspace.workspace_kind == "user":
        if member:
            return
        raise WorkspaceAccessDeniedError("你尚未加入该项目")
    if user.role == "admin":
        return
    if workspace.workspace_kind == "customer":
        if member or has_workspace_group_access(db, user, workspace_id):
            return
        raise WorkspaceAccessDeniedError("你尚未加入该项目")
    if not workspace.is_hidden:
        return
    if member or has_workspace_group_access(db, user, workspace_id):
        return
    raise WorkspaceAccessDeniedError("你尚未加入该项目")


def ensure_workspace_member(db: Session, user_id: int, workspace_id: int) -> None:
    if not workspace_membership(db, user_id, workspace_id):
        raise WorkspaceAccessDeniedError("你尚未加入该项目")
