from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request
import urllib.request

from .adapter_utils import first_number, source_status_from_snapshot, timestamp_for_ui
from .paths import ensure_gbrain_environment, resolve_gbrain_source_paths
from .settings import (
    DEFAULT_OLLAMA_BASE_URL,
    EMBEDDING_PROVIDER_CONFIG_KEY,
    EMBEDDING_PROVIDER_ENV,
    LOCAL_EMBEDDING_PROVIDERS,
)


class GBrainHealthMixin:
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
        sync_source = source_status_from_snapshot(status_snapshot, self.settings.company_source_id)
        page_count = first_number(sync_source, "pages", "page_count") or first_number(
            source, "page_count", "pages", "pageCount"
        )
        chunk_count = first_number(sync_source, "chunks_total", "chunk_count", "chunks") or first_number(
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
            "last_refresh": timestamp_for_ui(last_sync or manifest.get("finished_at")),
        }

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
