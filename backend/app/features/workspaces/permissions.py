from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.workspaces.schemas import MemberResponse, UpsertWorkspaceMemberRequest
from models.user import User
from models.workspace import Workspace, WorkspaceGroupAccess, WorkspaceMember


def normalize_group_name(value: str | None) -> str:
    return (value or "").strip()


def serialize_workspace_member(member: WorkspaceMember, user: User) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        username=user.username,
        nickname=user.nickname,
        role=member.role,
        joined_at=member.joined_at,
    )


def validate_workspace_member_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in {"admin", "member"}:
        raise HTTPException(status_code=400, detail="工作区成员角色不合法")
    return normalized


def workspace_membership(db: Session, user_id: int, workspace_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )


def workspace_access_groups(db: Session, workspace_id: int) -> list[str]:
    return [
        row.group_name
        for row in db.query(WorkspaceGroupAccess)
        .filter(WorkspaceGroupAccess.workspace_id == workspace_id)
        .order_by(WorkspaceGroupAccess.group_name.asc())
        .all()
    ]


def has_workspace_group_access(db: Session, user: User, workspace_id: int) -> bool:
    group_name = normalize_group_name(getattr(user, "work_group", ""))
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


def can_open_workspace(db: Session, user: User, workspace: Workspace) -> bool:
    if workspace.workspace_kind == "user":
        return workspace_membership(db, user.id, workspace.id) is not None
    if user.role == "admin":
        return True
    if workspace.workspace_kind == "customer":
        return workspace_membership(db, user.id, workspace.id) is not None or has_workspace_group_access(db, user, workspace.id)
    if not workspace.is_hidden:
        return True
    return workspace_membership(db, user.id, workspace.id) is not None or has_workspace_group_access(db, user, workspace.id)


def ensure_can_open_workspace(db: Session, user: User, workspace: Workspace) -> None:
    if not can_open_workspace(db, user, workspace):
        raise HTTPException(status_code=403, detail="无权访问该工作区")


def is_workspace_admin(db: Session, user: User, workspace_id: int) -> bool:
    member = workspace_membership(db, user.id, workspace_id)
    if member and member.role == "admin":
        return True
    if user.role == "admin":
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        return bool(workspace and workspace.workspace_kind != "user")
    return False


def ensure_member(db: Session, user_id: int, workspace_id: int) -> WorkspaceMember:
    member = workspace_membership(db, user_id, workspace_id)
    if member:
        return member
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.role == "admin":
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if workspace and workspace.workspace_kind != "user":
            return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="admin")
    if user:
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if workspace and workspace.workspace_kind == "project":
            if not workspace.is_hidden or has_workspace_group_access(db, user, workspace_id):
                return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")
        if workspace and workspace.workspace_kind == "customer" and has_workspace_group_access(db, user, workspace_id):
            return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="member")
    if not member:
        raise HTTPException(status_code=403, detail="你尚未加入该工作区")
    return member


def ensure_workspace_admin(db: Session, user: User, workspace_id: int) -> WorkspaceMember:
    member = ensure_member(db, user.id, workspace_id)
    if member.role != "admin" and user.role != "admin":
        raise HTTPException(status_code=403, detail="仅工作区管理员可管理成员")
    return member


def ensure_mutable_membership_workspace(workspace: Workspace) -> None:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持邀请成员")


def resolve_member_target_user(db: Session, req: UpsertWorkspaceMemberRequest) -> User:
    target_user: User | None = None
    if req.user_id is not None:
        target_user = db.query(User).filter(User.id == req.user_id).first()
    elif req.username and req.username.strip():
        target_user = db.query(User).filter(User.username == req.username.strip()).first()
    else:
        raise HTTPException(status_code=400, detail="需要提供用户 ID 或用户名")
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not target_user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return target_user


def local_workspace_admin_count(db: Session, workspace_id: int) -> int:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "admin")
        .count()
    )
