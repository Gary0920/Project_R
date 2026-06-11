from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from os import getenv
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.schemas import UTCDateTimeModel
from models import BASE_DIR, get_db
from models.audit_log import AuditLog
from models.client_update import ClientUpdateRelease
from models.user import User

router = APIRouter(prefix="/updates", tags=["updates"])


def _resolve_update_root() -> Path:
    raw = getenv("UPDATE_PACKAGES_PATH", "./update_packages")
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


UPDATE_PACKAGES_ROOT = _resolve_update_root()


class ClientUpdateInfo(UTCDateTimeModel):
    id: int
    version: str
    platform: str
    release_notes: str
    minimum_supported_version: str
    is_force_update: bool
    size_bytes: int
    sha256: str
    filename: str
    download_url: str
    is_active: bool
    created_at: datetime


class LatestClientUpdateResponse(BaseModel):
    update_available: bool
    current_version: str = ""
    latest: ClientUpdateInfo | None = None


class ClientUpdateReleaseListResponse(BaseModel):
    items: list[ClientUpdateInfo]


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")


def _safe_segment(value: str, *, fallback: str = "package") -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-_")
    return safe or fallback


def _version_key(version: str) -> tuple[int, ...]:
    cleaned = version.strip().lstrip("vV")
    values: list[int] = []
    for part in re.split(r"[.\-_+]", cleaned):
        match = re.match(r"(\d+)", part)
        values.append(int(match.group(1)) if match else -1)
    while len(values) < 4:
        values.append(0)
    return tuple(values)


def _compare_versions(left: str, right: str) -> int:
    left_key = _version_key(left)
    right_key = _version_key(right)
    if left_key == right_key:
        return 0
    return 1 if left_key > right_key else -1


def _latest_release(db: Session, platform: str) -> ClientUpdateRelease | None:
    releases = (
        db.query(ClientUpdateRelease)
        .filter(ClientUpdateRelease.platform == platform, ClientUpdateRelease.is_active == True)
        .all()
    )
    if not releases:
        return None
    return sorted(releases, key=lambda item: (_version_key(item.version), item.id or 0), reverse=True)[0]


def _download_url(release: ClientUpdateRelease) -> str:
    return f"/updates/download/{quote(release.version, safe='')}?platform={quote(release.platform, safe='')}"


def _to_update_info(release: ClientUpdateRelease, current_version: str = "") -> ClientUpdateInfo:
    force_update = bool(release.is_force_update)
    if current_version and release.minimum_supported_version:
        force_update = force_update or _compare_versions(current_version, release.minimum_supported_version) < 0
    return ClientUpdateInfo(
        version=release.version,
        id=release.id,
        platform=release.platform,
        release_notes=release.release_notes,
        minimum_supported_version=release.minimum_supported_version,
        is_force_update=force_update,
        size_bytes=release.size_bytes,
        sha256=release.sha256,
        filename=release.filename,
        download_url=_download_url(release),
        is_active=bool(release.is_active),
        created_at=release.created_at,
    )


def _assert_under_root(path: Path, root: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="更新包路径非法")


@router.get("/latest", response_model=LatestClientUpdateResponse)
def get_latest_update(
    current_version: str = Query("", max_length=64),
    platform: str = Query("win32", max_length=32),
    db: Session = Depends(get_db),
):
    normalized_platform = _safe_segment(platform, fallback="win32")
    release = _latest_release(db, normalized_platform)
    if not release:
        return LatestClientUpdateResponse(update_available=False, current_version=current_version, latest=None)
    available = True
    if current_version:
        available = _compare_versions(current_version, release.version) < 0
    return LatestClientUpdateResponse(
        update_available=available,
        current_version=current_version,
        latest=_to_update_info(release, current_version=current_version),
    )


@router.get("/download/{version}")
def download_update_package(
    version: str,
    platform: str = Query("win32", max_length=32),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_platform = _safe_segment(platform, fallback="win32")
    release = (
        db.query(ClientUpdateRelease)
        .filter(
            ClientUpdateRelease.platform == normalized_platform,
            ClientUpdateRelease.version == version,
            ClientUpdateRelease.is_active == True,
        )
        .first()
    )
    if not release:
        raise HTTPException(status_code=404, detail="更新包不存在")
    path = Path(release.file_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="更新包文件不存在，请联系管理员")
    _assert_under_root(path, UPDATE_PACKAGES_ROOT)
    return FileResponse(path, media_type="application/octet-stream", filename=release.filename)


@router.get("/admin/releases", response_model=ClientUpdateReleaseListResponse)
def list_update_releases(
    platform: str = Query("win32", max_length=32),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    normalized_platform = _safe_segment(platform, fallback="win32")
    releases = (
        db.query(ClientUpdateRelease)
        .filter(ClientUpdateRelease.platform == normalized_platform)
        .all()
    )
    releases = sorted(releases, key=lambda item: (_version_key(item.version), item.id or 0), reverse=True)
    return ClientUpdateReleaseListResponse(items=[_to_update_info(item) for item in releases])


@router.post("/admin/releases", response_model=ClientUpdateInfo)
async def upload_update_release(
    version: str = Form(..., max_length=64),
    release_notes: str = Form("", max_length=20000),
    minimum_supported_version: str = Form("", max_length=64),
    platform: str = Form("win32", max_length=32),
    is_force_update: bool = Form(False),
    is_active: bool = Form(True),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(user)
    normalized_version = version.strip().lstrip("vV")
    if not normalized_version:
        raise HTTPException(status_code=400, detail="版本号不能为空")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", normalized_version):
        raise HTTPException(status_code=400, detail="版本号只能包含字母、数字、点、横线和下划线")
    normalized_platform = _safe_segment(platform, fallback="win32")
    safe_version = _safe_segment(normalized_version, fallback="version")
    original_filename = _safe_segment(file.filename or f"Project_R-{safe_version}.exe")

    target_dir = UPDATE_PACKAGES_ROOT / normalized_platform / safe_version
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / original_filename
    _assert_under_root(target_path, UPDATE_PACKAGES_ROOT)

    hasher = hashlib.sha256()
    size_bytes = 0
    with target_path.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            hasher.update(chunk)
            output.write(chunk)

    if size_bytes <= 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="更新包不能为空")

    release = (
        db.query(ClientUpdateRelease)
        .filter(ClientUpdateRelease.platform == normalized_platform, ClientUpdateRelease.version == normalized_version)
        .first()
    )
    now = datetime.now(timezone.utc)
    if release:
        old_path = Path(release.file_path)
        if old_path != target_path and old_path.exists():
            old_path.unlink()
        release.updated_at = now
    else:
        release = ClientUpdateRelease(
            platform=normalized_platform,
            version=normalized_version,
            created_by=user.id,
            created_at=now,
        )
        db.add(release)

    release.filename = original_filename
    release.file_path = str(target_path)
    release.sha256 = hasher.hexdigest()
    release.size_bytes = size_bytes
    release.release_notes = release_notes.strip()
    release.minimum_supported_version = minimum_supported_version.strip().lstrip("vV")
    release.is_force_update = is_force_update
    release.is_active = is_active
    db.add(
        AuditLog(
            user_id=user.id,
            action="client_update_publish",
            detail=f"{normalized_platform}:{normalized_version}:{original_filename}:{size_bytes}",
            success=True,
        )
    )
    db.commit()
    db.refresh(release)
    return _to_update_info(release)
