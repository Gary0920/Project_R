from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import GBrainAdapter
from app.features.knowledge.gbrain.graph import (
    apply_entity_merge_candidate_action,
    build_entity_merge_candidate_preview,
    build_entity_merge_candidates,
    build_source_graph,
)
from app.features.workspaces.audit import audit_detail, write_workspace_audit
from app.features.workspaces.gbrain_graph import workspace_gbrain_graph_scope, workspace_profile_cards
from app.features.workspaces.permissions import ensure_can_open_workspace, is_workspace_admin
from app.features.workspaces.schemas import (
    WorkspaceEntityMergeActionRequest,
    WorkspaceEntityMergeCandidatesResponse,
    WorkspaceKnowledgeGraphResponse,
)
from models.user import User
from models.workspace import Workspace


def workspace_knowledge_graph(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    focus: str | None,
    entity_type: str | None,
    limit: int,
) -> WorkspaceKnowledgeGraphResponse:
    ensure_can_open_workspace(db, user, workspace)
    scope = workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = _derived_path_from_scope(scope)
    graph = build_source_graph(
        source_id,
        derived_path=derived_path,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
    )
    write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_graph_view",
        audit_detail(
            workspace.id,
            "knowledge/graph",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            nodes=len(graph.get("nodes") or []),
            edges=len(graph.get("edges") or []),
            events=len(graph.get("events") or []),
        ),
    )
    db.commit()
    return WorkspaceKnowledgeGraphResponse(
        ok=bool(graph.get("ok")),
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_kind=workspace.workspace_kind,
        source_id=source_id,
        source_scope=str(scope["source_scope"]),
        intelligence_kind=str(scope["intelligence_kind"]),
        derived_path=str(graph.get("derived_path") or derived_path),
        focus=focus,
        entity_type=entity_type,
        nodes=list(graph.get("nodes") or []),
        edges=list(graph.get("edges") or []),
        events=list(graph.get("events") or []),
        profile_cards=workspace_profile_cards(graph),
        stats=graph.get("stats") if isinstance(graph.get("stats"), dict) else None,
        warnings=[str(item) for item in graph.get("warnings") or []],
    )


def workspace_entity_merge_candidates(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    focus: str | None,
    limit: int,
) -> WorkspaceEntityMergeCandidatesResponse:
    _ensure_workspace_admin(db, user, workspace, detail="仅系统管理员或工作区管理员可查看实体候选")
    scope = workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = _derived_path_from_scope(scope)
    result = build_entity_merge_candidates(source_id, derived_path=derived_path, focus=focus, limit=limit)
    write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidates_view",
        audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            candidates=len(result.get("candidates") or []),
        ),
    )
    db.commit()
    return WorkspaceEntityMergeCandidatesResponse(
        ok=bool(result.get("ok")),
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_kind=workspace.workspace_kind,
        source_id=source_id,
        source_scope=str(scope["source_scope"]),
        derived_path=str(result.get("derived_path") or derived_path),
        focus=focus,
        candidates=list(result.get("candidates") or []),
        stats=result.get("stats") if isinstance(result.get("stats"), dict) else None,
        warnings=[str(item) for item in result.get("warnings") or []],
    )


def workspace_entity_merge_candidate_action(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: WorkspaceEntityMergeActionRequest,
    adapter_cls: type = GBrainAdapter,
) -> dict:
    _ensure_workspace_admin(db, user, workspace, detail="仅系统管理员或工作区管理员可处理实体候选")
    if request.action not in {"create_entity_page", "dismiss", "record_alias", "apply_relink_changes"}:
        raise HTTPException(status_code=400, detail="实体候选操作不合法")

    scope = workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = _derived_path_from_scope(scope)
    result = apply_entity_merge_candidate_action(
        source_id,
        request.candidate_id,
        request.action,
        derived_path=derived_path,
        actor=user.username,
    )
    sync_result: dict | None = None
    if result.get("ok") and result.get("status") in {
        "created",
        "already_exists",
        "alias_recorded",
        "alias_already_exists",
        "relink_applied",
    }:
        sync_result = adapter_cls().sync_source(source_id=source_id, repo_path=derived_path, no_pull=True)
        result["sync"] = sync_result

    write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidate_action",
        audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates/action",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            action=request.action,
            status=result.get("status"),
            candidate_id=request.candidate_id[:160],
            sync=(sync_result or {}).get("status") or "",
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选操作失败")
    return result


def workspace_entity_merge_candidate_preview(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    candidate_id: str,
) -> dict:
    _ensure_workspace_admin(db, user, workspace, detail="仅系统管理员或工作区管理员可预览实体候选")
    scope = workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    derived_path = _derived_path_from_scope(scope)
    result = build_entity_merge_candidate_preview(source_id, candidate_id, derived_path=derived_path)
    write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_entity_merge_candidate_preview",
        audit_detail(
            workspace.id,
            "knowledge/entity-merge-candidates/preview",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            status=result.get("status"),
            candidate_id=candidate_id[:160],
            changes=((result.get("stats") or {}).get("planned_relink_changes") or 0),
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选预览失败")
    return result


def workspace_native_graph_context(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    slug: str,
    depth: int,
    direction: str,
    link_type: str | None,
    adapter_cls: type = GBrainAdapter,
) -> dict:
    ensure_can_open_workspace(db, user, workspace)
    scope = workspace_gbrain_graph_scope(workspace)
    source_id = str(scope["source_id"])
    result = adapter_cls().graph_context(
        slug,
        source_id=source_id,
        depth=depth,
        direction=direction,
        link_type=link_type,
    )
    write_workspace_audit(
        db,
        user.id,
        "workspace_gbrain_native_graph_context",
        audit_detail(
            workspace.id,
            "knowledge/graph/native-context",
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            source_id=source_id,
            slug=slug[:160],
            status=result.get("status"),
        ),
    )
    db.commit()
    return result


def _derived_path_from_scope(scope: dict[str, object]) -> Path:
    derived_path = scope["derived_path"]
    if not isinstance(derived_path, Path):
        raise HTTPException(status_code=500, detail="工作区 GBrain 路径配置错误")
    return derived_path


def _ensure_workspace_admin(db: Session, user: User, workspace: Workspace, *, detail: str) -> None:
    if not is_workspace_admin(db, user, workspace.id):
        raise HTTPException(status_code=403, detail=detail)
