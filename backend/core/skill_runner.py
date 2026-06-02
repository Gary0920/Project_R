from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from core.time_utils import serialize_datetime_utc
from models.skill_run import SkillRun

BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_ROOTS = (BASE_DIR / "skills" / "builtin", BASE_DIR / "skills" / "enterprise")


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    display_name: str
    description: str
    category: str
    priority: str
    trigger: list[str]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    references: list[str]
    execution: dict[str, Any]
    governance: dict[str, Any]
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "trigger": self.trigger,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "references": self.references,
            "execution": self.execution,
            "governance": self.governance,
            "path": self.path,
        }


def _parse_skill_file(path: Path) -> SkillDefinition | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    meta = yaml.safe_load(text[3:end]) or {}
    name = str(meta.get("name") or path.parent.name)
    return SkillDefinition(
        name=name,
        display_name=str(meta.get("display_name") or name),
        description=str(meta.get("description") or ""),
        category=str(meta.get("category") or ""),
        priority=str(meta.get("priority") or "medium"),
        trigger=list(meta.get("trigger") or []),
        inputs=list(meta.get("inputs") or []),
        outputs=list(meta.get("outputs") or []),
        references=list(meta.get("references") or []),
        execution=dict(meta.get("execution") or {}),
        governance=dict(meta.get("governance") or {}),
        path=path.relative_to(BASE_DIR).as_posix(),
    )


class SkillRunner:
    _instance: "SkillRunner | None" = None

    @classmethod
    def get(cls) -> "SkillRunner":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}
        self.reload()

    def reload(self) -> list[SkillDefinition]:
        skills: dict[str, SkillDefinition] = {}
        for root in SKILLS_ROOTS:
            if not root.exists():
                continue
            for skill_file in sorted(root.glob("*/SKILL.md")):
                definition = _parse_skill_file(skill_file)
                if definition:
                    skills[definition.name] = definition
        self._skills = skills
        return self.list_skills()

    def list_skills(self, *, include_internal: bool = False) -> list[SkillDefinition]:
        priority_order = {"high": 0, "medium": 1, "low": 2}
        skills = self._skills.values()
        if not include_internal:
            skills = [skill for skill in skills if not _is_internal_skill(skill)]
        return sorted(
            skills,
            key=lambda item: (priority_order.get(item.priority, 9), item.category, item.display_name),
        )

    def get_skill(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def match_skill(self, text: str, *, include_internal: bool = False) -> dict[str, Any] | None:
        normalized = text.strip().lower()
        if not normalized:
            return None
        best: tuple[float, SkillDefinition, str] | None = None
        for skill in self._skills.values():
            if not include_internal and _is_internal_skill(skill):
                continue
            candidates = [skill.display_name, skill.description, *skill.trigger]
            for candidate in candidates:
                cand = str(candidate).strip().lower()
                if not cand:
                    continue
                score = 0.0
                if cand in normalized:
                    score = 1.0
                elif any(part and part in normalized for part in cand.split()):
                    score = 0.55
                if score and (best is None or score > best[0]):
                    best = (score, skill, str(candidate))
        if not best:
            return None
        score, skill, reason = best
        return {"skill": skill.to_dict(), "confidence": score, "reason": reason}

    def start_run(
        self,
        db: Session,
        skill_name: str,
        user_id: int,
        session_id: int | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> SkillRun:
        skill = self.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {skill_name}")
        provided = inputs or {}
        missing = [
            item
            for item in skill.inputs
            if item.get("required", False) and not provided.get(str(item.get("name", "")))
        ]
        run = SkillRun(
            skill_name=skill.name,
            user_id=user_id,
            session_id=session_id,
            status="collecting_inputs" if missing else "ready",
            inputs_json=json.dumps(provided, ensure_ascii=False),
            missing_inputs_json=json.dumps(missing, ensure_ascii=False),
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def submit_input(self, db: Session, run: SkillRun, payload: dict[str, Any]) -> SkillRun:
        skill = self.get_skill(run.skill_name)
        if not skill:
            raise ValueError(f"Skill not found: {run.skill_name}")

        existing = json.loads(run.inputs_json or "{}")
        merged = {**existing, **payload}
        missing = [
            item
            for item in skill.inputs
            if item.get("required", False) and not merged.get(str(item.get("name", "")))
        ]
        run.inputs_json = json.dumps(merged, ensure_ascii=False)
        run.missing_inputs_json = json.dumps(missing, ensure_ascii=False)
        run.status = "collecting_inputs" if missing else "ready"
        db.commit()
        db.refresh(run)
        return run


def run_to_dict(run: SkillRun, skill: SkillDefinition | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "skill_name": run.skill_name,
        "skill": skill.to_dict() if skill else None,
        "user_id": run.user_id,
        "session_id": run.session_id,
        "status": run.status,
        "inputs": json.loads(run.inputs_json or "{}"),
        "missing_inputs": json.loads(run.missing_inputs_json or "[]"),
        "dispatch": _skill_dispatch_plan(skill),
        "created_at": serialize_datetime_utc(run.created_at),
        "updated_at": serialize_datetime_utc(run.updated_at),
    }


def _is_internal_skill(skill: SkillDefinition) -> bool:
    return str((skill.governance or {}).get("visibility") or "").strip().lower() == "internal"


def _skill_dispatch_plan(skill: SkillDefinition | None) -> dict[str, Any] | None:
    if not skill:
        return None
    execution = skill.execution or {}
    governance = skill.governance or {}
    steps = execution.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    if not execution and not governance:
        return None
    allowed_tools = governance.get("allowed_tools") or execution.get("allowed_tools") or []
    return {
        "mode": str(execution.get("mode") or ""),
        "risk_level": str(governance.get("risk_level") or execution.get("risk_level") or "low"),
        "requires_confirmation": bool(governance.get("requires_confirmation") or execution.get("requires_confirmation")),
        "allowed_tools": [str(tool) for tool in allowed_tools if str(tool).strip()],
        "steps": [
            {
                "id": str(step.get("id") or step.get("tool") or index + 1),
                "tool": str(step.get("tool") or ""),
                "label": str(step.get("label") or step.get("title") or step.get("tool") or "执行步骤"),
                "risk_level": str(step.get("risk_level") or governance.get("risk_level") or "low"),
                "requires_confirmation": bool(step.get("requires_confirmation")),
            }
            for index, step in enumerate(steps)
            if isinstance(step, dict)
        ],
    }
