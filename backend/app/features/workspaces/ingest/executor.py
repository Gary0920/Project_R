from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.features.workspaces.ingest.gbrain_sync import sync_workspace_gbrain_source
from app.features.workspaces.ingest.projection import finalize_workspace_ingest_projection
from app.features.workspaces.ingest.run import workspace_ingest_manifest_counts, workspace_ingest_status_event


WorkspaceCompiler = Callable[[Any, str, bool], dict]
AdapterFactory = Callable[[], Any]


def execute_workspace_ingest_core(
    db: Any,
    workspace: Any,
    actor_user_id: int,
    *,
    source_path: str,
    recursive: bool,
    run_id: str,
    started_at: datetime,
    status_history: list[dict],
    compile_project: WorkspaceCompiler,
    compile_customer: WorkspaceCompiler,
    adapter_factory: AdapterFactory,
) -> dict:
    workspace_kind = str(getattr(workspace, "workspace_kind", "") or "")
    pending_reviews_created = 0

    if workspace_kind not in {"project", "customer"}:
        gbrain_error = "该工作区类型不进入 GBrain 知识库"
        run_status = "failed"
        status_history.append(workspace_ingest_status_event(run_status, gbrain_error))
        return {
            "ok": False,
            "workspace_id": workspace.id,
            "indexed_files": 0,
            "rag_status": "skipped",
            "compiled_files": 0,
            "pending_extractor_capability_files": 0,
            "pending_transcription_files": 0,
            "skipped_files": 0,
            "failed_files": 0,
            "pending_reviews_created": pending_reviews_created,
            "ingest_path": source_path,
            "ingest_recursive": recursive,
            "gbrain_source_id": None,
            "gbrain_status": "not_applicable_private_workspace",
            "gbrain_sync_status": "not_applicable_private_workspace",
            "gbrain_think_status": None,
            "gbrain_error": gbrain_error,
            "run_status": run_status,
            "run_id": run_id,
            "run": None,
            "manifest": None,
        }

    manifest = (
        compile_customer(workspace, source_path, recursive)
        if workspace_kind == "customer"
        else compile_project(workspace, source_path, recursive)
    )
    counts = workspace_ingest_manifest_counts(manifest)
    compiled_files = int(counts["compiled_files"])
    pending_extractor_capability_files = int(counts["pending_extractor_capability_files"])
    pending_transcription_files = int(counts["pending_transcription_files"])
    skipped_files = int(counts["skipped_files"])
    failed_files = int(counts["failed_files"])
    gbrain_source_id = str(counts["source_id"])
    if compiled_files > 0:
        status_history.append(workspace_ingest_status_event("gbrain_ready", "已生成 GBrain-ready Markdown"))

    sync_result = sync_workspace_gbrain_source(
        adapter_factory(),
        workspace,
        workspace_kind=workspace_kind,
        compiled_files=compiled_files,
        source_id=gbrain_source_id,
    )
    source_ok = bool(sync_result["source_ok"])
    sync_ok = bool(sync_result["sync_ok"])
    gbrain_think_ok = bool(sync_result["gbrain_think_ok"])
    gbrain_status = sync_result["gbrain_status"]
    gbrain_sync_status = sync_result["gbrain_sync_status"]
    gbrain_think_status = sync_result["gbrain_think_status"]
    gbrain_error = sync_result["gbrain_error"]
    ok = bool(failed_files == 0 and source_ok and sync_ok and gbrain_think_ok)

    projection = finalize_workspace_ingest_projection(
        db,
        workspace,
        manifest,
        actor_user_id=actor_user_id,
        run_id=run_id,
        source_path=source_path,
        recursive=recursive,
        started_at=started_at,
        status_history=status_history,
        compiled_files=compiled_files,
        failed_files=failed_files,
        pending_extractor_capability_files=pending_extractor_capability_files,
        pending_transcription_files=pending_transcription_files,
        skipped_files=skipped_files,
        sync_ok=sync_ok,
        ok=ok,
        gbrain_sync_status=gbrain_sync_status,
        gbrain_error=gbrain_error,
        gbrain_think_status=gbrain_think_status,
    )
    run_status = str(projection["run_status"])
    indexed = int(projection["indexed"])
    rag_status = str(projection["rag_status"])

    return {
        "ok": ok,
        "workspace_id": workspace.id,
        "indexed_files": indexed,
        "rag_status": rag_status,
        "compiled_files": compiled_files,
        "pending_extractor_capability_files": pending_extractor_capability_files,
        "pending_transcription_files": pending_transcription_files,
        "skipped_files": skipped_files,
        "failed_files": failed_files,
        "pending_reviews_created": pending_reviews_created,
        "ingest_path": source_path,
        "ingest_recursive": recursive,
        "gbrain_source_id": gbrain_source_id,
        "gbrain_status": gbrain_status,
        "gbrain_sync_status": gbrain_sync_status,
        "gbrain_think_status": gbrain_think_status,
        "gbrain_error": gbrain_error,
        "run_status": run_status,
        "run_id": run_id,
        "run": manifest.get("run") if isinstance(manifest, dict) else None,
        "manifest": manifest,
    }
