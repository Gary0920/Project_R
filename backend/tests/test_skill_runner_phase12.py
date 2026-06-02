import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.skills as skills_api
import core.skill_execution as skill_execution
from core.skill_dispatcher import SkillDispatchError, SkillDispatcher
from core.skill_runner import SkillDefinition
from core.skill_runner import SkillRunner
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User
from models.workspace import Workspace


class SkillRunnerPhase12Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        SkillRunner._instance = None
        self.generated_root = tempfile.TemporaryDirectory()
        self.original_generated_root = skill_execution.GENERATED_FILES_ROOT
        skill_execution.GENERATED_FILES_ROOT = Path(self.generated_root.name)
        self.admin = User(username="skill-admin", password_hash="hash", role="admin", nickname="Admin")
        self.employee = User(username="skill-user", password_hash="hash", role="employee", nickname="User")
        self.db.add_all([self.admin, self.employee])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.employee)
        self.session = ChatSession(user_id=self.employee.id, title="Skill session")
        self.db.add(self.session)
        self.db.commit()
        self.db.refresh(self.session)

    def tearDown(self):
        skill_execution.GENERATED_FILES_ROOT = self.original_generated_root
        self.generated_root.cleanup()
        self.db.close()
        SkillRunner._instance = None

    def test_builtin_business_skills_can_be_listed_and_matched(self):
        skills = skills_api.list_skills(self.employee, self.db)
        names = [skill.name for skill in skills]

        self.assertIn("client-reply-drafting", names)
        self.assertIn("project-communication-analysis", names)
        self.assertNotIn("web-search-content", names)

        reply_match = skills_api.match_skill(
            skills_api.MatchSkillRequest(text="帮我回复客户这封邮件"),
            self.employee,
            self.db,
        )
        self.assertEqual(reply_match.skill.name, "client-reply-drafting")

        analysis_match = skills_api.match_skill(
            skills_api.MatchSkillRequest(text="帮我分析客户邮件有没有 VO 风险"),
            self.employee,
            self.db,
        )
        self.assertEqual(analysis_match.skill.name, "project-communication-analysis")

        internal_match = skills_api.match_skill(
            skills_api.MatchSkillRequest(text="帮我联网搜索一下"),
            self.employee,
            self.db,
        )
        self.assertIsNone(internal_match.skill)

    def test_start_run_collects_required_inputs(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(skill_name="client-reply-drafting", session_id=self.session.id),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "collecting_inputs")
        self.assertEqual(run.skill_name, "client-reply-drafting")
        self.assertEqual(run.session_id, self.session.id)
        missing_names = {item["name"] for item in run.missing_inputs}
        self.assertEqual(missing_names, {"reply_brief"})
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "skill_run_start").count(), 1)

    def test_start_run_with_required_inputs_becomes_ready_for_text_skill(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(
                skill_name="project-communication-analysis",
                inputs={
                    "communication_text": "Builder says we must fix site damage immediately and absorb cost.",
                },
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "ready")
        self.assertEqual(run.missing_inputs, [])
        self.assertEqual(run.inputs["communication_text"], "Builder says we must fix site damage immediately and absorb cost.")
        self.assertEqual(run.skill.execution["mode"], "llm_chat_text")
        self.assertEqual(run.dispatch["steps"][0]["tool"], "project_r.context.compose")
        self.assertIsNone(run.generated_file)

    def test_submit_input_merges_fields_until_run_is_ready(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(
                skill_name="client-reply-drafting",
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "collecting_inputs")

        updated = skills_api.submit_skill_input(
            run.id,
            skills_api.SubmitSkillInputRequest(
                inputs={
                    "reply_brief": "Please draft a cautious reply rejecting responsibility for site damage.",
                }
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(updated.status, "ready")
        self.assertEqual(updated.missing_inputs, [])
        self.assertEqual(updated.inputs["reply_brief"], "Please draft a cautious reply rejecting responsibility for site damage.")
        self.assertIsNone(updated.generated_file)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "skill_run_input").count(), 1)

    def test_user_cannot_bind_or_read_other_users_session_and_run(self):
        with self.assertRaises(HTTPException) as exc:
            skills_api.start_skill_run(
                skills_api.StartSkillRunRequest(skill_name="client-reply-drafting", session_id=self.session.id),
                self.admin,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 404)

        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(skill_name="client-reply-drafting"),
            self.employee,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            skills_api.get_skill_run(run.id, self.admin, self.db)

        self.assertEqual(exc.exception.status_code, 404)

        with self.assertRaises(HTTPException) as exc:
            skills_api.submit_skill_input(
                run.id,
                skills_api.SubmitSkillInputRequest(inputs={"project_name": "x"}),
                self.admin,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 404)

    def test_only_admin_can_reload_skills(self):
        with self.assertRaises(HTTPException) as exc:
            skills_api.reload_skills(self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)
        reloaded = skills_api.reload_skills(self.admin, self.db)
        self.assertTrue(any(skill.name == "client-reply-drafting" for skill in reloaded))

    def test_dispatcher_rejects_tool_not_allowed_by_skill_governance(self):
        runner = SkillRunner.get()
        runner._skills["unsafe-test-skill"] = SkillDefinition(
            name="unsafe-test-skill",
            display_name="Unsafe test skill",
            description="",
            category="test",
            priority="low",
            trigger=[],
            inputs=[],
            outputs=[],
            references=[],
            execution={
                "mode": "dispatcher",
                "steps": [{"id": "render", "label": "Render", "tool": "llm.complete"}],
            },
            governance={"risk_level": "low", "allowed_tools": ["other.tool"]},
            path="skills/builtin/unsafe-test-skill/SKILL.md",
        )
        run = SkillRun(
            skill_name="unsafe-test-skill",
            user_id=self.employee.id,
            session_id=self.session.id,
            status="ready",
            inputs_json="{}",
            missing_inputs_json="[]",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        with self.assertRaises(SkillDispatchError):
            SkillDispatcher().execute(self.db, run, generated_root=Path(self.generated_root.name))


if __name__ == "__main__":
    unittest.main()
