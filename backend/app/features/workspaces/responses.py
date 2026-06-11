from __future__ import annotations

from sqlalchemy.orm import Session

from app.features.workspaces.permissions import is_workspace_admin
from app.features.workspaces.schemas import WorkspaceResponse
from models.user import User
from models.workspace import Workspace, WorkspaceMember


def workspace_response(
    db: Session,
    workspace: Workspace,
    member_count: int | None = None,
    user: User | None = None,
) -> WorkspaceResponse:
    count = member_count
    if count is None:
        count = db.query(WorkspaceMember).filter(WorkspaceMember.workspace_id == workspace.id).count()
    can_manage = bool(user and is_workspace_admin(db, user, workspace.id))
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        created_by=workspace.created_by,
        member_count=count,
        brand=workspace.brand,
        workspace_kind=workspace.workspace_kind,
        is_default=workspace.is_default,
        is_archived=workspace.is_archived,
        is_hidden=workspace.is_hidden,
        can_rename=not workspace.is_default and can_manage,
        can_delete=not workspace.is_default and can_manage,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )
