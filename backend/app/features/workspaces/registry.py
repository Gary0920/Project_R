from __future__ import annotations

from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.features.workspaces.files.storage import (
    WorkspaceStorageConfig,
    ensure_storage_path,
    project_brand_dirs,
    safe_username,
    slugify,
)
from app.features.workspaces.permissions import workspace_membership
from models.user import User
from models.workspace import Workspace, WorkspaceMember


def ensure_default_workspace(db: Session, user: User) -> Workspace:
    existing = (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(
            Workspace.workspace_kind == "user",
            Workspace.is_default == True,
            WorkspaceMember.user_id == user.id,
        )
        .first()
    )
    if existing:
        expected_name = f"{user.username}的工作台"
        if existing.name.endswith(" 的私人空间") or existing.name.endswith("的私人空间"):
            existing.name = expected_name
            existing.description = "用户默认个人工作台"
        if existing.storage_path:
            existing.storage_path = ""
            db.commit()
        elif existing.name == expected_name:
            db.commit()
        return existing

    slug_base = f"user-{safe_username(user.username)}"
    slug = slug_base
    suffix = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{slug_base}-{suffix}"
        suffix += 1
    workspace = Workspace(
        name=f"{user.username}的工作台",
        slug=slug,
        description="用户默认个人工作台",
        created_by=user.id,
        brand="",
        workspace_kind="user",
        is_default=True,
    )
    db.add(workspace)
    db.flush()
    workspace.storage_path = ""
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def find_existing_project_folder(
    brand: str,
    slug: str,
    name: str | None,
    config: WorkspaceStorageConfig,
) -> Path | None:
    brand_dir = (config.workspaces_root / config.project_root_name / brand).resolve()
    if not brand_dir.exists() or not brand_dir.is_dir():
        return None
    candidates = {slug.casefold()}
    if name:
        candidates.add(name.casefold())
    for child in brand_dir.iterdir():
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name.casefold() in candidates or slugify(child.name) == slug:
            return child.resolve()
    return None


def register_existing_project_folder(
    db: Session,
    user: User,
    brand: str,
    project_dir: Path,
    config: WorkspaceStorageConfig,
    *,
    add_member: bool = False,
) -> Workspace | None:
    if not project_dir.exists() or not project_dir.is_dir() or project_dir.is_symlink():
        return None
    slug = slugify(project_dir.name)
    if db.query(Workspace).filter(Workspace.slug == slug).first():
        return None
    workspace = Workspace(
        name=project_dir.name,
        slug=slug,
        description="",
        created_by=user.id,
        storage_path=str(project_dir.resolve()),
        brand=brand,
        workspace_kind="project",
        is_default=False,
    )
    db.add(workspace)
    db.flush()
    workspace.storage_path = ensure_storage_path(workspace, config)
    if add_member:
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def find_crm_workspace(db: Session, *, crm_workspace_slug: str, crm_workspace_name: str) -> Workspace | None:
    exact = (
        db.query(Workspace)
        .filter(
            Workspace.workspace_kind == "customer",
            or_(Workspace.slug == crm_workspace_slug, Workspace.name == crm_workspace_name),
        )
        .order_by(Workspace.id.asc())
        .first()
    )
    if exact:
        return exact
    return (
        db.query(Workspace)
        .filter(Workspace.workspace_kind == "customer")
        .order_by(Workspace.id.asc())
        .first()
    )


def ensure_crm_workspace(
    db: Session,
    user: User,
    config: WorkspaceStorageConfig,
    *,
    crm_workspace_name: str,
    add_member: bool = False,
) -> Workspace:
    workspace = find_crm_workspace(
        db,
        crm_workspace_slug=config.crm_workspace_slug,
        crm_workspace_name=crm_workspace_name,
    )
    if workspace is None:
        workspace = Workspace(
            name=crm_workspace_name,
            slug=config.crm_workspace_slug,
            description="全公司 CRM 客户情报工作区",
            created_by=user.id,
            storage_path=str((config.workspaces_root / config.customer_root_name / config.crm_workspace_slug).resolve()),
            brand=config.customer_brand,
            workspace_kind="customer",
            is_default=False,
            is_hidden=True,
        )
        db.add(workspace)
        db.flush()
    workspace.name = crm_workspace_name
    workspace.slug = config.crm_workspace_slug
    workspace.brand = config.customer_brand
    workspace.workspace_kind = "customer"
    workspace.storage_path = ensure_storage_path(workspace, config)
    if add_member and not workspace_membership(db, user.id, workspace.id):
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin"))
    db.commit()
    db.refresh(workspace)
    return workspace


def sync_project_folders(db: Session, user: User, config: WorkspaceStorageConfig) -> None:
    project_root = (config.workspaces_root / config.project_root_name).resolve()
    if not project_root.exists():
        return
    for brand, brand_dir in project_brand_dirs(config):
        if not brand_dir.exists() or not brand_dir.is_dir():
            continue
        for child in sorted(brand_dir.iterdir(), key=lambda item: item.name.lower()):
            register_existing_project_folder(db, user, brand, child.resolve(), config)
