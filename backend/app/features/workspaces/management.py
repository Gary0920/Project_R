from __future__ import annotations

from typing import Callable

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.features.notifications.service import notify_user
from app.features.workspaces.audit import audit_detail, write_workspace_audit
from app.features.workspaces.permissions import (
    ensure_mutable_membership_workspace,
    ensure_workspace_admin,
    has_workspace_group_access,
    is_workspace_admin,
    local_workspace_admin_count,
    normalize_group_name,
    resolve_member_target_user,
    serialize_workspace_member,
    validate_workspace_member_role,
    workspace_access_groups,
    workspace_membership,
)
from app.features.workspaces.schemas import (
    MemberResponse,
    UpdateWorkspaceMemberRoleRequest,
    UpdateWorkspaceRequest,
    UpsertWorkspaceGroupRequest,
    UpsertWorkspaceMemberRequest,
    WorkspaceGroupCandidateResponse,
    WorkspaceGroupResponse,
    WorkspaceMemberCandidateResponse,
    WorkspaceResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceGroupAccess, WorkspaceMember


def update_workspace(
    db: Session,
    workspace_id: int,
    req: UpdateWorkspaceRequest,
    user: User,
    *,
    workspace_response: Callable[[Session, Workspace, int | None, User | None], WorkspaceResponse],
) -> WorkspaceResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    ensure_workspace_admin(db, user, workspace_id)
    if workspace.is_default and (req.name is not None or req.description is not None):
        raise HTTPException(status_code=400, detail="默认工作区不能重命名或修改")

    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        if len(name) > 128:
            raise HTTPException(status_code=400, detail="项目名称不能超过 128 个字符")
        workspace.name = name
    if req.description is not None:
        workspace.description = req.description.strip()
    if req.is_hidden is not None:
        if workspace.workspace_kind == "user":
            raise HTTPException(status_code=400, detail="个人工作台不支持隐藏项目设置")
        workspace.is_hidden = req.is_hidden

    db.commit()
    db.refresh(workspace)
    return workspace_response(db, workspace, None, user)


def list_workspace_member_candidates(
    db: Session,
    workspace_id: int,
    query: str,
    limit: int,
    user: User,
) -> list[WorkspaceMemberCandidateResponse]:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    text = query.strip().lower()
    member_roles = {
        member.user_id: member.role
        for member in db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace_id).all()
    }
    users_query = db.query(User).filter(User.is_active == True)
    if text:
        needle = f"%{text}%"
        users_query = users_query.filter(
            or_(
                User.username.ilike(needle),
                User.nickname.ilike(needle),
                User.work_group.ilike(needle),
            )
        )
    users = users_query.order_by(User.username.asc()).limit(limit).all()
    return [
        WorkspaceMemberCandidateResponse(
            user_id=item.id,
            username=item.username,
            nickname=item.nickname,
            work_group=item.work_group,
            role=item.role,
            is_member=item.id in member_roles,
            member_role=member_roles.get(item.id),
        )
        for item in users
    ]


def list_workspace_group_candidates(
    db: Session,
    workspace_id: int,
    query: str,
    limit: int,
    user: User,
) -> list[WorkspaceGroupCandidateResponse]:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    authorized = set(workspace_access_groups(db, workspace_id))
    groups: dict[str, WorkspaceGroupCandidateResponse] = {}
    for (group_name,) in db.query(User.work_group).filter(User.work_group != "").distinct().all():
        normalized = normalize_group_name(group_name)
        if normalized:
            groups[normalized] = WorkspaceGroupCandidateResponse(
                group_name=normalized,
                source="user",
                is_authorized=normalized in authorized,
            )
    for group_name in authorized:
        groups[group_name] = WorkspaceGroupCandidateResponse(
            group_name=group_name,
            source=groups.get(group_name).source if group_name in groups else "workspace",
            is_authorized=True,
        )
    text = query.strip().lower()
    items = [
        item
        for item in groups.values()
        if not text or text in item.group_name.lower()
    ]
    return sorted(items, key=lambda item: (not item.is_authorized, item.group_name.lower()))[:limit]


def upsert_workspace_member(
    db: Session,
    workspace_id: int,
    req: UpsertWorkspaceMemberRequest,
    user: User,
) -> MemberResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    role = validate_workspace_member_role(req.role)
    target_user = resolve_member_target_user(db, req)
    member = workspace_membership(db, target_user.id, workspace_id)
    action = "workspace_member_update" if member else "workspace_member_invite"
    if member:
        member.role = role
    else:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=target_user.id, role=role)
        db.add(member)
    db.flush()
    write_workspace_audit(
        db,
        user.id,
        action,
        audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user.id, role=role),
    )
    notify_user(
        db,
        target_user.id,
        category="workspace",
        severity="info",
        title="工作区权限已更新",
        content=f"{workspace.name}：你已被设置为{'工作区管理员' if role == 'admin' else '成员'}。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:member:{target_user.id}:{role}",
    )
    db.commit()
    db.refresh(member)
    db.refresh(target_user)
    return serialize_workspace_member(member, target_user)


