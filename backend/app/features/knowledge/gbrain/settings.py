from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is a declared dependency.
    load_dotenv = None  # type: ignore[assignment]

BASE_DIR = Path(__file__).resolve().parents[4]
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_BACKEND_ENV_PATH = BASE_DIR / ".env"
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
_DOTENV_LOADED_PATHS: set[Path] = set()


def ensure_gbrain_dotenv_loaded(env_path: Path | None = None) -> None:
    """Load backend .env before reading GBrain settings.

    FastAPI loads .env in main.py, but scripts and direct adapter imports do not
    pass through main.py. Keep this at the adapter seam so GBrain CLI/scripts and
    tests see the same auth configuration as the running backend.
    """
    if os.getenv("GBRAIN_DOTENV_AUTOLOAD", "true").strip().lower() in {"0", "false", "no", "off"}:
        return
    path = (env_path or DEFAULT_BACKEND_ENV_PATH).resolve()
    if path in _DOTENV_LOADED_PATHS:
        return
    _DOTENV_LOADED_PATHS.add(path)
    if load_dotenv is None or not path.exists():
        return
    load_dotenv(path, override=False)


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

def load_gbrain_settings() -> GBrainSettings:
    ensure_gbrain_dotenv_loaded()
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
