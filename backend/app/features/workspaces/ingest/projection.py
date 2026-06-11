from __future__ import annotations

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.features.workspaces.files.signature import record_file_signature
from app.features.workspaces.ingest.run import (
    derive_workspace_ingest_run_status,
    finalize_workspace_ingest_manifest,
    overall_workspace_ingest_rag_status,
    workspace_ingest_item_rag_status,
    workspace_ingest_run_status_label,
    workspace_ingest_status_event,
)
from models.workspace import WorkspaceFile


def update_workspace_file_rag_statuses_from_manifest(
    db: Any,
    workspace: Any,
    manifest: dict,
    sync_ok: bool,
    actor_user_id: int,
) -> int:
    items_by_source = {
        str(item.get("source_file")): item
        for item in manifest.get("items", [])
        if isinstance(item, dict) and item.get("source_file")
    }
    now = datetime.now(timezone.utc)
    indexed = 0
    metas = (
        db.query(WorkspaceFile)
        .filter(WorkspaceFile.workspace_id == workspace.id, WorkspaceFile.deleted_at.is_(None))
        .all()
    )
    metas_by_path = {meta.relative_path: meta for meta in metas}
    root = Path(workspace.storage_path or "").resolve()
    for rel_path, item in items_by_source.items():
        if rel_path in metas_by_path:
            continue
        source_path = (root / rel_path).resolve()
        try:
            source_path.relative_to(root)
        except ValueError:
            continue
        if not source_path.exists() or not source_path.is_file():
            continue
        guessed_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        meta = WorkspaceFile(
            workspace_id=workspace.id,
            uploaded_by=actor_user_id,
            relative_path=rel_path,
            original_name=source_path.name,
            content_type=guessed_type[:128],
            size=source_path.stat().st_size,
            rag_status="new",
            updated_at=now,
        )
        record_file_signature(meta, source_path)
        db.add(meta)
        db.flush()
        metas_by_path[rel_path] = meta
        metas.append(meta)
    for meta in metas:
        item = items_by_source.get(meta.relative_path)
        if not item:
            continue
        meta.rag_status = workspace_ingest_item_rag_status(item, sync_ok=sync_ok)
        if str(item.get("status") or "") == "compiled":
            source_path = (root / meta.relative_path).resolve()
            if source_path.exists() and source_path.is_file():
                record_file_signature(meta, source_path)
        meta.updated_at = now
        if meta.rag_status in {"indexed", "synced"}:
            indexed += 1
    return indexed


def finalize_workspace_ingest_projection(
    db: Any,
    workspace: Any,
    manifest: dict,
    *,
    actor_user_id: int,
    run_id: str,
    source_path: str,
    recursive: bool,
    started_at: datetime,
    status_history: list[dict],
    compiled_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    skipped_files: int,
    sync_ok: bool,
    ok: bool,
    gbrain_sync_status: str | None,
    gbrain_error: str | None,
    gbrain_think_status: str | None,
) -> dict[str, Any]:
    run_status = derive_workspace_ingest_run_status(
        compiled_files=compiled_files,
        failed_files=failed_files,
        pending_extractor_capability_files=pending_extractor_capability_files,
        pending_transcription_files=pending_transcription_files,
        skipped_files=skipped_files,
        sync_ok=sync_ok,
        ok=ok,
    )
    status_history.append(workspace_ingest_status_event(run_status, workspace_ingest_run_status_label(run_status)))
    finalize_workspace_ingest_manifest(
        workspace,
        manifest,
        run_id=run_id,
        run_status=run_status,
        source_path=source_path,
        recursive=recursive,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        status_history=status_history,
        sync_ok=sync_ok,
        gbrain_sync_status=gbrain_sync_status,
        gbrain_error=gbrain_error,
        gbrain_think_status=gbrain_think_status,
    )
    indexed = update_workspace_file_rag_statuses_from_manifest(db, workspace, manifest, sync_ok, actor_user_id)
    rag_status = overall_workspace_ingest_rag_status(
        ok=ok,
        indexed_files=indexed,
        failed_files=failed_files,
        pending_extractor_capability_files=pending_extractor_capability_files,
        pending_transcription_files=pending_transcription_files,
        skipped_files=skipped_files,
    )
    return {
        "run_status": run_status,
        "indexed": indexed,
        "rag_status": rag_status,
    }
