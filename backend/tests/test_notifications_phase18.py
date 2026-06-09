import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.admin as admin_api
import api.notifications as notifications_api
import api.skills as skills_api
import api.workspaces as workspaces_api
import core.skill_execution as skill_execution
from core.notification_service import notify_knowledge_review_pending, notify_user
from core.skill_runner import SkillRunner
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.knowledge_review import KnowledgeReview
from models.notification import Notification
from models.user import User
from models.workspace import Workspace, WorkspaceFile
from pathlib import Path


class _FakeGBrainAdapter:
    def sync_source(self, **kwargs):
        return {"status": "disabled"}

    def ensure_project_source(self, workspace):
        return {"ok": True, "source": {"status": "registered"}}

    def sync_project_source(self, workspace, **kwargs):
        return {"status": "ok"}


class NotificationsPhase18Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        SkillRunner._instance = None
        self.generated_root = tempfile.TemporaryDirectory()
        self.workspace_root = tempfile.TemporaryDirectory()
        self.gbrain_root = tempfile.TemporaryDirectory()
        self.original_generated_root = skill_execution.GENERATED_FILES_ROOT
        self.original_workspace_root = workspaces_api.WORKSPACES_ROOT
        self.original_gbrain_adapter = admin_api.GBrainAdapter
        self.original_workspace_gbrain_adapter = workspaces_api.GBrainAdapter
        skill_execution.GENERATED_FILES_ROOT = Path(self.generated_root.name)
        workspaces_api.WORKSPACES_ROOT = Path(self.workspace_root.name)
        admin_api.GBrainAdapter = _FakeGBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        self.env_backup = {
            key: os.environ.get(key)
            for key in (
                "GBRAIN_HOME",
                "GBRAIN_COMPANY_RAW_PATH",
                "GBRAIN_COMPANY_DERIVED_PATH",
                "GBRAIN_COMPANY_MANIFESTS_PATH",
                "GBRAIN_PREPROCESSED_ROOT",
                "GBRAIN_LOCAL_GIT_ENABLED",
                "GBRAIN_DOTENV_AUTOLOAD",
            )
        }
        root = Path(self.gbrain_root.name)
        os.environ["GBRAIN_HOME"] = str(root)
        os.environ["GBRAIN_COMPANY_RAW_PATH"] = str(root / "raw")
        os.environ["GBRAIN_COMPANY_DERIVED_PATH"] = str(root / "derived")
        os.environ["GBRAIN_COMPANY_MANIFESTS_PATH"] = str(root / "manifests")
        os.environ["GBRAIN_PREPROCESSED_ROOT"] = str(root / "_preprocessed")
        os.environ["GBRAIN_LOCAL_GIT_ENABLED"] = "false"
        os.environ["GBRAIN_DOTENV_AUTOLOAD"] = "false"
        self.admin = User(username="admin", password_hash="hash", role="admin", nickname="Admin")
        self.employee = User(username="employee", password_hash="hash", role="employee", nickname="Employee")
        self.other_admin = User(username="admin-2", password_hash="hash", role="admin", nickname="Admin 2")
        self.db.add_all([self.admin, self.employee, self.other_admin])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.employee)
        self.db.refresh(self.other_admin)

    def tearDown(self):
        skill_execution.GENERATED_FILES_ROOT = self.original_generated_root
        workspaces_api.WORKSPACES_ROOT = self.original_workspace_root
        admin_api.GBrainAdapter = self.original_gbrain_adapter
        workspaces_api.GBrainAdapter = self.original_workspace_gbrain_adapter
        for key, value in self.env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.generated_root.cleanup()
        self.workspace_root.cleanup()
        self.gbrain_root.cleanup()
        self.db.close()
        SkillRunner._instance = None

    def test_counts_filters_read_and_action_status(self):
        pending = notify_user(
            self.db,
            self.employee.id,
            category="risk",
            severity="critical",
            title="磁盘空间不足",
            action_status="pending",
            action_kind="open_settings",
            action_payload={"section": "admin"},
        )
        notify_user(
            self.db,
            self.employee.id,
            category="system",
            severity="info",
            title="系统更新说明",
        )
        self.db.commit()
        self.db.refresh(pending)

        counts = notifications_api.notification_counts(self.employee, self.db)
        self.assertEqual(counts.unread_count, 2)
        self.assertEqual(counts.pending_count, 1)

        pending_list = notifications_api.list_notifications(50, 0, "pending", self.employee, self.db)
        self.assertEqual([item.id for item in pending_list.items], [pending.id])

        with self.assertRaises(HTTPException) as exc:
            notifications_api.update_action_status(
                pending.id,
                notifications_api.UpdateActionStatusRequest(status="dismissed"),
                self.employee,
                self.db,
            )
        self.assertEqual(exc.exception.status_code, 400)

        notifications_api.update_action_status(
            pending.id,
            notifications_api.UpdateActionStatusRequest(status="done"),
            self.employee,
            self.db,
        )
        counts = notifications_api.notification_counts(self.employee, self.db)
        self.assertEqual(counts.pending_count, 0)

    def test_admin_cleanup_only_removes_expired_closed_notifications(self):
        old = notify_user(
            self.db,
            self.employee.id,
            category="system",
            severity="info",
            title="过期通知",
        )
        old.is_read = True
        old.action_status = "done"
        old.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        pending = notify_user(
            self.db,
            self.employee.id,
            category="risk",
            severity="critical",
            title="待处理风险",
            action_status="pending",
        )
        pending.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        self.db.commit()
        old_id = old.id
        pending_id = pending.id

        with self.assertRaises(HTTPException):
            notifications_api.cleanup_expired_notifications(self.employee, self.db)
        result = notifications_api.cleanup_expired_notifications(self.admin, self.db)

        self.assertEqual(result["removed"], 1)
        self.assertIsNone(self.db.get(Notification, old_id))
        self.assertIsNotNone(self.db.get(Notification, pending_id))

    def test_skill_completion_creates_task_success_notification(self):
        response = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(
                skill_name="client-reply-drafting",
                inputs={
                    "reply_brief": "Client asks us to absorb delay cost, but we should reject responsibility.",
                },
            ),
            self.employee,
            self.db,
        )

        self.assertEqual(response.status, "ready")
        self.assertEqual(
            self.db.query(Notification).filter(Notification.user_id == self.employee.id).count(),
            0,
        )

    def test_skill_missing_inputs_create_pending_task_notification(self):
        response = skills_api.start_skill_run(
            skills_api.StartSkillRunRequest(skill_name="client-reply-drafting", inputs={}),
            self.employee,
            self.db,
        )

        self.assertEqual(response.status, "collecting_inputs")
        notification = (
            self.db.query(Notification)
            .filter(Notification.user_id == self.employee.id, Notification.event_key == f"skill_run:{response.id}:blocked")
            .one()
        )
        self.assertEqual(notification.category, "task")
        self.assertEqual(notification.severity, "warning")
        self.assertEqual(notification.action_status, "pending")
        self.assertEqual(notification.action_kind, "open_skill_run")

    def test_workspace_join_and_index_refresh_create_workspace_notifications(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="BG001"),
            self.admin,
            self.db,
        )

        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.employee.id, role="member"),
            self.admin,
            self.db,
        )

        joined = (
            self.db.query(Notification)
            .filter(
                Notification.user_id == self.employee.id,
                Notification.event_key == f"workspace:{workspace.id}:member:{self.employee.id}:member",
            )
            .one()
        )
        self.assertEqual(joined.category, "workspace")

        self.db.add(
            WorkspaceFile(
                workspace_id=workspace.id,
                uploaded_by=self.employee.id,
                relative_path="99-未归档文件/a.txt",
                original_name="a.txt",
                content_type="text/plain",
                size=1,
            )
        )
        workspace_model = self.db.query(Workspace).filter(Workspace.id == workspace.id).one()
        file_path = Path(workspace_model.storage_path) / "99-未归档文件" / "a.txt"
        file_path.write_text("index me", encoding="utf-8")
        self.db.commit()
        workspaces_api.refresh_workspace_knowledge(workspace.id, self.admin, self.db)

        index_notifications = (
            self.db.query(Notification)
            .filter(
                Notification.category == "workspace",
                Notification.title == "工作区知识库录入完成",
                Notification.user_id == self.admin.id,
            )
            .all()
        )
        self.assertTrue(index_notifications)

    def test_admin_risk_alert_and_knowledge_review_pending_notifications(self):
        result = notifications_api.create_risk_alert(
            notifications_api.CreateRiskAlertRequest(title="服务器磁盘空间不足", content="剩余不足 15%"),
            self.admin,
            self.db,
        )
        self.assertEqual(result["created"], 2)
        with self.assertRaises(HTTPException):
            notifications_api.create_risk_alert(
                notifications_api.CreateRiskAlertRequest(title="员工告警"),
                self.employee,
                self.db,
            )

        review = KnowledgeReview(submitter_id=self.employee.id, content="候选知识", source="chat")
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        notify_knowledge_review_pending(self.db, review_id=review.id, source=review.source)
        self.db.commit()

        approval = self.db.query(Notification).filter(Notification.category == "approval").first()
        self.assertIsNotNone(approval)
        self.assertEqual(approval.action_status, "pending")

        admin_api.review_knowledge(
            review.id,
            admin_api.ReviewKnowledgeRequest(status="approved"),
            self.admin,
            self.db,
        )
        self.db.refresh(approval)
        self.assertEqual(approval.action_status, "done")


if __name__ == "__main__":
    unittest.main()
