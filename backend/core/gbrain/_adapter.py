from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request
import urllib.request

BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_COMPANY_WIKI_ROOT = BASE_DIR / "workspace_data" / "global" / "company-wiki"
DEFAULT_GBRAIN_HOME = BASE_DIR / "workspace_data" / "_gbrain"
DEFAULT_PREPROCESSED_ROOT = BASE_DIR / "workspace_data" / "_preprocessed"
DEFAULT_COMPANY_GBRAIN_READY_PATH = DEFAULT_PREPROCESSED_ROOT / "company" / "company-wiki" / "gbrain-ready"
DEFAULT_COMPANY_RUNTIME_MANIFESTS_PATH = DEFAULT_GBRAIN_HOME / "manifests"
DEFAULT_GBRAIN_CLI_WORKDIR = PROJECT_ROOT / "reference" / "gbrain-master"
DEFAULT_COMPANY_SOURCE_NAME = "Project_R Company Wiki"
PROJECT_SOURCE_ID_MAX_LENGTH = 32
PROJECT_SOURCE_ID_PREFIX = "project"
CUSTOMER_SOURCE_ID_PREFIX = "customer"
CRM_CUSTOMER_SOURCE_ID = "customer-crm"
CUSTOMER_INTELLIGENCE_SOURCE_ID = CRM_CUSTOMER_SOURCE_ID
CRM_CUSTOMER_SLUG = "CRM"
# Legacy MVP source id. Keep it as an explicit cleanup target; product paths
# and customer workspace queries use CUSTOMER_INTELLIGENCE_SOURCE_ID.
CUSTOMER_REFERENCE_SOURCE_ID = "customer-reference"
EMBEDDING_PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "zeroentropyai": "ZEROENTROPY_API_KEY",
    "voyage": "VOYAGE_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "zhipu": "ZHIPUAI_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "together": "TOGETHER_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "google": "GOOGLE_GENERATIVE_AI_API_KEY",
    "azure-openai": "AZURE_OPENAI_API_KEY",
}
EMBEDDING_PROVIDER_CONFIG_KEY = {
    "openai": "openai_api_key",
    "zeroentropyai": "zeroentropy_api_key",
    "voyage": "voyage_api_key",
    "minimax": "minimax_api_key",
    "zhipu": "zhipu_api_key",
    "dashscope": "dashscope_api_key",
    "together": "together_api_key",
    "openrouter": "openrouter_api_key",
    "google": "google_api_key",
    "azure-openai": "azure_openai_api_key",
}
LOCAL_EMBEDDING_PROVIDERS = {"ollama", "llama-server", "litellm", "lmstudio"}
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
GBRAIN_MAINTENANCE_JOB_NAMES = {
    "sync",
    "embed",
    "lint",
    "import",
    "extract",
    "backlinks",
    "autopilot-cycle",
}
GBRAIN_JOB_STATUSES = {"waiting", "active", "completed", "failed", "delayed", "dead", "cancelled"}
GBRAIN_CITATION_FIXER_TOOLS = ("search", "get_page", "put_page", "list_pages")
GBRAIN_CONTRADICTION_SEVERITIES = {"low", "medium", "high"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _first_csv_value(value: str | None) -> str:
    if not value:
        return ""
    return next((item.strip() for item in value.split(",") if item.strip()), "")


def _apply_gbrain_provider_env(env: dict[str, str]) -> dict[str, str]:
    if not env.get("DEEPSEEK_API_KEY"):
        deepseek_key = _first_csv_value(env.get("DEEPSEEK_API_KEYS"))
        if deepseek_key:
            env["DEEPSEEK_API_KEY"] = deepseek_key
    return env


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    path = Path(raw)
    if path.is_absolute():
        return path
    return (BASE_DIR / path).resolve()


@dataclass(frozen=True)
class GBrainSettings:
    enabled: bool
    base_url: str
    service_bearer_token: str = field(default="", repr=False)
    timeout_seconds: float = 5.0
    home_path: Path = DEFAULT_GBRAIN_HOME
    company_source_id: str = "company-wiki"
    company_source_name: str = DEFAULT_COMPANY_SOURCE_NAME
    raw_path: Path = DEFAULT_COMPANY_WIKI_ROOT / "raw"
    derived_path: Path = DEFAULT_COMPANY_GBRAIN_READY_PATH
    manifests_path: Path = DEFAULT_COMPANY_RUNTIME_MANIFESTS_PATH
    local_git_enabled: bool = True
    cli_workdir: Path = DEFAULT_GBRAIN_CLI_WORKDIR
    bun_executable: str = "bun"
    http_bind: str = "127.0.0.1"
    think_enabled: bool = False
    think_source_scope_verified: bool = False
    think_oauth_client_id: str = ""
    think_oauth_client_secret: str = field(default="", repr=False)
    think_oauth_scope: str = "read write"
    think_oauth_token_auth_method: str = "client_secret_post"
    think_allowed_sources: tuple[str, ...] = field(default_factory=tuple)
    think_project_clients_enabled: bool = True
    think_model: str = ""
    think_rounds: int = 1
    think_timeout_seconds: float = 90.0
    agent_enabled: bool = False
    agent_oauth_client_id: str = ""
    agent_oauth_client_secret: str = field(default="", repr=False)
    agent_oauth_scope: str = "agent"
    agent_oauth_token_auth_method: str = "client_secret_post"
    agent_model: str = ""
    agent_gateway_loop_verified: bool = False
    agent_binding_submit_verified: bool = False
    agent_inline_execution_verified: bool = False
    agent_execution_verified: bool = False
    agent_timeout_seconds: float = 120.0
    citation_fixer_tools: tuple[str, ...] = GBRAIN_CITATION_FIXER_TOOLS

    @property
    def service_configured(self) -> bool:
        return bool(self.base_url.strip())

    @property
    def http_port(self) -> int:
        parsed = urlparse(self.base_url)
        if parsed.port:
            return parsed.port
        if parsed.scheme == "https":
            return 443
        return 80

    @property
    def service_record_path(self) -> Path:
        return self.manifests_path / "gbrain-http-service.json"

    @property
    def service_log_path(self) -> Path:
        return self.manifests_path / "gbrain-http-service.log"

    @property
    def think_source_clients_path(self) -> Path:
        return self.manifests_path / "gbrain-think-source-clients.json"


@dataclass(frozen=True)
class GBrainSourcePaths:
    source_scope: str
    source_id: str
    raw: Path
    gbrain_ready: Path
    runs: Path
    manifests: Path
    preprocessed_root: Path
    legacy_derived: Path | None = None
    legacy_manifests: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_scope": self.source_scope,
            "source_id": self.source_id,
            "raw": self.raw,
            "gbrain_ready": self.gbrain_ready,
            "runs": self.runs,
            "manifests": self.manifests,
            "preprocessed_root": self.preprocessed_root,
        }
        if self.legacy_derived is not None:
            payload["legacy_derived"] = self.legacy_derived
        if self.legacy_manifests is not None:
            payload["legacy_manifests"] = self.legacy_manifests
        return payload


def load_gbrain_settings() -> GBrainSettings:
    return GBrainSettings(
        enabled=_env_bool("GBRAIN_ENABLED", True),
        base_url=os.getenv("GBRAIN_BASE_URL", "http://127.0.0.1:3131").strip(),
        service_bearer_token=os.getenv("GBRAIN_SERVICE_BEARER_TOKEN", "").strip(),
        timeout_seconds=_env_float("GBRAIN_TIMEOUT_SECONDS", 5.0),
        home_path=_env_path("GBRAIN_HOME", DEFAULT_GBRAIN_HOME),
        company_source_id=os.getenv("GBRAIN_COMPANY_SOURCE_ID", "company-wiki").strip() or "company-wiki",
        company_source_name=os.getenv("GBRAIN_COMPANY_SOURCE_NAME", DEFAULT_COMPANY_SOURCE_NAME).strip()
        or DEFAULT_COMPANY_SOURCE_NAME,
        raw_path=_env_path("GBRAIN_COMPANY_RAW_PATH", DEFAULT_COMPANY_WIKI_ROOT / "raw"),
        derived_path=_env_path("GBRAIN_COMPANY_DERIVED_PATH", DEFAULT_COMPANY_GBRAIN_READY_PATH),
        manifests_path=_env_path("GBRAIN_COMPANY_MANIFESTS_PATH", DEFAULT_COMPANY_RUNTIME_MANIFESTS_PATH),
        local_git_enabled=_env_bool("GBRAIN_LOCAL_GIT_ENABLED", True),
        cli_workdir=_env_path("GBRAIN_CLI_WORKDIR", DEFAULT_GBRAIN_CLI_WORKDIR),
        bun_executable=os.getenv("GBRAIN_BUN_BIN", "bun").strip() or "bun",
        http_bind=os.getenv("GBRAIN_HTTP_BIND", "127.0.0.1").strip() or "127.0.0.1",
        think_enabled=_env_bool("GBRAIN_THINK_ENABLED", False),
        think_source_scope_verified=_env_bool("GBRAIN_THINK_SOURCE_SCOPE_VERIFIED", False),
        think_oauth_client_id=os.getenv("GBRAIN_THINK_OAUTH_CLIENT_ID", "").strip(),
        think_oauth_client_secret=os.getenv("GBRAIN_THINK_OAUTH_CLIENT_SECRET", "").strip(),
        think_oauth_scope=os.getenv("GBRAIN_THINK_OAUTH_SCOPE", "read write").strip() or "read write",
        think_oauth_token_auth_method=os.getenv(
            "GBRAIN_THINK_OAUTH_TOKEN_AUTH_METHOD",
            "client_secret_post",
        ).strip()
        or "client_secret_post",
        think_allowed_sources=_env_csv("GBRAIN_THINK_ALLOWED_SOURCES"),
        think_project_clients_enabled=_env_bool("GBRAIN_THINK_PROJECT_CLIENTS_ENABLED", True),
        think_model=os.getenv("GBRAIN_THINK_MODEL", "").strip(),
        think_rounds=max(1, _env_int("GBRAIN_THINK_ROUNDS", 1)),
        think_timeout_seconds=max(5.0, _env_float("GBRAIN_THINK_TIMEOUT_SECONDS", 90.0)),
        agent_enabled=_env_bool("GBRAIN_AGENT_ENABLED", False),
        agent_oauth_client_id=os.getenv("GBRAIN_AGENT_OAUTH_CLIENT_ID", "").strip(),
        agent_oauth_client_secret=os.getenv("GBRAIN_AGENT_OAUTH_CLIENT_SECRET", "").strip(),
        agent_oauth_scope=os.getenv("GBRAIN_AGENT_OAUTH_SCOPE", "agent").strip() or "agent",
        agent_oauth_token_auth_method=os.getenv(
            "GBRAIN_AGENT_OAUTH_TOKEN_AUTH_METHOD",
            "client_secret_post",
        ).strip()
        or "client_secret_post",
        agent_model=os.getenv("GBRAIN_AGENT_MODEL", "").strip(),
        agent_gateway_loop_verified=_env_bool("GBRAIN_AGENT_GATEWAY_LOOP_VERIFIED", False),
        agent_binding_submit_verified=_env_bool("GBRAIN_AGENT_BINDING_SUBMIT_VERIFIED", False),
        agent_inline_execution_verified=_env_bool("GBRAIN_AGENT_INLINE_EXECUTION_VERIFIED", False),
        agent_execution_verified=_env_bool("GBRAIN_AGENT_EXECUTION_VERIFIED", False),
        agent_timeout_seconds=max(5.0, _env_float("GBRAIN_AGENT_TIMEOUT_SECONDS", 120.0)),
        citation_fixer_tools=_env_csv("GBRAIN_CITATION_FIXER_TOOLS") or GBRAIN_CITATION_FIXER_TOOLS,
    )


