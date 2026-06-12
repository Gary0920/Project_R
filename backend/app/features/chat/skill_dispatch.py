"""Chat-to-skill dispatch — route chat messages to Skill execution.

Extracted from api/chat.py. These functions bridge chat messages to the
SkillRunner system: matching skills, starting runs, continuing collecting
inputs, and writing assistant responses.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.features.agents.events import serialize_agent_run
from app.features.chat.skill_text import (
    extract_skill_inputs as _extract_skill_inputs,
    missing_input_fields_text as _missing_input_fields_text,
    missing_input_instruction as _missing_input_instruction,
)
from app.features.skills.execution import execute_ready_run, generated_file_payload
from app.features.skills.runner import SkillRunner, run_to_dict
from models.message import ChatMessage
from models.session import ChatSession
from models.skill_run import SkillRun


def start_skill_run_from_chat(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    """Try to match a skill from natural language and start a run."""
    runner = SkillRunner.get()
    match = runner.match_skill(content)
    if not match:
        return None
    return start_skill_run_by_name(db, user_id, session_id, match["skill"]["name"])


def start_skill_run_by_name(db: Session, user_id: int, session_id: int, skill_name: str) -> dict | None:
    """Start a skill run by name and return the initial response."""
    runner = SkillRunner.get()
    skill = runner.get_skill(skill_name)
    if not skill:
        return None
    run = runner.start_run(db, skill.name, user_id=user_id, session_id=session_id)
    missing = run_to_dict(run, skill)["missing_inputs"]
    if missing:
        instruction = _missing_input_instruction(skill.name, missing)
        fields = _missing_input_fields_text(missing)
        reply = (
            f"已识别到业务 Skill：{skill.display_name}，但还不能开始执行。\n\n"
            f"请补充以下信息：\n{fields}\n\n"
            f"下一步操作：\n```text\n{instruction}\n```"
        )
    else:
        reply = f"已识别到业务 Skill：{skill.display_name}，信息已齐全，可以继续执行。"
    return {
        "reply": reply,
        "skill_run": run_to_dict(run, skill),
        "generated_file": generated_file_payload(db, run.generated_file_id),
    }


def continue_active_skill_run(db: Session, user_id: int, session_id: int, content: str) -> dict | None:
    """Continue a skill run that's collecting inputs."""
    run = (
        db.query(SkillRun)
        .filter(
            SkillRun.user_id == user_id,
            SkillRun.session_id == session_id,
            SkillRun.status == "collecting_inputs",
        )
        .order_by(SkillRun.id.desc())
        .first()
    )
    if not run:
        return None
    runner = SkillRunner.get()
    skill = runner.get_skill(run.skill_name)
    if not skill:
        return None
    current = run_to_dict(run, skill)
    extracted = _extract_skill_inputs(content, current["missing_inputs"])
    if not extracted:
        fields = _missing_input_fields_text(current["missing_inputs"])
        instruction = _missing_input_instruction(run.skill_name, current["missing_inputs"])
        return {
            "reply": (
                f"我还没有识别到可写入 {skill.display_name} 的字段。\n\n"
                f"请按下面字段补充：\n{fields}\n\n"
                f"下一步操作：\n```text\n{instruction}\n```"
            ),
            "skill_run": current,
            "generated_file": generated_file_payload(db, run.generated_file_id),
        }

    run = runner.submit_input(db, run, extracted)
    run = execute_ready_run(db, run)
    payload = run_to_dict(run, skill)
    if run.status == "completed":
        reply = f"{skill.display_name} 已生成完成，可以下载结果文件。"
    else:
        fields = _missing_input_fields_text(payload["missing_inputs"])
        instruction = _missing_input_instruction(run.skill_name, payload["missing_inputs"])
        reply = (
            f"已记录补充信息，还需要：\n{fields}\n\n"
            f"下一步操作：\n```text\n{instruction}\n```"
        )
    return {
        "reply": reply,
        "skill_run": payload,
        "generated_file": generated_file_payload(db, run.generated_file_id),
    }


def write_skill_assistant_response(
    db: Session,
    user_id: int,
    session: ChatSession,
    user_message_id: int,
    content: str,
    skill_response: dict,
    context_trace: dict | None = None,
    write_skill_agent_run: Any = None,
    write_chat_audit: Any = None,
) -> dict:
    """Write a skill assistant response as a ChatMessage and record agent run.

    Args:
        write_skill_agent_run: Optional callback for agent run recording (injected by
            api/chat.py wrapper to avoid circular imports and support monkeypatching).
        write_chat_audit: Optional callback for audit logging.
    """
    context_trace = context_trace or {}
    assistant_message = ChatMessage(
        session_id=session.id,
        user_id=user_id,
        role="assistant",
        content=skill_response["reply"],
        provider="project_r",
        model="skill_runner",
        token_input=0,
        token_output=0,
        token_total=0,
        status="success",
        rag_used=False,
        sources_json="[]",
        context_json=json.dumps(context_trace, ensure_ascii=False),
        version_group_id=str(uuid.uuid4()),
    )
    db.add(assistant_message)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_message)
    agent_run = None
    if write_skill_agent_run:
        agent_run = write_skill_agent_run(
            db,
            user_id=user_id,
            session=session,
            message_id=assistant_message.id,
            skill_response=skill_response,
        )
        db.commit()
    if write_chat_audit:
        write_chat_audit(
            db,
            user_id,
            session.id,
            content,
            True,
            f"skill_run={skill_response['skill_run']['skill_name']}",
            token_cost=0,
        )
    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message.id,
        "reply": skill_response["reply"],
        "provider": "project_r",
        "model": "skill_runner",
        "key_index": None,
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "intent": "skill_trigger",
        "sources": [],
        "generated_file": skill_response.get("generated_file"),
        "skill_run": skill_response["skill_run"],
        "agent_run": serialize_agent_run(db, agent_run) if agent_run else None,
        "context_trace": context_trace,
    }
