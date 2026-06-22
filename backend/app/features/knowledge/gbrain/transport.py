from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request
import urllib.request

from .adapter_utils import should_retry_sync_with_service_restart


ApplyProviderEnv = Callable[[dict[str, str]], dict[str, str]]


class GBrainTransport:
    def __init__(
        self,
        settings: Any,
        *,
        apply_provider_env: ApplyProviderEnv,
        default_ollama_base_url: str,
    ):
        self.settings = settings
        self._apply_provider_env = apply_provider_env
        self._default_ollama_base_url = default_ollama_base_url

    def call_mcp_tool(
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
                    "result": parse_mcp_tool_payload(raw),
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

    def sync_source_via_cli(
        self,
        *,
        source_id: str,
        full: bool,
        no_pull: bool,
        no_embed: bool,
        mcp_response: dict[str, Any],
        probe_service_health: Callable[[], dict[str, Any]],
        stop_http_service: Callable[[], dict[str, Any]],
        start_http_service: Callable[[], dict[str, Any]],
        clear_stale_pglite_state: Callable[[], None],
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

        env = self._gbrain_cli_env()
        if probe_service_health().get("status") == "ok":
            stopped = stop_http_service()
            if not stopped.get("ok"):
                restarted = start_http_service()
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
            clear_stale_pglite_state()
            try:
                result = self.run_sync_cli(args, env)
            finally:
                restarted = start_http_service()
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

        clear_stale_pglite_state()
        first = self.run_sync_cli(args, env)
        if first.get("status") == "ok" or not should_retry_sync_with_service_restart(first):
            return {**first, "method": "cli", "mcp_response": mcp_response}

        stopped = stop_http_service()
        clear_stale_pglite_state()
        retry = self.run_sync_cli(args, env)
        restarted = start_http_service()
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

    def run_cli_exclusive(
        self,
        args: list[str],
        *,
        reason: str,
        timeout: int,
        probe_service_health: Callable[[], dict[str, Any]],
        stop_http_service: Callable[[], dict[str, Any]],
        start_http_service: Callable[[], dict[str, Any]],
        clear_stale_pglite_state: Callable[[], None],
    ) -> dict[str, Any]:
        env = self._gbrain_cli_env()
        if probe_service_health().get("status") == "ok":
            stopped = stop_http_service()
            if not stopped.get("ok"):
                restarted = start_http_service()
                return {
                    "status": "cli_error",
                    "error": "Unable to stop GBrain HTTP service for exclusive CLI operation",
                    "service_restart": {
                        "reason": reason,
                        "stop": stopped,
                        "start": restarted,
                    },
                }
            clear_stale_pglite_state()
            try:
                result = self.run_gbrain_cli(args, env, timeout)
            finally:
                restarted = start_http_service()
            service_restart = {"reason": reason, "stop": stopped, "start": restarted}
            return {**result, "service_restart": service_restart}

        clear_stale_pglite_state()
        return self.run_gbrain_cli(args, env, timeout)

    def run_gbrain_cli(self, args: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
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

    def run_sync_cli(self, args: list[str], env: dict[str, str]) -> dict[str, Any]:
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

    def _gbrain_cli_env(self) -> dict[str, str]:
        env = self._apply_provider_env(os.environ.copy())
        env["GBRAIN_HOME"] = str(self.settings.home_path.resolve())
        env.setdefault("OLLAMA_BASE_URL", self._default_ollama_base_url)
        env.pop("DATABASE_URL", None)
        return env


def parse_mcp_tool_payload(raw: str) -> dict[str, Any]:
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
