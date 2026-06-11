from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.skills.runner import SkillDefinition, SkillRunner, run_to_dict
from models.skill_run import SkillRun


class SkillDispatchError(Exception):
    pass


class SkillDispatchBlocked(SkillDispatchError):
    pass


class SkillDispatcher:
    def __init__(self):
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {}

    def execute(self, db: Session, run: SkillRun, *, generated_root: Path) -> SkillRun:
        skill = SkillRunner.get().get_skill(run.skill_name)
        if not skill:
            raise SkillDispatchError(f"Skill not found: {run.skill_name}")
        steps = _dispatch_steps(skill)
        if not steps:
            return run

        inputs = run_to_dict(run, skill)["inputs"]
        run.status = "running"
        db.flush()
        results: list[dict[str, Any]] = []
        for step in steps:
            tool_name = _step_tool(step)
            _ensure_tool_allowed(skill, step, tool_name)
            tool = self._tools.get(tool_name)
            if not tool:
                raise SkillDispatchError(f"Skill tool not registered: {tool_name}")
            result = tool(db=db, run=run, skill=skill, step=step, inputs=inputs, generated_root=generated_root)
            results.append({"step_id": str(step.get("id") or ""), "tool": tool_name, **result})
        run.status = "completed"
        return run


def _dispatch_steps(skill: SkillDefinition) -> list[dict[str, Any]]:
    execution = skill.execution or {}
    if str(execution.get("mode") or "") != "dispatcher":
        return []
    steps = execution.get("steps") or []
    if not isinstance(steps, list):
        raise SkillDispatchError(f"Skill execution steps must be a list: {skill.name}")
    return [step for step in steps if isinstance(step, dict)]


def _ensure_tool_allowed(skill: SkillDefinition, step: dict[str, Any], tool_name: str) -> None:
    governance = skill.governance or {}
    execution = skill.execution or {}
    if bool(governance.get("requires_confirmation") or execution.get("requires_confirmation") or step.get("requires_confirmation")):
        raise SkillDispatchBlocked(f"Skill requires confirmation before executing: {skill.name}")
    allowed_tools = governance.get("allowed_tools") or execution.get("allowed_tools") or []
    allowed = {str(tool).strip() for tool in allowed_tools if str(tool).strip()}
    if not allowed:
        raise SkillDispatchError(f"Skill dispatcher requires an allowed_tools governance list: {skill.name}")
    if tool_name not in allowed:
        raise SkillDispatchError(f"Skill tool is not allowed by governance policy: {tool_name}")


def _step_tool(step: dict[str, Any]) -> str:
    tool_name = str(step.get("tool") or "").strip()
    if not tool_name:
        raise SkillDispatchError("Skill execution step is missing tool")
    return tool_name
