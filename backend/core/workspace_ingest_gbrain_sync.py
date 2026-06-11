from __future__ import annotations

from typing import Any


def sync_workspace_gbrain_source(
    adapter: Any,
    workspace: Any,
    *,
    workspace_kind: str,
    compiled_files: int,
    source_id: str,
) -> dict[str, Any]:
    if compiled_files <= 0:
        return {
            "source_ok": True,
            "sync_ok": True,
            "gbrain_think_ok": True,
            "gbrain_status": "not_required_no_compiled_files",
            "gbrain_sync_status": "not_required_no_compiled_files",
            "gbrain_think_status": "not_required_no_compiled_files",
            "gbrain_error": None,
        }

    if workspace_kind == "customer":
        source_result = adapter.ensure_customer_source(workspace)
        sync_source = adapter.sync_customer_source
        sync_error = "GBrain customer source sync failed"
        clients_disabled = "customer_clients_disabled"
        think_error = "GBrain customer think OAuth client preparation failed"
    else:
        source_result = adapter.ensure_project_source(workspace)
        sync_source = adapter.sync_project_source
        sync_error = "GBrain project source sync failed"
        clients_disabled = "project_clients_disabled"
        think_error = "GBrain project think OAuth client preparation failed"

    source_ok = bool(source_result.get("ok"))
    gbrain_status = str(
        (source_result.get("source") or {}).get("status")
        or source_result.get("registration", {}).get("status")
        or ""
    )
    gbrain_sync_status = None
    gbrain_think_status = None
    gbrain_error = None
    gbrain_think_ok = True

    if source_ok:
        sync_result = sync_source(workspace, no_pull=True)
        gbrain_sync_status = str(sync_result.get("status") or "")
        if sync_result.get("status") != "ok":
            gbrain_error = str(sync_result.get("error") or sync_error)
        elif source_id:
            think_result = _prepare_think_source_client(adapter, source_id, clients_disabled, think_error)
            gbrain_think_status = think_result["gbrain_think_status"]
            gbrain_think_ok = bool(think_result["gbrain_think_ok"])
            gbrain_error = think_result["gbrain_error"]
    else:
        gbrain_error = str(source_result.get("registration", {}).get("error") or "")

    sync_ok = gbrain_sync_status == "ok"
    return {
        "source_ok": source_ok,
        "sync_ok": sync_ok,
        "gbrain_think_ok": gbrain_think_ok,
        "gbrain_status": gbrain_status,
        "gbrain_sync_status": gbrain_sync_status,
        "gbrain_think_status": gbrain_think_status,
        "gbrain_error": gbrain_error,
    }


def _prepare_think_source_client(
    adapter: Any,
    source_id: str,
    clients_disabled_status: str,
    failure_message: str,
) -> dict[str, Any]:
    settings = getattr(adapter, "settings", None)
    if settings is None or not hasattr(adapter, "ensure_think_source_client"):
        return {"gbrain_think_status": "not_checked", "gbrain_think_ok": True, "gbrain_error": None}
    if not settings.think_enabled:
        return {"gbrain_think_status": "disabled", "gbrain_think_ok": True, "gbrain_error": None}
    if not settings.think_source_scope_verified:
        return {"gbrain_think_status": "source_scope_unverified", "gbrain_think_ok": True, "gbrain_error": None}
    if not settings.think_project_clients_enabled:
        return {"gbrain_think_status": clients_disabled_status, "gbrain_think_ok": True, "gbrain_error": None}

    think_client_result = adapter.ensure_think_source_client(source_id)
    gbrain_think_status = str(think_client_result.get("status") or "")
    if think_client_result.get("ok"):
        return {"gbrain_think_status": gbrain_think_status, "gbrain_think_ok": True, "gbrain_error": None}
    return {
        "gbrain_think_status": gbrain_think_status,
        "gbrain_think_ok": False,
        "gbrain_error": str(think_client_result.get("error") or failure_message),
    }
