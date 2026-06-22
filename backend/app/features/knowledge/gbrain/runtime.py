from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request
import urllib.request

from .adapter_utils import discover_gbrain_service_pids, pid_exists, terminate_pid, utc_now


ApplyProviderEnv = Callable[[dict[str, str]], dict[str, str]]
EnsureEnvironment = Callable[[Any], dict[str, Any]]


class GBrainRuntime:
    def __init__(
        self,
        settings: Any,
        *,
        ensure_environment: EnsureEnvironment,
        apply_provider_env: ApplyProviderEnv,
        default_ollama_base_url: str,
    ):
        self.settings = settings
        self._ensure_environment = ensure_environment
        self._apply_provider_env = apply_provider_env
        self._default_ollama_base_url = default_ollama_base_url

    def probe_service_health(self) -> dict[str, Any]:
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
        record = self.read_service_record()
        pid = record.get("pid")
        discovered_pids = discover_gbrain_service_pids(self.settings.http_port)
        pid_alive = pid_exists(int(pid)) if isinstance(pid, int) else False
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
        self._ensure_environment(self.settings)
        current_health = self.probe_service_health()
        if current_health.get("status") == "ok":
            return {"ok": True, "status": "already_running", "service": current_health}
        self.clear_stale_pglite_state()

        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "missing_gbrain_cli",
                "error": f"GBrain CLI not found at {cli_file}",
            }

        env = self._apply_provider_env(os.environ.copy())
        env["GBRAIN_HOME"] = str(self.settings.home_path.resolve())
        env.setdefault("OLLAMA_BASE_URL", self._default_ollama_base_url)
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

        self.write_service_record(
            {
                "pid": process.pid,
                "started_at": utc_now(),
                "base_url": self.settings.base_url,
                "workdir": str(self.settings.cli_workdir.resolve()),
                "command": args,
                "log_path": str(self.settings.service_log_path.resolve()),
            }
        )
        time.sleep(1.5)
        service = self.probe_service_health()
        return {
            "ok": service.get("status") == "ok",
            "status": "started" if service.get("status") == "ok" else "started_but_not_ready",
            "pid": process.pid,
            "service": service,
            "log_path": str(self.settings.service_log_path.resolve()),
        }

    def stop_http_service(self) -> dict[str, Any]:
        record = self.read_service_record()
        pid = record.get("pid")
        pids: list[int] = []
        if isinstance(pid, int) and pid_exists(pid):
            pids.append(pid)
        for discovered_pid in discover_gbrain_service_pids(self.settings.http_port):
            if discovered_pid not in pids:
                pids.append(discovered_pid)

        if not pids:
            if isinstance(pid, int):
                self.delete_service_record()
                return {"ok": True, "status": "stale_record_removed", "pid": pid}
            return {"ok": True, "status": "no_project_r_managed_process"}

        stopped: list[int] = []
        failed: list[int] = []
        for target_pid in pids:
            terminated = terminate_pid(target_pid)
            if terminated:
                stopped.append(target_pid)
            else:
                failed.append(target_pid)
        time.sleep(0.8)
        still_alive = [target_pid for target_pid in pids if pid_exists(target_pid)]
        ok = not failed and not still_alive
        if ok:
            self.delete_service_record()
            self.clear_stale_pglite_state()
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

    def read_service_record(self) -> dict[str, Any]:
        path = self.settings.service_record_path
        if not path.exists():
            return {}
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}
        return record if isinstance(record, dict) else {}

    def write_service_record(self, record: dict[str, Any]) -> None:
        self.settings.manifests_path.mkdir(parents=True, exist_ok=True)
        self.settings.service_record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete_service_record(self) -> None:
        try:
            self.settings.service_record_path.unlink(missing_ok=True)
        except OSError:
            pass

    def clear_stale_pglite_state(self) -> None:
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
                lock_pid_alive = isinstance(lock_pid, int) and pid_exists(lock_pid)
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
