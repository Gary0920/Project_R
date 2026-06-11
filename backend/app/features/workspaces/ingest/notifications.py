from __future__ import annotations

from typing import Any

from core.notification_service import notify_user


def notify_workspace_ingest_queued(
    db: Any,
    *,
    workspace: Any,
    actor_user_id: int,
    job_id: int,
    request_label: str,
) -> None:
    notify_user(
        db,
        actor_user_id,
        category="workspace",
        severity="info",
        title="工作区知识库录入已排队",
        content=f"{workspace.name}：后台正在处理{request_label}，完成后会再次通知你。",
        action_status="pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id, "ingest_job_id": job_id},
    )


def notify_workspace_ingest_finished(
    db: Any,
    *,
    workspace: Any,
    actor_user_id: int,
    ok: bool,
    indexed_files: int,
    failed_files: int,
    pending_extractor_capability_files: int,
    pending_transcription_files: int,
    gbrain_error: str | None,
) -> None:
    if ok and failed_files == 0:
        title = "工作区知识库录入完成"
        severity = "success"
    else:
        title = "工作区知识库录入未完成"
        severity = "warning"
    details = [
        f"已入库 {indexed_files} 个文件",
        f"待能力补齐 {pending_extractor_capability_files} 个",
        f"待转写 {pending_transcription_files} 个",
        f"失败 {failed_files} 个",
    ]
    if gbrain_error:
        details.append(f"GBrain：{gbrain_error}")
    notify_user(
        db,
        actor_user_id,
        category="workspace",
        severity=severity,
        title=title,
        content=f"{workspace.name}：" + "，".join(details) + "。",
        action_status="none" if ok else "pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": workspace.id},
    )


def notify_workspace_ingest_failed(
    db: Any,
    *,
    job: Any,
    workspace: Any | None,
    error: str,
) -> None:
    notify_user(
        db,
        job.requested_by,
        category="workspace",
        severity="warning",
        title="工作区知识库录入失败",
        content=f"{workspace.name if workspace else '项目'}：后台录入任务失败，原因：{error}",
        action_status="pending",
        action_kind="open_workspace",
        action_payload={"workspace_id": job.workspace_id, "ingest_job_id": job.id},
    )
