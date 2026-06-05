from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any

from core.gbrain import GBrainAdapter, load_gbrain_settings, resolve_gbrain_source_paths


TERMINAL_JOB_STATUSES = {"completed", "failed", "dead", "cancelled", "canceled"}
SUCCESS_JOB_STATUSES = {"completed"}


def load_citation_fixer_job_state() -> dict[str, Any]:
    path = _state_path()
    state = _default_state()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                state.update(_normalize_state(data))
        except (OSError, json.JSONDecodeError):
            state["state_error"] = "failed_to_read_state"
    state["path"] = str(path.resolve())
    return state


def record_citation_fixer_job(
    *,
    submit_result: dict[str, Any],
    page_slug: str | None,
    review_id: int | None,
    allowed_slug_prefixes: list[str],
    actor: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    job_id = _extract_job_id(submit_result)
    state = load_citation_fixer_job_state()
    if job_id is None:
        state["last_submit_without_job_id"] = {
            "submitted_at": _now(),
            "actor": actor,
            "status": submit_result.get("status"),
        }
        _write_state(state)
        return {**state, "tracked": False}

    settings = load_gbrain_settings()
    payload = _tool_payload(submit_result)
    status = _normalize_status(payload.get("status") if isinstance(payload, dict) else submit_result.get("status")) or "submitted"
    job = {
        "job_id": job_id,
        "name": "citation-fixer",
        "source_id": source_id or settings.company_source_id,
        "page_slug": page_slug or "",
        "review_id": review_id,
        "allowed_slug_prefixes": [str(item) for item in allowed_slug_prefixes],
        "status": status,
        "submitted_at": _now(),
        "submitted_by": actor,
        "last_checked_at": None,
        "last_notified_status": "",
        "last_result": submit_result,
        "reconcile": None,
    }
    jobs = [item for item in state.get("tracked_jobs") or [] if _int_or_none(item.get("job_id")) != job_id]
    jobs.append(job)
    state["tracked_jobs"] = _trim_jobs(jobs)
    _write_state(state)
    return {**state, "tracked": True, "tracked_job": job}


def poll_citation_fixer_jobs(*, actor: str = "system", adapter: GBrainAdapter | None = None) -> dict[str, Any]:
    state = load_citation_fixer_job_state()
    tracked_jobs = [item for item in state.get("tracked_jobs") or [] if isinstance(item, dict)]
    if not tracked_jobs:
        return {"ok": True, "status": "no_tracked_jobs", "checked": 0, "transitions": [], "state": state}

    adapter = adapter or GBrainAdapter()
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

        if status_after in SUCCESS_JOB_STATUSES:
            item["reconcile"] = reconcile_citation_fixer_sidecar(
                source_id=str(item.get("source_id") or load_gbrain_settings().company_source_id),
                page_slug=str(item.get("page_slug") or ""),
            )

        if status_after in TERMINAL_JOB_STATUSES and item.get("last_notified_status") != status_after:
            transition = {
                "job_id": job_id,
                "name": "citation-fixer",
                "source_id": str(item.get("source_id") or ""),
                "page_slug": str(item.get("page_slug") or ""),
                "review_id": item.get("review_id"),
                "status": status_after,
                "previous_status": status_before,
                "checked_at": item["last_checked_at"],
                "reconcile": item.get("reconcile"),
            }
            transitions.append(transition)
            item["last_notified_status"] = status_after

    state["tracked_jobs"] = _trim_jobs(tracked_jobs)
    state["last_job_poll_at"] = _now()
    state["last_job_poll_by"] = actor
    state["last_job_poll_result"] = {"checked": checked, "transitions": transitions}
    _write_state(state)
    return {
        "ok": True,
        "status": "polled",
        "checked": checked,
        "transitions": transitions,
        "state": {**state, "path": str(_state_path().resolve())},
    }


def rollback_citation_fixer_job(*, job_id: int, actor: str) -> dict[str, Any]:
    state = load_citation_fixer_job_state()
    jobs = [item for item in state.get("tracked_jobs") or [] if isinstance(item, dict)]
    target = next((item for item in jobs if _int_or_none(item.get("job_id")) == int(job_id)), None)
    if target is None:
        return {"ok": False, "status": "job_not_tracked", "job_id": job_id}

    existing = target.get("rollback") if isinstance(target.get("rollback"), dict) else None
    if existing and existing.get("ok"):
        return {"ok": True, "status": "already_rolled_back", "job_id": job_id, "rollback": existing, "state": state}

    reconcile = target.get("reconcile") if isinstance(target.get("reconcile"), dict) else {}
    git_info = reconcile.get("git") if isinstance(reconcile.get("git"), dict) else {}
    commit_hash = str(git_info.get("commit_hash") or "").strip()
    if not commit_hash:
        return {"ok": False, "status": "missing_reconcile_commit", "job_id": job_id}

    settings = load_gbrain_settings()
    if str(target.get("source_id") or settings.company_source_id) != settings.company_source_id:
        return {"ok": False, "status": "unsupported_source", "job_id": job_id, "source_id": target.get("source_id")}

    source_paths = resolve_gbrain_source_paths("company", settings=settings)
    sidecar_path = reconcile.get("sidecar") if isinstance(reconcile.get("sidecar"), str) else None
    cleanup_paths = [Path(sidecar_path)] if sidecar_path else []
    rollback = _revert_commit(
        source_paths.gbrain_ready,
        commit_hash,
        message=f"Revert GBrain citation-fixer job #{job_id}",
        cleanup_paths=cleanup_paths,
    )
    target["rollback"] = {
        **rollback,
        "job_id": job_id,
        "actor": actor,
        "rolled_back_at": _now(),
        "reverted_commit": commit_hash,
    }
    state["tracked_jobs"] = _trim_jobs(jobs)
    state["last_rollback_at"] = _now()
    state["last_rollback_by"] = actor
    state["last_rollback_result"] = target["rollback"]
    _write_state(state)
    return {
        "ok": bool(rollback.get("ok")),
        "status": "rolled_back" if rollback.get("ok") else rollback.get("status") or "rollback_failed",
        "job_id": job_id,
        "rollback": target["rollback"],
        "state": {**state, "path": str(_state_path().resolve())},
    }


def reconcile_citation_fixer_sidecar(*, source_id: str, page_slug: str) -> dict[str, Any]:
    if not page_slug:
        return {"ok": False, "status": "missing_page_slug"}
    settings = load_gbrain_settings()
    if source_id != settings.company_source_id:
        return {"ok": False, "status": "unsupported_source", "source_id": source_id}

    derived = resolve_gbrain_source_paths("company", settings=settings).gbrain_ready
    sidecar = _sidecar_path(derived, source_id=source_id, page_slug=page_slug)
    canonical = _canonical_path(derived, page_slug=page_slug)
    if not sidecar.exists():
        return {"ok": False, "status": "sidecar_missing", "sidecar": str(sidecar)}

    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(sidecar.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        sidecar.unlink()
        _remove_empty_parents(sidecar.parent, stop_at=derived / ".sources")
    except OSError:
        pass
    commit = _commit_paths(derived, [canonical, sidecar], message="Apply GBrain citation-fixer result")
    return {
        "ok": bool(commit.get("ok")),
        "status": "synced_to_gbrain_ready" if commit.get("ok") else "git_commit_failed",
        "canonical": str(canonical),
        "sidecar": str(sidecar),
        "git": commit,
    }


def _default_state() -> dict[str, Any]:
    return {
        "tracked_jobs": [],
        "last_job_poll_at": None,
        "last_job_poll_by": "",
        "last_job_poll_result": None,
        "last_rollback_at": None,
        "last_rollback_by": "",
        "last_rollback_result": None,
        "last_submit_without_job_id": None,
    }


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "tracked_jobs": _normalize_jobs(data.get("tracked_jobs")),
        "last_job_poll_at": data.get("last_job_poll_at") or None,
        "last_job_poll_by": str(data.get("last_job_poll_by") or ""),
        "last_job_poll_result": data.get("last_job_poll_result") if isinstance(data.get("last_job_poll_result"), dict) else None,
        "last_rollback_at": data.get("last_rollback_at") or None,
        "last_rollback_by": str(data.get("last_rollback_by") or ""),
        "last_rollback_result": data.get("last_rollback_result") if isinstance(data.get("last_rollback_result"), dict) else None,
        "last_submit_without_job_id": data.get("last_submit_without_job_id") if isinstance(data.get("last_submit_without_job_id"), dict) else None,
    }


def _state_path() -> Path:
    return load_gbrain_settings().manifests_path / "gbrain-citation-fixer-jobs.json"


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    persisted = {key: value for key, value in state.items() if key != "path"}
    path.write_text(json.dumps(persisted, ensure_ascii=False, indent=2), encoding="utf-8")


def _sidecar_path(derived: Path, *, source_id: str, page_slug: str) -> Path:
    return derived / ".sources" / source_id / Path(*page_slug.split("/")).with_suffix(".md")


def _canonical_path(derived: Path, *, page_slug: str) -> Path:
    return derived / Path(*page_slug.split("/")).with_suffix(".md")


def _commit_paths(repo: Path, paths: list[Path], *, message: str) -> dict[str, Any]:
    if not (repo / ".git").exists():
        return {"ok": False, "status": "no_git_repo", "error": f"{repo} is not a git repo"}
    rel_paths = [path.relative_to(repo).as_posix() for path in paths]
    add = subprocess.run(["git", "-C", str(repo), "add", "--", *rel_paths], text=True, capture_output=True, check=False)
    if add.returncode != 0:
        return {"ok": False, "status": "git_add_failed", "error": add.stderr.strip() or add.stdout.strip()}
    commit = subprocess.run(["git", "-C", str(repo), "commit", "-m", message], text=True, capture_output=True, check=False)
    if commit.returncode == 0:
        return {
            "ok": True,
            "status": "committed",
            "output": commit.stdout.strip(),
            "commit_hash": _git_head(repo),
            "created_commit": True,
        }
    output = f"{commit.stdout}\n{commit.stderr}".strip()
    if "nothing to commit" in output.lower():
        return {"ok": True, "status": "already_committed", "output": output, "created_commit": False}
    return {"ok": False, "status": "git_commit_failed", "error": output}


def _revert_commit(repo: Path, commit_hash: str, *, message: str, cleanup_paths: list[Path] | None = None) -> dict[str, Any]:
    if not (repo / ".git").exists():
        return {"ok": False, "status": "no_git_repo", "error": f"{repo} is not a git repo"}
    revert = subprocess.run(
        ["git", "-C", str(repo), "revert", "--no-edit", commit_hash],
        text=True,
        capture_output=True,
        check=False,
    )
    if revert.returncode != 0:
        return {
            "ok": False,
            "status": "git_revert_failed",
            "error": f"{revert.stdout}\n{revert.stderr}".strip(),
        }
    cleaned: list[str] = []
    for path in cleanup_paths or []:
        if repo.resolve() not in path.resolve().parents and path.resolve() != repo.resolve():
            continue
        if path.exists():
            path.unlink()
            cleaned.append(path.relative_to(repo).as_posix())
    if cleaned:
        add = subprocess.run(["git", "-C", str(repo), "add", "--", *cleaned], text=True, capture_output=True, check=False)
        if add.returncode != 0:
            return {
                "ok": False,
                "status": "git_cleanup_add_failed",
                "error": f"{add.stdout}\n{add.stderr}".strip(),
            }
    commit = subprocess.run(["git", "-C", str(repo), "commit", "--amend", "-m", message], text=True, capture_output=True, check=False)
    if commit.returncode != 0:
        return {
            "ok": False,
            "status": "git_amend_failed",
            "error": f"{commit.stdout}\n{commit.stderr}".strip(),
        }
    return {
        "ok": True,
        "status": "reverted",
        "output": f"{revert.stdout}\n{commit.stdout}".strip(),
        "commit_hash": _git_head(repo),
        "cleaned_paths": cleaned,
    }


def _git_head(repo: Path) -> str | None:
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True, capture_output=True, check=False)
    if head.returncode == 0:
        return head.stdout.strip()
    return None


