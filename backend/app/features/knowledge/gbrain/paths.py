from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapter_utils import ensure_directory, ensure_local_git_repo, path_status
from .settings import (
    BASE_DIR,
    CRM_CUSTOMER_SLUG,
    CRM_CUSTOMER_SOURCE_ID,
    CUSTOMER_SOURCE_ID_PREFIX,
    DEFAULT_PREPROCESSED_ROOT,
    GBrainSettings,
    PROJECT_SOURCE_ID_MAX_LENGTH,
    PROJECT_SOURCE_ID_PREFIX,
    _env_path,
    load_gbrain_settings,
)

@dataclass(frozen=True)
class GBrainSourcePaths:
    source_scope: str
    source_id: str
    raw: Path
    gbrain_ready: Path
    runs: Path
    manifests: Path
    preprocessed_root: Path
    legacy_derived: Path | None = None
    legacy_manifests: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_scope": self.source_scope,
            "source_id": self.source_id,
            "raw": self.raw,
            "gbrain_ready": self.gbrain_ready,
            "runs": self.runs,
            "manifests": self.manifests,
            "preprocessed_root": self.preprocessed_root,
        }
        if self.legacy_derived is not None:
            payload["legacy_derived"] = self.legacy_derived
        if self.legacy_manifests is not None:
            payload["legacy_manifests"] = self.legacy_manifests
        return payload

def ensure_gbrain_environment(settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    source_paths = resolve_gbrain_source_paths("company", settings=settings)
    errors: list[str] = []

    for path in (
        source_paths.raw,
        source_paths.gbrain_ready,
        source_paths.runs,
        source_paths.manifests,
        settings.manifests_path,
    ):
        ensure_directory(path, errors)

    git_status = ensure_local_git_repo(source_paths.gbrain_ready, settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")

    return {
        "ok": not errors,
        "source_id": settings.company_source_id,
        "gbrain_home": path_status(settings.home_path),
        "gbrain_config_dir": path_status(settings.home_path / ".gbrain"),
        "paths": {
            "raw": path_status(source_paths.raw),
            "gbrain_ready": path_status(source_paths.gbrain_ready),
            "runs": path_status(source_paths.runs),
            "manifests": path_status(source_paths.manifests),
            "legacy_derived": path_status(source_paths.legacy_derived or settings.derived_path),
            "legacy_manifests": path_status(source_paths.legacy_manifests or settings.manifests_path),
            # Compatibility key for older admin UI code; now points at gbrain-ready.
            "derived": path_status(source_paths.gbrain_ready),
            "migration_status": _gbrain_path_migration_status(source_paths.gbrain_ready, source_paths.legacy_derived),
        },
        "local_git": git_status,
        "errors": errors,
    }


def project_source_id_for_workspace(workspace: Any) -> str:
    workspace_id = getattr(workspace, "id", None)
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError("project workspace must be persisted before creating a GBrain source id")
    brand = _source_id_segment(str(getattr(workspace, "brand", "") or "project"), fallback="project")
    suffix = str(workspace_id)
    max_brand_len = PROJECT_SOURCE_ID_MAX_LENGTH - len(PROJECT_SOURCE_ID_PREFIX) - len(suffix) - 2
    brand = brand[: max(1, max_brand_len)].strip("-") or "project"
    return f"{PROJECT_SOURCE_ID_PREFIX}-{brand}-{suffix}"


def customer_source_id_for_workspace(workspace: Any) -> str:
    slug_value = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "").strip()
    if slug_value.casefold() == CRM_CUSTOMER_SLUG.casefold():
        return CRM_CUSTOMER_SOURCE_ID
    workspace_id = getattr(workspace, "id", None)
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError("customer workspace must be persisted before creating a GBrain source id")
    slug = _source_id_segment(str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer"), fallback="customer")
    suffix = str(workspace_id)
    max_slug_len = PROJECT_SOURCE_ID_MAX_LENGTH - len(CUSTOMER_SOURCE_ID_PREFIX) - len(suffix) - 2
    slug = slug[: max(1, max_slug_len)].strip("-") or "customer"
    return f"{CUSTOMER_SOURCE_ID_PREFIX}-{slug}-{suffix}"


def resolve_gbrain_source_paths(
    source_scope: str,
    *,
    workspace: Any | None = None,
    settings: GBrainSettings | None = None,
) -> GBrainSourcePaths:
    scope = source_scope.strip().lower().replace("_", "-")
    preprocessed_root = _env_path("GBRAIN_PREPROCESSED_ROOT", DEFAULT_PREPROCESSED_ROOT)
    if scope in {"company", "company-wiki", "global"}:
        settings = settings or load_gbrain_settings()
        root = _env_path(
            "GBRAIN_COMPANY_PREPROCESSED_ROOT",
            preprocessed_root / "company" / settings.company_source_id,
        )
        return GBrainSourcePaths(
            source_scope="company",
            source_id=settings.company_source_id,
            raw=settings.raw_path.resolve(),
            gbrain_ready=_env_path("GBRAIN_COMPANY_GBRAIN_READY_PATH", root / "gbrain-ready"),
            runs=_env_path("GBRAIN_COMPANY_PREPROCESS_RUNS_PATH", root / "runs"),
            manifests=_env_path("GBRAIN_COMPANY_PREPROCESS_MANIFESTS_PATH", root / "manifests"),
            preprocessed_root=root.resolve(),
            legacy_derived=(settings.raw_path.parent / "derived").resolve(),
            legacy_manifests=(settings.raw_path.parent / "manifests").resolve(),
        )
    if workspace is None:
        raise ValueError(f"{scope or 'source'} scope requires a workspace")
    if scope == "project":
        raw_root = _workspace_raw_root(workspace, "project")
        source_id = project_source_id_for_workspace(workspace)
        brand = _path_segment(str(getattr(workspace, "brand", "") or "BFI"), fallback="BFI").upper()
        slug = _path_segment(str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "project"), fallback="project")
        root = preprocessed_root / "project" / brand / f"{getattr(workspace, 'id')}-{slug}"
        return GBrainSourcePaths(
            source_scope="project",
            source_id=source_id,
            raw=raw_root,
            gbrain_ready=(root / "gbrain-ready").resolve(),
            runs=(root / "runs").resolve(),
            manifests=(root / "manifests").resolve(),
            preprocessed_root=root.resolve(),
            legacy_derived=(raw_root / "derived").resolve(),
            legacy_manifests=(raw_root / "manifests").resolve(),
        )
    if scope == "customer":
        raw_root = _workspace_raw_root(workspace, "customer")
        source_id = customer_source_id_for_workspace(workspace)
        slug_value = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "").strip()
        if slug_value.casefold() == CRM_CUSTOMER_SLUG.casefold():
            root = preprocessed_root / "customer" / "crm"
            return GBrainSourcePaths(
                source_scope="customer",
                source_id=source_id,
                raw=raw_root,
                gbrain_ready=(root / "gbrain-ready").resolve(),
                runs=(root / "runs").resolve(),
                manifests=(root / "manifests").resolve(),
                preprocessed_root=root.resolve(),
                legacy_derived=(raw_root / "derived").resolve(),
                legacy_manifests=(raw_root / "manifests").resolve(),
            )
        slug = _path_segment(
            str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer"),
            fallback="customer",
        )
        root = preprocessed_root / "customer" / f"{getattr(workspace, 'id')}-{slug}"
        return GBrainSourcePaths(
            source_scope="customer",
            source_id=source_id,
            raw=raw_root,
            gbrain_ready=(root / "gbrain-ready").resolve(),
            runs=(root / "runs").resolve(),
            manifests=(root / "manifests").resolve(),
            preprocessed_root=root.resolve(),
            legacy_derived=(raw_root / "derived").resolve(),
            legacy_manifests=(raw_root / "manifests").resolve(),
        )
    raise ValueError(f"unsupported GBrain source scope: {source_scope}")


def _warn_if_source_repo_scope_mismatch(
    *,
    source_id: str,
    repo_path: Path,
    settings: GBrainSettings,
) -> None:
    """Log a warning when source_id and repo_path appear to belong to different scopes.

    This is a soft check — it does not raise.  The hard guard lives in
    sync_source(), which refuses to default repo_path for non-company sources.
    """
    import logging
    _log = logging.getLogger("gbrain.adapter")

    company_repo = resolve_gbrain_source_paths("company", settings=settings).gbrain_ready.resolve()
    repo = repo_path.resolve()

    is_project_source = source_id.startswith(f"{PROJECT_SOURCE_ID_PREFIX}-")
    is_customer_source = source_id.startswith(f"{CUSTOMER_SOURCE_ID_PREFIX}-")

    # Project source id pointing at company repo
    if is_project_source and str(repo) == str(company_repo):
        _log.warning(
            "Possible source/repo mismatch: source_id='%s' looks like a project "
            "source but repo_path points to the company gbrain-ready directory. "
            "Use sync_project_source() to ensure correct repo resolution.",
            source_id,
        )
    # Customer source id pointing at company repo
    elif is_customer_source and str(repo) == str(company_repo):
        _log.warning(
            "Possible source/repo mismatch: source_id='%s' looks like a customer "
            "source but repo_path points to the company gbrain-ready directory. "
            "Use sync_customer_source() to ensure correct repo resolution.",
            source_id,
        )


def _workspace_raw_root(workspace: Any, workspace_kind: str) -> Path:
    storage_path = str(getattr(workspace, "storage_path", "") or "").strip()
    if storage_path:
        return Path(storage_path).resolve()
    if workspace_kind == "project":
        brand = str(getattr(workspace, "brand", "") or "BFI").strip().upper() or "BFI"
        slug = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "project").strip() or "project"
        return (BASE_DIR / "workspace_data" / "project" / brand / slug).resolve()
    slug = str(getattr(workspace, "slug", "") or getattr(workspace, "name", "") or "customer").strip() or "customer"
    if slug.casefold() == CRM_CUSTOMER_SLUG.casefold():
        return (BASE_DIR / "workspace_data" / "customer" / CRM_CUSTOMER_SLUG).resolve()
    return (BASE_DIR / "workspace_data" / "customer" / slug).resolve()


def _path_segment(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized or fallback


def _gbrain_path_migration_status(gbrain_ready: Path, legacy_derived: Path | None) -> str:
    has_ready = gbrain_ready.exists() and any(gbrain_ready.iterdir())
    has_legacy = bool(legacy_derived and legacy_derived.exists() and any(legacy_derived.iterdir()))
    if has_ready and has_legacy:
        return "both_present"
    if has_ready:
        return "gbrain_ready"
    if has_legacy:
        return "legacy_only"
    return "empty"


def project_source_paths_for_workspace(workspace: Any) -> dict[str, Path]:
    resolved = resolve_gbrain_source_paths("project", workspace=workspace)
    return {
        "root": resolved.raw,
        "raw": resolved.raw,
        "derived": resolved.gbrain_ready,
        "gbrain_ready": resolved.gbrain_ready,
        "runs": resolved.runs,
        "manifests": resolved.manifests,
        "preprocessed_root": resolved.preprocessed_root,
        "legacy_derived": resolved.legacy_derived,
        "legacy_manifests": resolved.legacy_manifests,
    }


def customer_source_paths_for_workspace(workspace: Any) -> dict[str, Path]:
    resolved = resolve_gbrain_source_paths("customer", workspace=workspace)
    return {
        "root": resolved.raw,
        "raw": resolved.raw,
        "derived": resolved.gbrain_ready,
        "gbrain_ready": resolved.gbrain_ready,
        "runs": resolved.runs,
        "manifests": resolved.manifests,
        "preprocessed_root": resolved.preprocessed_root,
        "legacy_derived": resolved.legacy_derived,
        "legacy_manifests": resolved.legacy_manifests,
    }


def ensure_project_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    paths = project_source_paths_for_workspace(workspace)
    errors: list[str] = []
    for key in ("root", "derived", "runs", "manifests"):
        ensure_directory(paths[key], errors)
    git_status = ensure_local_git_repo(paths["derived"], settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")
    return {
        "ok": not errors,
        "source_id": project_source_id_for_workspace(workspace),
        "paths": {key: path_status(path) for key, path in paths.items()},
        "local_git": git_status,
        "errors": errors,
    }


def ensure_customer_gbrain_environment(workspace: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    paths = customer_source_paths_for_workspace(workspace)
    errors: list[str] = []
    for key in ("root", "derived", "runs", "manifests"):
        ensure_directory(paths[key], errors)
    git_status = ensure_local_git_repo(paths["derived"], settings.local_git_enabled)
    if git_status.get("error"):
        errors.append(f"local git: {git_status['error']}")
    return {
        "ok": not errors,
        "source_id": customer_source_id_for_workspace(workspace),
        "paths": {key: path_status(path) for key, path in paths.items()},
        "local_git": git_status,
        "errors": errors,
    }


def project_source_registration_plan(workspace: Any) -> dict[str, Any]:
    source_id = project_source_id_for_workspace(workspace)
    paths = project_source_paths_for_workspace(workspace)
    name = _project_source_display_name(workspace)
    return {
        "source_id": source_id,
        "name": name,
        "path": str(paths["derived"].resolve()),
        "gbrain_ready_path": str(paths["gbrain_ready"].resolve()),
        "legacy_derived_path": str(paths["legacy_derived"].resolve()) if paths.get("legacy_derived") else None,
        "migration_status": _gbrain_path_migration_status(paths["gbrain_ready"], paths.get("legacy_derived")),
        "federated": False,
        "operator_command": (
            f"gbrain sources add {source_id} "
            f"--path {paths['derived'].resolve()} "
            f"--name \"{name}\" --no-federated"
        ),
    }


def customer_source_registration_plan(workspace: Any) -> dict[str, Any]:
    source_id = customer_source_id_for_workspace(workspace)
    paths = customer_source_paths_for_workspace(workspace)
    name = f"Project_R Customer - {getattr(workspace, 'name', source_id)}"
    return {
        "source_id": source_id,
        "name": name,
        "path": str(paths["derived"].resolve()),
        "gbrain_ready_path": str(paths["gbrain_ready"].resolve()),
        "legacy_derived_path": str(paths["legacy_derived"].resolve()) if paths.get("legacy_derived") else None,
        "migration_status": _gbrain_path_migration_status(paths["gbrain_ready"], paths.get("legacy_derived")),
        "federated": False,
        "operator_command": (
            f"gbrain sources add {source_id} "
            f"--path {paths['derived'].resolve()} "
            f"--name \"{name}\" --no-federated"
        ),
    }

def _source_id_segment(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized or fallback


def _project_source_display_name(workspace: Any) -> str:
    brand = str(getattr(workspace, "brand", "") or "").strip().upper()
    name = str(getattr(workspace, "name", "") or getattr(workspace, "slug", "") or "").strip()
    parts = ["Project_R", "Project"]
    if brand:
        parts.append(brand)
    if name:
        parts.append(name)
    return " ".join(parts)
