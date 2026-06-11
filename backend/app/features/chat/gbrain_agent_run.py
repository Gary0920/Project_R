from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run
from app.features.chat.context_trace import gbrain_think_trace, safe_trace_list


def write_gbrain_think_agent_run(
    db: Session,
    *,
    user_id: int,
    session: Any,
    message_id: int,
    query: str,
    think_result: dict,
    response_sources: list[dict],
    safe_event_detail: Callable[[object], str],
):
    ok = bool(think_result.get("ok"))
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="gbrain_think",
        source_id=str(think_result.get("source_id") or ""),
        title="GBrain Think 知识推理",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="context_trace",
        title="限定知识库 Source",
        detail=str(think_result.get("source_id") or session.workspace_id or "company-wiki"),
        status="completed",
        payload={"workspace_id": session.workspace_id, "source_id": think_result.get("source_id")},
    )
    metadata = think_result.get("metadata") if isinstance(think_result.get("metadata"), dict) else {}
    add_agent_event(
        db,
        run,
        event_type="tool_call",
        title="调用 GBrain think",
        detail=safe_event_detail(query),
        status="completed" if ok else "failed",
        payload={
            "model": think_result.get("model"),
            "status": think_result.get("status"),
            "source_count": len(response_sources),
            "gaps": safe_trace_list(metadata.get("gaps")),
            "conflicts": safe_trace_list(metadata.get("conflicts")),
            "warnings": safe_trace_list(metadata.get("warnings")),
        },
    )
    if response_sources:
        add_agent_event(
            db,
            run,
            event_type="citation",
            title="整理引用来源",
            detail=f"{len(response_sources)} 个来源",
            status="completed",
            payload={"sources": response_sources[:8]},
        )
    error_message = "" if ok else str(think_result.get("error") or think_result.get("status") or "GBrain think unavailable")
    return finish_agent_run(
        db,
        run,
        status="completed" if ok else "failed",
        result={
            "model": think_result.get("model"),
            "source_id": think_result.get("source_id"),
            "source_count": len(response_sources),
            "gbrain_think": gbrain_think_trace(think_result),
        },
        error_message=error_message,
    )
