from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import CUSTOMER_INTELLIGENCE_SOURCE_ID, GBrainAdapter
from app.features.knowledge.gbrain.graph import (
    apply_entity_merge_candidate_action,
    build_entity_merge_candidate_preview,
    build_entity_merge_candidates,
    build_source_graph,
)
from app.features.knowledge.quality.admin_helpers import write_audit
from models.user import User


GraphSourceResolver = Callable[[Session, str], Path | None]


def view_source_graph(
    db: Session,
    *,
    user: User,
    source_id: str,
    focus: str | None,
    entity_type: str | None,
    limit: int,
    resolve_source_path: GraphSourceResolver,
) -> dict[str, Any]:
    derived_path = _require_derived_path(db, source_id, resolve_source_path=resolve_source_path)
    result = build_source_graph(
        source_id,
        derived_path=derived_path,
        focus=focus,
        entity_type=entity_type,
        limit=limit,
    )
    write_audit(
        db,
        user.id,
        "admin_gbrain_graph_view",
        f"source_id={source_id}, focus={focus or ''}, nodes={len(result.get('nodes') or [])}, edges={len(result.get('edges') or [])}",
    )
    db.commit()
    return result


def list_entity_merge_candidates(
    db: Session,
    *,
    user: User,
    source_id: str,
    focus: str | None,
    limit: int,
    resolve_source_path: GraphSourceResolver,
) -> dict[str, Any]:
    derived_path = _require_derived_path(db, source_id, resolve_source_path=resolve_source_path)
    result = build_entity_merge_candidates(source_id, derived_path=derived_path, focus=focus, limit=limit)
    write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidates_view",
        f"source_id={source_id}, focus={focus or ''}, candidates={len(result.get('candidates') or [])}",
    )
    db.commit()
    return result


def apply_entity_merge_action(
    db: Session,
    *,
    user: User,
    request: Any,
    resolve_source_path: GraphSourceResolver,
    adapter_cls: type[GBrainAdapter] = GBrainAdapter,
) -> dict[str, Any]:
    source_id = request.source_id.strip() or CUSTOMER_INTELLIGENCE_SOURCE_ID
    derived_path = _require_derived_path(db, source_id, resolve_source_path=resolve_source_path)
    result = apply_entity_merge_candidate_action(
        source_id,
        request.candidate_id,
        request.action,
        derived_path=derived_path,
        actor=user.username,
    )
    sync_result: dict[str, Any] | None = None
    if result.get("ok") and result.get("status") in {
        "created",
        "already_exists",
        "alias_recorded",
        "alias_already_exists",
        "relink_applied",
    }:
        sync_result = adapter_cls().sync_source(source_id=source_id, repo_path=derived_path, no_pull=True)
        result["sync"] = sync_result
    write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidate_action",
        (
            f"source_id={source_id}, action={request.action}, status={result.get('status')}, "
            f"candidate_id={request.candidate_id[:160]}, sync={(sync_result or {}).get('status') or ''}"
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选操作失败")
    return result


def preview_entity_merge_candidate(
    db: Session,
    *,
    user: User,
    source_id: str,
    candidate_id: str,
    resolve_source_path: GraphSourceResolver,
) -> dict[str, Any]:
    source_id = source_id.strip() or CUSTOMER_INTELLIGENCE_SOURCE_ID
    derived_path = _require_derived_path(db, source_id, resolve_source_path=resolve_source_path)
    result = build_entity_merge_candidate_preview(source_id, candidate_id, derived_path=derived_path)
    write_audit(
        db,
        user.id,
        "admin_gbrain_entity_merge_candidate_preview",
        (
            f"source_id={source_id}, status={result.get('status')}, "
            f"candidate_id={candidate_id[:160]}, changes={((result.get('stats') or {}).get('planned_relink_changes') or 0)}"
        ),
    )
    db.commit()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "实体候选预览失败")
    return result


def _require_derived_path(
    db: Session,
    source_id: str,
    *,
    resolve_source_path: GraphSourceResolver,
) -> Path:
    derived_path = resolve_source_path(db, source_id)
    if derived_path is None:
        raise HTTPException(status_code=404, detail="未知或不可用的 GBrain source")
    return derived_path
