from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.knowledge.gbrain import (
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.workspaces.audit import audit_detail, write_workspace_audit, write_workspace_file_agent_run
from app.features.workspaces.files.service import resolve_conflict_path, resolve_workspace_child, safe_name, safe_relative_path
from app.features.workspaces.files.storage import ensure_not_trash_path
from app.features.workspaces.meetings.markdown import compose_gbrain_ready_meeting
from app.features.workspaces.meetings.validation import validate_meeting_folder
from app.features.workspaces.schemas import MeetingIngestRequest, MeetingIngestResponse
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


def ingest_meeting_to_gbrain_asset(
    db: Session,
    user: User,
    workspace: Workspace,
    root: Path,
    req: MeetingIngestRequest,
) -> MeetingIngestResponse:
    is_single_file_actions = (
        req.single_file_path is not None
        and req.single_file_path.rstrip("/").endswith("actions-latest.md")
    )

    folder_dir: Path | None = None
    if not is_single_file_actions:
        _folder_rel, folder_dir = validate_meeting_folder(
            workspace_kind=workspace.workspace_kind,
            root=root,
            folder_path=req.folder_path,
            safe_relative_path=safe_relative_path,
            ensure_not_trash_path=ensure_not_trash_path,
            resolve_workspace_child=resolve_workspace_child,
        )

    member = db.query(WorkspaceMember).filter(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == user.id,
    ).first()
    is_admin = member and member.role == "admin"
    is_system_admin = user.role == "admin"

    if workspace.workspace_kind == "customer":
        if not (is_admin or is_system_admin):
            raise HTTPException(status_code=403, detail="仅客户工作区管理员可录入会议资料")
    elif workspace.workspace_kind == "project":
        if not (is_admin or is_system_admin):
            raise HTTPException(status_code=403, detail="仅项目管理员可录入会议文件夹")

    if folder_dir is None:
        folder_dir = resolve_workspace_child(root, safe_relative_path(req.folder_path))

    if workspace.workspace_kind == "project":
        source_id = project_source_id_for_workspace(workspace)
        paths = project_source_paths_for_workspace(workspace)
        source_scope = "project"
    else:
        source_id = customer_source_id_for_workspace(workspace)
        paths = customer_source_paths_for_workspace(workspace)
        source_scope = "customer"

    gbrain_ready_dir = paths.get("gbrain_ready", Path(""))
    if isinstance(gbrain_ready_dir, str):
        gbrain_ready_dir = Path(gbrain_ready_dir)
    gbrain_ready_dir.mkdir(parents=True, exist_ok=True)

    if is_single_file_actions:
        ingested, skipped, warning, gbrain_ready_path = _ingest_single_actions_file(
            db,
            workspace.id,
            root,
            folder_dir,
            gbrain_ready_dir,
            source_scope,
        )
    else:
        ingested, skipped, warning, gbrain_ready_path = _ingest_full_meeting(
            db,
            workspace.id,
            root,
            folder_dir,
            gbrain_ready_dir,
            source_scope,
        )

    write_workspace_audit(
        db,
        user.id,
        "meeting_gbrain_ingest",
        audit_detail(
            workspace.id,
            req.folder_path,
            actor_id=user.id,
            source_id=source_id,
            source_scope=source_scope,
            ingested=ingested,
            skipped=skipped,
            gbrain_ready_path=str(gbrain_ready_path.resolve()),
            gbrain_ready_generated=True,
            gbrain_synced=False,
            single_file_actions_only=is_single_file_actions,
            warning=warning if warning else None,
        ),
    )
    agent_run = write_workspace_file_agent_run(
        db,
        user_id=user.id,
        workspace=workspace,
        source_type="meeting_gbrain_ingest",
        title="会议行动项录入 GBrain" if is_single_file_actions else "会议资料录入 GBrain",
        path=req.folder_path,
        detail=f"已生成 {len(ingested)} 个 GBrain-ready 文件，跳过 {len(skipped)} 个旧版本",
    )
    db.commit()
    return MeetingIngestResponse(
        ok=True,
        meeting_folder_path=req.folder_path,
        gbrain_ready_path=str(gbrain_ready_path.resolve()),
        source_id=source_id,
        source_scope=source_scope,
        ingested_files=ingested,
        skipped_files=skipped,
        gbrain_ingest=True,
        agent_run=serialize_agent_run(db, agent_run),
        warning=warning,
    )


def _ingest_single_actions_file(
    db: Session,
    workspace_id: int,
    root: Path,
    folder_dir: Path,
    gbrain_ready_dir: Path,
    source_scope: str,
) -> tuple[list[str], list[str], str, Path]:
    actions_latest = folder_dir / "05-行动项" / "actions-latest.md"
    if not actions_latest.exists():
        raise HTTPException(status_code=400, detail="行动项文件 actions-latest.md 不存在")

    actions_md = actions_latest.read_text(encoding="utf-8")
    actions_rel = actions_latest.relative_to(root).as_posix()
    warning = ""
    if (folder_dir / "04-会议纪要" / "minutes-latest.md").exists() and (folder_dir / "02-转录文本" / "transcript-latest.md").exists():
        warning = "该会议存在完整的纪要和转录文件。建议改为录入完整会议资料以获取更全面的知识上下文。"

    meeting_name = folder_dir.name
    gbrain_ready_markdown = compose_gbrain_ready_meeting(
        meeting_name,
        "",
        "",
        actions_md,
        source_scope=source_scope,
        source_context="action_items_only",
    )
    gbrain_ready_path = _write_gbrain_ready_markdown(gbrain_ready_dir, meeting_name, gbrain_ready_markdown)

    metadata = db.query(WorkspaceFile).filter(
        WorkspaceFile.workspace_id == workspace_id,
        WorkspaceFile.relative_path == actions_rel,
    ).first()
    if metadata:
        metadata.rag_status = "gbrain_ready"

    return [actions_rel], [], warning, gbrain_ready_path


def _ingest_full_meeting(
    db: Session,
    workspace_id: int,
    root: Path,
    folder_dir: Path,
    gbrain_ready_dir: Path,
    source_scope: str,
) -> tuple[list[str], list[str], str, Path]:
    sections = {
        "04-会议纪要": "minutes",
        "02-转录文本": "transcript",
        "05-行动项": "actions",
    }
    ingested: list[str] = []
    skipped: list[str] = []
    collected: dict[str, str] = {}
    for subdir, prefix in sections.items():
        dir_path = folder_dir / subdir
        if not dir_path.exists():
            continue
        latest_path = dir_path / f"{prefix}-latest.md"
        if not latest_path.exists():
            continue
        latest_rel = latest_path.relative_to(root).as_posix()
        ingested.append(latest_rel)
        collected[subdir] = latest_path.read_text(encoding="utf-8")

        version_pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.md$", re.IGNORECASE)
        for child in dir_path.iterdir():
            if not child.is_file() or child.name == f"{prefix}-latest.md":
                continue
            if version_pattern.match(child.name):
                superseded_rel = child.relative_to(root).as_posix()
                skipped.append(superseded_rel)
                metadata = db.query(WorkspaceFile).filter(
                    WorkspaceFile.workspace_id == workspace_id,
                    WorkspaceFile.relative_path == superseded_rel,
                ).first()
                if metadata:
                    metadata.rag_status = "skipped_superseded_version"

    if not collected:
        raise HTTPException(status_code=400, detail="没有可录入的会议文件。请先生成纪要和转录。")

    meeting_name = folder_dir.name
    gbrain_ready_markdown = compose_gbrain_ready_meeting(
        meeting_name,
        collected.get("04-会议纪要", ""),
        collected.get("02-转录文本", ""),
        collected.get("05-行动项", ""),
        source_scope=source_scope,
        source_context="full_meeting",
    )
    gbrain_ready_path = _write_gbrain_ready_markdown(gbrain_ready_dir, meeting_name, gbrain_ready_markdown)

    for ingested_path in ingested:
        metadata = db.query(WorkspaceFile).filter(
            WorkspaceFile.workspace_id == workspace_id,
            WorkspaceFile.relative_path == ingested_path,
        ).first()
        if metadata:
            metadata.rag_status = "gbrain_ready"

    return ingested, skipped, "", gbrain_ready_path


def _write_gbrain_ready_markdown(gbrain_ready_dir: Path, meeting_name: str, content: str) -> Path:
    target = resolve_conflict_path(gbrain_ready_dir, f"{safe_name(meeting_name)}.md", "keep_both")
    if target is None:
        raise HTTPException(status_code=500, detail="无法写入 GBrain-ready 文件")
    target.write_text(content, encoding="utf-8")
    return target
