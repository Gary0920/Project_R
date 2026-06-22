from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def summary_from_results(results: Iterable[Any], *, status_keys: Iterable[str]) -> dict[str, int]:
    items = list(results)
    summary = {"total": len(items)}
    for status in status_keys:
        summary[status] = sum(1 for item in items if getattr(item, "status", None) == status)
    return summary


def status_summary_from_results(results: Iterable[Any], *, defaults: dict[str, int] | None = None) -> dict[str, int]:
    items = list(results)
    statuses = {str(getattr(item, "status", "")) for item in items if getattr(item, "status", "")}
    summary = {status: sum(1 for item in items if getattr(item, "status", None) == status) for status in sorted(statuses)}
    summary["total"] = len(items)
    if defaults:
        for key, value in defaults.items():
            summary[key] = value if key not in summary else summary[key]
    return summary


def manifest_item_from_result(result: Any, *, source_root: Path, target_root: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_file": relative_posix(result.source_path, source_root),
        "status": result.status,
        "source_sha256": result.source_sha256,
    }
    if result.target_path is not None:
        item["target_file"] = relative_posix(result.target_path, target_root)
    if result.error:
        item["error"] = result.error
    metadata = getattr(result, "metadata", {}) or {}
    item.update({key: value for key, value in metadata.items() if value not in (None, [], {})})
    return item


def write_manifest_with_git_status(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    repo_path: Path,
    local_git_enabled: bool,
    commit_changes: Callable[[Path, dict[str, Any], bool], dict[str, Any]],
) -> dict[str, Any]:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    git_status = commit_changes(repo_path, manifest["summary"], local_git_enabled)
    manifest["local_git"] = git_status
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