def _path_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "writable": path.exists() and os.access(path, os.W_OK),
    }


def _ensure_directory(path: Path, errors: list[str]) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"{path}: {exc}")


def _ensure_local_git_repo(path: Path, enabled: bool) -> dict[str, Any]:
    git_dir = path / ".git"
    result: dict[str, Any] = {
        "enabled": enabled,
        "initialized": git_dir.exists(),
        "path": str(git_dir.resolve()),
        "error": None,
    }
    if not enabled:
        return result
    if git_dir.exists():
        return result
    if not path.exists():
        result["error"] = f"derived path does not exist: {path}"
        return result

    try:
        completed = subprocess.run(
            ["git", "init"],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = str(exc)
        return result

    result["initialized"] = git_dir.exists()
    if completed.returncode != 0:
        result["error"] = (completed.stderr or completed.stdout or "git init failed").strip()
    return result


def ensure_gbrain_environment(settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    source_paths = resolve_gbrain_source_paths("company", settings=settings)
    errors: list[str] = []

    for path in (
        source_paths.raw,
        source_paths.gbrain_ready,
        source_paths.runs,
        source_paths.manifests,
        settings.manifests_path,
    ):
        _ensure_directory(path, errors)

    git_status = _ensure_local_git_repo(source_paths.gbrain_ready, settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")

    return {
        "ok": not errors,
        "source_id": settings.company_source_id,
        "gbrain_home": _path_status(settings.home_path),
        "gbrain_config_dir": _path_status(settings.home_path / ".gbrain"),
        "paths": {
            "raw": _path_status(source_paths.raw),
            "gbrain_ready": _path_status(source_paths.gbrain_ready),
            "runs": _path_status(source_paths.runs),
            "manifests": _path_status(source_paths.manifests),
            "legacy_derived": _path_status(source_paths.legacy_derived or settings.derived_path),
            "legacy_manifests": _path_status(source_paths.legacy_manifests or settings.manifests_path),
            # Compatibility key for older admin UI code; now points at gbrain-ready.
            "derived": _path_status(source_paths.gbrain_ready),
            "migration_status": _gbrain_path_migration_status(source_paths.gbrain_ready, source_paths.legacy_derived),
        },
        "local_git": git_status,
        "errors": errors,
    }


def project_source_id_for_workspace(workspace: Any) -> str:
    workspace_id = getattr(workspace, "id", None)
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError("project workspace must be persisted before creating a GBrain source id")
    brand = _source_id_segment(str(getattr(workspace, "brand", "") or "project"), fallback="project")
    suffix = str(workspace_id)
    max_brand_len = PROJECT_SOURCE_ID_MAX_LENGTH - len(PROJECT_SOURCE_ID_PREFIX) - len(suffix) - 2
    brand = brand[: max(1, max_brand_len)].strip("-") or "project"
    return f"{PROJECT_SOURCE_ID_PREFIX}-{brand}-{suffix}"


def customer_source_id_for_workspace(workspace: Any) -> str:
    slug_value = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "").strip()
    if slug_value.casefold() == CRM_CUSTOMER_SLUG.casefold():
        return CRM_CUSTOMER_SOURCE_ID
    workspace_id = getattr(workspace, "id", None)
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError("customer workspace must be persisted before creating a GBrain source id")
    slug = _source_id_segment(str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer"), fallback="customer")
    suffix = str(workspace_id)
    max_slug_len = PROJECT_SOURCE_ID_MAX_LENGTH - len(CUSTOMER_SOURCE_ID_PREFIX) - len(suffix) - 2
    slug = slug[: max(1, max_slug_len)].strip("-") or "customer"
    return f"{CUSTOMER_SOURCE_ID_PREFIX}-{slug}-{suffix}"


def resolve_gbrain_source_paths(
    source_scope: str,
    *,
    workspace: Any | None = None,
    settings: GBrainSettings | None = None,
) -> GBrainSourcePaths:
    scope = source_scope.strip().lower().replace("_", "-")
    preprocessed_root = _env_path("GBRAIN_PREPROCESSED_ROOT", DEFAULT_PREPROCESSED_ROOT)
    if scope in {"company", "company-wiki", "global"}:
        settings = settings or load_gbrain_settings()
        root = _env_path(
            "GBRAIN_COMPANY_PREPROCESSED_ROOT",
            preprocessed_root / "company" / settings.company_source_id,
        )
        return GBrainSourcePaths(
            source_scope="company",
            source_id=settings.company_source_id,
            raw=settings.raw_path.resolve(),
            gbrain_ready=_env_path("GBRAIN_COMPANY_GBRAIN_READY_PATH", root / "gbrain-ready"),
            runs=_env_path("GBRAIN_COMPANY_PREPROCESS_RUNS_PATH", root / "runs"),
            manifests=_env_path("GBRAIN_COMPANY_PREPROCESS_MANIFESTS_PATH", root / "manifests"),
            preprocessed_root=root.resolve(),
            legacy_derived=(settings.raw_path.parent / "derived").resolve(),
            legacy_manifests=(settings.raw_path.parent / "manifests").resolve(),
        )
    if workspace is None:
        raise ValueError(f"{scope or 'source'} scope requires a workspace")
    if scope == "project":
        raw_root = _workspace_raw_root(workspace, "project")
        source_id = project_source_id_for_workspace(workspace)
        brand = _path_segment(str(getattr(workspace, "brand", "") or "BFI"), fallback="BFI").upper()
        slug = _path_segment(str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "project"), fallback="project")
        root = preprocessed_root / "project" / brand / f"{getattr(workspace, 'id')}-{slug}"
        return GBrainSourcePaths(
            source_scope="project",
            source_id=source_id,
            raw=raw_root,
            gbrain_ready=(root / "gbrain-ready").resolve(),
            runs=(root / "runs").resolve(),
            manifests=(root / "manifests").resolve(),
            preprocessed_root=root.resolve(),
            legacy_derived=(raw_root / "derived").resolve(),
            legacy_manifests=(raw_root / "manifests").resolve(),
        )
    if scope == "customer":
        raw_root = _workspace_raw_root(workspace, "customer")
        source_id = customer_source_id_for_workspace(workspace)
        slug_value = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "").strip()
        if slug_value.casefold() == CRM_CUSTOMER_SLUG.casefold():
            root = preprocessed_root / "customer" / "crm"
            return GBrainSourcePaths(
                source_scope="customer",
                source_id=source_id,
                raw=raw_root,
                gbrain_ready=(root / "gbrain-ready").resolve(),
                runs=(root / "runs").resolve(),
                manifests=(root / "manifests").resolve(),
                preprocessed_root=root.resolve(),
                legacy_derived=(raw_root / "derived").resolve(),
                legacy_manifests=(raw_root / "manifests").resolve(),
            )
        slug = _path_segment(
            str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer"),
            fallback="customer",
        )
        root = preprocessed_root / "customer" / f"{getattr(workspace, 'id')}-{slug}"
        return GBrainSourcePaths(
            source_scope="customer",
            source_id=source_id,
            raw=raw_root,
            gbrain_ready=(root / "gbrain-ready").resolve(),
            runs=(root / "runs").resolve(),
            manifests=(root / "manifests").resolve(),
            preprocessed_root=root.resolve(),
            legacy_derived=(raw_root / "derived").resolve(),
            legacy_manifests=(raw_root / "manifests").resolve(),
        )
    raise ValueError(f"unsupported GBrain source scope: {source_scope}")


def _workspace_raw_root(workspace: Any, workspace_kind: str) -> Path:
    storage_path = str(getattr(workspace, "storage_path", "") or "").strip()
    if storage_path:
        return Path(storage_path).resolve()
    if workspace_kind == "project":
        brand = str(getattr(workspace, "brand", "") or "BFI").strip().upper() or "BFI"
        slug = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "project").strip() or "project"
        return (BASE_DIR / "workspace_data" / "project" / brand / slug).resolve()
    slug = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer").strip() or "customer"
    if slug.casefold() == CRM_CUSTOMER_SLUG.casefold():
        return (BASE_DIR / "workspace_data" / "customer" / CRM_CUSTOMER_SLUG).resolve()
    return (BASE_DIR / "workspace_data" / "customer" / slug).resolve()


