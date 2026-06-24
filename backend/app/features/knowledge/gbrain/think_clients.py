from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request
import urllib.request

from .adapter_utils import oauth_token_error_is_missing_client
from .settings import CUSTOMER_INTELLIGENCE_SOURCE_ID, CUSTOMER_SOURCE_ID_PREFIX, PROJECT_SOURCE_ID_PREFIX


class GBrainThinkClientMixin:
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
            if not oauth_token_error_is_missing_client(token_check):
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