def _remove_empty_parents(path: Path, *, stop_at: Path) -> None:
    stop_at = stop_at.resolve()
    current = path.resolve()
    while current != stop_at and stop_at in current.parents:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _normalize_jobs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    jobs: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        job_id = _int_or_none(item.get("job_id"))
        if job_id is None:
            continue
        jobs.append(
            {
                "job_id": job_id,
                "name": str(item.get("name") or "citation-fixer"),
                "source_id": str(item.get("source_id") or ""),
                "page_slug": str(item.get("page_slug") or ""),
                "review_id": item.get("review_id"),
                "allowed_slug_prefixes": [str(prefix) for prefix in item.get("allowed_slug_prefixes") or []],
                "status": _normalize_status(item.get("status")) or "unknown",
                "submitted_at": item.get("submitted_at") or None,
                "submitted_by": str(item.get("submitted_by") or ""),
                "last_checked_at": item.get("last_checked_at") or None,
                "last_notified_status": _normalize_status(item.get("last_notified_status")),
                "last_result": item.get("last_result") if isinstance(item.get("last_result"), dict) else None,
                "reconcile": item.get("reconcile") if isinstance(item.get("reconcile"), dict) else None,
                "rollback": item.get("rollback") if isinstance(item.get("rollback"), dict) else None,
            }
        )
    return _trim_jobs(jobs)


def _trim_jobs(value: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return value[-100:]


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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
