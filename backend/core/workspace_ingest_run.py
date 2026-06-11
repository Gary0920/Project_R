from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.gbrain_customer_sources import CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME
from core.gbrain_project_ingest import PROJECT_INGEST_MANIFEST_NAME
from core.time_utils import serialize_datetime_utc


WORKSPACE_INGEST_RUN_STATUSES = {
    "queued",
    "preprocessing",
    "gbrain_ready",
    "sync_pending",
    "synced",
    "failed",
    "pending_capability",
    "ignored",
}


def workspace_ingest_status_event(status: str, message: str = "", at: datetime | None = None) -> dict:
    normalized = status if status in WORKSPACE_INGEST_RUN_STATUSES else "failed"
    return {
        "status": normalized,
        "message": message,
        "at": serialize_datetime_utc(at or datetime.now(timezone.utc)),
    }


def workspace_ingest_run_payload(
    *,
    run_id: str,
    status: str,
    workspace: Any | None,
    source_id: str | None,
    source_path: str,
    recursive: bool,
    started_at: datetime | None,
    finished_at: datetime | None,
    error: str | None,
    status_history: list[dict],
) -> dict:
    normalized = status if status in WORKSPACE_INGEST_RUN_STATUSES else "failed"
    return {
        "run_id": run_id,
        "status": normalized,
        "workspace_id": getattr(workspace, "id", None),
        "workspace_kind": getattr(workspace, "workspace_kind", None),
        "workspace_name": getattr(workspace, "name", ""),
        "source_id": source_id,
        "source_path": source_path,
        "recursive": recursive,
        "started_at": serialize_datetime_utc(started_at) if started_at else None,
        "finished_at": serialize_datetime_utc(finished_at) if finished_at else None,
        "error": error or None,
        "status_history": status_history,
    }


def derive_workspace_ingest_run_status(
    *,
    compiled_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    skipped_files: int,
    sync_ok: bool,
    ok: bool,
) -> str:
    if failed_files > 0:
        return "failed"
    if compiled_files > 0 and not sync_ok:
        return "sync_pending"
    if compiled_files > 0 and ok:
        return "synced"
    if pending_extractor_capability_files > 0 or pending_transcription_files > 0:
        return "pending_capability"
    if not ok:
        return "failed"
    if skipped_files > 0:
        return "ignored"
    return "ignored"


def workspace_ingest_run_status_label(status: str) -> str:
    return {
        "queued": "任务已排队",
        "preprocessing": "正在预处理源文件",
        "gbrain_ready": "已生成 GBrain-ready Markdown",
        "sync_pending": "GBrain 同步待处理",
        "synced": "GBrain 同步完成",
        "failed": "录入失败",
        "pending_capability": "等待预处理能力补齐",
        "ignored": "已忽略或无可处理文件",
    }.get(status, status)


def workspace_ingest_manifest_counts(manifest: dict | None) -> dict[str, int | str]:
    manifest = manifest if isinstance(manifest, dict) else {}
    summary = manifest.get("summary") if isinstance(manifest.get("summary"), dict) else {}
    return {
        "source_id": str(manifest.get("source_id") or ""),
        "compiled_files": int(summary.get("compiled", 0) or 0),
        "pending_extractor_capability_files": int(summary.get("pending_extractor_capability", 0) or 0),
        "pending_transcription_files": int(summary.get("pending_transcription", 0) or 0),
        "skipped_files": int(summary.get("skipped", 0) or 0),
        "failed_files": int(summary.get("failed", 0) or 0),
    }


def workspace_ingest_item_run_status(item: dict, *, sync_ok: bool) -> str:
    status = str(item.get("status") or "")
    if status == "compiled":
        return "synced" if sync_ok else "sync_pending"
    if status in {"pending_extractor_capability", "pending_transcription"} or status.startswith("pending_"):
        return "pending_capability"
    if status == "failed":
        return "failed"
    if status in {"skipped", "ignored"}:
        return "ignored"
    return "failed" if status else "ignored"


def workspace_ingest_item_rag_status(item: dict, *, sync_ok: bool) -> str:
    status = str(item.get("status") or "")
    if status == "compiled":
        return "synced" if sync_ok else "sync_pending"
    if status == "pending_extractor_capability":
        return "pending_extractor_capability"
    if status == "pending_transcription":
        return "pending_transcription"
    if status == "failed":
        return "failed"
    if status == "skipped":
        return "skipped"
    return "pending"


def workspace_ingest_manifest_name(workspace: Any) -> str:
    if getattr(workspace, "workspace_kind", None) == "customer":
        return CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME
    return PROJECT_INGEST_MANIFEST_NAME


