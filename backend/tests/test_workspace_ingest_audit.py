from core.workspace_ingest_audit import workspace_ingest_audit_fields


def test_workspace_ingest_audit_fields_projects_payload_and_request_scope():
    fields = workspace_ingest_audit_fields(
        {
            "indexed_files": 2,
            "failed_files": 1,
            "pending_extractor_capability_files": 3,
            "pending_transcription_files": 4,
            "pending_reviews_created": 5,
            "gbrain_source_id": "project-bfi-7",
            "gbrain_status": "ready",
            "gbrain_sync_status": "synced",
            "gbrain_think_status": "ready",
        },
        source_path="01-资料",
        recursive=False,
    )

    assert fields == {
        "indexed_files": 2,
        "failed_files": 1,
        "pending_extractor_capability_files": 3,
        "pending_transcription_files": 4,
        "pending_reviews_created": 5,
        "gbrain_source_id": "project-bfi-7",
        "gbrain_status": "ready",
        "gbrain_sync_status": "synced",
        "gbrain_think_status": "ready",
        "ingest_path": "01-资料",
        "ingest_recursive": False,
    }


def test_workspace_ingest_audit_fields_defaults_counts():
    fields = workspace_ingest_audit_fields({}, source_path="", recursive=True)

    assert fields["indexed_files"] == 0
    assert fields["failed_files"] == 0
    assert fields["pending_extractor_capability_files"] == 0
    assert fields["pending_transcription_files"] == 0
    assert fields["pending_reviews_created"] == 0
    assert fields["ingest_path"] == ""
    assert fields["ingest_recursive"] is True