def _path_segment(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized or fallback


def _gbrain_path_migration_status(gbrain_ready: Path, legacy_derived: Path | None) -> str:
    has_ready = gbrain_ready.exists() and any(gbrain_ready.iterdir())
    has_legacy = bool(legacy_derived and legacy_derived.exists() and any(legacy_derived.iterdir()))
    if has_ready and has_legacy:
        return "both_present"
    if has_ready:
        return "gbrain_ready"
    if has_legacy:
        return "legacy_only"
    return "empty"


def project_source_paths_for_workspace(workspace: Any) -> dict[str, Path]:
    resolved = resolve_gbrain_source_paths("project", workspace=workspace)
    return {
        "root": resolved.raw,
        "raw": resolved.raw,
        "derived": resolved.gbrain_ready,
        "gbrain_ready": resolved.gbrain_ready,
        "runs": resolved.runs,
        "manifests": resolved.manifests,
        "preprocessed_root": resolved.preprocessed_root,
        "legacy_derived": resolved.legacy_derived,
        "legacy_manifests": resolved.legacy_manifests,
    }


def customer_source_paths_for_workspace(workspace: Any) -> dict[str, Path]:
    resolved = resolve_gbrain_source_paths("customer", workspace=workspace)
    return {
        "root": resolved.raw,
        "raw": resolved.raw,
        "derived": resolved.gbrain_ready,
        "gbrain_ready": resolved.gbrain_ready,
        "runs": resolved.runs,
        "manifests": resolved.manifests,
        "preprocessed_root": resolved.preprocessed_root,
        "legacy_derived": resolved.legacy_derived,
        "legacy_manifests": resolved.legacy_manifests,
    }


def ensure_project_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    paths = project_source_paths_for_workspace(workspace)
    errors: list[str] = []
    for key in ("root", "derived", "runs", "manifests"):
        _ensure_directory(paths[key], errors)
    git_status = _ensure_local_git_repo(paths["derived"], settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")
    return {
        "ok": not errors,
        "source_id": project_source_id_for_workspace(workspace),
        "paths": {key: _path_status(path) for key, path in paths.items()},
        "local_git": git_status,
        "errors": errors,
    }


def ensure_customer_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    paths = customer_source_paths_for_workspace(workspace)
    errors: list[str] = []
    for key in ("root", "derived", "runs", "manifests"):
        _ensure_directory(paths[key], errors)
    git_status = _ensure_local_git_repo(paths["derived"], settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")
    return {
        "ok": not errors,
        "source_id": customer_source_id_for_workspace(workspace),
        "paths": {key: _path_status(path) for key, path in paths.items()},
        "local_git": git_status,
        "errors": errors,
    }


def project_source_registration_plan(workspace: Any) -> dict[str, Any]:
    source_id = project_source_id_for_workspace(workspace)
    paths = project_source_paths_for_workspace(workspace)
    name = _project_source_display_name(workspace)
    return {
        "source_id": source_id,
        "name": name,
        "path": str(paths["derived"].resolve()),
        "gbrain_ready_path": str(paths["gbrain_ready"].resolve()),
        "legacy_derived_path": str(paths["legacy_derived"].resolve()) if paths.get("legacy_derived") else None,
        "migration_status": _gbrain_path_migration_status(paths["gbrain_ready"], paths.get("legacy_derived")),
        "federated": False,
        "operator_command": (
            f"gbrain sources add {source_id} "
            f"--path {paths['derived'].resolve()} "
            f"--name \"{name}\" --no-federated"
        ),
    }


def customer_source_registration_plan(workspace: Any) -> dict[str, Any]:
    source_id = customer_source_id_for_workspace(workspace)
    paths = customer_source_paths_for_workspace(workspace)
    name = f"Project_R Customer - {getattr(workspace, 'name', source_id)}"
    return {
        "source_id": source_id,
        "name": name,
        "path": str(paths["derived"].resolve()),
        "gbrain_ready_path": str(paths["gbrain_ready"].resolve()),
        "legacy_derived_path": str(paths["legacy_derived"].resolve()) if paths.get("legacy_derived") else None,
        "migration_status": _gbrain_path_migration_status(paths["gbrain_ready"], paths.get("legacy_derived")),
        "federated": False,
        "operator_command": (
            f"gbrain sources add {source_id} "
            f"--path {paths['derived'].resolve()} "
            f"--name \"{name}\" --no-federated"
        ),
    }


class GBrainAdapter:
    def __init__(self, settings: GBrainSettings | None = None):
        self.settings = settings or load_gbrain_settings()
        self._think_oauth_tokens: dict[str, tuple[str, float]] = {}
        self._agent_oauth_access_token = ""
        self._agent_oauth_expires_at = 0.0

    def health(self) -> dict[str, Any]:
        environment = ensure_gbrain_environment(self.settings)
        service = self._probe_service_health()
        company_source = self.company_source_status()
        local_config = self._local_config_status()
        return {
            "enabled": self.settings.enabled,
            "configured": self.settings.service_configured,
            "base_url": self.settings.base_url,
            "source_id": self.settings.company_source_id,
            "service": service,
            "service_process": self.service_process_status(),
            "company_source": company_source,
            "local_config": local_config,
            "environment": environment,
            "readiness": self._readiness(service, company_source, local_config, environment),
        }

    def admin_status(self) -> dict[str, Any]:
        health = self.health()
        source = health.get("company_source", {}).get("source") or {}
        embedding = health.get("local_config", {}).get("embedding") or {}
        manifest = self.latest_ingest_manifest()
        doctor = self.doctor()
        status_snapshot = self.status_snapshot()
        sync_source = _source_status_from_snapshot(status_snapshot, self.settings.company_source_id)
        page_count = _first_number(sync_source, "pages", "page_count") or _first_number(
            source, "page_count", "pages", "pageCount"
        )
        chunk_count = _first_number(sync_source, "chunks_total", "chunk_count", "chunks") or _first_number(
            source, "chunk_count", "chunks_total", "chunks", "chunkCount"
        )
        last_sync = sync_source.get("last_sync_at") or source.get("last_sync_at") or source.get("last_sync")

        return {
            "ok": bool(
                health.get("enabled")
                and health.get("service", {}).get("status") == "ok"
                and health.get("company_source", {}).get("registered")
                and embedding.get("semantic_search_ready")
            ),
            "source_id": self.settings.company_source_id,
            "base_url": self.settings.base_url,
            "service": health.get("service"),
            "service_process": health.get("service_process"),
            "source": health.get("company_source"),
            "embedding": embedding,
            "semantic_search_ready": bool(embedding.get("semantic_search_ready")),
            "page_count": page_count,
            "chunk_count": chunk_count,
            "last_sync": last_sync,
            "ingest": manifest,
            "doctor": self._doctor_summary(doctor),
            "status_snapshot": status_snapshot,
            "sync_source": sync_source,
            "environment": health.get("environment"),
            "readiness": health.get("readiness"),
            # Compatibility fields for older admin UI code.
            "source_dirs": [str(resolve_gbrain_source_paths("company", settings=self.settings).gbrain_ready.resolve())],
            "legacy_source_dirs": [str(self.settings.derived_path.resolve())],
            "embedding_model": embedding.get("model") or "",
            "indexed_files": page_count,
            "indexed_chunks": chunk_count,
            "last_refresh": _timestamp_for_ui(last_sync or manifest.get("finished_at")),
        }

    def latest_ingest_manifest(self) -> dict[str, Any]:
        source_paths = resolve_gbrain_source_paths("company", settings=self.settings)
        manifest_path = source_paths.manifests / "company-wiki-ingest-manifest.json"
        legacy_manifest_path = self.settings.manifests_path / "company-wiki-ingest-manifest.json"
        if not manifest_path.exists() and legacy_manifest_path.exists():
            manifest_path = legacy_manifest_path
        if not manifest_path.exists():
            return {
                "exists": False,
                "path": str(manifest_path.resolve()),
                "legacy_path": str(legacy_manifest_path.resolve()),
                "summary": {"total": 0, "compiled": 0, "skipped": 0, "failed": 0},
                "items": [],
            }
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "exists": True,
                "path": str(manifest_path.resolve()),
                "error": str(exc),
                "summary": {"total": 0, "compiled": 0, "skipped": 0, "failed": 0},
                "items": [],
            }
        payload["exists"] = True
        payload["path"] = str(manifest_path.resolve())
        payload["legacy_path"] = str(legacy_manifest_path.resolve())
        return payload

    def source_registration_plan(self) -> dict[str, Any]:
        source_paths = resolve_gbrain_source_paths("company", settings=self.settings)
        return {
            "source_id": self.settings.company_source_id,
            "name": self.settings.company_source_name,
            "path": str(source_paths.gbrain_ready.resolve()),
            "gbrain_ready_path": str(source_paths.gbrain_ready.resolve()),
            "legacy_derived_path": str((source_paths.legacy_derived or self.settings.derived_path).resolve()),
            "migration_status": _gbrain_path_migration_status(source_paths.gbrain_ready, source_paths.legacy_derived),
            "federated": True,
            "operator_command": (
                f"gbrain sources add {self.settings.company_source_id} "
                f"--path {source_paths.gbrain_ready.resolve()} "
                f"--name \"{self.settings.company_source_name}\" --federated"
            ),
        }

    def list_sources(self) -> dict[str, Any]:
        response = self._call_mcp_tool("sources_list", {"include_archived": True})
        if response["status"] != "ok":
            return response
        result = response.get("result")
        sources = result.get("sources", []) if isinstance(result, dict) else []
        return {
            "status": "ok",
            "sources": sources,
        }

    def company_source_status(self) -> dict[str, Any]:
        plan = self.source_registration_plan()
        return self._source_status(
            self.settings.company_source_id,
            Path(plan["path"]).resolve(),
            plan,
        )

    def source_status(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        return self._source_status(
            str(registration_plan["source_id"]),
            Path(registration_plan["path"]).resolve(),
            registration_plan,
        )

    def ensure_source(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        before = self.source_status(registration_plan)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": True,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for source registration",
                },
                "source": before,
            }
        registration = self.register_source(registration_plan)
        after = self.source_status(registration_plan) if registration.get("ok") else before
        return {
            "ok": bool(registration.get("ok")),
            "registration": registration,
            "source": after,
        }

    def register_source(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": registration_plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            str(registration_plan["source_id"]),
            "--path",
            str(registration_plan["path"]),
            "--name",
            str(registration_plan["name"]),
        ]
        if registration_plan.get("federated"):
            args.append("--federated")
        else:
            args.append("--no-federated")
        result = self._run_cli_exclusive(args, reason=f"register_source:{registration_plan['source_id']}", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": registration_plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_registered_source(
        self,
        registration_plan: dict[str, Any],
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        return self.sync_source(
            source_id=str(registration_plan["source_id"]),
            repo_path=Path(registration_plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def project_source_registration_plan(self, workspace: Any) -> dict[str, Any]:
        return project_source_registration_plan(workspace)

    def customer_source_registration_plan(self, workspace: Any) -> dict[str, Any]:
        return customer_source_registration_plan(workspace)

    def project_source_status(self, workspace: Any) -> dict[str, Any]:
        if str(getattr(workspace, "workspace_kind", "project") or "project") != "project":
            return {
                "status": "not_project",
                "registered": False,
                "expected": None,
                "source": {},
            }
        plan = project_source_registration_plan(workspace)
        return self._source_status(
            plan["source_id"],
            Path(plan["path"]).resolve(),
            plan,
        )

    def ensure_project_source(self, workspace: Any) -> dict[str, Any]:
        environment = ensure_project_gbrain_environment(workspace, self.settings)
        before = self.project_source_status(workspace)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": environment.get("ok"),
                "environment": environment,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "environment": environment,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for source registration",
                },
                "source": before,
            }
        registration = self.register_project_source(workspace)
        after = self.project_source_status(workspace) if registration.get("ok") else before
        return {
            "ok": bool(environment.get("ok") and registration.get("ok")),
            "environment": environment,
            "registration": registration,
            "source": after,
        }

    def register_project_source(self, workspace: Any) -> dict[str, Any]:
        plan = project_source_registration_plan(workspace)
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            plan["source_id"],
            "--path",
            plan["path"],
            "--name",
            plan["name"],
            "--no-federated",
        ]
        result = self._run_cli_exclusive(args, reason="register_project_source", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_project_source(
        self,
        workspace: Any,
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        plan = project_source_registration_plan(workspace)
        return self.sync_source(
            source_id=plan["source_id"],
            repo_path=Path(plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def customer_source_status(self, workspace: Any) -> dict[str, Any]:
        if str(getattr(workspace, "workspace_kind", "") or "") != "customer":
            return {
                "status": "not_customer",
                "registered": False,
                "expected": None,
                "source": {},
            }
        plan = customer_source_registration_plan(workspace)
        return self._source_status(
            plan["source_id"],
            Path(plan["path"]).resolve(),
            plan,
        )

    def ensure_customer_source(self, workspace: Any) -> dict[str, Any]:
        environment = ensure_customer_gbrain_environment(workspace, self.settings)
        before = self.customer_source_status(workspace)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": environment.get("ok"),
                "environment": environment,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "environment": environment,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for customer source registration",
                },
                "source": before,
            }
        registration = self.register_customer_source(workspace)
        after = self.customer_source_status(workspace) if registration.get("ok") else before
        return {
            "ok": bool(environment.get("ok") and registration.get("ok")),
            "environment": environment,
            "registration": registration,
            "source": after,
        }

    def register_customer_source(self, workspace: Any) -> dict[str, Any]:
        plan = customer_source_registration_plan(workspace)
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            plan["source_id"],
            "--path",
            plan["path"],
            "--name",
            plan["name"],
            "--no-federated",
        ]
        result = self._run_cli_exclusive(args, reason="register_customer_source", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_customer_source(
        self,
        workspace: Any,
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        plan = customer_source_registration_plan(workspace)
        return self.sync_source(
            source_id=plan["source_id"],
            repo_path=Path(plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def _source_status(
        self,
        source_id: str,
        expected_path: Path,
        registration_plan: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._call_mcp_tool("sources_status", {"id": source_id})
        if response["status"] != "ok":
            return {
                "status": response["status"],
                "registered": False,
                "expected": registration_plan,
                "error": response.get("error"),
                "http_status": response.get("http_status"),
            }

        result = response.get("result")
        source = result if isinstance(result, dict) else {}
        local_path = source.get("local_path")
        path_matches = False
        if isinstance(local_path, str) and local_path:
            try:
                path_matches = os.path.normcase(str(Path(local_path).resolve())) == os.path.normcase(str(expected_path))
            except OSError:
                path_matches = False

        registered = source.get("id") == source_id
        status = "registered" if registered and path_matches else "path_mismatch" if registered else "missing"
        return {
            "status": status,
            "registered": registered,
            "path_matches": path_matches,
            "expected": registration_plan,
            "source": source,
        }

    def _probe_service_health(self) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"status": "disabled"}
        if not self.settings.service_configured:
            return {"status": "not_configured"}

        url = self.settings.base_url.rstrip("/") + "/health"
        headers = {"Accept": "application/json"}
        if self.settings.service_bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.service_bearer_token}"
        request = Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                body = json.loads(raw) if raw else {}
                return {
                    "status": "ok",
                    "http_status": response.status,
                    "body": body,
                }
        except HTTPError as exc:
            return {
                "status": "http_error",
                "http_status": exc.code,
                "error": exc.reason,
            }
        except (URLError, TimeoutError, OSError) as exc:
            return {
                "status": "unreachable",
                "error": str(exc),
            }
        except json.JSONDecodeError as exc:
            return {
                "status": "invalid_response",
                "error": str(exc),
            }

    def service_process_status(self) -> dict[str, Any]:
        record = self._read_service_record()
        pid = record.get("pid")
        discovered_pids = _discover_gbrain_service_pids(self.settings)
        pid_alive = _pid_exists(int(pid)) if isinstance(pid, int) else False
        return {
            "record_exists": bool(record),
            "pid": pid,
            "pid_alive": pid_alive or bool(discovered_pids),
            "discovered_pids": discovered_pids,
            "record": record,
            "cli_workdir": str(self.settings.cli_workdir.resolve()),
            "bun_executable": self.settings.bun_executable,
            "port": self.settings.http_port,
            "bind": self.settings.http_bind,
            "log_path": str(self.settings.service_log_path.resolve()),
        }

    def start_http_service(self) -> dict[str, Any]:
        ensure_gbrain_environment(self.settings)
        current_health = self._probe_service_health()
        if current_health.get("status") == "ok":
            return {"ok": True, "status": "already_running", "service": current_health}
        self._clear_stale_pglite_state()

        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "missing_gbrain_cli",
                "error": f"GBrain CLI not found at {cli_file}",
            }

        env = _apply_gbrain_provider_env(os.environ.copy())
        env["GBRAIN_HOME"] = str(self.settings.home_path.resolve())
        env.setdefault("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        # Project_R uses DATABASE_URL for its own SQLite app DB; GBrain CLI
        # interprets the same variable as its engine DB URL. Keep the brain on
        # GBRAIN_HOME/.gbrain unless the operator explicitly configured it.
        env.pop("DATABASE_URL", None)
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "serve",
            "--http",
            "--port",
            str(self.settings.http_port),
            "--bind",
            self.settings.http_bind,
            "--suppress-bootstrap-token",
        ]
        try:
            log_handle = self.settings.service_log_path.open("a", encoding="utf-8")
            flags = 0
            if os.name == "nt":
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            process = subprocess.Popen(
                args,
                cwd=self.settings.cli_workdir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": False, "status": "start_failed", "error": str(exc)}
        finally:
            try:
                log_handle.close()
            except UnboundLocalError:
                pass
            except OSError:
                pass

        self._write_service_record(
            {
                "pid": process.pid,
                "started_at": _utc_now(),
                "base_url": self.settings.base_url,
                "workdir": str(self.settings.cli_workdir.resolve()),
                "command": args,
                "log_path": str(self.settings.service_log_path.resolve()),
            }
        )
        time.sleep(1.5)
        service = self._probe_service_health()
        return {
            "ok": service.get("status") == "ok",
            "status": "started" if service.get("status") == "ok" else "started_but_not_ready",
            "pid": process.pid,
            "service": service,
            "log_path": str(self.settings.service_log_path.resolve()),
        }

    def stop_http_service(self) -> dict[str, Any]:
        record = self._read_service_record()
        pid = record.get("pid")
        pids: list[int] = []
        if isinstance(pid, int) and _pid_exists(pid):
            pids.append(pid)
        for discovered_pid in _discover_gbrain_service_pids(self.settings):
            if discovered_pid not in pids:
                pids.append(discovered_pid)

        if not pids:
            if isinstance(pid, int):
                self._delete_service_record()
                return {"ok": True, "status": "stale_record_removed", "pid": pid}
            return {"ok": True, "status": "no_project_r_managed_process"}

        stopped: list[int] = []
        failed: list[int] = []
        for target_pid in pids:
            terminated = _terminate_pid(target_pid)
            if terminated:
                stopped.append(target_pid)
            else:
                failed.append(target_pid)
        time.sleep(0.8)
        still_alive = [target_pid for target_pid in pids if _pid_exists(target_pid)]
        ok = not failed and not still_alive
        if ok:
            self._delete_service_record()
            self._clear_stale_pglite_state()
        return {
            "ok": ok,
            "status": "stopped" if ok else "stop_failed",
            "pids": pids,
            "stopped": stopped,
            "failed": failed,
            "still_alive": still_alive,
        }

    def restart_http_service(self) -> dict[str, Any]:
        stopped = self.stop_http_service()
        started = self.start_http_service()
        return {
            "ok": bool(started.get("ok")),
            "status": "restarted" if started.get("ok") else "restart_failed",
            "stop": stopped,
            "start": started,
        }

    def _read_service_record(self) -> dict[str, Any]:
        path = self.settings.service_record_path
        if not path.exists():
            return {}
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        return record if isinstance(record, dict) else {}

    def _write_service_record(self, record: dict[str, Any]) -> None:
        self.settings.manifests_path.mkdir(parents=True, exist_ok=True)
        self.settings.service_record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _delete_service_record(self) -> None:
        try:
            self.settings.service_record_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _clear_stale_pglite_state(self) -> None:
        brain_path = self.settings.home_path / ".gbrain" / "brain.pglite"
        if not brain_path.exists():
            return

        lock_dir = brain_path / ".gbrain-lock"
        lock_file = lock_dir / "lock"
        lock_pid_alive = False
        if lock_file.exists():
            try:
                lock = json.loads(lock_file.read_text(encoding="utf-8-sig"))
                lock_pid = lock.get("pid")
                lock_pid_alive = isinstance(lock_pid, int) and _pid_exists(lock_pid)
            except (OSError, json.JSONDecodeError):
                lock_pid_alive = False
            if not lock_pid_alive:
                shutil.rmtree(lock_dir, ignore_errors=True)

        postmaster_pid = brain_path / "postmaster.pid"
        if postmaster_pid.exists() and not lock_pid_alive:
            try:
                postmaster_pid.unlink()
            except OSError:
                pass

    def _local_config_status(self) -> dict[str, Any]:
        config_path = self.settings.home_path / ".gbrain" / "config.json"
        if not config_path.exists():
            return {
                "exists": False,
                "path": str(config_path.resolve()),
                "embedding": {
                    "semantic_search_ready": False,
                    "reason": "gbrain config not found",
                },
            }
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "exists": True,
                "path": str(config_path.resolve()),
                "error": str(exc),
                "embedding": {
                    "semantic_search_ready": False,
                    "reason": "gbrain config unreadable",
                },
            }

        model = str(config.get("embedding_model") or os.getenv("GBRAIN_EMBEDDING_MODEL") or "").strip()
        dimensions = config.get("embedding_dimensions") or os.getenv("GBRAIN_EMBEDDING_DIMENSIONS")
        disabled = bool(config.get("embedding_disabled"))
        provider = model.split(":", 1)[0].lower() if ":" in model else ""
        provider_env = EMBEDDING_PROVIDER_ENV.get(provider)
        provider_config_key = EMBEDDING_PROVIDER_CONFIG_KEY.get(provider)
        provider_configured = self._embedding_provider_configured(
            provider,
            provider_env,
            provider_config_key,
            config,
            model,
        )
        semantic_search_ready = not disabled and bool(model) and provider_configured is True
        reason = None
        if disabled:
            reason = "embedding disabled in GBrain config"
        elif not model:
            reason = "embedding model not configured"
        elif provider_configured is False:
            if provider == "ollama":
                reason = "ollama service or embedding model is not available"
            else:
                reason = f"missing {provider_env}" if provider_env else "embedding provider not configured"
        elif provider_configured is None:
            reason = "embedding provider availability is unknown"

        return {
            "exists": True,
            "path": str(config_path.resolve()),
            "engine": config.get("engine"),
            "schema_pack": config.get("schema_pack"),
            "embedding": {
                "semantic_search_ready": semantic_search_ready,
                "disabled": disabled,
                "model": model or None,
                "dimensions": int(dimensions) if str(dimensions or "").isdigit() else dimensions,
                "provider": provider or None,
                "provider_env": provider_env,
                "provider_config_key": provider_config_key,
                "provider_configured": provider_configured,
                "reason": reason,
            },
        }

    def _embedding_provider_configured(
        self,
        provider: str,
        provider_env: str | None,
        provider_config_key: str | None,
        config: dict[str, Any],
        model: str,
    ) -> bool | None:
        if not provider:
            return False
        if provider == "ollama":
            return self._ollama_model_available(model)
        if provider in LOCAL_EMBEDDING_PROVIDERS:
            return None
        if provider_env:
            return bool(os.getenv(provider_env) or (provider_config_key and config.get(provider_config_key)))
        return None

    def _ollama_model_available(self, model: str) -> bool:
        model_id = model.split(":", 1)[1].strip() if ":" in model else model.strip()
        if not model_id:
            return False

        base_url = os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip() or DEFAULT_OLLAMA_BASE_URL
        api_root = base_url.rstrip("/")
        if api_root.endswith("/v1"):
            api_root = api_root[:-3].rstrip("/")

        request = Request(api_root + "/api/tags", headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=min(self.settings.timeout_seconds, 3.0)) as response:
                raw = response.read().decode("utf-8", errors="replace")
                payload = json.loads(raw) if raw else {}
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False

        models = payload.get("models", [])
        if not isinstance(models, list):
            return False
        accepted_names = {model_id, f"{model_id}:latest"}
        for item in models:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and name in accepted_names:
                return True
        return False

    def _call_mcp_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"status": "disabled"}
        if not self.settings.service_configured:
            return {"status": "not_configured"}
        token = bearer_token or self.settings.service_bearer_token
        if not token:
            return {
                "status": "auth_required",
                "error": "GBrain bearer token is not configured",
            }

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
            "id": 1,
        }
        request = Request(
            self.settings.base_url.rstrip("/") + "/mcp",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json, text/event-stream",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds or self.settings.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return {
                    "status": "ok",
                    "http_status": response.status,
                    "result": self._parse_mcp_tool_payload(raw),
                }
        except HTTPError as exc:
            return {
                "status": "http_error",
                "http_status": exc.code,
                "error": exc.reason,
            }
        except (URLError, TimeoutError, OSError) as exc:
            return {
                "status": "unreachable",
                "error": str(exc),
            }
        except (json.JSONDecodeError, ValueError) as exc:
            return {
                "status": "invalid_response",
                "error": str(exc),
            }

    @staticmethod
    def _parse_mcp_tool_payload(raw: str) -> dict[str, Any]:
        payload_text = raw.strip()
        data_lines = [line.removeprefix("data:").strip() for line in raw.splitlines() if line.startswith("data:")]
        if data_lines:
            payload_text = data_lines[-1]

        envelope = json.loads(payload_text)
        if envelope.get("error"):
            return {"error": envelope["error"]}

        result = envelope.get("result", {})
        content = result.get("content", []) if isinstance(result, dict) else []
        if not content:
            return result if isinstance(result, dict) else {}

        first = content[0]
        if not isinstance(first, dict):
            return result if isinstance(result, dict) else {}
        text = first.get("text")
        if not isinstance(text, str) or not text.strip():
            return result if isinstance(result, dict) else {}
        return json.loads(text)

    def _think_allowed_sources(self) -> tuple[str, ...]:
        return self.settings.think_allowed_sources or (self.settings.company_source_id,)

    @staticmethod
    def _is_project_source_id(source_id: str) -> bool:
        return source_id.startswith(f"{PROJECT_SOURCE_ID_PREFIX}-")

    @staticmethod
    def _is_customer_source_id(source_id: str) -> bool:
        return source_id == CUSTOMER_INTELLIGENCE_SOURCE_ID or source_id.startswith(f"{CUSTOMER_SOURCE_ID_PREFIX}-")

    def _supports_auto_think_source_client(self, source_id: str) -> bool:
        return self._is_project_source_id(source_id) or self._is_customer_source_id(source_id)

    def _think_source_gate(self, target_source_id: str) -> dict[str, Any] | None:
        if not self.settings.think_enabled:
            return {
                "status": "disabled",
                "source_id": target_source_id,
                "error": "GBRAIN_THINK_ENABLED is not true",
            }
        if not self.settings.think_source_scope_verified:
            return {
                "status": "source_scope_unverified",
                "source_id": target_source_id,
                "error": (
                    "GBrain think is not enabled because source-scoped retrieval has not been verified. "
                    "Current upstream think gather does not thread sourceId/allowedSources through every retrieval stream."
                ),
            }
        return None

    def _resolve_think_client_credentials(
        self,
        target_source_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        allowed_sources = self._think_allowed_sources()
        if target_source_id in allowed_sources:
            if not self.settings.think_oauth_client_id or not self.settings.think_oauth_client_secret:
                return {}, {
                    "status": "oauth_required",
                    "source_id": target_source_id,
                    "error": "GBRAIN_THINK_OAUTH_CLIENT_ID and GBRAIN_THINK_OAUTH_CLIENT_SECRET are required",
                }
            return {
                "source": "env",
                "source_id": target_source_id,
                "client_id": self.settings.think_oauth_client_id,
                "client_secret": self.settings.think_oauth_client_secret,
                "scope": self.settings.think_oauth_scope,
                "token_auth_method": self.settings.think_oauth_token_auth_method,
                "allowed_sources": list(allowed_sources),
                "cache_key": f"env:{self.settings.think_oauth_client_id}",
            }, None

        if self._supports_auto_think_source_client(target_source_id):
            if not self.settings.think_project_clients_enabled:
                return {}, {
                    "status": "source_not_allowed",
                    "source_id": target_source_id,
                    "allowed_sources": list(allowed_sources),
                    "error": "Managed GBrain think OAuth clients are disabled",
                }
            client = self.ensure_think_source_client(target_source_id)
            if not client.get("ok"):
                return {}, {
                    "status": client.get("status") or "oauth_required",
                    "source_id": target_source_id,
                    "error": client.get("error") or "Unable to prepare source-scoped GBrain think OAuth client",
                }
            return {
                "source": "manifest",
                "source_id": target_source_id,
                "client_id": str(client["client_id"]),
                "client_secret": str(client["client_secret"]),
                "scope": str(client.get("scope") or self.settings.think_oauth_scope),
                "token_auth_method": str(
                    client.get("token_auth_method") or self.settings.think_oauth_token_auth_method
                ),
                "allowed_sources": [target_source_id],
                "cache_key": f"manifest:{target_source_id}:{client['client_id']}",
            }, None

        return {}, {
            "status": "source_not_allowed",
            "source_id": target_source_id,
            "allowed_sources": list(allowed_sources),
            "error": "Requested GBrain think source is not listed in GBRAIN_THINK_ALLOWED_SOURCES",
        }

    def ensure_think_source_client(self, source_id: str) -> dict[str, Any]:
        source_id = str(source_id or "").strip()
        if not source_id:
            return {"ok": False, "status": "invalid_source", "error": "source_id is required"}
        if not self._supports_auto_think_source_client(source_id):
            return {
                "ok": False,
                "status": "unsupported_source",
                "source_id": source_id,
                "error": "Automatic GBrain think OAuth client registration is only enabled for managed project/customer sources",
            }

        manifest = self._load_think_source_clients_manifest()
        if manifest.get("status") != "ok":
            return {**manifest, "ok": False, "source_id": source_id}

        clients = manifest["clients"]
        existing = clients.get(source_id)
        if self._is_valid_think_source_client(existing, source_id):
            token_check = self._fetch_oauth_token(
                client_id=str(existing["client_id"]),
                client_secret=str(existing["client_secret"]),
                scope=str(existing.get("scope") or self.settings.think_oauth_scope),
                token_auth_method=str(existing.get("token_auth_method") or self.settings.think_oauth_token_auth_method),
            )
            if token_check.get("status") == "ok":
                return {
                    "ok": True,
                    "status": "already_registered",
                    "source_id": source_id,
                    **existing,
                }
            if not _oauth_token_error_is_missing_client(token_check):
                return {
                    "ok": False,
                    "status": token_check.get("status") or "token_check_failed",
                    "source_id": source_id,
                    "error": token_check.get("error") or "GBrain OAuth client token check failed",
                }
            clients.pop(source_id, None)
            self._think_oauth_tokens.pop(f"manifest:{source_id}:{existing['client_id']}", None)

        registered = self.register_think_source_client(source_id)
        if not registered.get("ok"):
            return registered

        client_record = {
            "source_id": source_id,
            "name": registered["name"],
            "client_id": registered["client_id"],
            "client_secret": registered["client_secret"],
            "scope": self.settings.think_oauth_scope,
            "token_auth_method": self.settings.think_oauth_token_auth_method,
            "allowed_sources": [source_id],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        clients[source_id] = client_record
        written = self._write_think_source_clients_manifest(clients)
        if written.get("status") != "ok":
            return {
                "ok": False,
                "status": written.get("status"),
                "source_id": source_id,
                "error": written.get("error"),
            }
        return {
            "ok": True,
            "status": "registered",
            **client_record,
            "service_restart": registered.get("service_restart"),
        }

    def register_think_source_client(self, source_id: str) -> dict[str, Any]:
        cli_file = self.settings.cli_workdir / "src" / "commands" / "auth.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "source_id": source_id,
                "error": f"GBrain auth CLI not found at {cli_file}",
            }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        name = f"project-r-think-{source_id}-{timestamp}"
        args = [
            self.settings.bun_executable,
            "run",
            "src/commands/auth.ts",
            "register-client",
            name,
            "--grant-types",
            "client_credentials",
            "--scopes",
            self.settings.think_oauth_scope,
            "--source",
            source_id,
            "--federated-read",
            source_id,
            "--token-endpoint-auth-method",
            self.settings.think_oauth_token_auth_method,
        ]
        result = self._run_cli_exclusive(args, reason="register_think_source_client", timeout=90)
        combined_output = "\n".join(
            part
            for part in (
                (result.get("result") or {}).get("stdout"),
                (result.get("result") or {}).get("stderr"),
            )
            if isinstance(part, str) and part
        )
        if result.get("status") != "ok":
            redacted = self._redact_oauth_registration_output(combined_output or str(result.get("error") or ""))
            return {
                "ok": False,
                "status": result.get("status") or "cli_error",
                "source_id": source_id,
                "name": name,
                "error": redacted[-1000:] or "gbrain register-client failed",
                "service_restart": result.get("service_restart"),
            }
        try:
            client_id, client_secret = self._parse_oauth_registration_output(combined_output)
        except ValueError as exc:
            return {
                "ok": False,
                "status": "invalid_registration_output",
                "source_id": source_id,
                "name": name,
                "error": str(exc),
                "result": {
                    "stdout": self._redact_oauth_registration_output((result.get("result") or {}).get("stdout") or ""),
                    "stderr": self._redact_oauth_registration_output((result.get("result") or {}).get("stderr") or ""),
                },
                "service_restart": result.get("service_restart"),
            }
        return {
            "ok": True,
            "status": "ok",
            "source_id": source_id,
            "name": name,
            "client_id": client_id,
            "client_secret": client_secret,
            "result": {
                "stdout": self._redact_oauth_registration_output((result.get("result") or {}).get("stdout") or ""),
                "stderr": self._redact_oauth_registration_output((result.get("result") or {}).get("stderr") or ""),
            },
            "service_restart": result.get("service_restart"),
        }

    def _load_think_source_clients_manifest(self) -> dict[str, Any]:
        path = self.settings.think_source_clients_path
        if not path.exists():
            return {"status": "ok", "clients": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"status": "invalid_manifest", "error": str(exc), "path": str(path.resolve())}
        if not isinstance(payload, dict):
            return {"status": "invalid_manifest", "error": "manifest root is not an object", "path": str(path.resolve())}
        clients = payload.get("clients")
        if not isinstance(clients, dict):
            clients = {}
        return {"status": "ok", "clients": clients}

    def _write_think_source_clients_manifest(self, clients: dict[str, Any]) -> dict[str, Any]:
        path = self.settings.think_source_clients_path
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "clients": clients,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, path)
            return {"status": "ok", "path": str(path.resolve())}
        except OSError as exc:
            return {"status": "write_failed", "error": str(exc), "path": str(path.resolve())}

    def _is_valid_think_source_client(self, client: Any, source_id: str) -> bool:
        if not isinstance(client, dict):
            return False
        if client.get("source_id") != source_id:
            return False
        if not isinstance(client.get("client_id"), str) or not client.get("client_id").strip():
            return False
        if not isinstance(client.get("client_secret"), str) or not client.get("client_secret").strip():
            return False
        allowed_sources = client.get("allowed_sources")
        return isinstance(allowed_sources, list) and source_id in allowed_sources

    @staticmethod
    def _parse_oauth_registration_output(output: str) -> tuple[str, str]:
        client_id_match = re.search(r"Client ID:\s*(\S+)", output)
        client_secret_match = re.search(r"Client Secret:\s*(\S+)", output)
        if not client_id_match:
            raise ValueError("GBrain register-client output did not include a Client ID")
        if not client_secret_match or client_secret_match.group(1).startswith("<"):
            raise ValueError("GBrain register-client output did not include a confidential Client Secret")
        return client_id_match.group(1).strip(), client_secret_match.group(1).strip()

    @staticmethod
    def _redact_oauth_registration_output(output: str) -> str:
        return re.sub(r"(Client Secret:\s*)\S+", r"\1<redacted>", output)

    def _get_think_bearer_token(
        self,
        target_source_id: str,
    ) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
        gate = self._think_source_gate(target_source_id)
        if gate:
            return None, gate, None

        credentials, credential_error = self._resolve_think_client_credentials(target_source_id)
        if credential_error:
            return None, credential_error, None

        cache_key = str(credentials["cache_key"])
        cached = self._think_oauth_tokens.get(cache_key)
        if cached and time.time() < cached[1]:
            return cached[0], None, credentials

        token_response = self._fetch_oauth_token(
            client_id=str(credentials["client_id"]),
            client_secret=str(credentials["client_secret"]),
            scope=str(credentials["scope"]),
            token_auth_method=str(credentials["token_auth_method"]),
        )
        if token_response.get("status") != "ok":
            return None, {**token_response, "source_id": target_source_id}, credentials
        token = str(token_response.get("access_token") or "")
        if not token:
            return None, {
                "status": "invalid_response",
                "source_id": target_source_id,
                "error": "GBrain OAuth token response did not include access_token",
            }, credentials
        try:
            expires_in = int(token_response.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        self._think_oauth_tokens[cache_key] = (token, time.time() + max(30, expires_in - 30))
        return token, None, credentials

    def _fetch_think_oauth_token(self) -> dict[str, Any]:
        return self._fetch_oauth_token(
            client_id=self.settings.think_oauth_client_id,
            client_secret=self.settings.think_oauth_client_secret,
            scope=self.settings.think_oauth_scope,
            token_auth_method=self.settings.think_oauth_token_auth_method,
        )

    def _fetch_oauth_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        scope: str,
        token_auth_method: str,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"status": "disabled"}
        if not self.settings.service_configured:
            return {"status": "not_configured"}

        form = {
            "grant_type": "client_credentials",
            "scope": scope,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        method = token_auth_method.strip().lower()
        if method == "client_secret_basic":
            raw = f"{client_id}:{client_secret}"
            headers["Authorization"] = "Basic " + base64.b64encode(raw.encode("utf-8")).decode("ascii")
        else:
            form["client_id"] = client_id
            form["client_secret"] = client_secret

        request = Request(
            self.settings.base_url.rstrip("/") + "/token",
            data=urlencode(form).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:600]
            return {
                "status": "token_request_failed",
                "http_status": exc.code,
                "error": body or str(exc),
            }
        except (URLError, TimeoutError, OSError) as exc:
            return {"status": "unreachable", "error": str(exc)}

        try:
            payload = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            return {"status": "invalid_response", "error": str(exc)}
        if not isinstance(payload, dict):
            return {"status": "invalid_response", "error": "OAuth token response is not an object"}
        if payload.get("error"):
            return {
                "status": "token_request_failed",
                "error": str(payload.get("error_description") or payload.get("error")),
            }
        return {
            "status": "ok",
            "access_token": payload.get("access_token"),
            "expires_in": payload.get("expires_in", 3600),
            "token_type": payload.get("token_type"),
        }

    def query(
        self,
        query: str,
        *,
        source_id: str | None = None,
        limit: int = 5,
        expand: bool = False,
        detail: str = "medium",
    ) -> dict[str, Any]:
        return self._call_mcp_tool(
            "query",
            {
                "query": query,
                "source_id": source_id or self.settings.company_source_id,
                "limit": limit,
                "expand": expand,
                "detail": detail,
            },
        )

    def think(
        self,
        query: str,
        *,
        source_id: str | None = None,
        rounds: int | None = None,
        model: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error

        arguments: dict[str, Any] = {
            "question": query,
            "rounds": max(1, rounds or self.settings.think_rounds),
        }
        selected_model = model or self.settings.think_model
        if selected_model:
            arguments["model"] = selected_model
        if since:
            arguments["since"] = since
        if until:
            arguments["until"] = until

        response = self._call_mcp_tool(
            "think",
            arguments,
            bearer_token=token,
            timeout_seconds=self.settings.think_timeout_seconds,
        )
        return {
            **response,
            "method": "mcp",
            "source_id": target_source_id,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
        }

    def _agent_gate(self) -> dict[str, Any] | None:
        if not self.settings.agent_enabled:
            return {
                "status": "disabled",
                "error": "GBRAIN_AGENT_ENABLED is not true",
            }
        if not self.settings.agent_oauth_client_id or not self.settings.agent_oauth_client_secret:
            return {
                "status": "oauth_required",
                "error": "GBRAIN_AGENT_OAUTH_CLIENT_ID and GBRAIN_AGENT_OAUTH_CLIENT_SECRET are required",
            }
        return None

    def _get_agent_bearer_token(self) -> tuple[str | None, dict[str, Any] | None]:
        gate = self._agent_gate()
        if gate:
            return None, gate
        if self._agent_oauth_access_token and time.time() < self._agent_oauth_expires_at:
            return self._agent_oauth_access_token, None
        token_response = self._fetch_oauth_token(
            client_id=self.settings.agent_oauth_client_id,
            client_secret=self.settings.agent_oauth_client_secret,
            scope=self.settings.agent_oauth_scope,
            token_auth_method=self.settings.agent_oauth_token_auth_method,
        )
        if token_response.get("status") != "ok":
            return None, token_response
        token = str(token_response.get("access_token") or "")
        if not token:
            return None, {
                "status": "invalid_response",
                "error": "GBrain agent OAuth token response did not include access_token",
            }
        try:
            expires_in = int(token_response.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        self._agent_oauth_access_token = token
        self._agent_oauth_expires_at = time.time() + max(30, expires_in - 30)
        return token, None

    def submit_agent(
        self,
        *,
        prompt: str,
        allowed_tools: list[str] | tuple[str, ...] | None = None,
        allowed_slug_prefixes: list[str] | tuple[str, ...] | None = None,
        max_turns: int = 20,
        model: str | None = None,
        queue: str | None = None,
    ) -> dict[str, Any]:
        token, gate_error = self._get_agent_bearer_token()
        if gate_error:
            return gate_error
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "max_turns": max(1, min(int(max_turns or 20), 100)),
        }
        selected_model = model or self.settings.agent_model
        if selected_model:
            arguments["model"] = selected_model
        if allowed_tools:
            arguments["allowed_tools"] = [str(tool).strip() for tool in allowed_tools if str(tool).strip()]
        if allowed_slug_prefixes:
            arguments["allowed_slug_prefixes"] = [
                prefix.strip() for prefix in allowed_slug_prefixes if isinstance(prefix, str) and prefix.strip()
            ]
        if queue:
            arguments["queue"] = queue.strip()
        response = self._call_mcp_tool(
            "submit_agent",
            arguments,
            bearer_token=token,
            timeout_seconds=self.settings.agent_timeout_seconds,
        )
        return {
            **response,
            "method": "mcp",
            "job_type": "subagent",
        }

    def submit_citation_fixer(
        self,
        *,
        page_slug: str | None = None,
        review_id: int | None = None,
        notes: str | None = None,
        allowed_slug_prefixes: list[str] | tuple[str, ...] | None = None,
        max_turns: int = 30,
        model: str | None = None,
        queue: str | None = None,
    ) -> dict[str, Any]:
        prompt = self._build_citation_fixer_prompt(
            page_slug=page_slug,
            review_id=review_id,
            notes=notes,
        )
        return self.submit_agent(
            prompt=prompt,
            allowed_tools=self.settings.citation_fixer_tools,
            allowed_slug_prefixes=allowed_slug_prefixes,
            max_turns=max_turns,
            model=model,
            queue=queue,
        )

    def get_page(self, slug: str, *, include_deleted: bool = False) -> dict[str, Any]:
        arguments: dict[str, Any] = {"slug": slug}
        if include_deleted:
            arguments["include_deleted"] = True
        return self._call_mcp_tool("get_page", arguments)

    def graph_context(
        self,
        slug: str,
        *,
        source_id: str | None = None,
        depth: int = 2,
        direction: str = "both",
        link_type: str | None = None,
        include_timeline: bool = True,
        include_backlinks: bool = True,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error
        clean_slug = str(slug or "").strip().removesuffix(".md")
        if not clean_slug:
            return {"status": "invalid_request", "error": "slug is required"}
        traversal_arguments: dict[str, Any] = {
            "slug": clean_slug,
            "depth": max(1, min(int(depth or 2), 10)),
            "direction": direction if direction in {"in", "out", "both"} else "both",
        }
        if link_type:
            traversal_arguments["link_type"] = str(link_type).strip()
        response: dict[str, Any] = {
            "status": "ok",
            "method": "mcp",
            "source_id": target_source_id,
            "slug": clean_slug,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
            "traverse_graph": self._call_mcp_tool(
                "traverse_graph",
                traversal_arguments,
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
        }
        if include_timeline:
            response["timeline"] = self._call_mcp_tool(
                "get_timeline",
                {"slug": clean_slug},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            )
        if include_backlinks:
            response["backlinks"] = self._call_mcp_tool(
                "get_backlinks",
                {"slug": clean_slug},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            )
        return response

    def schema_context(
        self,
        *,
        source_id: str | None = None,
        orphan_limit: int = 20,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error
        response: dict[str, Any] = {
            "status": "ok",
            "method": "mcp",
            "source_id": target_source_id,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
            "active_schema_pack": self._call_mcp_tool(
                "get_active_schema_pack",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_stats": self._call_mcp_tool(
                "schema_stats",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_graph": self._call_mcp_tool(
                "schema_graph",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_review_orphans": self._call_mcp_tool(
                "schema_review_orphans",
                {"limit": max(1, min(int(orphan_limit or 20), 200))},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
        }
        return response

    def _build_citation_fixer_prompt(
        self,
        *,
        page_slug: str | None,
        review_id: int | None,
        notes: str | None,
    ) -> str:
        scope = f"Only inspect and patch the GBrain page `{page_slug}`." if page_slug else (
            "Scan the bound source for citation-format issues in a small, safe batch."
        )
        review_line = f"Project_R KnowledgeReview id: {review_id}." if review_id is not None else (
            "No Project_R review id was provided."
        )
        notes_line = notes.strip() if isinstance(notes, str) and notes.strip() else "No extra operator notes."
        return (
            "Use the GBrain `citation-fixer` skill.\n"
            f"{scope}\n"
            f"{review_line}\n"
            f"Operator notes: {notes_line}\n\n"
            "Follow the upstream citation-fixer contract exactly: fix malformed citation formatting, "
            "resolve deterministic links only when a configured resolver/API provides the data, flag missing or "
            "uncitable facts, and never invent citations or delete unsupported facts. Report pages scanned, "
            "citations found, issues fixed, tweet links resolved, remaining gaps, and any pages left for human review."
        )

    def sync_source(
        self,
        *,
        source_id: str | None = None,
        repo_path: Path | None = None,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        source_id = source_id or self.settings.company_source_id
        default_repo = resolve_gbrain_source_paths("company", settings=self.settings).gbrain_ready
        repo = (repo_path or default_repo).resolve()
        # GBrain currently marks sync_brain as localOnly, so HTTP MCP may hide it.
        # Try MCP first for future compatibility, then fall back to same-host CLI.
        mcp_response = self._call_mcp_tool(
            "sync_brain",
            {
                "repo": str(repo),
                "full": full,
                "no_pull": no_pull,
                "no_embed": no_embed,
            },
        )
        if _mcp_tool_invocation_succeeded(mcp_response):
            return {**mcp_response, "method": "mcp"}
        return self._sync_source_via_cli(
            source_id=source_id,
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
            mcp_response=mcp_response,
        )

    def _sync_source_via_cli(
        self,
        *,
        source_id: str,
        full: bool,
        no_pull: bool,
        no_embed: bool,
        mcp_response: dict[str, Any],
    ) -> dict[str, Any]:
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "status": "cli_unavailable",
                "method": "cli",
                "error": f"GBrain CLI not found at {cli_file}",
                "mcp_response": mcp_response,
            }

        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sync",
            "--source",
            source_id,
        ]
        if full:
            args.append("--full")
        if no_pull:
            args.append("--no-pull")
        if no_embed:
            args.append("--no-embed")

        env = _apply_gbrain_provider_env(os.environ.copy())
        env["GBRAIN_HOME"] = str(self.settings.home_path.resolve())
        env.setdefault("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        env.pop("DATABASE_URL", None)
        if self._probe_service_health().get("status") == "ok":
            stopped = self.stop_http_service()
            if not stopped.get("ok"):
                restarted = self.start_http_service()
                return {
                    "status": "cli_error",
                    "method": "cli",
                    "error": "Unable to stop GBrain HTTP service for exclusive PGLite sync",
                    "mcp_response": mcp_response,
                    "service_restart": {
                        "reason": "run_local_only_sync_with_exclusive_pglite",
                        "stop": stopped,
                        "start": restarted,
                    },
                }
            self._clear_stale_pglite_state()
            try:
                result = self._run_sync_cli(args, env)
            finally:
                restarted = self.start_http_service()
            return {
                **result,
                "method": "cli",
                "mcp_response": mcp_response,
                "service_restart": {
                    "reason": "run_local_only_sync_with_exclusive_pglite",
                    "stop": stopped,
                    "start": restarted,
                },
            }

        self._clear_stale_pglite_state()
        first = self._run_sync_cli(args, env)
        if first.get("status") == "ok" or not _should_retry_sync_with_service_restart(first):
            return {**first, "method": "cli", "mcp_response": mcp_response}

        stopped = self.stop_http_service()
        self._clear_stale_pglite_state()
        retry = self._run_sync_cli(args, env)
        restarted = self.start_http_service()
        return {
            **retry,
            "method": "cli",
            "mcp_response": mcp_response,
            "service_restart": {
                "reason": "retry_cli_sync_with_exclusive_pglite",
                "first_error": first.get("error"),
                "stop": stopped,
                "start": restarted,
            },
        }

    def _run_cli_exclusive(self, args: list[str], *, reason: str, timeout: int) -> dict[str, Any]:
        env = _apply_gbrain_provider_env(os.environ.copy())
        env["GBRAIN_HOME"] = str(self.settings.home_path.resolve())
        env.setdefault("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
        env.pop("DATABASE_URL", None)
        service_restart: dict[str, Any] | None = None
        if self._probe_service_health().get("status") == "ok":
            stopped = self.stop_http_service()
            if not stopped.get("ok"):
                restarted = self.start_http_service()
                return {
                    "status": "cli_error",
                    "error": "Unable to stop GBrain HTTP service for exclusive CLI operation",
                    "service_restart": {
                        "reason": reason,
                        "stop": stopped,
                        "start": restarted,
                    },
                }
            self._clear_stale_pglite_state()
            try:
                result = self._run_gbrain_cli(args, env, timeout)
            finally:
                restarted = self.start_http_service()
            service_restart = {"reason": reason, "stop": stopped, "start": restarted}
            return {**result, "service_restart": service_restart}

        self._clear_stale_pglite_state()
        return self._run_gbrain_cli(args, env, timeout)

    def _run_gbrain_cli(self, args: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                args,
                cwd=self.settings.cli_workdir,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "status": "cli_error",
                "error": str(exc),
            }

        ok = completed.returncode == 0
        return {
            "status": "ok" if ok else "cli_error",
            "result": {
                "returncode": completed.returncode,
                "stdout": (completed.stdout or "")[-4000:],
                "stderr": (completed.stderr or "")[-4000:],
            },
            "error": None if ok else (completed.stderr or completed.stdout or "gbrain cli failed").strip()[-1000:],
        }

    def _run_sync_cli(self, args: list[str], env: dict[str, str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                args,
                cwd=self.settings.cli_workdir,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "status": "cli_error",
                "error": str(exc),
            }

        ok = completed.returncode == 0
        return {
                "status": "ok" if ok else "cli_error",
                "result": {
                    "returncode": completed.returncode,
                    "stdout": (completed.stdout or "")[-4000:],
                    "stderr": (completed.stderr or "")[-4000:],
                },
            "error": None if ok else (completed.stderr or completed.stdout or "gbrain sync failed").strip()[-1000:],
        }

    def doctor(self) -> dict[str, Any]:
        return self._call_mcp_tool("run_doctor", {})

    def status_snapshot(self) -> dict[str, Any]:
        return self._call_mcp_tool("get_status_snapshot", {})

    def list_jobs(
        self,
        *,
        status: str | None = None,
        queue: str | None = None,
        name: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
        if status:
            normalized_status = status.strip().lower()
            if normalized_status not in GBRAIN_JOB_STATUSES:
                return {
                    "status": "invalid_status",
                    "error": f"Unsupported GBrain job status: {status}",
                    "allowed_statuses": sorted(GBRAIN_JOB_STATUSES),
                }
            arguments["status"] = normalized_status
        if queue:
            arguments["queue"] = queue.strip()
        if name:
            arguments["name"] = name.strip()
        return self._call_mcp_tool("list_jobs", arguments)

    def get_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("get_job", {"id": int(job_id)})

    def get_job_progress(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("get_job_progress", {"id": int(job_id)})

    def submit_job(
        self,
        *,
        name: str,
        data: dict[str, Any] | None = None,
        queue: str | None = None,
        priority: int | float | None = None,
        max_attempts: int | None = None,
        delay: int | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        job_name = name.strip()
        if job_name not in GBRAIN_MAINTENANCE_JOB_NAMES:
            return {
                "status": "invalid_job_name",
                "error": f"Unsupported GBrain maintenance job: {name}",
                "allowed_names": sorted(GBRAIN_MAINTENANCE_JOB_NAMES),
            }
        if data is not None and not isinstance(data, dict):
            return {
                "status": "invalid_params",
                "error": "GBrain job data must be a JSON object",
            }
        arguments: dict[str, Any] = {
            "name": job_name,
            "data": data or {},
        }
        if queue:
            arguments["queue"] = queue.strip()
        if priority is not None:
            arguments["priority"] = priority
        if max_attempts is not None:
            arguments["max_attempts"] = max(1, int(max_attempts))
        if delay is not None:
            arguments["delay"] = max(0, int(delay))
        if timeout_ms is not None:
            arguments["timeout_ms"] = max(1000, int(timeout_ms))
        return self._call_mcp_tool("submit_job", arguments, timeout_seconds=max(self.settings.timeout_seconds, 15.0))

    def cancel_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("cancel_job", {"id": int(job_id)})

    def retry_job(self, job_id: int) -> dict[str, Any]:
        return self._call_mcp_tool("retry_job", {"id": int(job_id)})

    def find_contradictions(
        self,
        *,
        slug: str | None = None,
        severity: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"limit": max(1, min(int(limit or 20), 100))}
        if slug:
            arguments["slug"] = slug.strip()
        if severity:
            normalized_severity = severity.strip().lower()
            if normalized_severity not in GBRAIN_CONTRADICTION_SEVERITIES:
                return {
                    "status": "invalid_severity",
                    "error": f"Unsupported contradiction severity: {severity}",
                    "allowed_severities": sorted(GBRAIN_CONTRADICTION_SEVERITIES),
                }
            arguments["severity"] = normalized_severity
        return self._call_mcp_tool("find_contradictions", arguments)

    def maintenance_check(self, *, target_score: int = 90) -> dict[str, Any]:
        return self._call_mcp_tool(
            "run_onboard",
            {
                "mode": "check",
                "target_score": max(1, min(int(target_score or 90), 100)),
            },
            timeout_seconds=max(self.settings.timeout_seconds, 30.0),
        )

    def agent_status(self) -> dict[str, Any]:
        oauth_configured = bool(self.settings.agent_oauth_client_id and self.settings.agent_oauth_client_secret)
        missing_tools = [
            tool for tool in GBRAIN_CITATION_FIXER_TOOLS if tool not in set(self.settings.citation_fixer_tools)
        ]
        binding_submit_verified = bool(self.settings.agent_binding_submit_verified)
        inline_execution_verified = bool(self.settings.agent_inline_execution_verified)
        execution_verified = bool(self.settings.agent_execution_verified)
        status = "disabled"
        if self.settings.agent_enabled and not oauth_configured:
            status = "oauth_required"
        elif self.settings.agent_enabled and oauth_configured and not execution_verified:
            status = "configured_unverified"
        elif self.settings.agent_enabled and oauth_configured and execution_verified:
            status = "ready"
        worker = self._agent_worker_status()
        selected_model = self.settings.agent_model.strip()
        model_requires_gateway_loop = bool(
            selected_model
            and not selected_model.lower().startswith(("anthropic:", "claude:", "claude-", "anthropic-"))
        )
        gateway_loop_status = "not_required"
        if model_requires_gateway_loop:
            gateway_loop_status = "verified" if self.settings.agent_gateway_loop_verified else "not_checked"
        return {
            "status": status,
            "enabled": self.settings.agent_enabled,
            "oauth_configured": oauth_configured,
            "client_configured": bool(self.settings.agent_oauth_client_id),
            "scope": self.settings.agent_oauth_scope,
            "model_configured": bool(self.settings.agent_model),
            "model_requires_gateway_loop": model_requires_gateway_loop,
            "gateway_loop_status": gateway_loop_status,
            "binding_submit_verified": binding_submit_verified,
            "inline_execution_verified": inline_execution_verified,
            "execution_verified": execution_verified,
            "execution_ready": status == "ready",
            "citation_fixer_tools": list(self.settings.citation_fixer_tools),
            "citation_fixer_missing_tools": missing_tools,
            "binding_requirements": {
                "scope": "agent",
                "tools": list(GBRAIN_CITATION_FIXER_TOOLS),
                "source_bound": True,
                "slug_prefix_bound": True,
                "budget_bound": True,
            },
            "binding_status": (
                "execution_verified"
                if execution_verified
                else "inline_execution_verified"
                if inline_execution_verified
                else "submit_verified"
                if binding_submit_verified
                else "not_verified"
            ),
            "worker": worker,
            "timeout_seconds": self.settings.agent_timeout_seconds,
        }

    def _agent_worker_status(self) -> dict[str, Any]:
        config_path = self.settings.home_path / ".gbrain" / "config.json"
        if not config_path.exists():
            return {
                "engine": None,
                "config_exists": False,
                "persistent_worker_supported": None,
                "mode": "unknown",
                "reason": "gbrain config not found",
            }
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "engine": None,
                "config_exists": True,
                "persistent_worker_supported": None,
                "mode": "unknown",
                "reason": f"gbrain config unreadable: {exc}",
            }
        engine = str(config.get("engine") or "").strip().lower() or None
        if engine == "pglite":
            return {
                "engine": engine,
                "config_exists": True,
                "persistent_worker_supported": False,
                "mode": "inline_only",
                "reason": "GBrain jobs worker daemon is Postgres-only; PGLite uses inline/follow execution.",
            }
        if engine in {"postgres", "postgresql"}:
            return {
                "engine": engine,
                "config_exists": True,
                "persistent_worker_supported": True,
                "mode": "persistent_worker_supported",
                "reason": None,
            }
        return {
            "engine": engine,
            "config_exists": True,
            "persistent_worker_supported": None,
            "mode": "unknown",
            "reason": "unknown GBrain engine",
        }

    def maintenance_status(self) -> dict[str, Any]:
        doctor = self.doctor()
        status_snapshot = self.status_snapshot()
        jobs = self.list_jobs(limit=20)
        contradictions = self.find_contradictions(limit=20)
        onboard_check = self.maintenance_check(target_score=90)
        parts = [doctor, status_snapshot, jobs, contradictions, onboard_check]
        return {
            "ok": all(part.get("status") == "ok" for part in parts),
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "doctor": doctor,
            "doctor_summary": self._doctor_summary(doctor),
            "status_snapshot": status_snapshot,
            "jobs": jobs,
            "contradictions": contradictions,
            "onboard_check": onboard_check,
            "agent": self.agent_status(),
            "allowed_job_names": sorted(GBRAIN_MAINTENANCE_JOB_NAMES),
        }

    @staticmethod
    def _doctor_summary(response: dict[str, Any]) -> dict[str, Any]:
        if response.get("status") != "ok":
            return {
                "status": response.get("status"),
                "error": response.get("error"),
                "http_status": response.get("http_status"),
                "checks": [],
            }
        result = response.get("result")
        if not isinstance(result, dict):
            return {"status": "invalid_response", "checks": []}
        checks = result.get("checks") if isinstance(result.get("checks"), list) else []
        notable = [
            {
                "name": check.get("name"),
                "status": check.get("status"),
                "message": check.get("message"),
            }
            for check in checks
            if isinstance(check, dict) and check.get("status") in {"warn", "fail"}
        ][:8]
        return {
            "status": result.get("status"),
            "health_score": result.get("health_score"),
            "brain_checks_score": result.get("brain_checks_score"),
            "category_scores": result.get("category_scores"),
            "warning_or_failed_checks": notable,
            "check_count": len(checks),
        }

    @staticmethod
    def _readiness(
        service: dict[str, Any],
        company_source: dict[str, Any],
        local_config: dict[str, Any],
        environment: dict[str, Any],
    ) -> dict[str, Any]:
        errors: list[str] = []
        warnings: list[str] = []
        if service.get("status") != "ok":
            errors.append("GBrain HTTP 服务不可用：请从管理员后台启动/重启，或运行 scripts/start-gbrain.ps1。")
        if not company_source.get("registered"):
            errors.append("company-wiki source 尚未注册到 GBrain。")
        elif not company_source.get("path_matches"):
            errors.append("company-wiki source 路径与 Project_R derived/ 目录不一致。")
        embedding = local_config.get("embedding") or {}
        if not embedding.get("semantic_search_ready"):
            reason = embedding.get("reason") or "embedding provider not ready"
            if embedding.get("provider") == "ollama":
                errors.append(f"Ollama embedding 不可用：确认 Ollama 已启动并已安装 mxbai-embed-large。原因：{reason}")
            else:
                errors.append(f"GBrain embedding 不可用：{reason}")
        for err in environment.get("errors", []):
            warnings.append(str(err))
        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
        }


def get_gbrain_health() -> dict[str, Any]:
    return GBrainAdapter().health()


def get_gbrain_admin_status() -> dict[str, Any]:
    return GBrainAdapter().admin_status()


def _source_id_segment(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized or fallback


def _project_source_display_name(workspace: Any) -> str:
    brand = str(getattr(workspace, "brand", "") or "").strip().upper()
    name = str(getattr(workspace, "name", "") or getattr(workspace, "slug", "") or "").strip()
    parts = ["Project_R", "Project"]
    if brand:
        parts.append(brand)
    if name:
        parts.append(name)
    return " ".join(parts)


def _first_number(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _source_status_from_snapshot(status_snapshot: dict[str, Any], source_id: str) -> dict[str, Any]:
    if status_snapshot.get("status") != "ok":
        return {}
    result = status_snapshot.get("result")
    if not isinstance(result, dict):
        return {}
    sync = result.get("sync")
    if not isinstance(sync, dict):
        return {}
    sources = sync.get("sources")
    if not isinstance(sources, list):
        return {}
    for source in sources:
        if isinstance(source, dict) and source.get("source_id") == source_id:
            return source
    return {}


def _mcp_tool_invocation_succeeded(response: dict[str, Any]) -> bool:
    if response.get("status") != "ok":
        return False
    result = response.get("result")
    if isinstance(result, dict) and result.get("error"):
        return False
    return True


def _oauth_token_error_is_missing_client(response: dict[str, Any]) -> bool:
    if response.get("status") == "ok":
        return False
    text = f"{response.get('error') or ''} {response.get('error_description') or ''}".lower()
    return any(marker in text for marker in ("client not found", "invalid_client", "invalid_grant"))


def _timestamp_for_ui(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return None


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _terminate_pid(pid: int) -> bool:
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return completed.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def _discover_gbrain_service_pids(settings: GBrainSettings) -> list[int]:
    port = str(settings.http_port)
    if os.name == "nt":
        script = (
            "$ErrorActionPreference='SilentlyContinue'; "
            "Get-CimInstance Win32_Process -Filter \"Name = 'bun.exe'\" | "
            "Where-Object { "
            "$_.CommandLine -like '*src*cli.ts*' -and "
            "$_.CommandLine -like '*serve*' -and "
            "$_.CommandLine -like '*--port*' -and "
            f"$_.CommandLine -like '*{port}*' "
            "} | Select-Object -ExpandProperty ProcessId"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return _parse_pid_lines(completed.stdout)

    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        command = parts[1]
        if "src/cli.ts" in command and "serve" in command and "--port" in command and port in command:
            pids.append(int(parts[0]))
    return pids


def _parse_pid_lines(value: str) -> list[int]:
    pids: list[int] = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            pids.append(int(stripped))
    return pids


def _should_retry_sync_with_service_restart(result: dict[str, Any]) -> bool:
    if result.get("status") == "ok":
        return False
    error = str(result.get("error") or "").lower()
    return any(
        marker in error
        for marker in (
            "pglite failed to initialize",
            "cannot connect to database",
            "database is locked",
            "timed out waiting for pglite lock",
            "could not acquire pglite lock",
            "resource busy",
        )
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
