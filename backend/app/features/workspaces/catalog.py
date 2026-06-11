from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.shared.time.utils import serialize_datetime_utc
from app.features.workspaces.schemas import (
    CreateWorkspaceRequest,
    MemberResponse,
    WorkspaceDetailResponse,
    WorkspaceResponse,
)
from models.user import User
from models.workspace import Workspace, WorkspaceGroupAccess, WorkspaceMember


def create_workspace(
    db: Session,
    req: CreateWorkspaceRequest,
    user: User,
    *,
    normalize_workspace_kind: Callable[[str | None, str | None], str],
    ensure_crm_workspace: Callable[..., Workspace],
    workspace_response: Callable[[Session, Workspace, int | None, User | None], WorkspaceResponse],
    normalize_brand: Callable[[str], str],
    slugify_name: Callable[[str], str],
    candidate_storage_path: Callable[[str, str, str], Path],
    workspaces_root: Path,
    find_existing_project_folder: Callable[[str, str, str | None], Path | None],
    register_existing_project_folder: Callable[..., Workspace | None],
    ensure_storage_path: Callable[..., str],
) -> WorkspaceResponse:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅系统管理员可新建工作区")

    workspace_kind = normalize_workspace_kind(req.workspace_kind, req.brand)
    if workspace_kind == "customer":
        workspace = ensure_crm_workspace(db, user, add_member=True)
        return workspace_response(db, workspace, None, user)

    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="工作区名称不能为空")
    if len(name) > 128:
        raise HTTPException(status_code=400, detail="工作区名称不能超过 128 个字符")

    brand = normalize_brand(req.brand)
    slug = slugify_name(name)
    existing = db.query(Workspace).filter(Workspace.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="已存在同名工作区，请选择已有工作区或使用不同名称")

    target_path = candidate_storage_path(slug, brand, workspace_kind)
    root = workspaces_root.resolve()
    if not target_path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="工作区目录不合法")

    if workspace_kind == "project":
        existing_folder = find_existing_project_folder(brand, slug, name)
        if existing_folder:
            workspace = register_existing_project_folder(db, user, brand, existing_folder, add_member=True)
            if workspace:
                return workspace_response(db, workspace, None, user)
            raise HTTPException(status_code=409, detail="后端已存在同名项目文件夹，请选择已有项目或更换项目名称")

    if target_path.exists():
        raise HTTPException(status_code=409, detail="后端已存在同名工作区文件夹，请选择已有工作区或更换名称")

    workspace = Workspace(
        name=name,
        slug=slug,
        description=req.description.strip(),
        created_by=user.id,
        brand=brand,
        workspace_kind=workspace_kind,
        is_default=False,
        is_hidden=workspace_kind == "customer",
    )
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    workspace.storage_path = ensure_storage_path(workspace)
    db.commit()

    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()

    return workspace_response(db, workspace, 1, user)


def list_workspaces(
    db: Session,
    user: User,
    *,
    ensure_default_workspace: Callable[[Session, User], Workspace],
    sync_project_folders: Callable[[Session, User], None],
    ensure_crm_workspace: Callable[..., Workspace],
    normalize_group_name: Callable[[str | None], str],
    can_open_workspace: Callable[[Session, User, Workspace], bool],
    workspace_response: Callable[[Session, Workspace, int | None, User | None], WorkspaceResponse],
    crm_workspace_slug: str,
) -> list[WorkspaceResponse]:
    ensure_default_workspace(db, user)
    sync_project_folders(db, user)
    ensure_crm_workspace(db, user)
    if user.role == "admin":
        workspaces = (
            db.query(Workspace)
            .filter(or_(Workspace.workspace_kind != "user", Workspace.created_by == user.id))
            .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())
            .all()
        )
        workspaces = [w for w in workspaces if w.workspace_kind != "customer" or w.slug == crm_workspace_slug]
    else:
        member_workspace_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        group_workspace_ids = select(WorkspaceGroupAccess.workspace_id).where(
            WorkspaceGroupAccess.group_name == normalize_group_name(user.work_group)
        )
        workspaces = (
            db.query(Workspace)
            .filter(
                or_(
                    Workspace.id.in_(member_workspace_ids),
                    Workspace.workspace_kind == "project",
                    Workspace.workspace_kind == "customer",
                    Workspace.id.in_(group_workspace_ids),
                )
            )
            .order_by(Workspace.is_default.desc(), Workspace.updated_at.desc())
            .all()
        )
        workspaces = [w for w in workspaces if can_open_workspace(db, user, w)]
        workspaces = [w for w in workspaces if w.workspace_kind != "customer" or w.slug == crm_workspace_slug]
    return [workspace_response(db, w, None, user) for w in workspaces]