def finalize_workspace_ingest_manifest(
    workspace: Any,
    manifest: dict | None,
    *,
    run_id: str,
    run_status: str,
    source_path: str,
    recursive: bool,
    started_at: datetime,
    finished_at: datetime,
    status_history: list[dict],
    sync_ok: bool,
    gbrain_sync_status: str | None,
    gbrain_error: str | None,
    gbrain_think_status: str | None,
) -> None:
    if not isinstance(manifest, dict):
        return
    source_id = str(manifest.get("source_id") or "")
    run_payload = workspace_ingest_run_payload(
        run_id=run_id,
        status=run_status,
        workspace=workspace,
        source_id=source_id,
        source_path=source_path,
        recursive=recursive,
        started_at=started_at,
        finished_at=finished_at,
        error=gbrain_error,
        status_history=status_history,
    )
    manifest["run_id"] = run_id
    manifest["run_status"] = run_status
    manifest["run"] = run_payload
    manifest["status_history"] = status_history
    manifest["sync"] = {
        "ok": bool(sync_ok),
        "status": gbrain_sync_status,
        "error": gbrain_error,
        "think_status": gbrain_think_status,
    }
    for item in manifest.get("items") or []:
        if not isinstance(item, dict):
            continue
        item["preprocess_status"] = str(item.get("status") or "")
        item["source_hash"] = item.get("source_hash") or item.get("source_sha256")
        if item.get("target_file"):
            item["gbrain_ready_file"] = item.get("gbrain_ready_file") or item["target_file"]
            item["output_file"] = item.get("output_file") or item["target_file"]
        item_run_status = workspace_ingest_item_run_status(item, sync_ok=sync_ok)
        item["run_status"] = item_run_status
        item["sync_status"] = item_run_status if item_run_status in {"synced", "sync_pending"} else "not_applicable"
        item["model_profile"] = item.get("model_profile") or item.get("extractor_profile") or "not_applicable"
        item["skill_version"] = (
            item.get("skill_version")
            or item.get("preprocessor_version")
            or item.get("extractor_profile")
            or item.get("content_kind")
            or "workspace-ingest-v1"
        )
        item["prompt_version"] = item.get("prompt_version") or item.get("extractor_prompt_version") or "not_applicable"

    manifests_path = manifest.get("manifests_path")
    runs_path = manifest.get("runs_path")
    try:
        run_path = None
        if runs_path:
            run_path = Path(str(runs_path)) / f"{run_id}.json"
            manifest["run_manifest_path"] = str(run_path.resolve())
        if manifests_path:
            path = Path(str(manifests_path)) / workspace_ingest_manifest_name(workspace)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if run_path is not None:
            run_path.parent.mkdir(parents=True, exist_ok=True)
            run_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        manifest["run_manifest_write_error"] = str(exc)


def workspace_ingest_result_payload(payload: dict) -> dict:
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    return {
        "workspace_id": payload.get("workspace_id"),
        "indexed_files": payload.get("indexed_files", 0),
        "compiled_files": payload.get("compiled_files", 0),
        "pending_extractor_capability_files": payload.get("pending_extractor_capability_files", 0),
        "pending_transcription_files": payload.get("pending_transcription_files", 0),
        "failed_files": payload.get("failed_files", 0),
        "gbrain_source_id": payload.get("gbrain_source_id"),
        "gbrain_sync_status": payload.get("gbrain_sync_status"),
        "rag_status": payload.get("rag_status"),
        "run_id": payload.get("run_id"),
        "run_status": payload.get("run_status"),
        "run": manifest.get("run"),
        "manifest_summary": manifest.get("summary"),
    }


def workspace_ingest_summary_text(payload: dict) -> str:
    run_status = payload.get("run_status") or payload.get("rag_status") or "unknown"
    return (
        f"状态 {run_status}，"
        f"已入库 {payload.get('indexed_files', 0)} 个，"
        f"已编译 {payload.get('compiled_files', 0)} 个，"
        f"待能力补齐 {payload.get('pending_extractor_capability_files', 0)} 个，"
        f"待转写 {payload.get('pending_transcription_files', 0)} 个，"
        f"失败 {payload.get('failed_files', 0)} 个"
    )


def overall_workspace_ingest_rag_status(
    *,
    ok: bool,
    indexed_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    skipped_files: int,
) -> str:
    if failed_files > 0:
        return "failed"
    if not ok:
        return "pending"
    if indexed_files > 0:
        return "indexed"
    if pending_transcription_files > 0:
        return "pending_transcription"
    if pending_extractor_capability_files > 0:
        return "pending_extractor_capability"
    if skipped_files > 0:
        return "skipped"
    return "indexed"
