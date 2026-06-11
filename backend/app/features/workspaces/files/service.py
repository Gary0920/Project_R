import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from models.user import User
from models.workspace import WorkspaceFile, WorkspaceMember


DEFAULT_WORKSPACE_DIRS = (
    "01-项目启动",
    "02-项目准备",
    "03-样品阶段",
    "04-施工图阶段",
    "05-开模阶段",
    "06-结构计算",
    "07-热工计算",
    "08-工程认证",
    "09-项目统筹会",
    "10-VMU阶段",
    "11-PMU阶段",
    "12-项目交接加工组",
    "13-加工拆单与下单",
    "14-大货生产",
    "15-物流运输",
    "16-项目结算",
    "17-财务与款项",
    "18-售后客诉",
    "19-变更管理",
    "20-会议与沟通",
    "21-Skill输出与草稿",
    "90-通用上传资料",
    "99-未归档文件",
)
DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS = DEFAULT_WORKSPACE_DIRS + (
    "20-会议与沟通/01-原始资料",
    "20-会议与沟通/02-转录文本",
    "20-会议与沟通/03-辅助总结",
    "20-会议与沟通/04-会议纪要",
    "20-会议与沟通/05-行动项",
    "21-Skill输出与草稿/01-待确认结果",
    "21-Skill输出与草稿/02-已确认保存",
    "90-通用上传资料/01-PDF与报告",
    "90-通用上传资料/02-Office文档",
    "90-通用上传资料/03-表格清单",
    "90-通用上传资料/04-邮件EML",
    "90-通用上传资料/05-图片截图",
    "90-通用上传资料/06-压缩包",
    "90-通用上传资料/07-其他",
)
DEFAULT_USER_WORKSPACE_DIRS = (
    "常用文件",
    "常用文件/模板",
    "常用文件/参考资料",
    "常用文件/图片素材",
    "常用文件/其他",
    "对话文件",
)
DEFAULT_CUSTOMER_WORKSPACE_DIRS = (
    "01-客户档案",
    "02-联系人与关系",
    "03-沟通记录",
    "04-原始资料",
    "99-未归档文件",
)
DEFAULT_UNFILED_DIR = "99-未归档文件"
MAX_WORKSPACE_UPLOAD_MB = int(os.getenv("WORKSPACE_MAX_UPLOAD_MB", "100"))
MAX_WORKSPACE_ADMIN_UPLOAD_MB = int(os.getenv("WORKSPACE_ADMIN_MAX_UPLOAD_MB", "1024"))
MAX_WORKSPACE_UPLOAD_BYTES = MAX_WORKSPACE_UPLOAD_MB * 1024 * 1024
MAX_WORKSPACE_ADMIN_UPLOAD_BYTES = MAX_WORKSPACE_ADMIN_UPLOAD_MB * 1024 * 1024
TRASH_DIRNAME = ".trash"

# ── Meeting folder constants ────────────────────────────────────────────
MEETING_SUBDIRS = (
    "01-原始资料",
    "02-转录文本",
    "03-辅助总结",
    "04-会议纪要",
    "05-行动项",
)
PROJECT_MEETING_PARENT = "20-会议与沟通"
CRM_MEETING_PARENT = "raw/会议记录"
MEETING_FOLDER_MAX_LEN = 80


def make_meeting_folder_name(timestamp: datetime | None, topic: str) -> str:
    """Generate YYYYMMDD-HHMM-sanitized-topic folder name."""
    ts = timestamp or datetime.now(timezone.utc)
    prefix = ts.strftime("%Y%m%d-%H%M")
    cleaned = re.sub(r"[^\w一-鿿.\-()（）\[\]【】 &]", "_", (topic or "未命名会议").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    name = f"{prefix}-{cleaned}" if cleaned else f"{prefix}-未命名会议"
    # Enforce max length on the whole name
    if len(name) > MEETING_FOLDER_MAX_LEN:
        keep_prefix = len(prefix) + 1  # prefix + hyphen
        tail = cleaned[:MEETING_FOLDER_MAX_LEN - keep_prefix].rstrip("_-")
        name = f"{prefix}-{tail or '未命名会议'}"
    return safe_name(name)


def meeting_parent_path(workspace_kind: str) -> str:
    """Return the parent directory path for meeting folders per workspace kind."""
    if workspace_kind == "project":
        return PROJECT_MEETING_PARENT
    if workspace_kind == "customer":
        return CRM_MEETING_PARENT
    raise HTTPException(status_code=400, detail="当前工作区类型不支持会议文件夹")


def meeting_folder_collision_free(parent: Path, name: str) -> Path:
    """Return a collision-free meeting folder path, appending (1), (2) etc."""
    candidate = parent / name
    if not candidate.exists():
        return candidate
    index = 1
    while True:
        candidate = parent / f"{name} ({index})"
        if not candidate.exists():
            return candidate
        index += 1


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


def member_can_mutate_file(
    member: WorkspaceMember,
    user_id: int,
    meta: WorkspaceFile | None,
    user_role: str = "",
) -> bool:
    if member.role == "admin" or user_role == "admin":
        return True
    return bool(meta and meta.uploaded_by == user_id)


def member_can_restore_file(
    member: WorkspaceMember,
    user_id: int,
    meta: WorkspaceFile,
    user_role: str = "",
) -> bool:
    if member.role == "admin" or user_role == "admin":
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
