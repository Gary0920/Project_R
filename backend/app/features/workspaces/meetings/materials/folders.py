from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.service import (
    MEETING_SUBDIRS,
    make_meeting_folder_name,
    meeting_folder_collision_free,
    meeting_parent_path,
    resolve_workspace_child,
    safe_relative_path,
)
from app.features.workspaces.files.storage import ensure_not_trash_path
from app.features.workspaces.meetings.utils import write_meeting_meta
from app.features.workspaces.schemas import CreateMeetingFolderRequest, MeetingFolderResponse
from models.user import User
from models.workspace import Workspace

MEETING_TYPES = [
    "项目统筹会",
    "客户沟通会",
    "技术交底",
    "现场协调",
    "内部复盘",
    "培训分享",
    "其他",
]


def create_meeting_folder_for_workspace(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    req: CreateMeetingFolderRequest,
) -> MeetingFolderResponse:
    if workspace.workspace_kind == "user":
        raise HTTPException(status_code=400, detail="个人工作台不支持创建会议文件夹")
    if req.meeting_type not in MEETING_TYPES:
        raise HTTPException(status_code=400, detail=f"会议类型不合法，可选值：{', '.join(MEETING_TYPES)}")

    parent_rel_str = meeting_parent_path(workspace.workspace_kind)
    parent_rel = safe_relative_path(parent_rel_str)
    ensure_not_trash_path(parent_rel)
    parent = resolve_workspace_child(root, parent_rel)
    parent.mkdir(parents=True, exist_ok=True)

    meeting_dt: datetime | None = None
    if req.meeting_time:
        try:
            meeting_dt = datetime.fromisoformat(req.meeting_time)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="会议时间格式不合法，请使用 ISO-8601")

    folder_name = make_meeting_folder_name(meeting_dt, req.topic)
    meeting_dir = meeting_folder_collision_free(parent, folder_name)
    meeting_dir.mkdir(parents=True, exist_ok=True)

    created_dirs: list[str] = []
    for sub in MEETING_SUBDIRS:
        sub_dir = meeting_dir / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        created_dirs.append(sub_dir.relative_to(root).as_posix())

    meeting_rel = meeting_dir.relative_to(root).as_posix()
    created_dirs.insert(0, meeting_rel)

    write_meeting_meta(
        meeting_dir,
        topic=req.topic,
        meeting_time=req.meeting_time,
        meeting_type=req.meeting_type,
    )

    write_workspace_audit(
        db,
        user.id,
        "meeting_folder_create",
        audit_detail(
            workspace.id,
            meeting_rel,
            actor_id=user.id,
            workspace_kind=workspace.workspace_kind,
            meeting_folder_path=meeting_rel,
            created_dirs=created_dirs,
            gbrain_ingest=False,
        ),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_folder_create",
        title="创建会议文件夹",
        path=meeting_rel,
        detail=f"会议：{req.topic}",
    )
    db.commit()
    return MeetingFolderResponse(
        ok=True,
        meeting_folder_path=meeting_rel,
        created_dirs=created_dirs,
        created_files=[],
        gbrain_ingest=False,
        agent_run=serialize_agent_run(db, agent_run),
    )
