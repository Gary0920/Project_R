from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from app.features.workspaces.files.service import MEETING_SUBDIRS, meeting_parent_path


def validate_meeting_folder(
    *,
    workspace_kind: str,
    root: Path,
    folder_path: str,
    safe_relative_path: Callable[[str], Path],
    ensure_not_trash_path: Callable[[Path], None],
    resolve_workspace_child: Callable[[Path, Path], Path],
    not_found_detail: str = "会议文件夹不存在",
    missing_detail: str = "请选择会议文件夹",
) -> tuple[Path, Path]:
    folder_rel = safe_relative_path(folder_path)
    ensure_not_trash_path(folder_rel)
    folder_dir = resolve_workspace_child(root, folder_rel)
    if not folder_dir.exists() or not folder_dir.is_dir():
        raise HTTPException(status_code=400, detail=not_found_detail)
    missing = [sub for sub in MEETING_SUBDIRS if not (folder_dir / sub).is_dir()]
    if missing:
        raise HTTPException(status_code=400, detail=missing_detail)
    expected_parent = meeting_parent_path(workspace_kind)
    folder_posix = folder_rel.as_posix()
    if folder_posix != expected_parent and not folder_posix.startswith(expected_parent + "/"):
        raise HTTPException(status_code=400, detail=f"会议文件夹必须位于 {expected_parent}/ 下")
    return folder_rel, folder_dir