def update_workspace_member_role(
    db: Session,
    workspace_id: int,
    target_user_id: int,
    req: UpdateWorkspaceMemberRoleRequest,
    user: User,
) -> MemberResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    role = validate_workspace_member_role(req.role)
    member = workspace_membership(db, target_user_id, workspace_id)
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member.role == "admin" and role != "admin" and local_workspace_admin_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一名工作区管理员")
    target_user = db.query(User).filter(User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="用户不存在")

    member.role = role
    write_workspace_audit(
        db,
        user.id,
        "workspace_member_role_update",
        audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user_id, role=role),
    )
    notify_user(
        db,
        target_user.id,
        category="workspace",
        severity="info",
        title="工作区角色已更新",
        content=f"{workspace.name}：你的角色已变更为{'工作区管理员' if role == 'admin' else '成员'}。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:role:{target_user.id}:{role}",
    )
    db.commit()
    db.refresh(member)
    return serialize_workspace_member(member, target_user)


def remove_workspace_member(db: Session, workspace_id: int, target_user_id: int, user: User) -> dict:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    member = workspace_membership(db, target_user_id, workspace_id)
    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")
    if member.role == "admin" and local_workspace_admin_count(db, workspace_id) <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一名工作区管理员")
    db.delete(member)
    write_workspace_audit(
        db,
        user.id,
        "workspace_member_remove",
        audit_detail(workspace_id, actor_id=user.id, target_user_id=target_user_id),
    )
    notify_user(
        db,
        target_user_id,
        category="workspace",
        severity="info",
        title="工作区访问权限已移除",
        content=f"{workspace.name}：你已不再是该工作区成员。",
        action_status="none",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
        event_key=f"workspace:{workspace.id}:remove:{target_user_id}",
    )
    db.commit()
    return {"ok": True}


def upsert_workspace_group(
    db: Session,
    workspace_id: int,
    req: UpsertWorkspaceGroupRequest,
    user: User,
) -> WorkspaceGroupResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    group_name = normalize_group_name(req.group_name)
    if not group_name:
        raise HTTPException(status_code=400, detail="组别不能为空")
    existing = (
        db.query(WorkspaceGroupAccess)
        .filter(WorkspaceGroupAccess.workspace_id == workspace_id, WorkspaceGroupAccess.group_name == group_name)
        .first()
    )
    if not existing:
        db.add(WorkspaceGroupAccess(workspace_id=workspace_id, group_name=group_name))
        write_workspace_audit(
            db,
            user.id,
            "workspace_group_access_add",
            audit_detail(workspace_id, actor_id=user.id, group_name=group_name),
        )
        db.commit()
    return WorkspaceGroupResponse(group_name=group_name)


def remove_workspace_group(db: Session, workspace_id: int, group_name: str, user: User) -> dict:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="工作区不存在")
    ensure_mutable_membership_workspace(workspace)
    ensure_workspace_admin(db, user, workspace_id)

    normalized = normalize_group_name(group_name)
    db.query(WorkspaceGroupAccess).filter(
        WorkspaceGroupAccess.workspace_id == workspace_id,
        WorkspaceGroupAccess.group_name == normalized,
    ).delete()
    write_workspace_audit(
        db,
        user.id,
        "workspace_group_access_remove",
        audit_detail(workspace_id, actor_id=user.id, group_name=normalized),
    )
    db.commit()
    return {"ok": True}


def join_workspace(db: Session, workspace_id: int, user: User) -> dict:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if existing:
        return {"ok": True, "message": "已是项目成员"}

    if user.role == "admin" and workspace.workspace_kind != "user":
        return {"ok": True, "message": "系统管理员无需加入即可访问"}
    if workspace.workspace_kind == "project" and not workspace.is_hidden:
        return {"ok": True, "message": "开放项目无需加入即可访问"}
    if workspace.workspace_kind in {"project", "customer"} and has_workspace_group_access(db, user, workspace_id):
        return {"ok": True, "message": "你的组别已获授权访问"}

    raise HTTPException(status_code=403, detail="受限工作区只能通过工作区管理员添加人员或组别授权")


def delete_workspace(db: Session, workspace_id: int, user: User) -> dict:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")
    if workspace.is_default:
        raise HTTPException(status_code=400, detail="默认工作区不能删除")

    if not is_workspace_admin(db, user, workspace_id):
        raise HTTPException(status_code=403, detail="仅项目管理员可删除")

    db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace_id
    ).delete()
    db.query(WorkspaceGroupAccess).filter(
        WorkspaceGroupAccess.workspace_id == workspace_id
    ).delete()
    db.delete(workspace)
    db.commit()
    return {"ok": True}
