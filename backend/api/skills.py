from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import get_current_user
from app.shared.time.schemas import UTCDateTimeModel
from core.notification_service import notify_skill_blocked
from app.features.skills.execution import execute_ready_run, generated_file_payload
from app.features.skills.runner import SkillRunner, run_to_dict
from models import get_db
from models.audit_log import AuditLog
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillResponse(BaseModel):
    name: str
    display_name: str
    description: str
    category: str
    priority: str
    trigger: list[str]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    references: list[str]
    execution: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)
    path: str


class MatchSkillRequest(BaseModel):
    text: str


class MatchSkillResponse(BaseModel):
    skill: SkillResponse | None = None
    confidence: float = 0.0
    reason: str = ""


class StartSkillRunRequest(BaseModel):
    skill_name: str
    session_id: int | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)


class SubmitSkillInputRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class SkillRunResponse(UTCDateTimeModel):
    id: int
    skill_name: str
    skill: SkillResponse | None = None
    user_id: int
    session_id: int | None = None
    status: str
    inputs: dict[str, Any]
    missing_inputs: list[dict[str, Any]]
    dispatch: dict[str, Any] | None = None
    generated_file: dict[str, str] | None = None
    created_at: datetime
    updated_at: datetime


def _ensure_session_owner(db: Session, session_id: int, user_id: int) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


def _serialize_run(run: SkillRun, db: Session) -> SkillRunResponse:
    runner = SkillRunner.get()
    skill = runner.get_skill(run.skill_name)
    payload = run_to_dict(run, skill)
    return SkillRunResponse(**payload, generated_file=generated_file_payload(db, run.generated_file_id))


@router.get("", response_model=list[SkillResponse])
def list_skills(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    runner = SkillRunner.get()
    return [SkillResponse(**skill.to_dict()) for skill in runner.list_skills()]


@router.post("/match", response_model=MatchSkillResponse)
def match_skill(
    req: MatchSkillRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    match = SkillRunner.get().match_skill(req.text)
    if not match:
        return MatchSkillResponse()
    return MatchSkillResponse(**match)


@router.post("/runs", response_model=SkillRunResponse)
def start_skill_run(
    req: StartSkillRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.session_id is not None:
        _ensure_session_owner(db, req.session_id, user.id)
    try:
        run = SkillRunner.get().start_run(
            db,
            skill_name=req.skill_name,
            user_id=user.id,
            session_id=req.session_id,
            inputs=req.inputs,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Skill 不存在") from exc
    run = execute_ready_run(db, run)
    if run.status == "collecting_inputs":
        notify_skill_blocked(
            db,
            run_id=run.id,
            user_id=run.user_id,
            skill_name=run.skill_name,
            missing_count=len(run_to_dict(run)["missing_inputs"]),
        )

    db.add(
        AuditLog(
            user_id=user.id,
            action="skill_run_start",
            detail=f"{run.skill_name}:{run.status}",
            success=True,
        )
    )
    db.commit()
    db.refresh(run)
    return _serialize_run(run, db)


@router.get("/runs/{run_id}", response_model=SkillRunResponse)
def get_skill_run(
    run_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(SkillRun).filter(SkillRun.id == run_id, SkillRun.user_id == user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Skill 运行记录不存在")
    return _serialize_run(run, db)


@router.post("/runs/{run_id}/inputs", response_model=SkillRunResponse)
def submit_skill_input(
    run_id: int,
    req: SubmitSkillInputRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(SkillRun).filter(SkillRun.id == run_id, SkillRun.user_id == user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Skill 运行记录不存在")
    try:
        run = SkillRunner.get().submit_input(db, run, req.inputs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Skill 不存在") from exc
    run = execute_ready_run(db, run)
    if run.status == "collecting_inputs":
        notify_skill_blocked(
            db,
            run_id=run.id,
            user_id=run.user_id,
            skill_name=run.skill_name,
            missing_count=len(run_to_dict(run)["missing_inputs"]),
        )

    db.add(
        AuditLog(
            user_id=user.id,
            action="skill_run_input",
            detail=f"{run.skill_name}:{run.status}",
            success=True,
        )
    )
    db.commit()
    db.refresh(run)
    return _serialize_run(run, db)


@router.post("/reload", response_model=list[SkillResponse])
def reload_skills(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    skills = SkillRunner.get().reload()
    return [SkillResponse(**skill.to_dict()) for skill in skills]
