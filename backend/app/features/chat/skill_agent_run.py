from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.agents.events import add_agent_event, create_agent_run, finish_agent_run


def write_skill_agent_run(
    db: Session,
    *,
    user_id: int,
    session: Any,
    message_id: int,
    skill_response: dict,
    safe_event_detail: Callable[[object], str],
    missing_input_instruction: Callable[[str, list[dict]], str],
    agent_status_for_skill_status: Callable[[str], str],
):
    """Create an AgentRun and add skill events for a completed/ongoing skill response.

    Records events for the selected skill, execution plan, missing input requests,
    generated file tool/result events, and chat text tool/result events.

    Returns the finished AgentRun.
    """
    skill_run = skill_response.get("skill_run") or {}
    generated_file = skill_response.get("generated_file")
    status = agent_status_for_skill_status(str(skill_run.get("status") or "running"))
    skill_name = str(skill_run.get("skill_name") or "skill")
    display_name = str(((skill_run.get("skill") or {}).get("display_name")) or skill_name)
    run = create_agent_run(
        db,
        user_id=user_id,
        session_id=session.id,
        message_id=message_id,
        workspace_id=session.workspace_id,
        source_type="skill",
        source_id=str(skill_run.get("id") or ""),
        title=f"运行 Skill：{display_name}",
        status="running",
    )
    add_agent_event(
        db,
        run,
        event_type="skill_selected",
        title="已选择业务 Skill",
        detail=display_name,
        status="completed",
        payload={"skill_name": skill_name, "skill_run_id": skill_run.get("id")},
    )
    dispatch = skill_run.get("dispatch") or {}
    dispatch_steps = dispatch.get("steps") or []
    if dispatch:
        add_agent_event(
            db,
            run,
            event_type="execution_plan",
            title="读取 Skill 执行计划",
            detail=str(dispatch.get("mode") or "manual"),
            status="completed",
            payload={
                "mode": dispatch.get("mode"),
                "risk_level": dispatch.get("risk_level"),
                "requires_confirmation": dispatch.get("requires_confirmation"),
                "allowed_tools": dispatch.get("allowed_tools") or [],
                "steps": dispatch_steps,
            },
        )
    missing_inputs = skill_run.get("missing_inputs") or []
    if missing_inputs:
        skill_name_inner = skill_run.get("skill_name") or ""
        field_detail = missing_input_instruction(str(skill_name_inner), missing_inputs)

        add_agent_event(
            db,
            run,
            event_type="input_request",
            title=f"等待用户补充参数（还需要 {len(missing_inputs)} 个字段）",
            detail=field_detail or f"还需要 {len(missing_inputs)} 个字段",
            status="waiting",
            payload={"missing_inputs": missing_inputs},
        )
    elif generated_file:
        if dispatch_steps:
            for step in dispatch_steps:
                add_agent_event(
                    db,
                    run,
                    event_type="tool_call",
                    title=str(step.get("label") or step.get("tool") or "执行 Skill 工具"),
                    detail=str(step.get("tool") or ""),
                    status="completed",
                    payload={
                        "tool": step.get("tool"),
                        "step_id": step.get("id"),
                        "risk_level": step.get("risk_level"),
                    },
                )
        else:
            add_agent_event(
                db,
                run,
                event_type="tool_call",
                title="执行 Skill 并生成文件",
                detail=str(generated_file.get("filename") or ""),
                status="completed",
                payload={"generated_file": generated_file},
            )
        add_agent_event(
            db,
            run,
            event_type="result",
            title="Skill 产物已生成",
            detail=str(generated_file.get("filename") or ""),
            status="completed",
            payload={"generated_file": generated_file},
        )
    else:
        if dispatch_steps:
            for step in dispatch_steps:
                add_agent_event(
                    db,
                    run,
                    event_type="tool_call",
                    title=str(step.get("label") or step.get("tool") or "执行 Skill 工具"),
                    detail=str(step.get("tool") or ""),
                    status=status,
                    payload={
                        "tool": step.get("tool"),
                        "step_id": step.get("id"),
                        "risk_level": step.get("risk_level"),
                        "skill_status": skill_run.get("status"),
                    },
                )
        else:
            add_agent_event(
                db,
                run,
                event_type="tool_call",
                title="执行 Skill",
                detail=safe_event_detail(skill_response.get("reply") or ""),
                status=status,
                payload={"skill_status": skill_run.get("status")},
            )
        if status == "completed":
            add_agent_event(
                db,
                run,
                event_type="result",
                title="Skill 输出已生成",
                detail=safe_event_detail(skill_response.get("reply") or ""),
                status="completed",
                payload={"output_type": "chat_text"},
            )
    result: dict[str, Any] = {"skill_run": skill_run}
    if generated_file:
        result["generated_file"] = generated_file
    return finish_agent_run(db, run, status=status, result=result)
