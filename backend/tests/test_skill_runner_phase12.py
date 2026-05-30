import os
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.skills as skills_api
import core.skill_execution as skill_execution
from core.skill_runner import SkillRunner
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.generated_file import GeneratedFile
from models.session import ChatSession
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

    def test_builtin_tag_printing_skill_can_be_listed_and_matched(self):
        skills = skills_api.list_skills(self.employee, self.db)
        names = [skill.name for skill in skills]

        self.assertIn("tag-printing", names)
        self.assertIn("client-reply-drafting", names)
        self.assertIn("project-communication-analysis", names)

        match = skills_api.match_skill(
            skills_api.MatchSkillRequest(text="帮我生成标签打印文件"),
            self.employee,
            self.db,
        )

        self.assertEqual(match.skill.name, "tag-printing")
        self.assertGreaterEqual(match.confidence, 1.0)

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

    def test_start_run_collects_required_inputs(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(skill_name="tag-printing", session_id=self.session.id),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "collecting_inputs")
        self.assertEqual(run.skill_name, "tag-printing")
        self.assertEqual(run.session_id, self.session.id)
        missing_names = {item["name"] for item in run.missing_inputs}
        self.assertEqual(missing_names, {"project_name", "project_code", "label_items", "template_file"})
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "skill_run_start").count(), 1)

    def test_start_run_executes_tag_printing_when_required_inputs_are_present(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(
                skill_name="tag-printing",
                inputs={
                    "project_name": "项目 A",
                    "project_code": "PR-A",
                    "label_items": [{"name": "样品", "quantity": 2}],
                    "template_file": "默认模板",
                },
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "completed")
        self.assertEqual(run.missing_inputs, [])
        self.assertEqual(run.inputs["project_code"], "PR-A")
        self.assertIsNotNone(run.generated_file)
        record = self.db.get(GeneratedFile, run.generated_file["id"])
        self.assertIsNotNone(record)
        self.assertTrue(Path(record.path).exists())
        with ZipFile(record.path) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("项目 A", sheet)
        self.assertIn("PR-A", sheet)

    def test_submit_input_merges_fields_until_run_is_ready(self):
        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(
                skill_name="tag-printing",
                inputs={"project_name": "项目 A"},
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(run.status, "collecting_inputs")

        updated = skills_api.submit_skill_input(
            run.id,
            skills_api.SubmitSkillInputRequest(
                inputs={
                    "project_code": "PR-A",
                    "label_items": [{"name": "样品", "quantity": 2}],
                    "template_file": "默认模板",
                }
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(updated.status, "completed")
        self.assertEqual(updated.missing_inputs, [])
        self.assertEqual(updated.inputs["project_name"], "项目 A")
        self.assertIsNotNone(updated.generated_file)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "skill_run_input").count(), 1)

    def test_user_cannot_bind_or_read_other_users_session_and_run(self):
        with self.assertRaises(HTTPException) as exc:
            skills_api.start_skill_run(
                skills_api.StartSkillRunRequest(skill_name="tag-printing", session_id=self.session.id),
                self.admin,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 404)

        run = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(skill_name="tag-printing"),
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
        self.assertTrue(any(skill.name == "tag-printing" for skill in reloaded))


if __name__ == "__main__":
    unittest.main()