def search_workspaces(
    db: Session,
    query_text: str,
    user: User,
    brand: str | None,
    *,
    sync_project_folders: Callable[[Session, User], None],
    ensure_crm_workspace: Callable[..., Workspace],
    normalize_brand: Callable[[str], str],
    normalize_group_name: Callable[[str | None], str],
    can_open_workspace: Callable[[Session, User, Workspace], bool],
    is_workspace_admin: Callable[[Session, User, int], bool],
    customer_brand: str,
    crm_workspace_slug: str,
) -> list[dict]:
    sync_project_folders(db, user)
    ensure_crm_workspace(db, user)
    query = query_text.strip()
    raw_brand = (brand or "").strip().upper()
    search_customer = raw_brand == customer_brand
    normalized_brand = normalize_brand(raw_brand) if raw_brand and not search_customer else None
    pattern = f"%{query}%" if query else "%"
    workspace_query = (
        db.query(Workspace)
        .filter(
            Workspace.workspace_kind == "customer" if search_customer else Workspace.workspace_kind.in_(("project", "customer")),
            Workspace.is_archived == False,
            Workspace.name.ilike(pattern) | Workspace.slug.ilike(pattern),
        )
    )
    if normalized_brand:
        workspace_query = workspace_query.filter(Workspace.workspace_kind == "project", Workspace.brand == normalized_brand)
    if search_customer:
        workspace_query = workspace_query.filter(Workspace.slug == crm_workspace_slug)
    else:
        workspace_query = workspace_query.filter(
            or_(Workspace.workspace_kind == "project", Workspace.slug == crm_workspace_slug)
        )
    if user.role != "admin":
        member_workspace_ids = select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
        group_workspace_ids = select(WorkspaceGroupAccess.workspace_id).where(
            WorkspaceGroupAccess.group_name == normalize_group_name(user.work_group)
        )
        workspace_query = workspace_query.filter(
            or_(
                (Workspace.workspace_kind == "project") & (Workspace.is_hidden == False),
                Workspace.id.in_(member_workspace_ids),
                Workspace.id.in_(group_workspace_ids),
            )
        )
    workspaces = workspace_query.order_by(
        Workspace.brand.asc(),
        Workspace.updated_at.desc(),
        Workspace.name.asc(),
    ).limit(100).all()
    member_ids = {
        row.workspace_id
        for row in db.query(WorkspaceMember.workspace_id)
        .filter(WorkspaceMember.user_id == user.id)
        .all()
    }
    manageable_ids = {w.id for w in workspaces if is_workspace_admin(db, user, w.id)}
    return [
        {
            "id": w.id,
            "name": w.name,
            "slug": w.slug,
            "description": w.description,
            "brand": w.brand,
            "workspace_kind": w.workspace_kind,
            "is_default": w.is_default,
            "is_hidden": w.is_hidden,
            "member_count": db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == w.id)
            .count(),
            "is_member": w.id in member_ids,
            "can_open": can_open_workspace(db, user, w),
            "can_rename": not w.is_default and w.id in manageable_ids,
            "can_delete": not w.is_default and w.id in manageable_ids,
            "is_archived": w.is_archived,
            "created_at": serialize_datetime_utc(w.created_at),
            "updated_at": serialize_datetime_utc(w.updated_at),
            "created_by": w.created_by,
        }
        for w in workspaces
    ]


def get_workspace(
    db: Session,
    workspace_id: int,
    user: User,
    *,
    can_open_workspace: Callable[[Session, User, Workspace], bool],
    ensure_member: Callable[[Session, int, int], WorkspaceMember],
    is_workspace_admin: Callable[[Session, User, int], bool],
    workspace_access_groups: Callable[[Session, int], list[str]],
) -> WorkspaceDetailResponse:
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not workspace:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not can_open_workspace(db, user, workspace):
        raise HTTPException(status_code=403, detail="你无权访问该隐藏项目")
    ensure_member(db, user.id, workspace_id)

    members = (
        db.query(WorkspaceMember, User)
        .join(User, WorkspaceMember.user_id == User.id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    member_list = [
        MemberResponse(
            user_id=member_user.id,
            username=member_user.username,
            nickname=member_user.nickname,
            role=wm.role,
            joined_at=wm.joined_at,
        )
        for wm, member_user in members
    ]

    can_manage = is_workspace_admin(db, user, workspace.id)
    return WorkspaceDetailResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        created_by=workspace.created_by,
        member_count=len(member_list),
        brand=workspace.brand,
        workspace_kind=workspace.workspace_kind,
        is_default=workspace.is_default,
        is_archived=workspace.is_archived,
        is_hidden=workspace.is_hidden,
        can_rename=not workspace.is_default and can_manage,
        can_delete=not workspace.is_default and can_manage,
        storage_path=workspace.storage_path,
        members=member_list,
        access_groups=workspace_access_groups(db, workspace.id),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )
