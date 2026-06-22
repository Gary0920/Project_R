from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from app.features.workspaces.files.service import DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS, TRASH_DIRNAME
from models.workspace import Workspace

DEFAULT_WORKSPACES_ROOT = Path(__file__).resolve().parents[4] / "workspace_data"
DEFAULT_PROJECT_ROOT_NAME = "project"
DEFAULT_CUSTOMER_ROOT_NAME = "customer"
DEFAULT_PROJECT_BRANDS = ("AURA", "BFI", "SPECWISE", "SYNOVA")
DEFAULT_CUSTOMER_BRAND = "CUSTOMER"
DEFAULT_CRM_WORKSPACE_SLUG = "CRM"
DEFAULT_CRM_RAW_DIR = "raw"


@dataclass(frozen=True)
class WorkspaceStorageConfig:
    workspaces_root: Path
    project_root_name: str
    customer_root_name: str
    project_brands: tuple[str, ...]
    customer_brand: str
    crm_workspace_slug: str
    crm_raw_dir: str


def default_workspace_storage_config() -> WorkspaceStorageConfig:
    return WorkspaceStorageConfig(
        workspaces_root=DEFAULT_WORKSPACES_ROOT,
        project_root_name=DEFAULT_PROJECT_ROOT_NAME,
        customer_root_name=DEFAULT_CUSTOMER_ROOT_NAME,
        project_brands=DEFAULT_PROJECT_BRANDS,
        customer_brand=DEFAULT_CUSTOMER_BRAND,
        crm_workspace_slug=DEFAULT_CRM_WORKSPACE_SLUG,
        crm_raw_dir=DEFAULT_CRM_RAW_DIR,
    )


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w一-鿿-]", "-", name.strip()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "workspace"


def safe_username(username: str) -> str:
    return slugify(username).replace("/", "-") or "user"


def project_brand_dirs(config: WorkspaceStorageConfig) -> list[tuple[str, Path]]:
    project_root = (config.workspaces_root / config.project_root_name).resolve()
    entries: dict[str, Path] = {}
    for brand in config.project_brands:
        entries[brand] = (project_root / brand).resolve()
    if project_root.exists():
        for child in project_root.iterdir():
            if child.is_dir() and not child.is_symlink():
                normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", child.name.strip()).strip("-._")
                if normalized:
                    entries[normalized.upper()] = child.resolve()
    return sorted(entries.items(), key=lambda item: item[0])


def project_brand_names(config: WorkspaceStorageConfig) -> list[str]:
    names = set(config.project_brands)
    for brand, _ in project_brand_dirs(config):
        names.add(brand)
    return sorted(names)


def normalize_brand(brand: str, config: WorkspaceStorageConfig) -> str:
    normalized = brand.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,63}", normalized or ""):
        raise HTTPException(status_code=400, detail="项目品牌不合法")
    if normalized not in project_brand_names(config):
        raise HTTPException(status_code=400, detail="项目品牌不合法")
    return normalized


def normalize_workspace_kind(kind: str | None, brand: str | None, config: WorkspaceStorageConfig) -> str:
    normalized = (kind or "").strip().lower()
    if (brand or "").strip().upper() == config.customer_brand:
        normalized = "customer"
    if not normalized:
        normalized = "project"
    if normalized not in {"project", "customer"}:
        raise HTTPException(status_code=400, detail="工作区类型不合法")
    return normalized


def workspace_dirs(workspace: Workspace, config: WorkspaceStorageConfig) -> tuple[str, ...]:
    if workspace.workspace_kind == "project":
        return DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS
    if workspace.workspace_kind == "customer":
        return (config.crm_raw_dir,)
    return ()


def is_trash_relative_path(path: Path) -> bool:
    return bool(path.parts) and path.parts[0] == TRASH_DIRNAME


def ensure_not_trash_path(path: Path) -> None:
    if is_trash_relative_path(path):
        raise HTTPException(status_code=400, detail="回收站不能作为普通文件夹操作")


def target_storage_path(workspace: Workspace, config: WorkspaceStorageConfig) -> Path:
    if workspace.workspace_kind == "user":
        return config.workspaces_root.resolve()
    if workspace.workspace_kind == "customer":
        return (config.workspaces_root / config.customer_root_name / config.crm_workspace_slug).resolve()
    brand = normalize_brand(workspace.brand or "BFI", config)
    return (config.workspaces_root / config.project_root_name / brand / workspace.slug).resolve()


def ensure_storage_path(
    workspace: Workspace,
    config: WorkspaceStorageConfig,
    *,
    create_user_scaffold: bool = False,
) -> str:
    if workspace.workspace_kind == "user":
        return ""
    root = config.workspaces_root.resolve()
    target = target_storage_path(workspace, config)
    path = Path(workspace.storage_path) if workspace.storage_path else target
    resolved = path.resolve()
    legacy_path = (config.workspaces_root / workspace.slug).resolve()
    if workspace.workspace_kind == "project" and resolved == legacy_path and legacy_path.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy_path), str(target))
        path = target
        resolved = target.resolve()
    if not resolved.is_relative_to(root) or (
        workspace.workspace_kind == "project"
        and not resolved.is_relative_to((config.workspaces_root / config.project_root_name).resolve())
    ):
        path = target
    if workspace.workspace_kind == "customer" and path.resolve() != target:
        path = target
    path.mkdir(parents=True, exist_ok=True)
    for dirname in workspace_dirs(workspace, config):
        (path / dirname).mkdir(parents=True, exist_ok=True)
    (path / TRASH_DIRNAME).mkdir(exist_ok=True)
    return str(path)


def workspace_file_root(workspace: Workspace, config: WorkspaceStorageConfig) -> Path:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不提供后端文件区")
    return Path(ensure_storage_path(workspace, config)).resolve()


def candidate_storage_path(slug: str, brand: str, workspace_kind: str, config: WorkspaceStorageConfig) -> Path:
    if workspace_kind == "customer":
        return (config.workspaces_root / config.customer_root_name / config.crm_workspace_slug).resolve()
    return (config.workspaces_root / config.project_root_name / brand / slug).resolve()
