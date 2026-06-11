from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from app.features.knowledge.gbrain import GBRAIN_MAINTENANCE_JOB_NAMES, GBrainAdapter, load_gbrain_settings


DEFAULT_DREAM_JOB_NAMES = ["autopilot-cycle"]
TERMINAL_JOB_STATUSES = {"completed", "failed", "dead", "cancelled", "canceled"}


def load_dream_cycle_config() -> dict[str, Any]:
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


def save_dream_cycle_config(updates: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    current = load_dream_cycle_config()
    merged = {**current, **updates}
    config = _normalize_config(merged, current.get("source_id") or load_gbrain_settings().company_source_id)
    config["updated_at"] = _now()
    if actor:
        config["updated_by"] = actor
    config["next_run_at"] = _next_run_at(config)
    _write_config(config)
    return {**config, "path": str(_config_path().resolve())}


def run_dream_cycle(*, force: bool = False, actor: str = "") -> dict[str, Any]:
    config = load_dream_cycle_config()
    due = _is_due(config)
    if not force and not config.get("enabled"):
        return {"ok": True, "status": "disabled", "ran": False, "due": due, "config": config}
    if not force and not due:
        return {"ok": True, "status": "not_due", "ran": False, "due": False, "config": config}

    adapter = GBrainAdapter()
    target_score = int(config.get("target_score") or 90)
    maintain_check = adapter.maintenance_check(target_score=target_score)
    job_results: list[dict[str, Any]] = []
    source_id = str(config.get("source_id") or load_gbrain_settings().company_source_id)
    ran_at = _now()
    tracked_jobs = list(config.get("tracked_jobs") or [])
    for name in config.get("job_names") or DEFAULT_DREAM_JOB_NAMES:
        job_result = adapter.submit_job(
            name=str(name),
            data=_job_data(str(name), source_id=source_id),
            queue="maintenance",
            priority=5,
            max_attempts=2,
        )
        job_results.append({"name": name, "result": job_result})
        tracked = _tracked_job_from_submit_result(str(name), job_result, submitted_at=ran_at)
        if tracked:
            tracked_jobs.append(tracked)

    ok = _tool_ok(maintain_check) and all(_tool_ok(item["result"]) for item in job_results)
    result = {
        "ok": ok,
        "status": "ran" if ok else "failed",
        "ran": True,
        "due": due,
        "ran_at": ran_at,
        "forced": force,
        "actor": actor,
        "maintain_check": maintain_check,
        "jobs": job_results,
    }
    config["last_run_at"] = result["ran_at"]
    config["last_result"] = result
    config["tracked_jobs"] = _trim_tracked_jobs(tracked_jobs)
    config["next_run_at"] = _next_run_at(config)
    _write_config(config)
    return {**result, "config": {**config, "path": str(_config_path().resolve())}}


def run_dream_cycle_tick(*, actor: str = "system") -> dict[str, Any]:
    config = load_dream_cycle_config()
    if not config.get("enabled"):
        return {"ok": True, "status": "disabled", "ran": False, "due": False, "config": config}
    if not _is_due(config):
        return {"ok": True, "status": "not_due", "ran": False, "due": False, "config": config}
    return run_dream_cycle(force=False, actor=actor)


def poll_dream_cycle_jobs(*, actor: str = "system") -> dict[str, Any]:
    config = load_dream_cycle_config()
    tracked_jobs = [item for item in config.get("tracked_jobs") or [] if isinstance(item, dict)]
    if not tracked_jobs:
        return {"ok": True, "status": "no_tracked_jobs", "checked": 0, "transitions": [], "config": config}

    adapter = GBrainAdapter()
    checked = 0
    transitions: list[dict[str, Any]] = []
    for item in tracked_jobs:
        job_id = _int_or_none(item.get("job_id"))
        if job_id is None:
            continue
        status_before = _normalize_status(item.get("status"))
        if status_before in TERMINAL_JOB_STATUSES and item.get("last_notified_status") == status_before:
            continue

        detail = adapter.get_job(job_id)
        checked += 1
        payload = _tool_payload(detail)
        status_after = _normalize_status(payload.get("status") if isinstance(payload, dict) else detail.get("status"))
        if status_after:
            item["status"] = status_after
        item["last_checked_at"] = _now()
        item["last_result"] = detail

        if status_after in TERMINAL_JOB_STATUSES and item.get("last_notified_status") != status_after:
            transition = {
                "job_id": job_id,
                "name": str(item.get("name") or ""),
                "status": status_after,
                "previous_status": status_before,
                "checked_at": item["last_checked_at"],
            }
            transitions.append(transition)
            item["last_notified_status"] = status_after

    config["tracked_jobs"] = _trim_tracked_jobs(tracked_jobs)
    config["last_job_poll_at"] = _now()
    config["last_job_poll_by"] = actor
    config["last_job_poll_result"] = {"checked": checked, "transitions": transitions}
    _write_config(config)
    return {
        "ok": True,
        "status": "polled",
        "checked": checked,
        "transitions": transitions,
        "config": {**config, "path": str(_config_path().resolve())},
    }


def _default_config(source_id: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "interval_hours": 168,
        "target_score": 90,
        "source_id": source_id,
        "job_names": DEFAULT_DREAM_JOB_NAMES,
        "last_run_at": None,
        "last_result": None,
        "tracked_jobs": [],
        "last_job_poll_at": None,
        "last_job_poll_by": "",
        "last_job_poll_result": None,
        "updated_at": None,
        "updated_by": "",
    }


def _normalize_config(data: dict[str, Any], fallback_source_id: str) -> dict[str, Any]:
    job_names = [
        str(name).strip()
        for name in data.get("job_names", DEFAULT_DREAM_JOB_NAMES)
        if str(name).strip() in GBRAIN_MAINTENANCE_JOB_NAMES
    ]
    return {
        "enabled": bool(data.get("enabled")),
        "interval_hours": max(1, min(int(data.get("interval_hours") or 168), 24 * 90)),
        "target_score": max(1, min(int(data.get("target_score") or 90), 100)),
        "source_id": str(data.get("source_id") or fallback_source_id).strip() or fallback_source_id,
        "job_names": job_names or DEFAULT_DREAM_JOB_NAMES,
        "last_run_at": data.get("last_run_at") or None,
        "last_result": data.get("last_result") if isinstance(data.get("last_result"), dict) else None,
        "tracked_jobs": _normalize_tracked_jobs(data.get("tracked_jobs")),
        "last_job_poll_at": data.get("last_job_poll_at") or None,
        "last_job_poll_by": str(data.get("last_job_poll_by") or ""),
        "last_job_poll_result": data.get("last_job_poll_result") if isinstance(data.get("last_job_poll_result"), dict) else None,
        "updated_at": data.get("updated_at") or None,
        "updated_by": str(data.get("updated_by") or ""),
    }


def _config_path() -> Path:
    settings = load_gbrain_settings()
    return settings.manifests_path / "gbrain-dream-cycle.json"


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


def _job_data(name: str, *, source_id: str) -> dict[str, Any]:
    if name == "sync":
        return {"sourceId": source_id, "noPull": True, "noEmbed": False}
    if name == "embed":
        return {"all": True}
    if name == "lint":
        return {"dryRun": True, "sourceId": source_id}
    if name == "backlinks":
        return {"action": "check", "dryRun": True, "sourceId": source_id}
    if name == "autopilot-cycle":
        return {"sourceId": source_id, "mode": "scheduled"}
    return {"sourceId": source_id}


def _tool_ok(result: dict[str, Any]) -> bool:
    return result.get("status") == "ok" and not (isinstance(result.get("result"), dict) and result["result"].get("error"))


def _tracked_job_from_submit_result(name: str, result: dict[str, Any], *, submitted_at: str) -> dict[str, Any] | None:
    job_id = _extract_job_id(result)
    if job_id is None:
        return None
    payload = _tool_payload(result)
    status = _normalize_status(payload.get("status") if isinstance(payload, dict) else result.get("status")) or "submitted"
    return {
        "job_id": job_id,
        "name": name,
        "status": status,
        "submitted_at": submitted_at,
        "last_checked_at": None,
        "last_notified_status": "",
    }


def _extract_job_id(result: dict[str, Any]) -> int | None:
    payload = _tool_payload(result)
    if isinstance(payload, dict):
        for key in ("id", "job_id", "jobId"):
            value = _int_or_none(payload.get(key))
            if value is not None:
                return value
    for key in ("id", "job_id", "jobId"):
        value = _int_or_none(result.get(key))
        if value is not None:
            return value
    return None


def _tool_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    payload = result.get("result")
    if isinstance(payload, dict):
        return payload
    return None


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _normalize_tracked_jobs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        job_id = _int_or_none(item.get("job_id"))
        if job_id is None:
            continue
        normalized.append(
            {
                "job_id": job_id,
                "name": str(item.get("name") or ""),
                "status": _normalize_status(item.get("status")) or "unknown",
                "submitted_at": item.get("submitted_at") or None,
                "last_checked_at": item.get("last_checked_at") or None,
                "last_notified_status": _normalize_status(item.get("last_notified_status")),
                "last_result": item.get("last_result") if isinstance(item.get("last_result"), dict) else None,
            }
        )
    return _trim_tracked_jobs(normalized)


def _trim_tracked_jobs(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return value[-100:]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
