"""Admin-level GBrain helper functions.

Pure helpers extracted from api/rag.py. Functions that use monkeypatched
module-level names (GBrainAdapter, load_gbrain_settings) remain in rag.py
as thin wrappers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import (
    CUSTOMER_INTELLIGENCE_SOURCE_ID,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    load_gbrain_settings,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.knowledge.gbrain.customer_sources import CUSTOMER_REFERENCE_DERIVED
from models.audit_log import AuditLog
from models.knowledge_review import KnowledgeReview
from models.workspace import Workspace


def create_pending_reviews_from_manifest(
    db: Session,
    user_id: int,
    manifest: dict[str, Any],
    settings: Any = None,
) -> int:
    """Create KnowledgeReview records for items marked pending_review in a compile manifest."""
    if settings is None:
        settings = load_gbrain_settings()
    created = 0
    for item in manifest.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("review_status") != "pending_review":
            continue
        target_file = item.get("target_file")
        if not isinstance(target_file, str) or not target_file:
            continue
        source = f"gbrain_pending_review:{target_file}"
        existing = (
            db.query(KnowledgeReview)
            .filter(KnowledgeReview.source == source, KnowledgeReview.status == "pending")
            .first()
        )
        if existing:
            continue
        content_path = (settings.derived_path / target_file).resolve()
        try:
            content_path.relative_to(settings.derived_path.resolve())
            content = content_path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            content = f"Pending review file: {target_file}"
        db.add(
            KnowledgeReview(
                submitter_id=user_id,
                content=content,
                source=source,
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
        )
        created += 1
    return created


def refresh_error(manifest: dict[str, Any], sync_result: dict[str, Any]) -> str:
    """Build an error message when knowledge refresh fails."""
    failed = int((manifest.get("summary") or {}).get("failed", 0) or 0)
    if failed:
        return f"raw 编译有 {failed} 个失败项，请查看 manifest 中的 error 后重试。"
    if sync_result.get("status") != "ok":
        return f"GBrain sync 未完成：{sync_result.get('status') or 'unknown'} {sync_result.get('error') or ''}".strip()
    return "刷新失败。"


def sync_chunks(sync_result: dict[str, Any]) -> int:
    """Extract chunk count from a GBrain sync result."""
    result = sync_result.get("result")
    if isinstance(result, dict):
        for key in ("chunksCreated", "chunks_created", "chunks"):
            value = result.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return 0


def write_audit(db: Session, user_id: int, action: str, detail: str) -> None:
    """Write a simple audit log entry."""
    db.add(AuditLog(user_id=user_id, action=action, detail=detail[:1000], success=True))


def gbrain_tool_ok(result: dict[str, Any]) -> bool:
    """Check if a GBrain MCP tool call returned ok."""
    return result.get("status") == "ok" and not (isinstance(result.get("result"), dict) and result["result"].get("error"))


def gbrain_job_id(result: dict[str, Any]) -> int | None:
    """Extract a numeric job ID from a GBrain tool call result."""
    payload = result.get("result")
    if isinstance(payload, dict):
        value = payload.get("id")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def project_source_statuses(
    db: Session,
    gbrain_adapter_cls: type | None = None,
) -> list[dict[str, Any]]:
    """Build a list of project source statuses for the admin dashboard."""
    if gbrain_adapter_cls is None:
        from app.features.knowledge.gbrain import GBrainAdapter as gbrain_adapter_cls

    projects = (
        db.query(Workspace)
        .filter(Workspace.workspace_kind == "project", Workspace.is_archived == False)
        .order_by(Workspace.updated_at.desc(), Workspace.id.desc())
        .limit(100)
        .all()
    )
    if not projects:
        return []
    adapter = gbrain_adapter_cls()
    statuses: list[dict[str, Any]] = []
    for workspace in projects:
        source_status = adapter.project_source_status(workspace)
        expected = source_status.get("expected") or {}
        statuses.append(
            {
                "workspace_id": workspace.id,
                "workspace_name": workspace.name,
                "brand": workspace.brand,
                "slug": workspace.slug,
                "source_id": expected.get("source_id"),
                "source_path": expected.get("path"),
                "status": source_status.get("status"),
                "registered": bool(source_status.get("registered")),
                "path_matches": bool(source_status.get("path_matches")),
                "source": source_status.get("source") or {},
                "error": source_status.get("error"),
            }
        )
    return statuses


def graph_source_derived_path(db: Session, source_id: str, settings: Any = None) -> Path | None:
    """Resolve the derived path for a given GBrain source ID."""
    if settings is None:
        settings = load_gbrain_settings()

    source_id = str(source_id or "").strip()
    if source_id == settings.company_source_id:
        return settings.derived_path
    if source_id == CUSTOMER_INTELLIGENCE_SOURCE_ID:
        return CUSTOMER_REFERENCE_DERIVED
    if source_id.startswith("project-"):
        projects = (
            db.query(Workspace)
            .filter(Workspace.workspace_kind == "project", Workspace.is_archived == False)
            .all()
        )
        for workspace in projects:
            try:
                if project_source_id_for_workspace(workspace) == source_id:
                    return project_source_paths_for_workspace(workspace)["derived"]
            except ValueError:
                continue
    if source_id.startswith("customer-"):
        customers = (
            db.query(Workspace)
            .filter(Workspace.workspace_kind == "customer", Workspace.is_archived == False)
            .all()
        )
        for workspace in customers:
            try:
                if customer_source_id_for_workspace(workspace) == source_id:
                    return customer_source_paths_for_workspace(workspace)["derived"]
            except ValueError:
                continue
    return None
