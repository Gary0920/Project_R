from app.features.knowledge import gbrain
from app.features.knowledge.gbrain import GBrainAdapter
import app.features.knowledge.gbrain.adapter as adapter_module


def test_gbrain_package_reexports_adapter_public_api():
    expected_exports = [
        "CRM_CUSTOMER_SOURCE_ID",
        "CUSTOMER_INTELLIGENCE_SOURCE_ID",
        "GBrainAdapter",
        "GBrainSettings",
        "GBrainSourcePaths",
        "customer_source_id_for_workspace",
        "customer_source_paths_for_workspace",
        "customer_source_registration_plan",
        "ensure_customer_gbrain_environment",
        "ensure_gbrain_environment",
        "ensure_project_gbrain_environment",
        "get_gbrain_admin_status",
        "get_gbrain_health",
        "load_gbrain_settings",
        "project_source_id_for_workspace",
        "project_source_paths_for_workspace",
        "project_source_registration_plan",
        "resolve_gbrain_source_paths",
    ]

    for name in expected_exports:
        assert getattr(gbrain, name) is getattr(adapter_module, name)


def test_gbrain_adapter_facade_keeps_existing_method_surface():
    expected_methods = [
        "admin_status",
        "agent_status",
        "cancel_job",
        "company_source_status",
        "customer_source_registration_plan",
        "customer_source_status",
        "doctor",
        "ensure_customer_source",
        "ensure_project_source",
        "ensure_source",
        "ensure_think_source_client",
        "find_contradictions",
        "get_job",
        "get_job_progress",
        "get_page",
        "graph_context",
        "health",
        "latest_ingest_manifest",
        "list_jobs",
        "list_sources",
        "maintenance_check",
        "maintenance_status",
        "project_source_registration_plan",
        "project_source_status",
        "query",
        "register_customer_source",
        "register_project_source",
        "register_source",
        "register_think_source_client",
        "restart_http_service",
        "schema_context",
        "service_process_status",
        "source_registration_plan",
        "source_status",
        "start_http_service",
        "status_snapshot",
        "stop_http_service",
        "submit_agent",
        "submit_citation_fixer",
        "submit_job",
        "sync_customer_source",
        "sync_project_source",
        "sync_registered_source",
        "sync_source",
        "think",
    ]

    for method_name in expected_methods:
        assert callable(getattr(GBrainAdapter, method_name))
