from __future__ import annotations

import subprocess
from typing import Any
import urllib.request

from . import paths as _paths
from . import settings as _settings
from .agent_client import GBrainAgentClientMixin
from .health import GBrainHealthMixin
from .maintenance_client import GBrainMaintenanceClientMixin
from .paths import (
    GBrainSourcePaths,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    customer_source_registration_plan,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
    project_source_registration_plan,
    resolve_gbrain_source_paths,
)
from .query_client import GBrainQueryClientMixin
from .runtime import GBrainRuntime
from .runtime_facade import GBrainRuntimeMixin
from .settings import (
    DEFAULT_BACKEND_ENV_PATH as _DEFAULT_BACKEND_ENV_PATH,
    DEFAULT_COMPANY_GBRAIN_READY_PATH,
    DEFAULT_COMPANY_RUNTIME_MANIFESTS_PATH,
    DEFAULT_COMPANY_SOURCE_NAME,
    DEFAULT_COMPANY_WIKI_ROOT,
    DEFAULT_GBRAIN_CLI_WORKDIR,
    DEFAULT_GBRAIN_HOME,
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_PREPROCESSED_ROOT,
    EMBEDDING_PROVIDER_CONFIG_KEY,
    EMBEDDING_PROVIDER_ENV,
    CRM_CUSTOMER_SOURCE_ID,
    CUSTOMER_INTELLIGENCE_SOURCE_ID,
    CUSTOMER_REFERENCE_SOURCE_ID,
    GBRAIN_CITATION_FIXER_TOOLS,
    GBRAIN_CONTRADICTION_SEVERITIES,
    GBRAIN_JOB_STATUSES,
    GBRAIN_MAINTENANCE_JOB_NAMES,
    LOCAL_EMBEDDING_PROVIDERS,
    GBrainSettings,
    _DOTENV_LOADED_PATHS,
    _apply_gbrain_provider_env,
    _env_bool,
    _env_csv,
    _env_float,
    _env_int,
    _env_path,
    ensure_gbrain_dotenv_loaded as _settings_ensure_gbrain_dotenv_loaded,
    load_gbrain_settings as _settings_load_gbrain_settings,
)
from .source_manager import GBrainSourceManagerMixin
from .think_clients import GBrainThinkClientMixin
from .transport import GBrainTransport, parse_mcp_tool_payload

DEFAULT_BACKEND_ENV_PATH = _DEFAULT_BACKEND_ENV_PATH


def _sync_settings_mutables() -> None:
    _settings.DEFAULT_BACKEND_ENV_PATH = DEFAULT_BACKEND_ENV_PATH


def ensure_gbrain_dotenv_loaded(env_path: _settings.Path | None = None) -> None:
    _sync_settings_mutables()
    _settings_ensure_gbrain_dotenv_loaded(env_path)


def load_gbrain_settings() -> GBrainSettings:
    _sync_settings_mutables()
    return _settings_load_gbrain_settings()


def ensure_gbrain_environment(settings: GBrainSettings | None = None) -> dict[str, Any]:
    return _paths.ensure_gbrain_environment(settings or load_gbrain_settings())


def ensure_project_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    return _paths.ensure_project_gbrain_environment(workspace, settings or load_gbrain_settings())


def ensure_customer_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    return _paths.ensure_customer_gbrain_environment(workspace, settings or load_gbrain_settings())


class GBrainAdapter(
    GBrainHealthMixin,
    GBrainSourceManagerMixin,
    GBrainRuntimeMixin,
    GBrainThinkClientMixin,
    GBrainQueryClientMixin,
    GBrainAgentClientMixin,
    GBrainMaintenanceClientMixin,
):
    def __init__(self, settings: GBrainSettings | None = None):
        self.settings = settings or load_gbrain_settings()
        self._runtime = GBrainRuntime(
            self.settings,
            ensure_environment=ensure_gbrain_environment,
            apply_provider_env=_apply_gbrain_provider_env,
            default_ollama_base_url=DEFAULT_OLLAMA_BASE_URL,
        )
        self._transport = GBrainTransport(
            self.settings,
            apply_provider_env=_apply_gbrain_provider_env,
            default_ollama_base_url=DEFAULT_OLLAMA_BASE_URL,
        )
        self._think_oauth_tokens: dict[str, tuple[str, float]] = {}
        self._agent_oauth_access_token = ""
        self._agent_oauth_expires_at = 0.0

    def _call_mcp_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        return self._transport.call_mcp_tool(
            name,
            arguments,
            bearer_token=bearer_token,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _parse_mcp_tool_payload(raw: str) -> dict[str, Any]:
        return parse_mcp_tool_payload(raw)


def get_gbrain_health() -> dict[str, Any]:
    return GBrainAdapter().health()


def get_gbrain_admin_status() -> dict[str, Any]:
    return GBrainAdapter().admin_status()


__all__ = [
    "CRM_CUSTOMER_SOURCE_ID",
    "CUSTOMER_INTELLIGENCE_SOURCE_ID",
    "CUSTOMER_REFERENCE_SOURCE_ID",
    "DEFAULT_BACKEND_ENV_PATH",
    "DEFAULT_COMPANY_GBRAIN_READY_PATH",
    "DEFAULT_COMPANY_RUNTIME_MANIFESTS_PATH",
    "DEFAULT_COMPANY_SOURCE_NAME",
    "DEFAULT_COMPANY_WIKI_ROOT",
    "DEFAULT_GBRAIN_CLI_WORKDIR",
    "DEFAULT_GBRAIN_HOME",
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_PREPROCESSED_ROOT",
    "EMBEDDING_PROVIDER_CONFIG_KEY",
    "EMBEDDING_PROVIDER_ENV",
    "GBRAIN_CITATION_FIXER_TOOLS",
    "GBRAIN_CONTRADICTION_SEVERITIES",
    "GBRAIN_JOB_STATUSES",
    "GBRAIN_MAINTENANCE_JOB_NAMES",
    "GBrainAdapter",
    "GBrainSettings",
    "GBrainSourcePaths",
    "LOCAL_EMBEDDING_PROVIDERS",
    "_DOTENV_LOADED_PATHS",
    "_apply_gbrain_provider_env",
    "_env_bool",
    "_env_csv",
    "_env_float",
    "_env_int",
    "_env_path",
    "customer_source_id_for_workspace",
    "customer_source_paths_for_workspace",
    "customer_source_registration_plan",
    "ensure_customer_gbrain_environment",
    "ensure_gbrain_dotenv_loaded",
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
