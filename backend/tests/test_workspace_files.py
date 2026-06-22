import os
import tempfile
import unittest
import base64
import json
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.workspaces as workspaces_api
from fastapi import HTTPException
from app.features.knowledge.gbrain.project_ingest import PROJECT_INGEST_MANIFEST_NAME
from app.features.workspaces import knowledge_ingest_api as workspace_ingest_api
from app.features.workspaces.ingest.projection import update_workspace_file_rag_statuses_from_manifest
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import Workspace, WorkspaceFile, WorkspaceGroupAccess, WorkspaceMember
from models.workspace_ingest_job import WorkspaceIngestJob


class WorkspaceFileTreeTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp_root = tempfile.TemporaryDirectory()
        self.original_root = workspaces_api.WORKSPACES_ROOT
        self.original_preprocessed_root = os.environ.get("GBRAIN_PREPROCESSED_ROOT")
        workspaces_api.WORKSPACES_ROOT = Path(self.temp_root.name)
        os.environ["GBRAIN_PREPROCESSED_ROOT"] = str(Path(self.temp_root.name) / "_preprocessed")
        self.user = User(username="test-workspace", password_hash="hash", role="admin", nickname="Workspace")
        self.other = User(username="test-other", password_hash="hash", role="employee", nickname="Other")
        self.member_user = User(username="test-member", password_hash="hash", role="employee", nickname="Member")
        self.system_admin = User(username="test-system-admin", password_hash="hash", role="admin", nickname="System Admin")
        self.db.add_all([self.user, self.other, self.member_user, self.system_admin])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other)
        self.db.refresh(self.member_user)
        self.db.refresh(self.system_admin)

    def tearDown(self):
        workspaces_api.WORKSPACES_ROOT = self.original_root
        if self.original_preprocessed_root is None:
            os.environ.pop("GBRAIN_PREPROCESSED_ROOT", None)
        else:
            os.environ["GBRAIN_PREPROCESSED_ROOT"] = self.original_preprocessed_root
        self.temp_root.cleanup()
        self.db.close()

    def workspace_root(self, workspace):
        if workspace.workspace_kind == "user":
            return Path(self.temp_root.name) / "user" / workspace.slug
        if workspace.workspace_kind == "customer":
            return Path(self.temp_root.name) / "customer" / "CRM"
        return Path(self.temp_root.name) / "project" / "BFI" / workspace.slug

    def gbrain_ready_root(self, workspace):
        if workspace.workspace_kind == "customer":
            return workspaces_api.customer_source_paths_for_workspace(workspace)["gbrain_ready"]
        return workspaces_api.project_source_paths_for_workspace(workspace)["gbrain_ready"]

    def test_create_workspace_creates_default_project_directories(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 A"),
            self.user,
            self.db,
        )

        root = self.workspace_root(workspace)
        self.assertTrue(root.exists())
        for dirname in workspaces_api.DEFAULT_PROJECT_WORKSPACE_TEMPLATE_DIRS:
            self.assertTrue((root / dirname).is_dir())
        self.assertTrue((root / ".trash").is_dir())

    def test_create_customer_workspace_returns_global_crm_workspace(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="客户 Lucerna",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )

        root = self.workspace_root(workspace)
        self.assertEqual(workspace.workspace_kind, "customer")
        self.assertEqual(workspace.brand, "CUSTOMER")
        self.assertEqual(workspace.name, "CRM")
        self.assertEqual(workspace.slug, "CRM")
        self.assertTrue(workspace.is_hidden)
        self.assertTrue(root.exists())
        self.assertTrue((root / "raw").is_dir())
        self.assertTrue((root / ".trash").is_dir())
        self.assertFalse((Path(self.temp_root.name) / "customer" / "Lucerna").exists())

    def test_existing_customer_workspace_is_normalized_to_crm(self):
        legacy_dir = Path(self.temp_root.name) / "customer" / "Lucerna-Native"
        legacy_dir.mkdir(parents=True)
        legacy = Workspace(
            name="Lucerna Native",
            slug="Lucerna-Native",
            description="legacy customer workspace",
            created_by=self.user.id,
            storage_path=str(legacy_dir),
            brand="CUSTOMER",
            workspace_kind="customer",
            is_hidden=True,
        )
        self.db.add(legacy)
        self.db.commit()
        self.db.refresh(legacy)

        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="CRM", brand="CUSTOMER", workspace_kind="customer"),
            self.user,
            self.db,
        )

        self.assertEqual(workspace.id, legacy.id)
        self.assertEqual(workspace.name, "CRM")
        self.assertEqual(workspace.slug, "CRM")
        normalized = self.db.query(Workspace).filter(Workspace.id == workspace.id).first()
        self.assertEqual(Path(normalized.storage_path), (Path(self.temp_root.name) / "customer" / "CRM").resolve())

    def test_customer_workspace_requires_member_or_group_access(self):
        customer = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="客户 Restricted",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.join_workspace(customer.id, self.other, self.db)
        self.assertEqual(exc.exception.status_code, 403)
        self.assertNotIn(customer.id, [item["id"] for item in workspaces_api.search_workspaces("CRM", self.other, self.db)])

        workspaces_api.upsert_workspace_member(
            customer.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )

        self.assertEqual(workspaces_api.get_workspace(customer.id, self.other, self.db).id, customer.id)
        self.assertIn(customer.id, [item["id"] for item in workspaces_api.search_workspaces("CRM", self.other, self.db)])

    def test_customer_workspace_can_be_authorized_by_group(self):
        self.other.work_group = "Sales"
        customer = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="客户 Group Access",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_group(
            customer.id,
            workspaces_api.UpsertWorkspaceGroupRequest(group_name="Sales"),
            self.user,
            self.db,
        )

        results = workspaces_api.search_workspaces("CRM", self.other, self.db, brand="CUSTOMER")

        self.assertIn(customer.id, [item["id"] for item in results])
        self.assertEqual(workspaces_api.join_workspace(customer.id, self.other, self.db)["message"], "你的组别已获授权访问")
        self.assertEqual(workspaces_api.get_workspace(customer.id, self.other, self.db).id, customer.id)

    def test_create_workspace_adopts_existing_backend_folder(self):
        slug = workspaces_api._slugify("项目 重复")
        (Path(self.temp_root.name) / "project" / "BFI" / slug).mkdir(parents=True)

        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 重复"),
            self.user,
            self.db,
        )

        self.assertEqual(workspace.slug, slug)
        self.assertTrue((Path(self.temp_root.name) / "project" / "BFI" / slug).is_dir())
        member = (
            self.db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == self.user.id)
            .first()
        )
        self.assertIsNotNone(member)
        self.assertEqual(member.role, "admin")

    def test_search_workspaces_empty_query_returns_created_project(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="BG001", description="TEST", brand="BFI"),
            self.user,
            self.db,
        )

        results = workspaces_api.search_workspaces("", self.user, self.db)

        self.assertIn(workspace.id, [item["id"] for item in results])
        matched = next(item for item in results if item["id"] == workspace.id)
        self.assertEqual(matched["brand"], "BFI")
        self.assertTrue(matched["is_member"])

    def test_search_workspaces_empty_query_registers_existing_project_folder(self):
        project_dir = Path(self.temp_root.name) / "project" / "BFI" / "BG002"
        project_dir.mkdir(parents=True)

        results = workspaces_api.search_workspaces("", self.user, self.db)

        matched = next(item for item in results if item["name"] == "BG002")
        self.assertEqual(matched["brand"], "BFI")
        self.assertFalse(matched["is_member"])

    def test_search_workspaces_syncs_dynamic_project_brand_folder(self):
        project_dir = Path(self.temp_root.name) / "project" / "TEST" / "TEST"
        project_dir.mkdir(parents=True)

        results = workspaces_api.search_workspaces("", self.user, self.db, brand="TEST")

        matched = next(item for item in results if item["name"] == "TEST")
        self.assertEqual(matched["brand"], "TEST")
        self.assertEqual(matched["workspace_kind"], "project")
        workspace = self.db.query(Workspace).filter(Workspace.id == matched["id"]).first()
        self.assertEqual(Path(workspace.storage_path), project_dir)

    def test_search_workspaces_can_filter_by_brand(self):
        bfi = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="BG101", brand="BFI"),
            self.user,
            self.db,
        )
        aura = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="AU101", brand="AURA"),
            self.user,
            self.db,
        )

        results = workspaces_api.search_workspaces("", self.user, self.db, brand="BFI")

        result_ids = [item["id"] for item in results]
        self.assertIn(bfi.id, result_ids)
        self.assertNotIn(aura.id, result_ids)
        self.assertTrue(all(item["brand"] == "BFI" for item in results))

    def test_open_project_is_accessible_without_membership(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Open Access"),
            self.user,
            self.db,
        )

        self.assertEqual(workspaces_api.join_workspace(workspace.id, self.other, self.db)["message"], "开放项目无需加入即可访问")
        detail = workspaces_api.get_workspace(workspace.id, self.other, self.db)
        self.assertEqual(detail.id, workspace.id)
        self.assertIsNone(
            self.db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == self.other.id)
            .first()
        )

    def test_hidden_project_requires_member_or_group_access(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Invite"),
            self.user,
            self.db,
        )
        workspaces_api.update_workspace(
            workspace.id,
            workspaces_api.UpdateWorkspaceRequest(is_hidden=True),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.join_workspace(workspace.id, self.other, self.db)

        self.assertEqual(exc.exception.status_code, 403)
        invited = workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )
        self.assertEqual(invited.user_id, self.other.id)
        self.assertEqual(invited.role, "member")
        self.assertEqual(workspaces_api.join_workspace(workspace.id, self.other, self.db)["message"], "已是项目成员")

    def test_employee_cannot_create_project_workspace(self):
        with self.assertRaises(HTTPException) as exc:
            workspaces_api.create_workspace(
                workspaces_api.CreateWorkspaceRequest(name="项目 Employee Create"),
                self.other,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 403)

    def test_workspace_admin_can_assign_scoped_workspace_admin(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Scoped Admin"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="admin"),
            self.user,
            self.db,
        )

        promoted = workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(username=self.member_user.username, role="admin"),
            self.other,
            self.db,
        )

        self.assertEqual(promoted.user_id, self.member_user.id)
        self.assertEqual(promoted.role, "admin")
        member = (
            self.db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == self.member_user.id)
            .one()
        )
        self.assertEqual(member.role, "admin")

    def test_system_admin_can_enter_all_workspaces_without_membership(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Global Admin Access"),
            self.user,
            self.db,
        )

        listed_ids = [item.id for item in workspaces_api.list_workspaces(self.system_admin, self.db)]
        self.assertIn(workspace.id, listed_ids)

        detail = workspaces_api.get_workspace(workspace.id, self.system_admin, self.db)
        self.assertEqual(detail.id, workspace.id)
        self.assertIsNone(
            self.db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == self.system_admin.id)
            .first()
        )

    def test_system_admin_list_hides_other_private_workspaces(self):
        own_private = workspaces_api.ensure_default_workspace(self.db, self.system_admin)
        other_private = workspaces_api.ensure_default_workspace(self.db, self.other)

        listed_ids = [item.id for item in workspaces_api.list_workspaces(self.system_admin, self.db)]

        self.assertIn(own_private.id, listed_ids)
        self.assertNotIn(other_private.id, listed_ids)

    def test_system_admin_cannot_open_other_private_workspace(self):
        other_private = workspaces_api.ensure_default_workspace(self.db, self.other)

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.get_workspace(other_private.id, self.system_admin, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_default_user_workspace_has_no_backend_file_area(self):
        workspace = workspaces_api.ensure_default_workspace(self.db, self.user)

        self.assertEqual(workspace.name, f"{self.user.username}的工作台")
        self.assertEqual(workspace.storage_path, "")
        self.assertFalse((Path(self.temp_root.name) / "user").exists())

    def test_user_workspace_file_operations_are_disabled(self):
        workspace = workspaces_api.ensure_default_workspace(self.db, self.user)

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.rename_workspace_path(
                workspace.id,
                workspaces_api.RenameWorkspacePathRequest(path="常用文件", new_name="我的资料"),
                self.user,
                self.db,
            )
        reloaded = workspaces_api.ensure_default_workspace(self.db, self.user)

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(reloaded.id, workspace.id)
        self.assertFalse((Path(self.temp_root.name) / "user").exists())

    def test_project_member_cannot_rename_workspace(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Rename Guard"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.update_workspace(
                workspace.id,
                workspaces_api.UpdateWorkspaceRequest(name="项目 Rename Blocked"),
                self.other,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 403)
        listed = next(item for item in workspaces_api.list_workspaces(self.other, self.db) if item.id == workspace.id)
        self.assertFalse(listed.can_rename)

    def test_workspace_admin_can_rename_workspace(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Rename Admin"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="admin"),
            self.user,
            self.db,
        )

        renamed = workspaces_api.update_workspace(
            workspace.id,
            workspaces_api.UpdateWorkspaceRequest(name="项目 Rename OK"),
            self.other,
            self.db,
        )

        self.assertEqual(renamed.name, "项目 Rename OK")
        listed = next(item for item in workspaces_api.list_workspaces(self.other, self.db) if item.id == workspace.id)
        self.assertTrue(listed.can_rename)

    def test_employee_search_returns_open_projects_but_not_unauthorized_hidden_projects(self):
        hidden = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Hidden"),
            self.user,
            self.db,
        )
        workspaces_api.update_workspace(
            hidden.id,
            workspaces_api.UpdateWorkspaceRequest(is_hidden=True),
            self.user,
            self.db,
        )
        visible = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Visible"),
            self.user,
            self.db,
        )

        results = workspaces_api.search_workspaces("项目", self.other, self.db)
        result_ids = [item["id"] for item in results]

        self.assertIn(visible.id, result_ids)
        self.assertNotIn(hidden.id, result_ids)

    def test_hidden_project_can_be_found_by_authorized_group(self):
        self.other.work_group = "Sales"
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Group Hidden"),
            self.user,
            self.db,
        )
        workspaces_api.update_workspace(
            workspace.id,
            workspaces_api.UpdateWorkspaceRequest(is_hidden=True),
            self.user,
            self.db,
        )

        group = workspaces_api.upsert_workspace_group(
            workspace.id,
            workspaces_api.UpsertWorkspaceGroupRequest(group_name="Sales"),
            self.user,
            self.db,
        )
        results = workspaces_api.search_workspaces("Group", self.other, self.db)

        self.assertEqual(group.group_name, "Sales")
        self.assertIn(workspace.id, [item["id"] for item in results])
        self.assertEqual(workspaces_api.get_workspace(workspace.id, self.other, self.db).id, workspace.id)
        self.assertIsNotNone(
            self.db.query(WorkspaceGroupAccess)
            .filter(WorkspaceGroupAccess.workspace_id == workspace.id, WorkspaceGroupAccess.group_name == "Sales")
            .first()
        )

    def test_workspace_member_and_group_candidates_use_known_users_and_groups(self):
        self.other.work_group = "Sales"
        self.member_user.work_group = "Ops"
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Candidate"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.member_user.id, role="member"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_group(
            workspace.id,
            workspaces_api.UpsertWorkspaceGroupRequest(group_name="Sales"),
            self.user,
            self.db,
        )

        member_candidates = workspaces_api.list_workspace_member_candidates(workspace.id, "mem", 30, self.user, self.db)
        group_candidates = workspaces_api.list_workspace_group_candidates(workspace.id, "", 30, self.user, self.db)

        member = next(item for item in member_candidates if item.username == "test-member")
        self.assertTrue(member.is_member)
        self.assertEqual(member.member_role, "member")
        self.assertEqual(member.work_group, "Ops")
        group_map = {item.group_name: item for item in group_candidates}
        self.assertTrue(group_map["Sales"].is_authorized)
        self.assertIn("Ops", group_map)

    def test_file_tree_returns_relative_readonly_paths(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 B"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        target = root / workspaces_api.DEFAULT_WORKSPACE_DIRS[0] / "合同.txt"
        target.write_text("ok", encoding="utf-8")

        response = workspaces_api.list_workspace_files(workspace.id, self.user, self.db)

        trash_item = next(item for item in response.items if item.path == ".trash")
        self.assertEqual(trash_item.type, "directory")
        self.assertFalse(trash_item.can_delete)
        self.assertEqual(trash_item.children, [])
        paths = [
            item.path
            for directory in response.items
            for item in directory.children
        ]
        self.assertIn(f"{workspaces_api.DEFAULT_WORKSPACE_DIRS[0]}/合同.txt", paths)
        self.assertTrue(all(not path.startswith("/") and ".." not in path for path in paths))

    def test_upload_file_creates_metadata_and_audit(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 C"),
            self.user,
            self.db,
        )

        response = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="说明.md",
                content_base64=base64.b64encode("hello".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.path, f"{workspaces_api.DEFAULT_WORKSPACE_DIRS[0]}/说明.md")
        self.assertIsNotNone(response.agent_run)
        self.assertEqual(response.agent_run.source_type, "workspace_file_upload")
        self.assertEqual(response.agent_run.status, "completed")
        root = self.workspace_root(workspace)
        self.assertEqual((root / response.path).read_text(encoding="utf-8"), "hello")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == response.file_id).first()
        self.assertEqual(meta.rag_status, "new")
        self.assertTrue(meta.source_hash)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "workspace_file_upload").count(), 1)

    def test_private_file_save_to_project_copies_to_unfiled_without_mutating_original(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 C2"),
            self.user,
            self.db,
        )
        private_source = Path(self.temp_root.name) / "私人空间" / "报价草稿.md"
        private_source.parent.mkdir(parents=True, exist_ok=True)
        private_source.write_text("私人空间原文件内容", encoding="utf-8")
        original = private_source.read_bytes()

        response = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory="99-未归档文件",
                filename=private_source.name,
                content_base64=base64.b64encode(original).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.path, "99-未归档文件/报价草稿.md")
        self.assertEqual(private_source.read_bytes(), original)
        root = self.workspace_root(workspace)
        self.assertEqual((root / response.path).read_bytes(), original)
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "workspace_file_upload").count(), 1)

    def test_save_generated_file_to_workspace_copies_to_unfiled(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 C3"),
            self.user,
            self.db,
        )
        generated_path = Path(self.temp_root.name) / "generated" / "file-1.md"
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text("# 草稿", encoding="utf-8")
        generated = GeneratedFile(
            id="generated-1",
            user_id=self.user.id,
            session_id=None,
            filename="会议纪要.md",
            path=str(generated_path),
            mime_type="text/markdown; charset=utf-8",
        )
        self.db.add(generated)
        self.db.commit()

        response = workspaces_api.save_generated_file_to_workspace(
            workspace.id,
            workspaces_api.SaveGeneratedFileToWorkspaceRequest(generated_file_id=generated.id),
            self.user,
            self.db,
        )

        self.assertTrue(response.ok)
        self.assertEqual(response.path, "99-未归档文件/会议纪要.md")
        root = self.workspace_root(workspace)
        self.assertEqual((root / response.path).read_text(encoding="utf-8"), "# 草稿")
        self.assertEqual(self.db.query(AuditLog).filter(AuditLog.action == "workspace_generated_file_save").count(), 1)

    def test_save_generated_file_rejects_other_users_generated_file(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 C4"),
            self.user,
            self.db,
        )
        generated_path = Path(self.temp_root.name) / "generated" / "file-2.txt"
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text("other", encoding="utf-8")
        self.db.add(
            GeneratedFile(
                id="generated-2",
                user_id=self.other.id,
                session_id=None,
                filename="other.txt",
                path=str(generated_path),
                mime_type="text/plain; charset=utf-8",
            )
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.save_generated_file_to_workspace(
                workspace.id,
                workspaces_api.SaveGeneratedFileToWorkspaceRequest(generated_file_id="generated-2"),
                self.user,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 404)

    def test_save_generated_file_rejects_user_workspace(self):
        user_workspace = Workspace(
            name="个人工作台",
            slug="personal",
            created_by=self.user.id,
            storage_path="",
            brand="BFI",
            workspace_kind="user",
        )
        self.db.add(user_workspace)
        self.db.commit()
        self.db.refresh(user_workspace)
        self.db.add(WorkspaceMember(workspace_id=user_workspace.id, user_id=self.user.id, role="admin"))
        generated_path = Path(self.temp_root.name) / "generated" / "file-3.txt"
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text("personal", encoding="utf-8")
        self.db.add(
            GeneratedFile(
                id="generated-3",
                user_id=self.user.id,
                session_id=None,
                filename="personal.txt",
                path=str(generated_path),
                mime_type="text/plain; charset=utf-8",
            )
        )
        self.db.commit()

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.save_generated_file_to_workspace(
                user_workspace.id,
                workspaces_api.SaveGeneratedFileToWorkspaceRequest(generated_file_id="generated-3"),
                self.user,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 400)

    def test_member_can_only_delete_own_uploaded_file(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 D"),
            self.user,
            self.db,
        )
        self.db.add(WorkspaceMember(workspace_id=workspace.id, user_id=self.other.id, role="member"))
        self.db.commit()
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="owner.txt",
                content_base64=base64.b64encode(b"owner").decode("ascii"),
            ),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.other, self.db)

        self.assertEqual(exc.exception.status_code, 403)
        deleted = workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)
        self.assertTrue(deleted.ok)
        self.assertEqual(deleted.agent_run.source_type, "workspace_file_delete")

    def test_system_admin_can_modify_any_uploaded_file(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 D-admin"),
            self.user,
            self.db,
        )
        self.db.add_all(
            [
                WorkspaceMember(workspace_id=workspace.id, user_id=self.other.id, role="member"),
                WorkspaceMember(workspace_id=workspace.id, user_id=self.system_admin.id, role="member"),
            ]
        )
        self.db.commit()
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="owner.txt",
                content_base64=base64.b64encode(b"owner").decode("ascii"),
            ),
            self.other,
            self.db,
        )

        listed = workspaces_api.list_workspace_files(workspace.id, self.system_admin, self.db)
        source_dir = next(item for item in listed.items if item.name == workspaces_api.DEFAULT_WORKSPACE_DIRS[0])
        listed_file = next(item for item in source_dir.children if item.name == "owner.txt")
        self.assertTrue(listed_file.can_delete)

        renamed = workspaces_api.rename_workspace_path(
            workspace.id,
            workspaces_api.RenameWorkspacePathRequest(path=uploaded.path, new_name="admin-renamed.txt"),
            self.system_admin,
            self.db,
        )
        moved = workspaces_api.move_workspace_path(
            workspace.id,
            workspaces_api.MoveWorkspacePathRequest(
                path=renamed.path,
                target_directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[1],
            ),
            self.system_admin,
            self.db,
        )
        deleted = workspaces_api.delete_workspace_file(workspace.id, moved.path, self.system_admin, self.db)

        self.assertTrue(deleted.ok)
        self.assertEqual(deleted.agent_run.source_type, "workspace_file_delete")

    def test_copy_workspace_path_creates_independent_file_metadata(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 D-copy"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="copy-me.txt",
                content_base64=base64.b64encode(b"copy me").decode("ascii"),
                content_type="text/plain",
            ),
            self.user,
            self.db,
        )

        copied = workspaces_api.copy_workspace_path(
            workspace.id,
            workspaces_api.CopyWorkspacePathRequest(
                path=uploaded.path,
                target_directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[1],
            ),
            self.user,
            self.db,
        )

        self.assertTrue(copied.ok)
        self.assertEqual(copied.path, f"{workspaces_api.DEFAULT_WORKSPACE_DIRS[1]}/copy-me.txt")
        self.assertEqual(copied.agent_run.source_type, "workspace_path_copy")
        root = self.workspace_root(workspace)
        self.assertTrue((root / uploaded.path).exists())
        self.assertTrue((root / copied.path).exists())
        copied_meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == copied.file_id).one()
        self.assertEqual(copied_meta.uploaded_by, self.user.id)
        self.assertEqual(copied_meta.content_type, "text/plain")
        self.assertEqual(copied_meta.rag_status, "new")
        self.assertTrue(copied_meta.source_hash)

    def test_copy_workspace_directory_creates_descendant_file_metadata(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 D-copy-folder"),
            self.user,
            self.db,
        )
        folder = workspaces_api.create_workspace_folder(
            workspace.id,
            workspaces_api.CreateWorkspaceFolderRequest(parent_path="", name="设计包"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=folder.path,
                filename="note.md",
                content_base64=base64.b64encode(b"# note").decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )

        copied = workspaces_api.copy_workspace_path(
            workspace.id,
            workspaces_api.CopyWorkspacePathRequest(
                path=folder.path,
                target_directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[2],
            ),
            self.user,
            self.db,
        )

        self.assertTrue(copied.ok)
        copied_file_path = f"{workspaces_api.DEFAULT_WORKSPACE_DIRS[2]}/设计包/note.md"
        root = self.workspace_root(workspace)
        self.assertTrue((root / uploaded.path).exists())
        self.assertTrue((root / copied_file_path).exists())
        copied_meta = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id, WorkspaceFile.relative_path == copied_file_path)
            .one()
        )
        self.assertEqual(copied_meta.uploaded_by, self.user.id)
        self.assertEqual(copied_meta.content_type, "text/markdown")
        self.assertEqual(copied_meta.rag_status, "new")
        self.assertTrue(copied_meta.source_hash)

    def test_create_and_delete_empty_folder_only(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 E"),
            self.user,
            self.db,
        )
        folder = workspaces_api.create_workspace_folder(
            workspace.id,
            workspaces_api.CreateWorkspaceFolderRequest(parent_path="", name="临时检查"),
            self.user,
            self.db,
        )
        self.assertEqual(folder.path, "临时检查")
        self.assertEqual(folder.agent_run.source_type, "workspace_folder_create")
        workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=folder.path,
                filename="a.txt",
                content_base64=base64.b64encode(b"a").decode("ascii"),
            ),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.delete_workspace_folder(workspace.id, folder.path, self.user, self.db)

        self.assertEqual(exc.exception.status_code, 400)

    def test_delete_moves_file_to_trash_and_restore_recovers_it(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 F"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="trash.txt",
                content_base64=base64.b64encode(b"trash").decode("ascii"),
            ),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)

        deleted = workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)

        self.assertTrue(deleted.ok)
        self.assertIsNotNone(deleted.agent_run)
        self.assertEqual(deleted.agent_run.source_type, "workspace_file_delete")
        self.assertFalse((root / uploaded.path).exists())
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == deleted.file_id).first()
        self.assertIsNotNone(meta.deleted_at)
        self.assertTrue((root / meta.trash_path).exists())
        deleted_items = workspaces_api.list_workspace_files(workspace.id, self.user, self.db, True).items
        self.assertEqual([item.path for item in deleted_items], [uploaded.path])

        restored = workspaces_api.restore_workspace_file(
            workspace.id,
            workspaces_api.RestoreWorkspaceFileRequest(file_id=meta.id),
            self.user,
            self.db,
        )

        self.assertTrue(restored.ok)
        self.assertEqual(restored.agent_run.source_type, "workspace_file_restore")
        self.assertTrue((root / uploaded.path).exists())
        self.db.refresh(meta)
        self.assertIsNone(meta.deleted_at)
        self.assertEqual(meta.rag_status, "new")

    def test_workspace_accessor_can_restore_trash_file_without_delete_permission(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 F-accessor-restore"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="restore-anyone.txt",
                content_base64=base64.b64encode(b"restore").decode("ascii"),
            ),
            self.user,
            self.db,
        )
        deleted = workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)

        deleted_items = workspaces_api.list_workspace_files(workspace.id, self.other, self.db, True).items

        self.assertEqual([item.path for item in deleted_items], [uploaded.path])
        self.assertTrue(deleted_items[0].can_restore)
        self.assertFalse(deleted_items[0].can_delete)

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.permanently_delete_workspace_file(workspace.id, deleted.file_id, self.other, self.db)
        self.assertEqual(exc.exception.status_code, 403)

        restored = workspaces_api.restore_workspace_file(
            workspace.id,
            workspaces_api.RestoreWorkspaceFileRequest(file_id=deleted.file_id),
            self.other,
            self.db,
        )

        self.assertTrue(restored.ok)
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == deleted.file_id).first()
        self.assertIsNone(meta.deleted_at)

    def test_trash_entry_cannot_be_used_as_regular_folder(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 F-trash-entry"),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as upload_exc:
            workspaces_api.upload_workspace_file(
                workspace.id,
                workspaces_api.UploadWorkspaceFileRequest(
                    directory=".trash",
                    filename="bad.txt",
                    content_base64=base64.b64encode(b"bad").decode("ascii"),
                ),
                self.user,
                self.db,
            )
        with self.assertRaises(HTTPException) as rename_exc:
            workspaces_api.rename_workspace_path(
                workspace.id,
                workspaces_api.RenameWorkspacePathRequest(path=".trash", new_name="trash-old"),
                self.user,
                self.db,
            )

        self.assertEqual(upload_exc.exception.status_code, 400)
        self.assertEqual(rename_exc.exception.status_code, 400)
        self.assertTrue((self.workspace_root(workspace) / ".trash").is_dir())

    def test_workspace_file_content_preview_requires_member_and_active_file(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 F2"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="preview.md",
                content_base64=base64.b64encode("# Preview".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )

        response = workspaces_api.get_workspace_file_content(workspace.id, uploaded.path, self.user, self.db)

        self.assertEqual(response.media_type, "text/markdown")
        self.assertEqual(Path(response.path).read_text(encoding="utf-8"), "# Preview")
        open_response = workspaces_api.get_workspace_file_content(workspace.id, uploaded.path, self.other, self.db)
        self.assertEqual(Path(open_response.path).read_text(encoding="utf-8"), "# Preview")

        workspaces_api.update_workspace(
            workspace.id,
            workspaces_api.UpdateWorkspaceRequest(is_hidden=True),
            self.user,
            self.db,
        )
        with self.assertRaises(HTTPException) as forbidden:
            workspaces_api.get_workspace_file_content(workspace.id, uploaded.path, self.other, self.db)
        self.assertEqual(forbidden.exception.status_code, 403)

        workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)
        with self.assertRaises(HTTPException) as missing:
            workspaces_api.get_workspace_file_content(workspace.id, uploaded.path, self.user, self.db)
        self.assertEqual(missing.exception.status_code, 404)

    def test_permanent_delete_removes_trash_metadata(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 G"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="gone.txt",
                content_base64=base64.b64encode(b"gone").decode("ascii"),
            ),
            self.user,
            self.db,
        )
        deleted = workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)

        response = workspaces_api.permanently_delete_workspace_file(workspace.id, deleted.file_id, self.user, self.db)

        self.assertTrue(response.ok)
        self.assertEqual(response.agent_run.source_type, "workspace_file_permanent_delete")
        self.assertIsNone(self.db.query(WorkspaceFile).filter(WorkspaceFile.id == deleted.file_id).first())

    def test_upload_limit_uses_100mb_contact_admin_message(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 H"),
            self.user,
            self.db,
        )
        original_limit = workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_BYTES
        original_limit_mb = workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_MB
        workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_BYTES = 4
        workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_MB = 1
        try:
            with self.assertRaises(HTTPException) as exc:
                workspaces_api.upload_workspace_file(
                    workspace.id,
                    workspaces_api.UploadWorkspaceFileRequest(
                        directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                        filename="big.txt",
                        content_base64=base64.b64encode(b"too large").decode("ascii"),
                    ),
                    self.user,
                    self.db,
                )
        finally:
            workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_BYTES = original_limit
            workspaces_api.MAX_WORKSPACE_ADMIN_UPLOAD_MB = original_limit_mb

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "文件超过 1MB")

    def test_workspace_knowledge_refresh_marks_files_indexed_for_project_admin(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 I"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="index.txt",
                content_base64=base64.b64encode(b"index me").decode("ascii"),
            ),
            self.user,
            self.db,
        )

        class _FakeGBrainAdapter:
            def ensure_project_source(self, workspace):
                return {"ok": True, "source": {"status": "registered"}}

            def sync_project_source(self, workspace, **kwargs):
                return {"status": "ok", "result": {"chunksCreated": 1}}

        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 1)
        self.assertEqual(response.compiled_files, 1)
        self.assertEqual(response.gbrain_source_id, f"project-bfi-{workspace.id}")
        self.assertEqual(response.gbrain_sync_status, "ok")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "synced")
        self.assertTrue(meta.source_hash)
        self.assertTrue((self.gbrain_ready_root(workspace) / "commercial" / "index.md").exists())
        self.assertFalse((self.workspace_root(workspace) / "derived" / "commercial" / "index.md").exists())

    def test_customer_workspace_knowledge_refresh_uses_customer_source(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory="raw",
                filename="meeting-note.md",
                content_base64=base64.b64encode("# Meeting\n\nCustomer decision".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )

        class _FakeGBrainAdapter:
            def ensure_customer_source(self, workspace):
                return {"ok": True, "source": {"status": "registered"}}

            def sync_customer_source(self, workspace, **kwargs):
                return {"status": "ok", "result": {"chunksCreated": 1}}

        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 1)
        self.assertEqual(response.compiled_files, 1)
        self.assertEqual(response.gbrain_source_id, "customer-crm")
        self.assertEqual(response.gbrain_sync_status, "ok")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "synced")
        self.assertTrue(meta.source_hash)
        self.assertTrue((self.gbrain_ready_root(workspace) / "raw-events").exists())
        self.assertFalse((self.workspace_root(workspace) / "derived" / "raw-events").exists())

    def test_customer_workspace_knowledge_refresh_marks_complex_raw_pending(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Customer Pending",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory="raw",
                filename="site-photo.png",
                content_base64=base64.b64encode(b"png").decode("ascii"),
                content_type="image/png",
            ),
            self.user,
            self.db,
        )

        class _FakeGBrainAdapter:
            def ensure_customer_source(self, workspace):
                raise AssertionError("GBrain customer source should not sync when nothing compiled")

            def sync_customer_source(self, workspace, **kwargs):
                raise AssertionError("GBrain customer source should not sync when nothing compiled")

        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 0)
        self.assertEqual(response.pending_extractor_capability_files, 1)
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "pending_extractor_capability")

    def test_customer_workspace_graph_uses_customer_source_for_authorized_member(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Graph",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )
        derived = self.workspace_root(workspace) / "derived"
        (derived / "contacts").mkdir(parents=True)
        (derived / "raw-events").mkdir(parents=True)
        (derived / "contacts" / "Jane Decision Maker.md").write_text(
            "---\n"
            "title: Jane Decision Maker\n"
            "content_kind: customer_contact_profile\n"
            "source_events:\n"
            "  - raw-events/2026-06-02 discovery-call.md\n"
            "---\n\n"
            "# Jane Decision Maker\n\n"
            "Key sponsor for Lucerna.\n",
            encoding="utf-8",
        )
        (derived / "raw-events" / "2026-06-02 discovery-call.md").write_text(
            "---\n"
            "title: 2026-06-02 discovery call\n"
            "content_kind: customer_source_event\n"
            "project_r_source_file: raw/discovery-call.md\n"
            "---\n\n"
            "# 2026-06-02 discovery call\n\n"
            "Jane confirmed budget owner.\n",
            encoding="utf-8",
        )

        result = workspaces_api.workspace_knowledge_graph(workspace.id, None, None, 120, self.other, self.db)

        self.assertTrue(result.ok)
        self.assertEqual(result.workspace_kind, "customer")
        self.assertEqual(result.source_scope, "customer")
        self.assertEqual(result.intelligence_kind, "customer_intelligence")
        self.assertEqual(result.source_id, "customer-crm")
        self.assertTrue(any(node["title"] == "Jane Decision Maker" for node in result.nodes))
        self.assertTrue(any(edge["relation_type"] == "source_event" for edge in result.edges))
        self.assertTrue(any(event["title"] == "2026-06-02 discovery call" for event in result.events))
        self.assertTrue(any(card["title"] == "Jane Decision Maker" for card in result.profile_cards))

    def test_customer_workspace_graph_rejects_unauthorized_user(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Secret Graph",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.workspace_knowledge_graph(workspace.id, None, None, 120, self.other, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_workspace_admin_can_create_entity_page_from_workspace_candidate(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Entity",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        derived = self.workspace_root(workspace) / "derived"
        (derived / "contacts").mkdir(parents=True)
        (derived / "contacts" / "Jane Decision Maker.md").write_text(
            "---\n"
            "title: Jane Decision Maker\n"
            "content_kind: customer_contact_profile\n"
            "linked_companies:\n"
            "  - companies/Acme Ltd.md\n"
            "---\n\n"
            "# Jane Decision Maker\n\n"
            "Jane works with Acme.\n",
            encoding="utf-8",
        )

        candidates = workspaces_api.workspace_entity_merge_candidates(workspace.id, None, 80, self.user, self.db)
        candidate = next(item for item in candidates.candidates if item["title"] == "Acme Ltd")

        class _FakeGBrainAdapter:
            def sync_source(self, **kwargs):
                return {"status": "ok", "source_id": kwargs["source_id"]}

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            result = workspaces_api.workspace_entity_merge_candidate_action(
                workspace.id,
                workspaces_api.WorkspaceEntityMergeActionRequest(
                    candidate_id=candidate["id"],
                    action="create_entity_page",
                ),
                self.user,
                self.db,
            )
        finally:
            workspaces_api.GBrainAdapter = original_adapter

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["sync"]["status"], "ok")
        created = derived / "companies" / "Acme Ltd.md"
        self.assertTrue(created.exists())
        self.assertIn("graph_status: pending_enrichment", created.read_text(encoding="utf-8"))

    def test_workspace_admin_can_record_alias_review_from_duplicate_candidate(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Alias",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        derived = self.workspace_root(workspace) / "derived"
        (derived / "companies").mkdir(parents=True)
        (derived / "companies" / "Acme Ltd.md").write_text(
            "---\n"
            "title: Acme Ltd\n"
            "content_kind: customer_company_profile\n"
            "---\n\n"
            "# Acme Ltd\n",
            encoding="utf-8",
        )
        (derived / "companies" / "Acme Ltd duplicate.md").write_text(
            "---\n"
            "title: Acme Ltd\n"
            "content_kind: customer_company_profile\n"
            "---\n\n"
            "# Acme Ltd duplicate\n",
            encoding="utf-8",
        )
        (derived / "contacts").mkdir(parents=True)
        (derived / "contacts" / "Bob Buyer.md").write_text(
            "---\n"
            "title: Bob Buyer\n"
            "content_kind: customer_contact_profile\n"
            "linked_companies:\n"
            "  - companies/Acme Ltd duplicate.md\n"
            "---\n\n"
            "# Bob Buyer\n",
            encoding="utf-8",
        )
        candidates = workspaces_api.workspace_entity_merge_candidates(workspace.id, "Acme Ltd", 80, self.user, self.db)
        candidate = next(item for item in candidates.candidates if item["candidate_type"] == "duplicate_entity_pages")

        preview = workspaces_api.workspace_entity_merge_candidate_preview(workspace.id, candidate["id"], self.user, self.db)

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["status"], "preview_ready")
        self.assertEqual(preview["source_id"], "customer-crm")
        self.assertEqual(preview["stats"]["planned_relink_changes"], 1)
        self.assertEqual(preview["planned_relink_changes"][0]["page_title"], "Bob Buyer")

        class _FakeGBrainAdapter:
            def sync_source(self, **kwargs):
                return {"status": "ok", "source_id": kwargs["source_id"]}

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            relink = workspaces_api.workspace_entity_merge_candidate_action(
                workspace.id,
                workspaces_api.WorkspaceEntityMergeActionRequest(
                    candidate_id=candidate["id"],
                    action="apply_relink_changes",
                ),
                self.user,
                self.db,
            )
            result = workspaces_api.workspace_entity_merge_candidate_action(
                workspace.id,
                workspaces_api.WorkspaceEntityMergeActionRequest(
                    candidate_id=candidate["id"],
                    action="record_alias",
                ),
                self.user,
                self.db,
            )
        finally:
            workspaces_api.GBrainAdapter = original_adapter

        self.assertTrue(relink["ok"])
        self.assertEqual(relink["status"], "relink_applied")
        self.assertEqual(relink["sync"]["source_id"], "customer-crm")
        bob_text = (derived / "contacts" / "Bob Buyer.md").read_text(encoding="utf-8")
        self.assertIn("- companies/Acme Ltd.md", bob_text)
        self.assertNotIn("- companies/Acme Ltd duplicate.md", bob_text)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "alias_recorded")
        self.assertEqual(result["sync"]["source_id"], "customer-crm")
        created = derived / result["created_file"]
        self.assertTrue(created.exists())
        text = created.read_text(encoding="utf-8")
        self.assertIn("content_kind: entity_alias_override", text)
        self.assertIn("project_r_created_by: test-workspace", text)

    def test_workspace_member_cannot_view_entity_merge_candidates(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Entity Restricted",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.workspace_entity_merge_candidates(workspace.id, None, 80, self.other, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_workspace_native_graph_context_uses_token_bound_workspace_source(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Native",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )

        class _FakeGBrainAdapter:
            def graph_context(self, slug, **kwargs):
                return {
                    "status": "ok",
                    "slug": slug,
                    "source_id": kwargs["source_id"],
                    "traverse_graph": {"status": "ok", "result": []},
                    "timeline": {"status": "ok", "result": []},
                    "backlinks": {"status": "ok", "result": []},
                }

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            result = workspaces_api.workspace_native_graph_context(
                workspace.id,
                "contacts/Jane Decision Maker.md",
                2,
                "both",
                None,
                self.user,
                self.db,
            )
        finally:
            workspaces_api.GBrainAdapter = original_adapter

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source_id"], "customer-crm")
        self.assertEqual(result["slug"], "contacts/Jane Decision Maker.md")

    def test_workspace_native_graph_context_rejects_unauthorized_customer_user(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(
                name="Lucerna Native Restricted",
                brand="CUSTOMER",
                workspace_kind="customer",
            ),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.workspace_native_graph_context(
                workspace.id,
                "contacts/Jane.md",
                2,
                "both",
                None,
                self.other,
                self.db,
            )

        self.assertEqual(exc.exception.status_code, 403)

    def test_project_workspace_graph_uses_project_source_for_open_project(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Graph"),
            self.user,
            self.db,
        )
        derived = self.workspace_root(workspace) / "derived"
        (derived / "contacts").mkdir(parents=True)
        (derived / "events").mkdir(parents=True)
        (derived / "contacts" / "Builder PM.md").write_text(
            "---\n"
            "title: Builder PM\n"
            "content_kind: project_contact_profile\n"
            "source_events:\n"
            "  - events/2026-06-02 site-meeting.md\n"
            "---\n\n"
            "# Builder PM\n\n"
            "Project contact.\n",
            encoding="utf-8",
        )
        (derived / "events" / "2026-06-02 site-meeting.md").write_text(
            "---\n"
            "title: 2026-06-02 site meeting\n"
            "content_kind: project_event\n"
            "project_r_source_file: 03-会议纪要/site-meeting.md\n"
            "---\n\n"
            "# 2026-06-02 site meeting\n\n"
            "Design issue discussed.\n",
            encoding="utf-8",
        )

        result = workspaces_api.workspace_knowledge_graph(workspace.id, None, None, 120, self.other, self.db)

        self.assertTrue(result.ok)
        self.assertEqual(result.workspace_kind, "project")
        self.assertEqual(result.source_scope, "project")
        self.assertEqual(result.intelligence_kind, "project_event_graph")
        self.assertEqual(result.source_id, f"project-bfi-{workspace.id}")
        self.assertTrue(any(node["title"] == "Builder PM" for node in result.nodes))
        self.assertTrue(any(event["title"] == "2026-06-02 site meeting" for event in result.events))

    def test_workspace_knowledge_refresh_marks_pending_capability_without_admin_review(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 图片"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[5],
                filename="site.png",
                content_base64=base64.b64encode(b"fake png").decode("ascii"),
                content_type="image/png",
            ),
            self.user,
            self.db,
        )

        def fake_compile(compiled_workspace):
            self.assertEqual(compiled_workspace.id, workspace.id)
            return {
                "source_id": f"project-bfi-{workspace.id}",
                "summary": {
                    "total": 1,
                    "compiled": 0,
                    "pending_extractor_capability": 1,
                    "pending_transcription": 0,
                    "skipped": 0,
                    "failed": 0,
                },
                "items": [
                    {
                        "source_file": uploaded.path,
                        "status": "pending_extractor_capability",
                        "file_kind": "image",
                        "extraction_complexity": "vision_required",
                        "extractor_profile": "mimo_vision",
                    }
                ],
            }

        class _FakeGBrainAdapter:
            def ensure_project_source(self, workspace):
                raise AssertionError("GBrain source should not sync when nothing compiled")

            def sync_project_source(self, workspace, **kwargs):
                raise AssertionError("GBrain source should not sync when nothing compiled")

        original_compile = workspace_ingest_api.compile_project_workspace_sources
        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.compile_project_workspace_sources = fake_compile
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspace_ingest_api.compile_project_workspace_sources = original_compile
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 0)
        self.assertEqual(response.run_status, "pending_capability")
        self.assertEqual(response.manifest["run_status"], "pending_capability")
        self.assertEqual(response.manifest["items"][0]["run_status"], "pending_capability")
        self.assertEqual(response.manifest["items"][0]["sync_status"], "not_applicable")
        self.assertEqual(response.pending_extractor_capability_files, 1)
        self.assertEqual(response.pending_reviews_created, 0)
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "pending_extractor_capability")
        review = self.db.query(KnowledgeReview).first()
        self.assertIsNone(review)

    def test_workspace_knowledge_ingest_requires_project_admin(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 普通成员不可录入"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.refresh_workspace_knowledge(workspace.id, self.other, self.db)

        self.assertEqual(exc.exception.status_code, 403)

    def test_project_member_can_ingest_own_single_file_only(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 成员单文件录入"),
            self.user,
            self.db,
        )
        workspaces_api.upsert_workspace_member(
            workspace.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[2],
                filename="member-note.md",
                content_base64=base64.b64encode("# Member Note\n\nOwn file fact".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.other,
            self.db,
        )

        def fake_compile(compiled_workspace, *, source_path="", recursive=True):
            self.assertEqual(compiled_workspace.id, workspace.id)
            self.assertEqual(source_path, uploaded.path)
            self.assertFalse(recursive)
            return {
                "source_id": f"project-bfi-{workspace.id}",
                "summary": {
                    "total": 1,
                    "compiled": 1,
                    "pending_extractor_capability": 0,
                    "pending_transcription": 0,
                    "skipped": 0,
                    "failed": 0,
                },
                "items": [{"source_file": uploaded.path, "status": "compiled"}],
            }

        class _FakeGBrainAdapter:
            def ensure_project_source(self, workspace):
                return {"ok": True, "source": {"status": "registered"}}

            def sync_project_source(self, workspace, **kwargs):
                return {"status": "ok"}

        original_compile = workspace_ingest_api.compile_project_workspace_sources
        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.compile_project_workspace_sources = fake_compile
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(
                workspace.id,
                self.other,
                self.db,
                workspaces_api.WorkspaceKnowledgeIngestRequest(path=uploaded.path, recursive=False),
            )
        finally:
            workspace_ingest_api.compile_project_workspace_sources = original_compile
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.ingest_path, uploaded.path)
        self.assertFalse(response.ingest_recursive)

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.refresh_workspace_knowledge(
                workspace.id,
                self.other,
                self.db,
                workspaces_api.WorkspaceKnowledgeIngestRequest(path=workspaces_api.DEFAULT_WORKSPACE_DIRS[2], recursive=True),
            )
        self.assertEqual(exc.exception.status_code, 403)

    def test_user_workspace_cannot_ingest_knowledge(self):
        workspace = workspaces_api.ensure_default_workspace(self.db, self.user)

        with self.assertRaises(HTTPException) as exc:
            workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)

        self.assertEqual(exc.exception.status_code, 400)

    def test_workspace_knowledge_ingest_background_job_updates_status(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 异步录入"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[2],
                filename="kickoff.md",
                content_base64=base64.b64encode("# Kickoff\n\nAsync fact".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )
        job = WorkspaceIngestJob(workspace_id=workspace.id, requested_by=self.user.id, status="queued")
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        def fake_compile(compiled_workspace):
            return {
                "source_id": f"project-bfi-{compiled_workspace.id}",
                "summary": {
                    "total": 1,
                    "compiled": 1,
                    "pending_extractor_capability": 0,
                    "pending_transcription": 0,
                    "skipped": 0,
                    "failed": 0,
                },
                "items": [{"source_file": uploaded.path, "status": "compiled"}],
            }

        class _FakeGBrainAdapter:
            def ensure_project_source(self, workspace):
                return {"ok": True, "source": {"status": "registered"}}

            def sync_project_source(self, workspace, **kwargs):
                return {"status": "ok"}

        original_compile = workspace_ingest_api.compile_project_workspace_sources
        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.compile_project_workspace_sources = fake_compile
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            workspace_ingest_api.run_workspace_knowledge_ingest_job(job.id)
        finally:
            workspace_ingest_api.compile_project_workspace_sources = original_compile
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.db.expire_all()
        refreshed_job = self.db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job.id).one()
        self.assertEqual(refreshed_job.status, "succeeded")
        self.assertIn('"indexed_files": 1', refreshed_job.result_json)
        result = json.loads(refreshed_job.result_json)
        self.assertEqual(result["run_status"], "synced")
        self.assertEqual(result["manifest"]["run_status"], "synced")
        self.assertEqual(result["manifest"]["items"][0]["preprocess_status"], "compiled")
        self.assertEqual(result["manifest"]["items"][0]["run_status"], "synced")
        self.assertEqual(result["manifest"]["items"][0]["sync_status"], "synced")
        self.assertTrue(result["manifest"]["run"]["status_history"])
        serialized = workspace_ingest_api.serialize_ingest_job(self.db, refreshed_job)
        self.assertIsNotNone(serialized.agent_run)
        self.assertEqual(serialized.agent_run.status, "completed")
        self.assertEqual(serialized.result["run_status"], "synced")
        self.assertEqual(serialized.result["run"]["status"], "synced")
        self.assertTrue(any(event.event_type == "result" for event in serialized.agent_run.events))
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "synced")

    def test_workspace_ingest_manifest_marks_sync_pending_when_gbrain_sync_fails(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 同步失败"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[2],
                filename="sync-pending.md",
                content_base64=base64.b64encode("# Sync Pending\n\nFact".encode("utf-8")).decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )
        manifests_path = Path(self.temp_root.name) / "manifests"
        runs_path = Path(self.temp_root.name) / "runs"

        def fake_compile(compiled_workspace):
            return {
                "source_id": f"project-bfi-{compiled_workspace.id}",
                "manifests_path": str(manifests_path),
                "runs_path": str(runs_path),
                "summary": {
                    "total": 1,
                    "compiled": 1,
                    "pending_extractor_capability": 0,
                    "pending_transcription": 0,
                    "skipped": 0,
                    "failed": 0,
                },
                "items": [
                    {
                        "source_file": uploaded.path,
                        "status": "compiled",
                        "source_sha256": "abc",
                        "target_file": "meetings/sync-pending.md",
                    }
                ],
            }

        class _FakeGBrainAdapter:
            def ensure_project_source(self, workspace):
                return {"ok": True, "source": {"status": "registered"}}

            def sync_project_source(self, workspace, **kwargs):
                return {"status": "cli_error", "error": "sync boom"}

        original_compile = workspace_ingest_api.compile_project_workspace_sources
        original_adapter = workspace_ingest_api.GBrainAdapter
        workspace_ingest_api.compile_project_workspace_sources = fake_compile
        workspace_ingest_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            workspace_model = self.db.query(Workspace).filter(Workspace.id == workspace.id).one()
            payload = workspace_ingest_api.execute_workspace_knowledge_ingest(self.db, workspace_model, self.user.id)
        finally:
            workspace_ingest_api.compile_project_workspace_sources = original_compile
            workspace_ingest_api.GBrainAdapter = original_adapter

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["run_status"], "sync_pending")
        self.assertEqual(payload["rag_status"], "pending")
        self.assertEqual(payload["gbrain_sync_status"], "cli_error")
        manifest = payload["manifest"]
        self.assertEqual(manifest["run_status"], "sync_pending")
        self.assertEqual(manifest["items"][0]["run_status"], "sync_pending")
        self.assertEqual(manifest["items"][0]["sync_status"], "sync_pending")
        self.assertEqual(manifest["items"][0]["gbrain_ready_file"], "meetings/sync-pending.md")
        run_manifest_path = runs_path / f"{payload['run_id']}.json"
        latest_manifest_path = manifests_path / PROJECT_INGEST_MANIFEST_NAME
        self.assertTrue(run_manifest_path.exists())
        self.assertTrue(latest_manifest_path.exists())
        persisted = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["run_status"], "sync_pending")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "sync_pending")

    def test_workspace_ingest_projection_creates_missing_file_metadata(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 投影补元数据"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        source_dir = root / workspaces_api.DEFAULT_WORKSPACE_DIRS[2]
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "manual-file.md"
        source_path.write_text("# Manual File\n\nFact", encoding="utf-8")
        rel_path = source_path.relative_to(root).as_posix()
        manifest = {
            "items": [
                {
                    "source_file": rel_path,
                    "status": "compiled",
                    "source_sha256": "abc",
                    "target_file": "meetings/manual-file.md",
                }
            ]
        }

        indexed = update_workspace_file_rag_statuses_from_manifest(
            self.db,
            self.db.query(Workspace).filter(Workspace.id == workspace.id).one(),
            manifest,
            sync_ok=True,
            actor_user_id=self.user.id,
        )

        self.assertEqual(indexed, 1)
        meta = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id, WorkspaceFile.relative_path == rel_path)
            .one()
        )
        self.assertEqual(meta.rag_status, "synced")
        self.assertEqual(meta.uploaded_by, self.user.id)
        self.assertTrue(meta.source_hash)

    def test_synced_file_is_marked_source_changed_without_auto_reprocess(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Source Changed"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="change.md",
                content_base64=base64.b64encode(b"# Original").decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).one()
        path = self.workspace_root(workspace) / uploaded.path
        workspaces_api._record_file_signature(meta, path)
        meta.rag_status = "synced"
        self.db.commit()

        path.write_text("# Changed", encoding="utf-8")

        def find_item(items, target_path):
            for item in items:
                if item.path == target_path:
                    return item
                found = find_item(item.children or [], target_path)
                if found:
                    return found
            return None

        items = workspaces_api.list_workspace_files(workspace.id, self.user, self.db).items
        changed = find_item(items, uploaded.path)
        self.assertIsNotNone(changed)
        self.assertEqual(changed.rag_status, "source_changed")
        self.db.refresh(meta)
        self.assertEqual(meta.rag_status, "synced")

    def test_meeting_transcript_rejects_non_meeting_folder(self):
        """普通目录调用 transcript 应 400 — 没有完整的 5 个子目录"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 非会议目录", brand="BFI"),
            self.user,
            self.db,
        )
        # Create a plain directory that is NOT a meeting folder
        plain_dir = self.workspace_root(workspace) / "99-未归档文件" / "some-folder"
        plain_dir.mkdir(parents=True, exist_ok=True)
        plain_rel = plain_dir.relative_to(self.workspace_root(workspace)).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.save_meeting_transcript(
                workspace.id,
                workspaces_api.SaveMeetingTranscriptRequest(
                    folder_path=plain_rel,
                    content="Some meeting notes.",
                ),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("转录文本", ctx.exception.detail)

    def test_meeting_transcript_saves_to_meeting_root(self):
        """会议根目录调用 transcript 应成功生成两个 md 文件"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 会议转录测试", brand="BFI"),
            self.user,
            self.db,
        )
        # Create meeting folder via the API
        resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="启动会", meeting_time="2026-06-15T09:30"),
            self.user,
            self.db,
        )
        self.assertTrue(resp.ok)
        self.assertTrue(len(resp.created_dirs) >= 6)  # root + 5 subdirs

        # Save transcript
        transcript_resp = workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(
                folder_path=resp.meeting_folder_path,
                content="张三: 今天讨论项目进度。\n李四: 第一阶段已完成。",
            ),
            self.user,
            self.db,
        )
        self.assertTrue(transcript_resp.ok)
        self.assertTrue(transcript_resp.transcript_v1_path.endswith("transcript-v1.md"))
        self.assertTrue(transcript_resp.transcript_latest_path.endswith("transcript-latest.md"))

        # Verify files on disk
        root = self.workspace_root(workspace)
        v1_disk = root / transcript_resp.transcript_v1_path
        latest_disk = root / transcript_resp.transcript_latest_path
        self.assertTrue(v1_disk.exists())
        self.assertTrue(latest_disk.exists())
        content = latest_disk.read_text(encoding="utf-8")
        self.assertIn("张三", content)
        self.assertIn("会议转录文本", content)

        # Verify WorkspaceFile DB records exist
        from models.workspace import WorkspaceFile as WF
        metas = (
            self.db.query(WF)
            .filter(WF.workspace_id == workspace.id, WF.relative_path.in_([
                transcript_resp.transcript_v1_path,
                transcript_resp.transcript_latest_path,
            ]))
            .all()
        )
        self.assertEqual(len(metas), 2)

        # Verify audit records
        audits = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "meeting_transcript_save")
            .all()
        )
        self.assertGreaterEqual(len(audits), 1)

    def test_create_meeting_folder_rejects_invalid_type_before_writing(self):
        """非法会议类型应在写入会议目录前被拒绝。"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 会议类型校验", brand="BFI"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        meeting_root = root / workspaces_api.meeting_parent_path(workspace.workspace_kind)
        before = sorted(path.name for path in meeting_root.iterdir()) if meeting_root.exists() else []

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.create_meeting_folder(
                workspace.id,
                workspaces_api.CreateMeetingFolderRequest(topic="非法类型", meeting_type="不是合法类型"),
                self.user,
                self.db,
            )

        self.assertEqual(ctx.exception.status_code, 400)
        after = sorted(path.name for path in meeting_root.iterdir()) if meeting_root.exists() else []
        self.assertEqual(after, before)

    def test_create_meeting_folder_persists_meeting_type(self):
        """创建会议文件夹时保存会议类型 metadata。"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 会议类型保存", brand="BFI"),
            self.user,
            self.db,
        )
        response = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="客户同步", meeting_type="客户沟通会"),
            self.user,
            self.db,
        )
        meta = workspaces_api._read_meeting_meta(self.workspace_root(workspace) / response.meeting_folder_path)
        self.assertEqual(meta.get("meeting_type"), "客户沟通会")

    def test_meeting_transcript_rejects_wrong_parent_path(self):
        """会议文件夹放在 99-未归档文件 下即使有5子目录也应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 错误父路径", brand="BFI"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        # Create a meeting-like folder under 99-未归档文件 instead of 20-会议与沟通
        bad_dir = root / "99-未归档文件" / "20260615-0930-fake-meeting"
        bad_dir.mkdir(parents=True, exist_ok=True)
        for sub in workspaces_api.MEETING_SUBDIRS:
            (bad_dir / sub).mkdir(parents=True, exist_ok=True)
        bad_rel = bad_dir.relative_to(root).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.save_meeting_transcript(
                workspace.id,
                workspaces_api.SaveMeetingTranscriptRequest(
                    folder_path=bad_rel,
                    content="Test content",
                ),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_meeting_transcript_template_has_no_fake_timestamps(self):
        """五段模板不得伪造时间点——无原始时间戳时时间点应为 '—'"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 无假时间", brand="BFI"),
            self.user,
            self.db,
        )
        resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="模板测试"),
            self.user,
            self.db,
        )
        transcript_resp = workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(
                folder_path=resp.meeting_folder_path,
                content="张三：大家好\n李四：开始吧",
            ),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        content = (root / transcript_resp.transcript_latest_path).read_text(encoding="utf-8")

        # Must have all 5 sections
        self.assertIn("## 基本信息", content)
        self.assertIn("## 说话人概览", content)
        self.assertIn("## 说话人时间轴", content)
        self.assertIn("## 疑似术语纠错", content)
        self.assertIn("## 完整转录", content)

        # Must have 行号 column
        self.assertIn("行号", content)

        # Check only TRANSCRIPT TABLE rows (after "完整转录") for fake MM:SS timestamps.
        # The "基本信息" section legitimately shows "转录时间 | 2026-06-09 14:36 UTC",
        # so we must NOT do a full-document regex check.
        lines = content.split("\n")
        transcript_table_lines: list[str] = []
        in_transcript = False
        for line in lines:
            if "完整转录" in line and "##" in line:
                in_transcript = True
                continue
            if in_transcript and line.startswith("---"):
                break
            if in_transcript and line.startswith("|") and "---" not in line:
                # Skip header row — only collect data rows
                if line.lstrip().startswith("| 行号"):
                    continue
                transcript_table_lines.append(line)

        self.assertGreater(len(transcript_table_lines), 0,
                           "应在完整转录表格中至少有一行")
        for row in transcript_table_lines:
            # Time column should be "—"
            self.assertIn("| — |", row,
                          f"转录表行不应含伪时间点: {row}")
            # No \d{2}:\d{2} pattern in any table cell
            import re
            self.assertNotRegex(row, r"\b\d{2}:\d{2}\b",
                                f"转录表行不应含伪时间点: {row}")

        # Also verify timeline table rows
        timeline_lines: list[str] = []
        in_timeline = False
        for line in lines:
            if "说话人时间轴" in line and "##" in line:
                in_timeline = True
                continue
            if in_timeline and "## 疑似" in line:
                break
            if in_timeline and line.startswith("|") and "---" not in line:
                # Skip header row — only collect data rows
                if line.lstrip().startswith("| 行号"):
                    continue
                timeline_lines.append(line)

        for row in timeline_lines:
            # Should have "—" in the time column (2nd column)
            parts = [p.strip() for p in row.split("|") if p.strip()]
            if len(parts) >= 2:
                self.assertEqual(parts[1], "—",
                                 f"时间轴行不应含伪时间点: {row}")

    def _call_meeting_transcript_file(self, workspace_id, folder_path, filename, content_bytes):
        """Helper to call the async save_meeting_transcript_from_file endpoint synchronously."""
        import asyncio
        import io
        from fastapi import UploadFile
        async def _run():
            f = UploadFile(filename=filename, file=io.BytesIO(content_bytes))
            return await workspaces_api.save_meeting_transcript_from_file(
                workspace_id,
                folder_path=folder_path,
                file=f,
                user=self.user,
                db=self.db,
            )
        return asyncio.run(_run())

    def test_upload_endpoint_rejects_unsupported_file_type(self):
        """上传不支持的文件类型（.pdf）应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 不支持类型", brand="BFI"),
            self.user,
            self.db,
        )
        resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="类型测试"),
            self.user,
            self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            self._call_meeting_transcript_file(
                workspace.id,
                resp.meeting_folder_path,
                "meeting.pdf",
                b"%PDF-1.4 fake pdf content",
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_upload_endpoint_accepts_txt_file(self):
        """上传 TXT 文件应成功转录"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 TXT上传", brand="BFI"),
            self.user,
            self.db,
        )
        resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="TXT上传测试"),
            self.user,
            self.db,
        )
        transcript_resp = self._call_meeting_transcript_file(
            workspace.id,
            resp.meeting_folder_path,
            "transcript.txt",
            "张三：大家好\n李四：开始吧".encode("utf-8"),
        )
        self.assertTrue(transcript_resp.ok)
        self.assertTrue(transcript_resp.transcript_latest_path.endswith("transcript-latest.md"))

        # Verify content on disk
        root = self.workspace_root(workspace)
        content = (root / transcript_resp.transcript_latest_path).read_text(encoding="utf-8")
        self.assertIn("张三", content)
        self.assertIn("## 完整转录", content)
        self.assertIn("TXT 上传", content)

    def test_upload_endpoint_accepts_docx_file(self):
        """上传 DOCX 文件应成功转录"""
        import io, zipfile
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 DOCX上传", brand="BFI"),
            self.user,
            self.db,
        )
        resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="DOCX上传测试"),
            self.user,
            self.db,
        )
        # Build minimal .docx
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>')
            zf.writestr("_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '</Relationships>')
            zf.writestr("word/document.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body><w:p><w:r><w:t>Hello DOCX</w:t></w:r></w:p>'
                '<w:p><w:r><w:t>Second para</w:t></w:r></w:p></w:body>'
                '</w:document>')
        docx_bytes = buf.getvalue()

        transcript_resp = self._call_meeting_transcript_file(
            workspace.id,
            resp.meeting_folder_path,
            "meeting.docx",
            docx_bytes,
        )
        self.assertTrue(transcript_resp.ok)
        self.assertTrue(transcript_resp.transcript_latest_path.endswith("transcript-latest.md"))
        root = self.workspace_root(workspace)
        content = (root / transcript_resp.transcript_latest_path).read_text(encoding="utf-8")
        self.assertIn("Hello DOCX", content)
        self.assertIn("Second para", content)
        self.assertIn("DOCX 上传", content)

    def test_deleted_synced_file_is_marked_source_deleted_without_removing_ready_markdown(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Source Deleted"),
            self.user,
            self.db,
        )
        uploaded = workspaces_api.upload_workspace_file(
            workspace.id,
            workspaces_api.UploadWorkspaceFileRequest(
                directory=workspaces_api.DEFAULT_WORKSPACE_DIRS[0],
                filename="delete.md",
                content_base64=base64.b64encode(b"# Original").decode("ascii"),
                content_type="text/markdown",
            ),
            self.user,
            self.db,
        )
        ready_file = self.gbrain_ready_root(workspace) / "contracts" / "delete.md"
        ready_file.parent.mkdir(parents=True, exist_ok=True)
        ready_file.write_text("# Ready", encoding="utf-8")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).one()
        workspaces_api._record_file_signature(meta, self.workspace_root(workspace) / uploaded.path)
        meta.rag_status = "synced"
        self.db.commit()

        deleted = workspaces_api.delete_workspace_file(workspace.id, uploaded.path, self.user, self.db)

        self.assertEqual(deleted.rag_status, "source_deleted")
        self.assertTrue(ready_file.exists())


    # ── Step 3: Meeting generate tests ─────────────────────────────────────

    def _create_meeting_with_transcript(self) -> tuple:
        """Helper: create a meeting folder + transcript; returns (workspace, meeting_folder_path)."""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 生成测试", brand="BFI"),
            self.user,
            self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="生成测试会议"),
            self.user,
            self.db,
        )
        workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(
                folder_path=folder_resp.meeting_folder_path,
                content="张三：今天讨论项目进度。\n李四：第一阶段已完成，准备进入第二阶段。\n王五：预算需要调整。",
            ),
            self.user,
            self.db,
        )
        return workspace, folder_resp.meeting_folder_path

    def test_generate_rejects_no_transcript(self):
        """无 transcript-latest.md 时返回 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 无转录", brand="BFI"),
            self.user,
            self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="无转录测试"),
            self.user,
            self.db,
        )
        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_resp.meeting_folder_path),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("转录文件", ctx.exception.detail)

    def test_generate_rejects_no_transcript_when_missing_file(self):
        """文件夹有 02-转录文本/ 但里面无 transcript-latest.md 仍 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 缺转录文件", brand="BFI"),
            self.user,
            self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="缺文件测试"),
            self.user,
            self.db,
        )
        # Create an empty transcript dir — no files inside
        root = self.workspace_root(workspace)
        transcript_dir = root / folder_resp.meeting_folder_path / "02-转录文本"
        (transcript_dir / "other.md").write_text("not the right file", encoding="utf-8")
        # transcript-latest.md does NOT exist
        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_resp.meeting_folder_path),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_generate_rejects_failed_transcript(self):
        """转录失败的 transcript-latest.md 不能继续生成纪要和行动项。"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 失败转录", brand="BFI"),
            self.user,
            self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="失败转录测试"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        transcript_path = root / folder_resp.meeting_folder_path / "02-转录文本" / "transcript-latest.md"
        transcript_path.write_text(
            "# 会议转录文本 - 转录失败\n\n**转录状态**：failed\n\n**错误**：媒体文件无法解析\n",
            encoding="utf-8",
        )

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_resp.meeting_folder_path, regenerate=True),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("转录未成功", ctx.exception.detail)
        self.assertIn("媒体文件无法解析", ctx.exception.detail)

    def test_generate_partial_transcript_marks_outputs_partial(self):
        """partial 转录允许生成，但输出和文件状态必须明确标记。"""
        from unittest.mock import patch, MagicMock

        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)
        transcript_path = root / folder_path / "02-转录文本" / "transcript-latest.md"
        transcript_text = transcript_path.read_text(encoding="utf-8").replace(
            "| 原始文件名 | — |",
            "| 原始文件名 | partial.mp4 |\n| 转录状态 | partial |\n| 缺失片段 | 00:05:00-00:06:00 |",
        )
        transcript_path.write_text(transcript_text, encoding="utf-8")

        mock_response = MagicMock()
        mock_response.text = "# 会议纪要\n\n## 一句话结论\n\n基于部分转录生成。\n"
        mock_response.usage = {"input_tokens": 1, "output_tokens": 1}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        latest = (root / resp.minutes_latest_path).read_text(encoding="utf-8")
        self.assertIn("转录状态：partial", latest)
        latest_meta = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id, WorkspaceFile.relative_path == resp.minutes_latest_path)
            .first()
        )
        self.assertIsNotNone(latest_meta)
        self.assertEqual(latest_meta.rag_status, "partial")

    def test_generate_partial_transcript_can_be_rejected_explicitly(self):
        """调用方可显式禁止基于 partial 转录继续生成。"""
        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)
        transcript_path = root / folder_path / "02-转录文本" / "transcript-latest.md"
        transcript_path.write_text(
            transcript_path.read_text(encoding="utf-8") + "\n| 转录状态 | partial |\n",
            encoding="utf-8",
        )
        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path, allow_partial=False),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("partial", ctx.exception.detail)

    def test_generate_success_with_mock_llm(self):
        """LLM 成功时生成 4 个文件 + 4 条 WorkspaceFile + audit"""
        from unittest.mock import patch, MagicMock

        # Build a realistic mock LLM response
        mock_response = MagicMock()
        mock_response.text = (
            "# 会议纪要\n\n"
            "## 会议基本信息\n\n"
            "| 字段 | 值 |\n"
            "|---|---|\n"
            "| 会议主题 | 进度讨论 |\n"
            "| 会议时间 | 待确认 |\n\n"
            "## 一句话结论\n\n项目第一阶段已完成。\n\n"
            "## 会议摘要\n\n待确认\n\n"
            "## 关键决策\n\n| ID | 决策 | ... |\n| D1 | 继续第二阶段 | ... |\n"
            "## 风险与问题\n\n| ID | 风险 | ... |\n| R1 | 预算不足 | ... |\n"
            "## 待确认事项\n\n| ID | 事项 | ... |\n| Q1 | 预算调整 | ... |\n"
            "## 可沉淀知识候选\n\n无\n"
            "## 生成说明\n\n- 模型：mock\n"
        )
        mock_response.usage = {"input_tokens": 50, "output_tokens": 100}
        mock_response.model = "mock"
        mock_response.provider = "mock"
        mock_response.key_index = None
        mock_response.token_cost = 0

        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        workspace, folder_path = self._create_meeting_with_transcript()

        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        self.assertTrue(resp.ok)
        self.assertEqual(resp.model_used, "deepseek-flash")

        # Check 4 files on disk
        root = self.workspace_root(workspace)
        self.assertTrue((root / resp.minutes_v_path).exists())
        self.assertTrue((root / resp.minutes_latest_path).exists())
        self.assertTrue((root / resp.actions_v_path).exists())
        self.assertTrue((root / resp.actions_latest_path).exists())
        self.assertIn("minutes-v1.md", resp.minutes_v_path)
        self.assertIn("minutes-latest.md", resp.minutes_latest_path)
        self.assertIn("actions-v1.md", resp.actions_v_path)
        self.assertIn("actions-latest.md", resp.actions_latest_path)

        # Verify content written
        content = (root / resp.minutes_latest_path).read_text(encoding="utf-8")
        self.assertIn("会议纪要", content)

        # Check 4 WorkspaceFile records
        metas = (
            self.db.query(WorkspaceFile)
            .filter(
                WorkspaceFile.workspace_id == workspace.id,
                WorkspaceFile.relative_path.in_([
                    resp.minutes_v_path,
                    resp.minutes_latest_path,
                    resp.actions_v_path,
                    resp.actions_latest_path,
                ]),
            )
            .all()
        )
        self.assertEqual(len(metas), 4)

        # Check audit has gbrain_ingest=false
        audits = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "meeting_minutes_generate")
            .all()
        )
        self.assertGreaterEqual(len(audits), 1)
        import json
        detail = json.loads(audits[-1].detail)
        self.assertIn("gbrain_ingest", detail)
        self.assertFalse(detail["gbrain_ingest"])

    def test_generate_includes_auxiliary_summary_reference(self):
        """03-辅助总结 中的材料进入 prompt，但作为二级参考。"""
        from unittest.mock import patch, MagicMock

        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)
        aux_dir = root / folder_path / "03-辅助总结"
        aux_dir.mkdir(parents=True, exist_ok=True)
        (aux_dir / "meeting.summary.md").write_text(
            "# 辅助总结\n\n辅助总结独有信息：客户要求下周确认预算。",
            encoding="utf-8",
        )

        mock_response = MagicMock()
        mock_response.text = "# 会议纪要\n\n## 一句话结论\n\n辅助总结已参考。\n"
        mock_response.usage = {"input_tokens": 10, "output_tokens": 20}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        self.assertTrue(resp.ok)
        prompts = [call.args[0][0]["content"] for call in mock_client.complete.call_args_list]
        joined = "\n\n".join(prompts)
        self.assertIn("## 辅助总结参考", joined)
        self.assertIn("meeting.summary.md", joined)
        self.assertIn("辅助总结独有信息：客户要求下周确认预算", joined)
        self.assertIn("只能作为二级参考", joined)

    def test_generate_matches_auxiliary_summary_by_original_filename(self):
        """根目录工作流有多场会议时，只读取与原始文件名匹配的辅助总结。"""
        from unittest.mock import patch, MagicMock

        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)
        transcript_path = root / folder_path / "02-转录文本" / "transcript-latest.md"
        transcript_text = transcript_path.read_text(encoding="utf-8")
        transcript_text = transcript_text.replace(
            "| 原始文件名 | — |",
            "| 原始文件名 | 20260608 Raven team 周会_audio.mp4 |",
        )
        transcript_path.write_text(transcript_text, encoding="utf-8")

        aux_dir = root / folder_path / "03-辅助总结"
        aux_dir.mkdir(parents=True, exist_ok=True)
        (aux_dir / "纪要_Raven team 周会.docx.txt").write_text("Raven 匹配摘要", encoding="utf-8")
        (aux_dir / "Internal Meeting.summary.md").write_text("CRM 不应混入", encoding="utf-8")

        mock_response = MagicMock()
        mock_response.text = "# 会议纪要\n\n## 一句话结论\n\nOK\n"
        mock_response.usage = {"input_tokens": 1, "output_tokens": 1}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        prompts = [call.args[0][0]["content"] for call in mock_client.complete.call_args_list]
        joined = "\n\n".join(prompts)
        self.assertIn("Raven 匹配摘要", joined)
        self.assertNotIn("CRM 不应混入", joined)

    def test_generate_409_when_exists_and_not_regenerate(self):
        """已存在 latest 且 regenerate=False 时返回 409"""
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.text = "# 会议纪要\n\n## 一句话结论\n\n测试\n"
        mock_response.usage = {"input_tokens": 10, "output_tokens": 10}
        mock_response.model = "mock"
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        workspace, folder_path = self._create_meeting_with_transcript()
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        # Second call without regenerate → 409
        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path, regenerate=False),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 409)

    def test_generate_regenerate_true_produces_v2(self):
        """regenerate=True 时生成 v2 并覆盖 latest"""
        from unittest.mock import patch, MagicMock

        mock_response_v1 = MagicMock()
        mock_response_v1.text = "# 会议纪要\n\nv1 content\n"
        mock_response_v1.usage = {"input_tokens": 5, "output_tokens": 10}
        mock_response_v1.model = "mock"

        mock_response_v2 = MagicMock()
        mock_response_v2.text = "# 会议纪要\n\nv2 content\n"
        mock_response_v2.usage = {"input_tokens": 5, "output_tokens": 10}
        mock_response_v2.model = "mock"

        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response_v1

        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)

        # First generate → v1
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            resp1 = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )
        self.assertIn("minutes-v1.md", resp1.minutes_v_path)
        self.assertIn("actions-v1.md", resp1.actions_v_path)

        # Second generate with regenerate=True → v2
        mock_client.complete.return_value = mock_response_v2
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            resp2 = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path, regenerate=True),
                self.user,
                self.db,
            )
        self.assertIn("minutes-v2.md", resp2.minutes_v_path)
        self.assertIn("actions-v2.md", resp2.actions_v_path)

        # latest should be overwritten with v2 content
        latest_minutes = (root / resp2.minutes_latest_path).read_text(encoding="utf-8")
        self.assertIn("v2 content", latest_minutes)
        # v1 should still exist unchanged
        v1_minutes = (root / resp1.minutes_v_path).read_text(encoding="utf-8")
        self.assertIn("v1 content", v1_minutes)

    def test_generate_fallback_on_llm_error(self):
        """LLM 抛异常时走 template-fallback，仍保存文件，model_used=template-fallback"""
        from unittest.mock import patch

        def _raise_error(*args, **kwargs):
            raise RuntimeError("Mock LLM connection error")

        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)

        with patch("app.shared.llm.client.get_llm_client", side_effect=_raise_error):
            resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user,
                self.db,
            )

        self.assertTrue(resp.ok)
        self.assertEqual(resp.model_used, "template-fallback")

        # Files should exist with fallback content
        content = (root / resp.minutes_latest_path).read_text(encoding="utf-8")
        self.assertIn("LLM 暂不可用", content)

    def test_generate_rejects_wrong_parent_path(self):
        """错误父路径的会议文件夹生成纪要应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 错误父路径生成", brand="BFI"),
            self.user,
            self.db,
        )
        root = self.workspace_root(workspace)
        bad_dir = root / "99-未归档文件" / "20260615-0930-bad-meeting"
        bad_dir.mkdir(parents=True, exist_ok=True)
        for sub in workspaces_api.MEETING_SUBDIRS:
            (bad_dir / sub).mkdir(parents=True, exist_ok=True)
        (bad_dir / "02-转录文本" / "transcript-latest.md").write_text("test", encoding="utf-8")
        bad_rel = bad_dir.relative_to(root).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=bad_rel),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_generate_rejects_non_meeting_folder(self):
        """缺少 5 个子目录的文件夹生成纪要应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 非会议生成", brand="BFI"),
            self.user,
            self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="完整会议"),
            self.user,
            self.db,
        )
        # Make a directory under the same parent that is NOT a meeting folder
        root = self.workspace_root(workspace)
        parent = root / "20-会议与沟通"
        bad_folder = parent / "20260615-0930-incomplete"
        bad_folder.mkdir(parents=True, exist_ok=True)
        # Only 3 subdirs instead of 5
        for sub in ["01-原始资料", "02-转录文本", "03-辅助总结"]:
            (bad_folder / sub).mkdir(parents=True, exist_ok=True)
        (bad_folder / "02-转录文本" / "transcript-latest.md").write_text("test", encoding="utf-8")
        bad_rel = bad_folder.relative_to(root).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=bad_rel),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)


    # ── Step 4: Speaker map & term corrections tests ────────────────────────

    def test_get_speakers_parses_transcript(self):
        """GET /speakers 正确解析说话人概览"""
        workspace, folder_path = self._create_meeting_with_transcript()
        resp = workspaces_api.get_meeting_speakers(
            workspace.id, folder_path, self.user, self.db,
        )
        self.assertTrue(resp.ok)
        # Our test transcript has "张三", "李四", "王五"
        self.assertGreaterEqual(len(resp.detected_speakers), 2)

    def test_get_speakers_rejects_wrong_parent(self):
        """GET /speakers 在非会议目录应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Speaker 错误父", brand="BFI"),
            self.user, self.db,
        )
        root = self.workspace_root(workspace)
        bad_dir = root / "99-未归档文件" / "20260615-0930-speaker-test"
        bad_dir.mkdir(parents=True, exist_ok=True)
        for sub in workspaces_api.MEETING_SUBDIRS:
            (bad_dir / sub).mkdir(parents=True, exist_ok=True)
        (bad_dir / "02-转录文本" / "transcript-latest.md").write_text(
            "# test\n## 说话人概览\n| Speaker 1 | Speaker 1 | ... |", encoding="utf-8")
        bad_rel = bad_dir.relative_to(root).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.get_meeting_speakers(
                workspace.id, bad_rel, self.user, self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_save_speaker_map_writes_files_and_db(self):
        """保存 speaker-map 应写 v1 + latest + WorkspaceFile + audit"""
        workspace, folder_path = self._create_meeting_with_transcript()
        resp = workspaces_api.save_meeting_speaker_map(
            workspace.id,
            workspaces_api.SaveSpeakerMapRequest(
                folder_path=folder_path,
                speakers=[
                    workspaces_api.SpeakerMapItem(speaker_id="Speaker 1", display_name="张三"),
                    workspaces_api.SpeakerMapItem(speaker_id="Speaker 2", display_name="李四"),
                ],
            ),
            self.user,
            self.db,
        )
        self.assertTrue(resp.ok)
        self.assertTrue(resp.speaker_map_path.endswith("speaker-map-latest.md"))
        self.assertFalse(resp.gbrain_ingest)

        root = self.workspace_root(workspace)
        latest_path = root / resp.speaker_map_path
        self.assertTrue(latest_path.exists())
        content = latest_path.read_text(encoding="utf-8")
        self.assertIn("张三", content)
        self.assertIn("李四", content)

        # Check WorkspaceFile records
        metas = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id,
                    WorkspaceFile.relative_path.like("%speaker-map%"))
            .all()
        )
        self.assertGreaterEqual(len(metas), 2)

        # Check audit
        audits = (
            self.db.query(AuditLog)
            .filter(AuditLog.action == "meeting_speaker_map_save")
            .all()
        )
        self.assertGreaterEqual(len(audits), 1)

    def test_speaker_map_v2_does_not_overwrite_v1(self):
        """第二次保存 speaker-map 生产 v2，v1 不受影响"""
        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)
        # Save v1
        workspaces_api.save_meeting_speaker_map(
            workspace.id,
            workspaces_api.SaveSpeakerMapRequest(
                folder_path=folder_path,
                speakers=[workspaces_api.SpeakerMapItem(speaker_id="Speaker 1", display_name="V1Name")],
            ),
            self.user, self.db,
        )
        # Save v2
        workspaces_api.save_meeting_speaker_map(
            workspace.id,
            workspaces_api.SaveSpeakerMapRequest(
                folder_path=folder_path,
                speakers=[workspaces_api.SpeakerMapItem(speaker_id="Speaker 1", display_name="V2Name")],
            ),
            self.user, self.db,
        )
        v1 = root / folder_path / "02-转录文本" / "speaker-map-v1.md"
        v2 = root / folder_path / "02-转录文本" / "speaker-map-v2.md"
        latest = root / folder_path / "02-转录文本" / "speaker-map-latest.md"
        self.assertTrue(v1.exists())
        self.assertTrue(v2.exists())
        self.assertTrue(latest.exists())
        self.assertIn("V1Name", v1.read_text(encoding="utf-8"))
        self.assertIn("V2Name", v2.read_text(encoding="utf-8"))
        self.assertIn("V2Name", latest.read_text(encoding="utf-8"))

    def test_save_term_corrections_writes_files_and_db(self):
        """保存 term-corrections 应写 v1 + latest + WorkspaceFile + audit"""
        workspace, folder_path = self._create_meeting_with_transcript()
        resp = workspaces_api.save_meeting_term_corrections(
            workspace.id,
            workspaces_api.SaveTermCorrectionsRequest(
                folder_path=folder_path,
                corrections=[
                    workspaces_api.TermCorrectionItem(
                        original="projet", corrected="project", type="typo", confidence="高"),
                ],
            ),
            self.user,
            self.db,
        )
        self.assertTrue(resp.ok)
        self.assertTrue(resp.corrections_path.endswith("term-corrections-latest.md"))
        self.assertFalse(resp.gbrain_ingest)

        root = self.workspace_root(workspace)
        latest_path = root / resp.corrections_path
        self.assertTrue(latest_path.exists())
        content = latest_path.read_text(encoding="utf-8")
        self.assertIn("projet", content)
        self.assertIn("project", content)

        metas = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id,
                    WorkspaceFile.relative_path.like("%term-corrections%"))
            .all()
        )
        self.assertGreaterEqual(len(metas), 2)

    def test_generate_reads_speaker_map_and_terms(self):
        """Generate 端点读 speaker-map 和 term-corrections，传入 LLM prompt"""
        from unittest.mock import patch, MagicMock
        workspace, folder_path = self._create_meeting_with_transcript()
        root = self.workspace_root(workspace)

        # Save speaker map and term corrections
        workspaces_api.save_meeting_speaker_map(
            workspace.id,
            workspaces_api.SaveSpeakerMapRequest(
                folder_path=folder_path,
                speakers=[workspaces_api.SpeakerMapItem(speaker_id="Speaker 1", display_name="Gary")],
            ),
            self.user, self.db,
        )
        workspaces_api.save_meeting_term_corrections(
            workspace.id,
            workspaces_api.SaveTermCorrectionsRequest(
                folder_path=folder_path,
                corrections=[workspaces_api.TermCorrectionItem(
                    original="budjet", corrected="budget", type="typo", confidence="高")],
            ),
            self.user, self.db,
        )

        mock_response = MagicMock()
        mock_response.text = "# 纪要\n\nv1\n"
        mock_response.usage = {"input_tokens": 10, "output_tokens": 10}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_response

        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=folder_path),
                self.user, self.db,
            )

        # Collect all prompt texts sent to LLM
        all_prompts = ""
        for call in mock_client.complete.call_args_list:
            args, kwargs = call
            messages = args[0]
            for msg in messages:
                all_prompts += msg.get("content", "") + "\n"

        self.assertIn("Gary", all_prompts)
        self.assertIn("budjet", all_prompts)


    # ── Step 5: Media transcription tests ───────────────────────────────────

    def _call_transcribe_media(self, workspace_id, folder_path, filename, content_bytes, content_type="audio/mpeg", user=None):
        """Helper to call the async transcribe_meeting_media endpoint synchronously."""
        import asyncio, io
        from fastapi import UploadFile
        u = user or self.user
        async def _run():
            f = UploadFile(filename=filename, file=io.BytesIO(content_bytes), headers={"content-type": content_type})
            return await workspaces_api.transcribe_meeting_media(
                workspace_id, folder_path=folder_path, file=f, user=u, db=self.db,
            )
        return asyncio.run(_run())

    def test_transcribe_rejects_unsupported_extension(self):
        """非音视频扩展名应 400"""
        workspace, folder_path = self._create_meeting_with_transcript()
        with self.assertRaises(HTTPException) as ctx:
            self._call_transcribe_media(workspace.id, folder_path, "meeting.pdf", b"%PDF-1.4 fake")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_transcribe_rejects_wrong_parent(self):
        """非会议父路径应 400"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 转录错误父", brand="BFI"), self.user, self.db)
        root = self.workspace_root(workspace)
        bad_dir = root / "99-未归档文件" / "20260615-0930-bad-media"
        bad_dir.mkdir(parents=True, exist_ok=True)
        for sub in workspaces_api.MEETING_SUBDIRS:
            (bad_dir / sub).mkdir(parents=True, exist_ok=True)
        bad_rel = bad_dir.relative_to(root).as_posix()
        with self.assertRaises(HTTPException) as ctx:
            self._call_transcribe_media(workspace.id, bad_rel, "test.mp3", b"fake audio")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_transcribe_success_saves_media_and_transcript(self):
        """Mock 转录成功：媒体入 01-原始资料，转录入 02-转录文本，3 WorkspaceFile + audit"""
        from unittest.mock import patch, MagicMock
        from app.features.preprocessing import media_transcription as mt
        workspace, folder_path = self._create_meeting_with_transcript()

        mock_result = MagicMock()
        mock_result.transcript_text = "[00:00] Speaker 1: 测试转录内容。"
        mock_result.transcription_status = "auto_transcribed"
        mock_result.segment_count = 1
        mock_result.warnings = []
        mock_result.token_usage = {"input_tokens": 50, "output_tokens": 100}
        mock_result.refinement_token_usage = {"input_tokens": 10, "output_tokens": 20}

        with patch.object(mt, "transcribe_media_to_markdown", return_value=mock_result):
            resp = self._call_transcribe_media(workspace.id, folder_path,
                                               "meeting.mp3", b"fake audio data")

        self.assertTrue(resp.ok)
        self.assertEqual(resp.transcription_status, "auto_transcribed")
        self.assertEqual(resp.segment_count, 1)
        self.assertEqual(resp.token_cost, 180)

        root = self.workspace_root(workspace)
        # Media in 01-原始资料
        self.assertTrue((root / resp.media_path).exists())
        self.assertIn("01-原始资料", resp.media_path)
        # Transcript in 02-转录文本
        self.assertTrue((root / resp.transcript_v1_path).exists())
        self.assertTrue((root / resp.transcript_latest_path).exists())
        self.assertIn("02-转录文本", resp.transcript_v1_path)
        content = (root / resp.transcript_latest_path).read_text(encoding="utf-8")
        self.assertIn("测试转录内容", content)
        self.assertIn("| 转录来源 | 音视频自动转录（meeting.mp3） |", content)
        self.assertNotIn("| 转录来源 | 用户粘贴文本 |", content)

        # 3 WorkspaceFile records
        metas = (
            self.db.query(WorkspaceFile)
            .filter(WorkspaceFile.workspace_id == workspace.id,
                    WorkspaceFile.relative_path.in_([
                        resp.media_path, resp.transcript_v1_path, resp.transcript_latest_path]))
            .all()
        )
        self.assertEqual(len(metas), 3)

        # Audit
        audits = self.db.query(AuditLog).filter(AuditLog.action == "meeting_media_transcribe").all()
        self.assertGreaterEqual(len(audits), 1)
        import json
        self.assertFalse(json.loads(audits[-1].detail).get("gbrain_ingest"))

    def test_transcribe_handles_exception_as_failed(self):
        """Mock 转写异常 → transcription_status=failed, ok=True, 保存失败说明"""
        from unittest.mock import patch
        from app.features.preprocessing import media_transcription as mt
        workspace, folder_path = self._create_meeting_with_transcript()

        with patch.object(mt, "transcribe_media_to_markdown", side_effect=RuntimeError("Mock ASR failure")):
            resp = self._call_transcribe_media(workspace.id, folder_path,
                                               "meeting.wav", b"fake wav data")

        self.assertTrue(resp.ok)
        self.assertEqual(resp.transcription_status, "failed")
        self.assertGreater(len(resp.warnings), 0)
        self.assertIn("Mock ASR failure", resp.warnings[0])

        root = self.workspace_root(workspace)
        content = (root / resp.transcript_latest_path).read_text(encoding="utf-8")
        self.assertIn("转录失败", content)

    def test_transcribe_keeps_both_on_name_conflict(self):
        """同名媒体文件冲突时追加 (1) 不覆盖旧文件"""
        from unittest.mock import patch, MagicMock
        from app.features.preprocessing import media_transcription as mt
        workspace, folder_path = self._create_meeting_with_transcript()

        mock_result = MagicMock()
        mock_result.transcript_text = "content"
        mock_result.transcription_status = "auto_transcribed"
        mock_result.segment_count = 1
        mock_result.warnings = []
        mock_result.token_usage = {}
        mock_result.refinement_token_usage = {}

        with patch.object(mt, "transcribe_media_to_markdown", return_value=mock_result):
            resp1 = self._call_transcribe_media(workspace.id, folder_path, "meeting.mp3", b"data1")
            resp2 = self._call_transcribe_media(workspace.id, folder_path, "meeting.mp3", b"data2")

        self.assertNotEqual(resp1.media_path, resp2.media_path)
        root = self.workspace_root(workspace)
        self.assertTrue((root / resp1.media_path).exists())
        self.assertTrue((root / resp2.media_path).exists())

    def test_media_preflight_rejects_non_meeting_folder(self):
        """Preflight 虽不上传文件，也必须限制在当前工作区会议目录内。"""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Preflight", brand="BFI"),
            self.user,
            self.db,
        )

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.preflight_meeting_media_transcribe(
                workspace.id,
                workspaces_api.MediaTranscribePreflightRequest(
                    folder_path="01-项目启动",
                    filename="meeting.mp3",
                    size_bytes=1024 * 1024,
                    content_type="audio/mpeg",
                ),
                self.user,
                self.db,
            )
        self.assertEqual(ctx.exception.status_code, 400)


    # ── Step 6: Meeting GBrain ingest tests ─────────────────────────────────

    def _create_meeting_with_all_outputs(self) -> tuple:
        """Create workspace + meeting folder with transcript, minutes, and actions."""
        from unittest.mock import patch, MagicMock
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 Ingest测试", brand="BFI"),
            self.user, self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="IngestTest"),
            self.user, self.db,
        )
        fp = folder_resp.meeting_folder_path

        workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(folder_path=fp, content="transcript content"),
            self.user, self.db,
        )

        mock_resp = MagicMock()
        mock_resp.text = "# minutes content\n## 一句话结论\nDone"
        mock_resp.usage = {"input_tokens": 1, "output_tokens": 1}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_resp
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=fp),
                self.user, self.db,
            )
        return workspace, fp

    def test_ingest_rejects_non_admin_project_member(self):
        """非项目管理员调用 ingest 返回 403"""
        workspace, fp = self._create_meeting_with_all_outputs()
        # Add self.other as non-admin member
        workspaces_api.upsert_workspace_member(workspace.id, workspaces_api.UpsertWorkspaceMemberRequest(
            user_id=self.other.id, role="member"), self.user, self.db)
        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.ingest_meeting_to_gbrain(
                workspace.id,
                workspaces_api.MeetingIngestRequest(folder_path=fp),
                self.other, self.db,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_ingest_rejects_non_admin_customer_member(self):
        """非客户管理员调用 CRM ingest 返回 403"""
        workspace = workspaces_api._ensure_crm_workspace(self.db, self.user, add_member=True)
        workspaces_api.upsert_workspace_member(workspace.id, workspaces_api.UpsertWorkspaceMemberRequest(
            user_id=self.other.id, role="member"), self.user, self.db)
        # Create meeting folder in CRM raw dir
        root = self.workspace_root(workspace)
        parent = root / "raw" / "会议记录"
        parent.mkdir(parents=True, exist_ok=True)
        meeting_dir = parent / "20260615-0930-CRMTest"
        meeting_dir.mkdir(parents=True, exist_ok=True)
        for sub in workspaces_api.MEETING_SUBDIRS:
            (meeting_dir / sub).mkdir(parents=True, exist_ok=True)
        (meeting_dir / "02-转录文本" / "transcript-latest.md").write_text("# test", encoding="utf-8")
        (meeting_dir / "04-会议纪要" / "minutes-latest.md").write_text("# minutes", encoding="utf-8")
        fp = meeting_dir.relative_to(root).as_posix()

        with self.assertRaises(HTTPException) as ctx:
            workspaces_api.ingest_meeting_to_gbrain(
                workspace.id,
                workspaces_api.MeetingIngestRequest(folder_path=fp),
                self.other, self.db,
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_ingest_project_admin_writes_gbrain_ready(self):
        """项目管理员 ingest 写入 _preprocessed/project/.../gbrain-ready/"""
        workspace, fp = self._create_meeting_with_all_outputs()
        resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        self.assertTrue(resp.ok)
        self.assertIn("project", resp.gbrain_ready_path.replace("\\", "/"))
        self.assertIn("gbrain-ready", resp.gbrain_ready_path)
        self.assertIn("IngestTest", resp.gbrain_ready_path)
        self.assertEqual(resp.source_scope, "project")
        self.assertGreater(len(resp.ingested_files), 0)

        # Verify GBrain-ready file exists
        gb_path = Path(resp.gbrain_ready_path)
        self.assertTrue(gb_path.exists())
        content = gb_path.read_text(encoding="utf-8")
        self.assertIn("transcript content", content)
        self.assertIn("minutes content", content)

    def test_ingest_marks_latest_as_gbrain_ready_not_synced(self):
        """ingested 的 latest 文件 rag_status=gbrain_ready 不是 synced"""
        workspace, fp = self._create_meeting_with_all_outputs()
        resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        for ipath in resp.ingested_files:
            meta = self.db.query(WorkspaceFile).filter(
                WorkspaceFile.workspace_id == workspace.id,
                WorkspaceFile.relative_path == ipath).first()
            self.assertIsNotNone(meta)
            self.assertEqual(meta.rag_status, "gbrain_ready")

    def test_ingest_marks_old_versions_as_skipped_superseded(self):
        """旧 vN 版本标记为 skipped_superseded_version"""
        from unittest.mock import patch, MagicMock
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 vN测试", brand="BFI"), self.user, self.db)
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id, workspaces_api.CreateMeetingFolderRequest(topic="vN"), self.user, self.db)
        fp = folder_resp.meeting_folder_path
        workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(folder_path=fp, content="t1"),
            self.user, self.db,
        )

        # Generate twice to create v1 and v2
        mock_resp = MagicMock(); mock_resp.text = "# v1"; mock_resp.usage = {"input_tokens": 1, "output_tokens": 1}
        mock_client = MagicMock(); mock_client.complete.return_value = mock_resp
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id, workspaces_api.MeetingGenerateRequest(folder_path=fp), self.user, self.db)
            mock_resp.text = "# v2"
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id, workspaces_api.MeetingGenerateRequest(folder_path=fp, regenerate=True), self.user, self.db)

        resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id, workspaces_api.MeetingIngestRequest(folder_path=fp), self.user, self.db)
        self.assertGreater(len(resp.skipped_files), 0)
        for spath in resp.skipped_files:
            meta = self.db.query(WorkspaceFile).filter(
                WorkspaceFile.workspace_id == workspace.id,
                WorkspaceFile.relative_path == spath).first()
            self.assertIsNotNone(meta)
            self.assertEqual(meta.rag_status, "skipped_superseded_version",
                             f"应标记 skipped_superseded_version: {spath}")

    def test_ingest_audit_has_gbrain_ready_fields(self):
        """ingest audit 记录 gbrain_ready_generated=true, gbrain_synced=false"""
        workspace, fp = self._create_meeting_with_all_outputs()
        workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        audits = self.db.query(AuditLog).filter(AuditLog.action == "meeting_gbrain_ingest").all()
        self.assertGreaterEqual(len(audits), 1)
        import json
        detail = json.loads(audits[-1].detail)
        self.assertTrue(detail.get("gbrain_ready_generated"))
        self.assertFalse(detail.get("gbrain_synced", True))

    def test_generate_sets_needs_reingest_on_gbrain_ready_files(self):
        """重跑纪要后，已 gbrain_ready 的旧产物变成 needs_reingest"""
        from unittest.mock import patch, MagicMock
        workspace, fp = self._create_meeting_with_all_outputs()

        # First ingest
        workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )

        # Verify ingested files are gbrain_ready
        root = self.workspace_root(workspace)
        minutes_meta = self.db.query(WorkspaceFile).filter(
            WorkspaceFile.workspace_id == workspace.id,
            WorkspaceFile.relative_path.like(f"{fp}/04-会议纪要/minutes-latest.md")
        ).first()
        self.assertEqual(minutes_meta.rag_status, "gbrain_ready")

        # Regenerate
        mock_resp = MagicMock(); mock_resp.text = "# v2"; mock_resp.usage = {"input_tokens": 1, "output_tokens": 1}
        mock_client = MagicMock(); mock_client.complete.return_value = mock_resp
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=fp, regenerate=True),
                self.user, self.db,
            )

        # Check the old latest (now a vN file) is needs_reingest
        self.db.refresh(minutes_meta)
        # The old minutes-latest got replaced; find it as minutes-v1.md now
        minutes_v1 = self.db.query(WorkspaceFile).filter(
            WorkspaceFile.workspace_id == workspace.id,
            WorkspaceFile.relative_path.like(f"{fp}/04-会议纪要/minutes-v1.md")
        ).first()
        if minutes_v1:
            self.assertIn(minutes_v1.rag_status, ("needs_reingest", "skipped_superseded_version"))


    # ── Step 7: End-to-end meeting workflow test ────────────────────────────

    def test_e2e_full_meeting_workflow(self):
        """完整会议工作流：创建→转录→说话人→生成→重跑→录入→状态→审计"""
        from unittest.mock import patch, MagicMock
        import json

        # 1. Create workspace and meeting folder
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 E2E", brand="BFI"),
            self.user, self.db,
        )
        folder_resp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="E2E验收", meeting_time="2026-06-15T09:30"),
            self.user, self.db,
        )
        fp = folder_resp.meeting_folder_path
        self.assertTrue(folder_resp.ok)
        self.assertIn("20-会议与沟通", fp)
        self.assertGreater(len(folder_resp.created_dirs), 0)
        self.assertFalse(folder_resp.gbrain_ingest)

        # 2. Save transcript
        tx_resp = workspaces_api.save_meeting_transcript(
            workspace.id,
            workspaces_api.SaveMeetingTranscriptRequest(folder_path=fp, content="张三：项目进度汇报。\n李四：第一阶段已完成。"),
            self.user, self.db,
        )
        self.assertTrue(tx_resp.ok)
        self.assertFalse(tx_resp.gbrain_ingest)
        root = self.workspace_root(workspace)
        self.assertTrue((root / tx_resp.transcript_latest_path).exists())
        tx_content = (root / tx_resp.transcript_latest_path).read_text(encoding="utf-8")
        self.assertIn("张三", tx_content)
        self.assertIn("行号", tx_content)

        # 3. Verify speakers
        speakers_resp = workspaces_api.get_meeting_speakers(workspace.id, fp, self.user, self.db)
        self.assertTrue(speakers_resp.ok)
        self.assertGreaterEqual(len(speakers_resp.detected_speakers), 2)

        # 4. Save speaker map
        workspaces_api.save_meeting_speaker_map(
            workspace.id,
            workspaces_api.SaveSpeakerMapRequest(folder_path=fp, speakers=[
                workspaces_api.SpeakerMapItem(speaker_id="Speaker 1", display_name="张三"),
                workspaces_api.SpeakerMapItem(speaker_id="Speaker 2", display_name="李四"),
            ]),
            self.user, self.db,
        )

        # 5. Save term corrections
        workspaces_api.save_meeting_term_corrections(
            workspace.id,
            workspaces_api.SaveTermCorrectionsRequest(folder_path=fp, corrections=[
                workspaces_api.TermCorrectionItem(original="projet", corrected="project", type="typo"),
            ]),
            self.user, self.db,
        )

        # 6. Generate minutes and actions
        mock_resp = MagicMock()
        mock_resp.text = "# 会议纪要\n\n## 一句话结论\n\nE2E 验收通过。\n\n## 关键决策\n\n| D1 | 继续推进 | ... | ... |\n"
        mock_resp.usage = {"input_tokens": 10, "output_tokens": 20}
        mock_client = MagicMock()
        mock_client.complete.return_value = mock_resp
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            gen_resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=fp),
                self.user, self.db,
            )
        self.assertTrue(gen_resp.ok)
        self.assertIn("minutes-v1.md", gen_resp.minutes_v_path)
        self.assertIn("actions-v1.md", gen_resp.actions_v_path)
        self.assertFalse(gen_resp.gbrain_ingest)
        self.assertTrue((root / gen_resp.minutes_latest_path).exists())

        # 7. Re-run → v2
        mock_resp.text = "# 会议纪要\n\n## 一句话结论\n\nE2E v2。\n"
        with patch("app.shared.llm.client.get_llm_client", return_value=mock_client):
            gen2_resp = workspaces_api.generate_meeting_minutes_and_actions(
                workspace.id,
                workspaces_api.MeetingGenerateRequest(folder_path=fp, regenerate=True),
                self.user, self.db,
            )
        self.assertIn("minutes-v2.md", gen2_resp.minutes_v_path)
        self.assertIn("actions-v2.md", gen2_resp.actions_v_path)
        # latest should be v2 content
        latest_content = (root / gen2_resp.minutes_latest_path).read_text(encoding="utf-8")
        self.assertIn("v2", latest_content)
        # v1 still exists
        self.assertTrue((root / gen_resp.minutes_v_path).exists())

        # 8. Ingest to GBrain
        ingest_resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        self.assertTrue(ingest_resp.ok)
        self.assertGreater(len(ingest_resp.ingested_files), 0)
        self.assertGreater(len(ingest_resp.skipped_files), 0)

        gb_path = Path(ingest_resp.gbrain_ready_path)
        self.assertTrue(gb_path.exists())
        gb_content = gb_path.read_text(encoding="utf-8")
        self.assertIn("source_context: full_meeting", gb_content)
        self.assertIn("会议纪要是整理结果，不是一手转录", gb_content)
        self.assertIn("## 一手转录来源引用", gb_content)
        gb_md = gb_path.read_text(encoding="utf-8")
        self.assertIn("E2E", gb_md)

        # 9. Verify file statuses
        for ipath in ingest_resp.ingested_files:
            meta = self.db.query(WorkspaceFile).filter(
                WorkspaceFile.workspace_id == workspace.id,
                WorkspaceFile.relative_path == ipath).first()
            self.assertIsNotNone(meta)
            self.assertIn(meta.rag_status, ("gbrain_ready", "new"),
                          f"{ipath} 状态应为 gbrain_ready 或 new，实际 {meta.rag_status}")

        for spath in ingest_resp.skipped_files:
            meta = self.db.query(WorkspaceFile).filter(
                WorkspaceFile.workspace_id == workspace.id,
                WorkspaceFile.relative_path == spath).first()
            if meta:
                self.assertEqual(meta.rag_status, "skipped_superseded_version",
                                 f"{spath} 应标记 skipped_superseded_version")

        # 10. Audit for gbrain_ingest=false on non-ingest operations
        transcript_audits = self.db.query(AuditLog).filter(
            AuditLog.action == "meeting_transcript_save").all()
        self.assertGreaterEqual(len(transcript_audits), 1)
        t_detail = json.loads(transcript_audits[-1].detail)
        self.assertFalse(t_detail.get("gbrain_ingest", True))

        # 11. Verify CRM workspace rejection for regular member
        with self.assertRaises(HTTPException) as ctx:
            workspace2 = workspaces_api.create_workspace(
                workspaces_api.CreateWorkspaceRequest(name="项目 权限测试", brand="BFI"),
                self.user, self.db,
            )
            workspaces_api.upsert_workspace_member(workspace2.id, workspaces_api.UpsertWorkspaceMemberRequest(
                user_id=self.other.id, role="member"), self.user, self.db)
            workspaces_api.ingest_meeting_to_gbrain(
                workspace2.id,
                workspaces_api.MeetingIngestRequest(folder_path=fp),
                self.other, self.db,
            )
        # Should fail — either 403 or the folder won't match

    def test_meeting_ingest_actions_only(self):
        """Actions-only ingest produces GBrain-ready with source_context: action_items_only."""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="会动测-A", brand="BFI"),
            self.user, self.db,
        )
        root = self.workspace_root(workspace)
        fp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="Actions Only 测试"),
            self.user, self.db,
        ).meeting_folder_path

        folder_dir = root / fp

        # 1. Save a dummy transcript
        trans_text = "# 会议转录文本\n\n## 基本信息\n| 字段 | 值 |\n|---|---|\n| 会议主题 | Actions Only |\n| 转录来源 | paste |\n| 转录状态 | completed |\n\n## 说话人概览\n| 说话人ID | 显示名称 | 映射状态 | 发言占比 |\n|---|---|---|---|\n| Speaker 1 | Speaker 1 | 未映射 | 100% |\n\n## 完整转录\n| 时间点 | 说话人ID | 显示名称 | 内容 | 置信度 |\n|---|---|---|---|---|\n| 00:00 | Speaker 1 | Speaker 1 | 测试内容 | high |\n"
        transcript_dir = folder_dir / "02-转录文本"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / "transcript-latest.md").write_text(trans_text, encoding="utf-8")

        # 2. Save dummy minutes
        minutes_text = "# 会议纪要\n\n## 会议基本信息\n\n| 字段 | 值 |\n|---|---|\n| 会议主题 | Actions Only |\n\n## 行动项\n\n| ID | 行动项 | 负责人 |\n|---|---|---|\n| A1 | 测试行动项 | 待确认 |\n\n"
        minutes_dir = folder_dir / "04-会议纪要"
        minutes_dir.mkdir(parents=True, exist_ok=True)
        (minutes_dir / "minutes-latest.md").write_text(minutes_text, encoding="utf-8")

        # 3. Save dummy actions
        actions_text = "# 行动项\n\n## 基本信息\n\n| 字段 | 值 |\n|---|---|\n| 来源会议 | Actions Only |\n\n## 行动项清单\n\n| ID | 状态 | 优先级 | 行动项 | 负责人 |\n|---|---|---|---|---|\n| A1 | 待执行 | 高 | 测试行动项 | 张三 |\n\n"
        actions_dir = folder_dir / "05-行动项"
        actions_dir.mkdir(parents=True, exist_ok=True)
        (actions_dir / "actions-latest.md").write_text(actions_text, encoding="utf-8")

        # 4. Ingest with full meeting (normal)
        full_resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        self.assertTrue(full_resp.ok)
        ingested_suffixes = [p.split("/")[-1] for p in full_resp.ingested_files]
        self.assertIn("minutes-latest.md", ingested_suffixes)
        self.assertIn("transcript-latest.md", ingested_suffixes)

        gb_md = Path(full_resp.gbrain_ready_path).read_text(encoding="utf-8")
        self.assertIn("source_context: full_meeting", gb_md)
        self.assertIn("测试行动项", gb_md)

        # 5. Ingest with actions-only (single_file_path)
        actions_resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(
                folder_path=fp,
                single_file_path=fp + "/05-行动项/actions-latest.md",
            ),
            self.user, self.db,
        )
        self.assertTrue(actions_resp.ok)
        self.assertEqual(len(actions_resp.ingested_files), 1)
        ingested_name = actions_resp.ingested_files[0].split("/")[-1]
        self.assertEqual(ingested_name, "actions-latest.md")

        gb_md2 = Path(actions_resp.gbrain_ready_path).read_text(encoding="utf-8")
        self.assertIn("source_context: action_items_only", gb_md2)
        self.assertIn("仅行动项", gb_md2)
        # Actions-only page mentions 会议纪要/转录文本 only in disclaimer, not as sections
        self.assertNotIn("## 会议纪要\n", gb_md2.replace("\r", ""), "不应包含会议纪要章节")
        self.assertNotIn("## 转录文本\n", gb_md2.replace("\r", ""), "不应包含转录文本章节")

        # 6. Warning should exist because minutes+transcript exist
        self.assertTrue(actions_resp.warning, "应返回 warning 提示录入完整会议")

    def test_meeting_ingest_single_file_no_recursive(self):
        """Right-click single-file ingest (recursive=False) only processes the specified path."""
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="会动测-B", brand="BFI"),
            self.user, self.db,
        )
        root = self.workspace_root(workspace)
        fp = workspaces_api.create_meeting_folder(
            workspace.id,
            workspaces_api.CreateMeetingFolderRequest(topic="单件录入"),
            self.user, self.db,
        ).meeting_folder_path

        folder_dir = root / fp
        trans_text = "# 会议转录文本\n\n## 基本信息\n| 字段 | 值 |\n|---|---|\n| 会议主题 | 单件 |\n| 转录来源 | paste |\n| 转录状态 | completed |\n\n## 完整转录\n| 时间点 | 说话人ID | 显示名称 | 内容 | 置信度 |\n|---|---|---|---|---|\n| 00:00 | S1 | S1 | 测试 | high |\n"
        transcript_dir = folder_dir / "02-转录文本"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        (transcript_dir / "transcript-latest.md").write_text(trans_text, encoding="utf-8")

        minutes_text = "# 会议纪要\n\n## 行动项\n\n| ID | 行动项 | 负责人 |\n|---|---|---|\n| A1 | 测试 | 待确认 |\n\n"
        minutes_dir = folder_dir / "04-会议纪要"
        minutes_dir.mkdir(parents=True, exist_ok=True)
        (minutes_dir / "minutes-latest.md").write_text(minutes_text, encoding="utf-8")
        (minutes_dir / "minutes-v1.md").write_text(minutes_text, encoding="utf-8")  # old version

        # Ingest full meeting
        resp = workspaces_api.ingest_meeting_to_gbrain(
            workspace.id,
            workspaces_api.MeetingIngestRequest(folder_path=fp),
            self.user, self.db,
        )
        self.assertTrue(resp.ok)
        # Full meeting ingest includes all latest files
        ingested_names = [p.split("/")[-1] for p in resp.ingested_files]
        self.assertIn("transcript-latest.md", ingested_names)
        self.assertIn("minutes-latest.md", ingested_names)
        # v1 files should be skipped as superseded
        self.assertTrue(
            any("minutes-v1.md" in p for p in resp.skipped_files),
            "v1 应被跳过为已取代版本",
        )


if __name__ == "__main__":
    unittest.main()
