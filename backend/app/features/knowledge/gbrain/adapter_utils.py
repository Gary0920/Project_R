from __future__ import annotations

import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def path_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "is_dir": path.is_dir(),
        "writable": path.exists() and os.access(path, os.W_OK),
    }


def ensure_directory(path: Path, errors: list[str]) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"{path}: {exc}")


def ensure_local_git_repo(path: Path, enabled: bool) -> dict[str, Any]:
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


def first_number(payload: dict[str, Any], *keys: str) -> int:
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


def source_status_from_snapshot(status_snapshot: dict[str, Any], source_id: str) -> dict[str, Any]:
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


def mcp_tool_invocation_succeeded(response: dict[str, Any]) -> bool:
    if response.get("status") != "ok":
        return False
    result = response.get("result")
    if isinstance(result, dict) and result.get("error"):
        return False
    return True


def oauth_token_error_is_missing_client(response: dict[str, Any]) -> bool:
    if response.get("status") == "ok":
        return False
    text = f"{response.get('error') or ''} {response.get('error_description') or ''}".lower()
    return any(marker in text for marker in ("client not found", "invalid_client", "invalid_grant"))


def timestamp_for_ui(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        return None


def pid_exists(pid: int) -> bool:
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
        if completed.stdout:
            return str(pid) in completed.stdout
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_pid(pid: int) -> bool:
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


def discover_gbrain_service_pids(http_port: int) -> list[int]:
    port = str(http_port)
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
        return parse_pid_lines(completed.stdout)

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


def parse_pid_lines(value: str) -> list[int]:
    pids: list[int] = []
    for line in value.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            pids.append(int(stripped))
    return pids


def should_retry_sync_with_service_restart(result: dict[str, Any]) -> bool:
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
