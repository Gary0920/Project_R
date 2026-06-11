from __future__ import annotations

from typing import Any


def workspace_ingest_audit_fields(
    payload: dict[str, Any],
    *,
    source_path: str,
    recursive: bool,
) -> dict[str, Any]:
    return {
        "indexed_files": payload.get("indexed_files", 0),
        "gbrain_source_id": payload.get("gbrain_source_id"),
        "gbrain_status": payload.get("gbrain_status"),
        "gbrain_sync_status": payload.get("gbrain_sync_status"),
        "gbrain_think_status": payload.get("gbrain_think_status"),
        "failed_files": payload.get("failed_files", 0),
        "pending_extractor_capability_files": payload.get("pending_extractor_capability_files", 0),
        "pending_transcription_files": payload.get("pending_transcription_files", 0),
        "pending_reviews_created": payload.get("pending_reviews_created", 0),
        "ingest_path": source_path,
        "ingest_recursive": recursive,
    }
