import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from models.user import User
from models.workspace import WorkspaceFile, WorkspaceMember


DEFAULT_WORKSPACE_DIRS = (
    "01-合同与报价",
    "02-图纸与技术资料",
    "03-会议纪要",
    "04-变更与签证",
    "05-生产与发货",
    "06-现场与客诉",
    "99-未归档文件",
)
DEFAULT_USER_WORKSPACE_DIRS = ("对话文件", "固定文件")
DEFAULT_UNFILED_DIR = "99-未归档文件"
MAX_WORKSPACE_UPLOAD_MB = int(os.getenv("WORKSPACE_MAX_UPLOAD_MB", "100"))
MAX_WORKSPACE_ADMIN_UPLOAD_MB = int(os.getenv("WORKSPACE_ADMIN_MAX_UPLOAD_MB", "1024"))
MAX_WORKSPACE_UPLOAD_BYTES = MAX_WORKSPACE_UPLOAD_MB * 1024 * 1024
MAX_WORKSPACE_ADMIN_UPLOAD_BYTES = MAX_WORKSPACE_ADMIN_UPLOAD_MB * 1024 * 1024
TRASH_DIRNAME = ".trash"


def safe_name(name: str) -> str:
    cleaned = Path(name).name.strip()
    cleaned = re.sub(r"[^\w一-鿿.\-()（）\[\]【】 &]", "_", cleaned)
    return cleaned[:120] or "untitled"


def safe_relative_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/").strip("/")
    if not normalized:
        return Path("")
    rel = Path(normalized)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise HTTPException(status_code=400, detail="路径不合法")
    return rel


def resolve_workspace_child(root: Path, rel_path: Path) -> Path:
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise HTTPException(status_code=400, detail="路径不合法")
    if target.exists() and target.is_symlink():
        raise HTTPException(status_code=400, detail="不允许操作符号链接")
    return target


def member_can_mutate_file(member: WorkspaceMember, user_id: int, meta: WorkspaceFile | None) -> bool:
    if member.role == "admin":
        return True
    return bool(meta and meta.uploaded_by == user_id)


def member_can_restore_file(member: WorkspaceMember, user_id: int, meta: WorkspaceFile) -> bool:
    if member.role == "admin":
        return True
    return meta.uploaded_by == user_id and meta.deleted_by == user_id


def upload_limit_for(
    user: User,
    member: WorkspaceMember,
    *,
    user_limit_bytes: int = MAX_WORKSPACE_UPLOAD_BYTES,
    user_limit_mb: int = MAX_WORKSPACE_UPLOAD_MB,
    admin_limit_bytes: int = MAX_WORKSPACE_ADMIN_UPLOAD_BYTES,
    admin_limit_mb: int = MAX_WORKSPACE_ADMIN_UPLOAD_MB,
) -> tuple[int, str]:
    if user.role == "admin" or member.role == "admin":
        return admin_limit_bytes, f"文件超过 {admin_limit_mb}MB"
    return user_limit_bytes, f"文件超过 {user_limit_mb}MB"


def is_template_root(rel_path: Path) -> bool:
    return len(rel_path.parts) == 1 and rel_path.as_posix() in DEFAULT_WORKSPACE_DIRS


def unique_child_path(parent: Path, filename: str) -> Path:
    candidate = parent / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 1
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def resolve_conflict_path(parent: Path, filename: str, strategy: str) -> Path | None:
    normalized = strategy.strip().lower()
    candidate = parent / filename
    if normalized == "skip" and candidate.exists():
        return None
    if normalized == "replace":
        return candidate
    if normalized != "keep_both":
        raise HTTPException(status_code=400, detail="同名冲突处理方式不合法")
    return unique_child_path(parent, filename)


def trash_target(root: Path, meta: WorkspaceFile, rel_path: str) -> Path:
    suffix = Path(rel_path).suffix
    stem = safe_name(Path(rel_path).stem)
    name = f"{int(datetime.now(timezone.utc).timestamp() * 1000)}-{meta.id}-{stem}{suffix}"
    trash_dir = root / TRASH_DIRNAME
    trash_dir.mkdir(exist_ok=True)
    return resolve_workspace_child(root, Path(TRASH_DIRNAME) / name)
