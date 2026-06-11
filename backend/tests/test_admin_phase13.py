import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.admin as admin_api
import api.auth as auth_api
from app.features.auth.system_accounts import SYSTEM_ADMIN_PASSWORD, SYSTEM_ADMIN_USERNAME, ensure_system_admin
from app.features.knowledge.gbrain import project_source_paths_for_workspace
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceMember


class _FakeGBrainAdapter:
    project_sync_count = 0
    submitted_citation_fixers = []

    def sync_source(self, **kwargs):
        return {"status": "disabled"}

    def sync_project_source(self, workspace, **kwargs):
        type(self).project_sync_count += 1
        return {"status": "ok"}

    def submit_citation_fixer(self, **kwargs):
        type(self).submitted_citation_fixers.append(kwargs)
        return {"status": "ok", "result": {"id": 42, "name": "subagent", "status": "waiting"}}


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
        _FakeGBrainAdapter.submitted_citation_fixers = []
        self.env_backup = {
            key: os.environ.get(key)
            for key in (
                "GBRAIN_HOME",
                "GBRAIN_COMPANY_RAW_PATH",
                "GBRAIN_COMPANY_DERIVED_PATH",
                "GBRAIN_COMPANY_GBRAIN_READY_PATH",
                "GBRAIN_COMPANY_MANIFESTS_PATH",
                "GBRAIN_LOCAL_GIT_ENABLED",
                "GBRAIN_PREPROCESSED_ROOT",
            )
        }
        root = Path(self.gbrain_root.name)
        preprocessed_root = root / "_preprocessed"
        os.environ["GBRAIN_HOME"] = str(root)
        os.environ["GBRAIN_COMPANY_RAW_PATH"] = str(root / "raw")
        os.environ["GBRAIN_COMPANY_DERIVED_PATH"] = str(root / "derived")
        os.environ["GBRAIN_COMPANY_GBRAIN_READY_PATH"] = str(
            preprocessed_root / "company" / "company-wiki" / "gbrain-ready"
        )
        os.environ["GBRAIN_COMPANY_MANIFESTS_PATH"] = str(root / "manifests")
        os.environ["GBRAIN_LOCAL_GIT_ENABLED"] = "false"
        os.environ["GBRAIN_PREPROCESSED_ROOT"] = str(preprocessed_root)

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

    def test_admin_cannot_create_reserved_fixture_usernames(self):
        for username in ["workspace", "member", "other", "system-admin"]:
            with self.subTest(username=username):
                with self.assertRaises(HTTPException) as context:
                    admin_api.create_user(
                        admin_api.CreateAdminUserRequest(
                            username=username,
                            password="Password123",
                            nickname=username,
                        ),
                        self.admin,
                        self.db,
                    )
                self.assertEqual(context.exception.status_code, 400)

    def test_admin_user_and_group_candidates_support_management_comboboxes(self):
        self.employee.work_group = "Sales"
        self.db.commit()

        user_candidates = admin_api.list_user_candidates("emp", 30, self.admin, self.db)
        group_candidates = admin_api.list_group_candidates("", 30, self.admin, self.db)

        employee = next(item for item in user_candidates if item.username == "employee")
        self.assertEqual(employee.nickname, "Employee")
        self.assertEqual(employee.work_group, "Sales")
        self.assertFalse(employee.is_system_account)

        sales = next(item for item in group_candidates if item.group_name == "Sales")
        self.assertEqual(sales.user_count, 1)

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

    def test_system_admin_is_created_repaired_and_immutable(self):
        system_admin = ensure_system_admin(self.db)

        login = auth_api.login(
            auth_api.LoginRequest(username=SYSTEM_ADMIN_USERNAME, password=SYSTEM_ADMIN_PASSWORD),
            self.db,
        )
        self.assertEqual(login.username, SYSTEM_ADMIN_USERNAME)
        self.assertEqual(login.role, "admin")

        system_admin.role = "employee"
        system_admin.nickname = "Changed"
        system_admin.avatar = "x"
        system_admin.is_active = False
        system_admin.password_hash = auth_api.pwd_context.hash("Changed123")
        self.db.commit()

        repaired = ensure_system_admin(self.db)
        self.assertEqual(repaired.role, "admin")
        self.assertEqual(repaired.nickname, "System Admin")
        self.assertEqual(repaired.avatar, "")
        self.assertTrue(repaired.is_active)
        self.assertTrue(auth_api.pwd_context.verify(SYSTEM_ADMIN_PASSWORD, repaired.password_hash))

        forbidden_calls = [
            lambda: admin_api.update_user(
                repaired.id,
                admin_api.UpdateAdminUserRequest(nickname="Nope"),
                self.admin,
                self.db,
            ),
            lambda: admin_api.reset_user_password(
                repaired.id,
                admin_api.ResetPasswordRequest(password="Other123"),
                self.admin,
                self.db,
            ),
            lambda: admin_api.delete_user(repaired.id, self.admin, self.db),
        ]
        for call in forbidden_calls:
            with self.assertRaises(HTTPException) as exc:
                call()
            self.assertEqual(exc.exception.status_code, 400)

        with self.assertRaises(HTTPException) as exc:
            auth_api.update_me(auth_api.UpdateCurrentUserRequest(nickname="Nope"), repaired, self.db)
        self.assertEqual(exc.exception.status_code, 400)

    def test_admin_can_delete_test_user_and_reassign_shared_project_records(self):
        created = admin_api.create_user(
            admin_api.CreateAdminUserRequest(
                username="delete-me",
                password="Password123",
                nickname="Delete Me",
            ),
            self.admin,
            self.db,
        )
        shared = Workspace(
            name="Shared Project",
            slug="shared-project",
            description="",
            created_by=created.id,
            brand="BFI",
            workspace_kind="project",
            is_default=False,
        )
        self.db.add(shared)
        self.db.commit()
        self.db.refresh(shared)
        self.db.add(WorkspaceMember(workspace_id=shared.id, user_id=created.id, role="admin"))
        self.db.add(
            WorkspaceFile(
                workspace_id=shared.id,
                uploaded_by=created.id,
                relative_path="demo.txt",
                original_name="demo.txt",
                content_type="text/plain",
                size=4,
            )
        )
        self.db.commit()

        response = admin_api.delete_user(created.id, self.admin, self.db)

        self.assertTrue(response.ok)
        self.assertIsNone(self.db.get(User, created.id))
        self.assertIsNone(
            self.db.query(Workspace).filter(Workspace.created_by == created.id, Workspace.workspace_kind == "user").first()
        )
        self.assertEqual(self.db.get(Workspace, shared.id).created_by, self.admin.id)
        self.assertEqual(self.db.query(WorkspaceFile).filter(WorkspaceFile.workspace_id == shared.id).one().uploaded_by, self.admin.id)
        self.assertIsNone(self.db.query(WorkspaceMember).filter(WorkspaceMember.user_id == created.id).first())
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "admin_user_delete").count(), 1)

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
        target = (
            Path(self.gbrain_root.name)
            / "_preprocessed"
            / "company"
            / "company-wiki"
            / "gbrain-ready"
            / "reviews"
            / "知识审核沉淀.md"
        )
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

        target = (
            Path(self.gbrain_root.name)
            / "_preprocessed"
            / "company"
            / "company-wiki"
            / "gbrain-ready"
            / "reviews"
            / "知识审核沉淀.md"
        )
        text = target.read_text(encoding="utf-8")
        self.assertIn("新内容", text)
        self.assertEqual(text.count(f"knowledge_review:{review.id}"), 1)

    def test_approve_project_pending_review_promotes_and_syncs_project_source(self):
        project_root = Path(self.gbrain_root.name) / "project" / "BFI" / "BG007"
        source_rel = "02-图纸与技术资料/Drawing.pdf"
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
        source_paths = project_source_paths_for_workspace(workspace)
        pending = source_paths["derived"] / ".pending_review" / "technical" / "Drawing.md"
        pending.parent.mkdir(parents=True)
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
        approved_file = source_paths["derived"] / "technical" / "Drawing.md"
        self.assertTrue(approved_file.exists())
        self.assertFalse(pending.exists())
        self.assertIn("review_status: approved", approved_file.read_text(encoding="utf-8"))
        self.db.refresh(meta)
        self.assertEqual(meta.rag_status, "indexed")
        self.assertEqual(_FakeGBrainAdapter.project_sync_count, 1)

    def test_admin_can_submit_citation_fixer_from_gbrain_answer_review(self):
        content = (
            "# 知识纠错候选 / Knowledge Correction Candidate\n\n"
            "## GBrain 引用来源 / GBrain Citations\n\n"
            "1. `rules/written-principle.md`\n"
            "   - 标题 / Title: 书面化原则\n"
            "   - 摘录 / Excerpt: citation issue\n\n"
            "## 管理员处理建议 / Admin Triage Guidance\n\n"
            "- 中文：如果只是引用格式或缺少引用，优先后续调用 GBrain citation-fixer；\n"
        )
        review = KnowledgeReview(
            submitter_id=self.employee.id,
            content=content,
            source="gbrain_answer_correction:message:99",
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        result = admin_api.submit_review_citation_fixer(
            review.id,
            admin_api.ReviewCitationFixerRequest(),
            self.admin,
            self.db,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tracking"]["tracked_job"]["job_id"], 42)
        self.assertEqual(_FakeGBrainAdapter.submitted_citation_fixers[0]["page_slug"], "rules/written-principle")
        self.assertEqual(_FakeGBrainAdapter.submitted_citation_fixers[0]["allowed_slug_prefixes"], ["rules/*"])
        self.db.refresh(review)
        self.assertEqual(review.status, "pending")
        state_path = Path(self.gbrain_root.name) / "manifests" / "gbrain-citation-fixer-jobs.json"
        self.assertTrue(state_path.exists())
        audit = self.db.query(AuditLog).filter(AuditLog.action == "admin_knowledge_review_citation_fixer").one()
        self.assertIn(f"review_id={review.id}", audit.detail)

    def test_admin_can_submit_citation_fixer_from_gbrain_think_review(self):
        content = (
            "# GBrain Think 缺口 / 冲突审核候选\n\n"
            "## GBrain 引用来源 / GBrain Citations\n\n"
            "1. `rules/written-principle.md`\n"
            "   - 标题 / Title: 书面化原则\n"
            "   - 摘录 / Excerpt: citation issue\n\n"
        )
        review = KnowledgeReview(
            submitter_id=self.employee.id,
            content=content,
            source="gbrain_think_review:message:99",
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        result = admin_api.submit_review_citation_fixer(
            review.id,
            admin_api.ReviewCitationFixerRequest(),
            self.admin,
            self.db,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(_FakeGBrainAdapter.submitted_citation_fixers[0]["page_slug"], "rules/written-principle")

    def test_non_gbrain_answer_review_cannot_submit_citation_fixer(self):
        review = KnowledgeReview(submitter_id=self.employee.id, content="候选知识", source="chat")
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        with self.assertRaises(HTTPException) as exc:
            admin_api.submit_review_citation_fixer(
                review.id,
                admin_api.ReviewCitationFixerRequest(),
                self.admin,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(_FakeGBrainAdapter.submitted_citation_fixers, [])

    def test_admin_can_list_template_skill_status(self):
        response = admin_api.list_templates(self.admin, self.db)

        names = {item["skill_name"] for item in response["items"]}
        self.assertIn("client-reply-drafting", names)
        self.assertIn("project-communication-analysis", names)


if __name__ == "__main__":
    unittest.main()
