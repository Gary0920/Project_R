import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.admin as admin_api
import api.auth as auth_api
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace, WorkspaceFile


class _FakeGBrainAdapter:
    project_sync_count = 0

    def sync_source(self, **kwargs):
        return {"status": "disabled"}

    def sync_project_source(self, workspace, **kwargs):
        type(self).project_sync_count += 1
        return {"status": "ok"}


class AdminPhase13Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.admin = User(username="admin", password_hash=auth_api.pwd_context.hash("Password123"), role="admin", nickname="Admin")
        self.employee = User(username="employee", password_hash=auth_api.pwd_context.hash("Password123"), role="employee", nickname="Employee")
        self.db.add_all([self.admin, self.employee])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.employee)
        self.gbrain_root = tempfile.TemporaryDirectory()
        self.original_gbrain_adapter = admin_api.GBrainAdapter
        admin_api.GBrainAdapter = _FakeGBrainAdapter
        _FakeGBrainAdapter.project_sync_count = 0
        self.env_backup = {
            key: os.environ.get(key)
            for key in (
                "GBRAIN_HOME",
                "GBRAIN_COMPANY_RAW_PATH",
                "GBRAIN_COMPANY_DERIVED_PATH",
                "GBRAIN_COMPANY_MANIFESTS_PATH",
                "GBRAIN_LOCAL_GIT_ENABLED",
            )
        }
        root = Path(self.gbrain_root.name)
        os.environ["GBRAIN_HOME"] = str(root)
        os.environ["GBRAIN_COMPANY_RAW_PATH"] = str(root / "raw")
        os.environ["GBRAIN_COMPANY_DERIVED_PATH"] = str(root / "derived")
        os.environ["GBRAIN_COMPANY_MANIFESTS_PATH"] = str(root / "manifests")
        os.environ["GBRAIN_LOCAL_GIT_ENABLED"] = "false"

    def tearDown(self):
        admin_api.GBrainAdapter = self.original_gbrain_adapter
        for key, value in self.env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.gbrain_root.cleanup()
        self.db.close()

    def test_admin_can_create_update_and_list_users(self):
        created = admin_api.create_user(
            admin_api.CreateAdminUserRequest(
                username="new-user",
                password="Password123",
                nickname="New User",
            ),
            self.admin,
            self.db,
        )

        self.assertEqual(created.username, "new-user")
        self.assertTrue(created.is_active)

        updated = admin_api.update_user(
            created.id,
            admin_api.UpdateAdminUserRequest(is_active=False, nickname="Disabled User"),
            self.admin,
            self.db,
        )

        self.assertFalse(updated.is_active)
        self.assertEqual(updated.nickname, "Disabled User")
        users = admin_api.list_users(self.admin, self.db)
        self.assertTrue(any(user.username == "new-user" for user in users))
        self.assertGreaterEqual(self.db.query(AuditLog).filter(AuditLog.action.like("admin_user_%")).count(), 2)

    def test_admin_can_reset_user_password(self):
        updated = admin_api.reset_user_password(
            self.employee.id,
            admin_api.ResetPasswordRequest(password="NewPassword123"),
            self.admin,
            self.db,
        )

        self.assertEqual(updated.id, self.employee.id)
        login = auth_api.login(auth_api.LoginRequest(username="employee", password="NewPassword123"), self.db)
        self.assertEqual(login.username, "employee")
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_user_reset_password").count(), 1)

    def test_employee_cannot_use_admin_endpoints(self):
        with self.assertRaises(HTTPException) as exc:
            admin_api.list_users(self.employee, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_inactive_user_cannot_login(self):
        self.employee.is_active = False
        self.db.commit()

        with self.assertRaises(HTTPException) as exc:
            auth_api.login(auth_api.LoginRequest(username="employee", password="Password123"), self.db)

        self.assertEqual(exc.exception.status_code, 401)

    def test_admin_can_review_knowledge_and_read_audit_logs(self):
        review = KnowledgeReview(submitter_id=self.employee.id, content="候选知识", source="chat")
        self.db.add(review)
        old_log = AuditLog(user_id=self.employee.id, action="chat", detail="old", success=True)
        old_log.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        new_log = AuditLog(user_id=self.employee.id, action="chat", detail="hello", success=True)
        self.db.add_all([old_log, new_log])
        self.db.commit()
        self.db.refresh(review)

        pending = admin_api.list_knowledge_reviews("pending", self.admin, self.db)
        self.assertEqual([item.id for item in pending], [review.id])

        approved = admin_api.review_knowledge(
            review.id,
            admin_api.ReviewKnowledgeRequest(status="approved"),
            self.admin,
            self.db,
        )

        self.assertEqual(approved.status, "approved")
        target = Path(self.gbrain_root.name) / "derived" / "reviews" / "知识审核沉淀.md"
        self.assertIn("候选知识", target.read_text(encoding="utf-8"))
        logs = admin_api.list_audit_logs(
            None,
            (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            None,
            10,
            self.admin,
            self.db,
        )
        self.assertTrue(any(log.action == "admin_knowledge_review" for log in logs))
        self.assertFalse(any(log.detail == "old" for log in logs))

    def test_approve_review_can_modify_content_and_does_not_duplicate_sink(self):
        review = KnowledgeReview(submitter_id=self.employee.id, content="旧内容", source="chat")
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        admin_api.review_knowledge(
            review.id,
            admin_api.ReviewKnowledgeRequest(status="approved", content="新内容"),
            self.admin,
            self.db,
        )
        admin_api.review_knowledge(
            review.id,
            admin_api.ReviewKnowledgeRequest(status="approved"),
            self.admin,
            self.db,
        )

        target = Path(self.gbrain_root.name) / "derived" / "reviews" / "知识审核沉淀.md"
        text = target.read_text(encoding="utf-8")
        self.assertIn("新内容", text)
        self.assertEqual(text.count(f"knowledge_review:{review.id}"), 1)

    def test_approve_project_pending_review_promotes_and_syncs_project_source(self):
        project_root = Path(self.gbrain_root.name) / "project" / "BFI" / "BG007"
        pending = project_root / "derived" / ".pending_review" / "technical" / "Drawing.md"
        pending.parent.mkdir(parents=True)
        source_rel = "02-图纸与技术资料/Drawing.pdf"
        pending.write_text(
            "---\n"
            "review_status: pending_review\n"
            f"project_r_source_file: {source_rel}\n"
            "---\n\n"
            "# Drawing\n\n"
            "- 中文：项目图纸已审核。\n"
            "  English: The project drawing has been reviewed.\n",
            encoding="utf-8",
        )
        workspace = Workspace(
            name="BG007",
            slug="BG007",
            brand="BFI",
            created_by=self.admin.id,
            storage_path=str(project_root),
            workspace_kind="project",
        )
        self.db.add(workspace)
        self.db.commit()
        self.db.refresh(workspace)
        meta = WorkspaceFile(
            workspace_id=workspace.id,
            relative_path=source_rel,
            original_name="Drawing.pdf",
            size=10,
            content_type="application/pdf",
            uploaded_by=self.employee.id,
            rag_status="pending_review",
        )
        self.db.add(meta)
        review = KnowledgeReview(
            submitter_id=self.employee.id,
            content=pending.read_text(encoding="utf-8"),
            source=f"gbrain_project_pending_review:{workspace.id}:.pending_review/technical/Drawing.md",
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        approved = admin_api.review_knowledge(
            review.id,
            admin_api.ReviewKnowledgeRequest(status="approved"),
            self.admin,
            self.db,
        )

        self.assertEqual(approved.status, "approved")
        approved_file = project_root / "derived" / "technical" / "Drawing.md"
        self.assertTrue(approved_file.exists())
        self.assertFalse(pending.exists())
        self.assertIn("review_status: approved", approved_file.read_text(encoding="utf-8"))
        self.db.refresh(meta)
        self.assertEqual(meta.rag_status, "indexed")
        self.assertEqual(_FakeGBrainAdapter.project_sync_count, 1)

    def test_admin_can_list_template_skill_status(self):
        response = admin_api.list_templates(self.admin, self.db)

        self.assertTrue(any(item["skill_name"] == "tag-printing" for item in response["items"]))


if __name__ == "__main__":
    unittest.main()
