from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from core.gbrain import GBrainAdapter, _apply_gbrain_provider_env, load_gbrain_settings


DEFAULT_PROBE_QUERIES = [
    "书面化原则是什么",
    "项目邮件相关规则是什么",
    "VMU 标准作业流程是什么",
]
TERMINAL_STATUS_OK = {"completed", "ok", "ran"}


def load_contradiction_probe_config() -> dict[str, Any]:
    settings = load_gbrain_settings()
    config = _default_config(settings.company_source_id)
    path = _config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config.update(_normalize_config(data, settings.company_source_id))
        except (OSError, json.JSONDecodeError):
            config["config_error"] = "failed_to_read_config"
    config["next_run_at"] = _next_run_at(config)
    config["path"] = str(path.resolve())
    return config


def save_contradiction_probe_config(updates: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    current = load_contradiction_probe_config()
    merged = {**current, **updates}
    config = _normalize_config(merged, current.get("source_id") or load_gbrain_settings().company_source_id)
    config["updated_at"] = _now()
    if actor:
        config["updated_by"] = actor
    config["next_run_at"] = _next_run_at(config)
    _write_config(config)
    return {**config, "path": str(_config_path().resolve())}


def run_contradiction_probe(*, force: bool = False, actor: str = "") -> dict[str, Any]:
    config = load_contradiction_probe_config()
    due = _is_due(config)
    if not force and not config.get("enabled"):
        return {"ok": True, "status": "disabled", "ran": False, "due": due, "config": config}
    if not force and not due:
        return {"ok": True, "status": "not_due", "ran": False, "due": False, "config": config}

    queries = [str(item).strip() for item in config.get("queries") or [] if str(item).strip()]
    if not queries:
        return {"ok": False, "status": "no_queries", "ran": False, "due": due, "config": config}

    ran_at = _now()
    probe = _run_gbrain_contradiction_probe_cli(
        queries=queries,
        top_k=int(config.get("top_k") or 5),
        budget_usd=float(config.get("budget_usd") or 1.0),
        judge_model=str(config.get("judge_model") or "").strip() or None,
        timeout_seconds=int(config.get("timeout_seconds") or 600),
    )
    latest = GBrainAdapter().find_contradictions(limit=int(config.get("result_limit") or 20)) if probe.get("ok") else None
    summary = _summarize_probe_output(probe.get("json"))
    ok = bool(probe.get("ok"))
    result = {
        "ok": ok,
        "status": "ran" if ok else probe.get("status") or "failed",
        "ran": True,
        "due": due,
        "ran_at": ran_at,
        "actor": actor,
        "probe": probe,
        "summary": summary,
        "latest_contradictions": latest,
    }
    config["last_run_at"] = ran_at
    config["last_result"] = _compact_result(result)
    config["last_summary"] = summary
    config["next_run_at"] = _next_run_at(config)
    _write_config(config)
    return {**result, "config": {**config, "path": str(_config_path().resolve())}}


def run_contradiction_probe_tick(*, actor: str = "system") -> dict[str, Any]:
    config = load_contradiction_probe_config()
    if not config.get("enabled"):
        return {"ok": True, "status": "disabled", "ran": False, "due": False, "config": config}
    if not _is_due(config):
        return {"ok": True, "status": "not_due", "ran": False, "due": False, "config": config}
    return run_contradiction_probe(force=False, actor=actor)


def _run_gbrain_contradiction_probe_cli(
    *,
    queries: list[str],
    top_k: int,
    budget_usd: float,
    judge_model: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    settings = load_gbrain_settings()
    cli = settings.cli_workdir / "src" / "cli.ts"
    if not cli.exists():
        return {"ok": False, "status": "cli_missing", "error": str(cli)}
    queries_file = _queries_file_path()
    queries_file.parent.mkdir(parents=True, exist_ok=True)
    queries_file.write_text(
        "\n".join(json.dumps({"query": query}, ensure_ascii=False) for query in queries) + "\n",
        encoding="utf-8",
    )
    command = [
        settings.bun_executable,
        "src/cli.ts",
        "eval",
        "suspected-contradictions",
        "run",
        "--queries-file",
        str(queries_file),
        "--top-k",
        str(max(1, min(top_k, 20))),
        "--budget-usd",
        str(max(0.01, budget_usd)),
        "--json",
        "--yes",
    ]
    if judge_model:
        command.extend(["--judge", judge_model])
    env = _apply_gbrain_provider_env(os.environ.copy())
    env["GBRAIN_HOME"] = str(settings.home_path)
    env["GBRAIN_NO_PROBE_PROMPT"] = "1"
    service_restart: dict[str, Any] | None = None
    adapter = GBrainAdapter(settings)
    service_status = adapter.service_process_status()
    service_running = bool(service_status.get("running") or service_status.get("discovered_pids"))
    if service_running:
        stopped = adapter.stop_http_service()
        service_restart = {"stopped": stopped}
    try:
        completed = _run_cli_command(
            command,
            cwd=settings.cli_workdir,
            env=env,
            timeout_seconds=max(30, timeout_seconds),
        )
    finally:
        if service_running:
            restarted = adapter.start_http_service()
            service_restart = {**(service_restart or {}), "restarted": restarted}
    stdout = str(completed.get("stdout") or "").strip()
    stderr = str(completed.get("stderr") or "").strip()
    parsed: Any = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "ok": completed.get("returncode") == 0 and isinstance(parsed, dict),
        "status": "completed" if completed.get("returncode") == 0 else "failed",
        "returncode": completed.get("returncode"),
        "json": parsed,
        "stdout": stdout[:4000],
        "stderr": stderr[:4000],
        "queries_file": str(queries_file.resolve()),
        "service_restart": service_restart,
        "command": _redacted_command(command),
    }


def _run_cli_command(command: list[str], *, cwd: Path, env: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or f"Timed out after {timeout_seconds}s",
        }


def _summarize_probe_output(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {"ok": False, "status": "missing_json"}
    per_query = report.get("per_query") if isinstance(report.get("per_query"), list) else []
    contradictions = []
    for item in per_query:
        if isinstance(item, dict) and isinstance(item.get("contradictions"), list):
            contradictions.extend([c for c in item["contradictions"] if isinstance(c, dict)])
    severity_counts: dict[str, int] = {}
    for finding in contradictions:
        severity = str(finding.get("severity") or "unknown").lower()
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    total = report.get("total_contradictions_flagged")
    if not isinstance(total, int):
        total = len(contradictions)
    return {
        "ok": True,
        "queries_evaluated": report.get("queries_evaluated") or len(per_query),
        "queries_with_contradiction": report.get("queries_with_contradiction"),
        "total_contradictions_flagged": total,
        "severity_counts": severity_counts,
        "prompt_version": report.get("prompt_version"),
    }


def _default_config(source_id: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "interval_hours": 168,
        "source_id": source_id,
        "queries": DEFAULT_PROBE_QUERIES,
        "top_k": 5,
        "budget_usd": 1.0,
        "judge_model": "",
        "timeout_seconds": 600,
        "result_limit": 20,
        "last_run_at": None,
        "last_result": None,
        "last_summary": None,
        "updated_at": None,
        "updated_by": "",
    }


def _normalize_config(data: dict[str, Any], fallback_source_id: str) -> dict[str, Any]:
    queries_raw = data.get("queries")
    if isinstance(queries_raw, str):
        queries = [line.strip() for line in queries_raw.splitlines() if line.strip()]
    elif isinstance(queries_raw, list):
        queries = [str(item).strip() for item in queries_raw if str(item).strip()]
    else:
        queries = list(DEFAULT_PROBE_QUERIES)
    return {
        "enabled": bool(data.get("enabled")),
        "interval_hours": max(1, min(_int(data.get("interval_hours"), 168), 24 * 90)),
        "source_id": str(data.get("source_id") or fallback_source_id).strip() or fallback_source_id,
        "queries": queries[:50],
        "top_k": max(1, min(_int(data.get("top_k"), 5), 20)),
        "budget_usd": max(0.01, min(_float(data.get("budget_usd"), 1.0), 100.0)),
        "judge_model": str(data.get("judge_model") or ""),
        "timeout_seconds": max(30, min(_int(data.get("timeout_seconds"), 600), 3600)),
        "result_limit": max(1, min(_int(data.get("result_limit"), 20), 100)),
        "last_run_at": data.get("last_run_at") or None,
        "last_result": data.get("last_result") if isinstance(data.get("last_result"), dict) else None,
        "last_summary": data.get("last_summary") if isinstance(data.get("last_summary"), dict) else None,
        "updated_at": data.get("updated_at") or None,
        "updated_by": str(data.get("updated_by") or ""),
    }


def _config_path() -> Path:
    return load_gbrain_settings().manifests_path / "gbrain-contradiction-probe.json"


def _queries_file_path() -> Path:
    return load_gbrain_settings().manifests_path / "gbrain-contradiction-probe-queries.jsonl"


def _write_config(config: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted = {key: value for key, value in config.items() if key != "path"}
    path.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_run_at(config: dict[str, Any]) -> str | None:
    last_run = _parse_time(config.get("last_run_at"))
    if not last_run:
        return None
    return (last_run + timedelta(hours=int(config.get("interval_hours") or 168))).isoformat()


def _is_due(config: dict[str, Any]) -> bool:
    if not config.get("enabled"):
        return False
    next_run = _parse_time(config.get("next_run_at"))
    return next_run is None or next_run <= datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result.get("ok"),
        "status": result.get("status"),
        "ran": result.get("ran"),
        "due": result.get("due"),
        "ran_at": result.get("ran_at"),
        "summary": result.get("summary"),
        "probe_status": (result.get("probe") or {}).get("status") if isinstance(result.get("probe"), dict) else None,
    }


def _redacted_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for item in command:
        if skip_next:
            redacted.append("***")
            skip_next = False
            continue
        redacted.append(item)
        if item in {"--judge"}:
            skip_next = True
    return redacted


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
