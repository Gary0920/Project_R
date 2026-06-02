import os
import tempfile
import unittest
import base64
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.workspaces as workspaces_api
from fastapi import HTTPException
from models import Base, SessionLocal, engine
from models.audit_log import AuditLog
from models.generated_file import GeneratedFile
from models.knowledge_review import KnowledgeReview
from models.user import User
from models.workspace import WorkspaceFile, WorkspaceGroupAccess, WorkspaceMember
from models.workspace_ingest_job import WorkspaceIngestJob


class WorkspaceFileTreeTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp_root = tempfile.TemporaryDirectory()
        self.original_root = workspaces_api.WORKSPACES_ROOT
        workspaces_api.WORKSPACES_ROOT = Path(self.temp_root.name)
        self.user = User(username="workspace", password_hash="hash", role="admin", nickname="Workspace")
        self.other = User(username="other", password_hash="hash", role="employee", nickname="Other")
        self.member_user = User(username="member", password_hash="hash", role="employee", nickname="Member")
        self.system_admin = User(username="system-admin", password_hash="hash", role="admin", nickname="System Admin")
        self.db.add_all([self.user, self.other, self.member_user, self.system_admin])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other)
        self.db.refresh(self.member_user)
        self.db.refresh(self.system_admin)

    def tearDown(self):
        workspaces_api.WORKSPACES_ROOT = self.original_root
        self.temp_root.cleanup()
        self.db.close()

    def workspace_root(self, workspace):
        if workspace.workspace_kind == "user":
            return Path(workspace.storage_path)
        if workspace.workspace_kind == "customer":
            return Path(self.temp_root.name) / "customer" / workspace.slug
        return Path(self.temp_root.name) / "project" / "BFI" / workspace.slug

    def test_create_workspace_creates_default_project_directories(self):
        workspace = workspaces_api.create_workspace(
            workspaces_api.CreateWorkspaceRequest(name="项目 A"),
            self.user,
            self.db,
        )

        root = self.workspace_root(workspace)
        self.assertTrue(root.exists())
        for dirname in workspaces_api.DEFAULT_WORKSPACE_DIRS:
            self.assertTrue((root / dirname).is_dir())
        self.assertTrue((root / ".trash").is_dir())

    def test_create_customer_workspace_is_hidden_and_scaffolded(self):
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
        self.assertTrue(workspace.is_hidden)
        self.assertTrue(root.exists())
        for dirname in workspaces_api.DEFAULT_CUSTOMER_WORKSPACE_DIRS:
            self.assertTrue((root / dirname).is_dir())

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
        self.assertNotIn(customer.id, [item["id"] for item in workspaces_api.search_workspaces("客户", self.other, self.db)])

        workspaces_api.upsert_workspace_member(
            customer.id,
            workspaces_api.UpsertWorkspaceMemberRequest(user_id=self.other.id, role="member"),
            self.user,
            self.db,
        )

        self.assertEqual(workspaces_api.get_workspace(customer.id, self.other, self.db).id, customer.id)
        self.assertIn(customer.id, [item["id"] for item in workspaces_api.search_workspaces("客户", self.other, self.db)])

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

        results = workspaces_api.search_workspaces("Group", self.other, self.db, brand="CUSTOMER")

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

    def test_default_user_workspace_uses_personal_workbench_scaffold(self):
        workspace = workspaces_api.ensure_default_workspace(self.db, self.user)

        self.assertEqual(workspace.name, f"{self.user.username}的工作台")
        root = self.workspace_root(workspace)
        self.assertTrue((root / "常用文件").is_dir())
        self.assertTrue((root / "常用文件" / "模板").is_dir())
        self.assertTrue((root / "常用文件" / "参考资料").is_dir())
        self.assertTrue((root / "常用文件" / "图片素材").is_dir())
        self.assertTrue((root / "常用文件" / "其他").is_dir())
        self.assertTrue((root / "对话文件").is_dir())

    def test_user_workspace_default_folders_can_be_renamed_or_deleted_without_recreation(self):
        workspace = workspaces_api.ensure_default_workspace(self.db, self.user)
        root = self.workspace_root(workspace)

        renamed = workspaces_api.rename_workspace_path(
            workspace.id,
            workspaces_api.RenameWorkspacePathRequest(path="常用文件", new_name="我的资料"),
            self.user,
            self.db,
        )
        deleted = workspaces_api.delete_workspace_folder(workspace.id, "对话文件", self.user, self.db)
        reloaded = workspaces_api.ensure_default_workspace(self.db, self.user)

        self.assertEqual(renamed.path, "我的资料")
        self.assertEqual(deleted.path, "对话文件")
        self.assertEqual(reloaded.id, workspace.id)
        self.assertTrue((root / "我的资料").is_dir())
        self.assertFalse((root / "常用文件").exists())
        self.assertFalse((root / "对话文件").exists())

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

        member = next(item for item in member_candidates if item.username == "member")
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
        self.assertEqual(meta.rag_status, "pending")
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
        self.assertEqual(copied_meta.rag_status, "pending")

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
        self.assertEqual(copied_meta.rag_status, "pending")

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
        self.assertEqual(meta.rag_status, "pending")

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

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspaces_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 1)
        self.assertEqual(response.compiled_files, 1)
        self.assertEqual(response.gbrain_source_id, f"project-bfi-{workspace.id}")
        self.assertEqual(response.gbrain_sync_status, "ok")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "indexed")
        self.assertTrue((self.workspace_root(workspace) / "derived" / "contracts" / "index.md").exists())

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
                directory="04-原始资料",
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

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspaces_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 1)
        self.assertEqual(response.compiled_files, 1)
        self.assertEqual(response.gbrain_source_id, f"customer-lucerna-{workspace.id}")
        self.assertEqual(response.gbrain_sync_status, "ok")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "indexed")
        self.assertTrue((self.workspace_root(workspace) / "derived" / "raw-events").exists())

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
                directory="04-原始资料",
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

        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspaces_api.GBrainAdapter = original_adapter

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
            "project_r_source_file: 04-原始资料/discovery-call.md\n"
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
        self.assertEqual(result.source_id, f"customer-lucerna-graph-{workspace.id}")
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
        self.assertEqual(preview["source_id"], f"customer-lucerna-alias-{workspace.id}")
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
        self.assertEqual(relink["sync"]["source_id"], f"customer-lucerna-alias-{workspace.id}")
        bob_text = (derived / "contacts" / "Bob Buyer.md").read_text(encoding="utf-8")
        self.assertIn("- companies/Acme Ltd.md", bob_text)
        self.assertNotIn("- companies/Acme Ltd duplicate.md", bob_text)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "alias_recorded")
        self.assertEqual(result["sync"]["source_id"], f"customer-lucerna-alias-{workspace.id}")
        created = derived / result["created_file"]
        self.assertTrue(created.exists())
        text = created.read_text(encoding="utf-8")
        self.assertIn("content_kind: entity_alias_override", text)
        self.assertIn("project_r_created_by: workspace", text)

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
        self.assertEqual(result["source_id"], f"customer-lucerna-native-{workspace.id}")
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

        original_compile = workspaces_api.compile_project_workspace_sources
        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.compile_project_workspace_sources = fake_compile
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            response = workspaces_api.refresh_workspace_knowledge(workspace.id, self.user, self.db)
        finally:
            workspaces_api.compile_project_workspace_sources = original_compile
            workspaces_api.GBrainAdapter = original_adapter

        self.assertTrue(response.ok)
        self.assertEqual(response.indexed_files, 0)
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

        original_compile = workspaces_api.compile_project_workspace_sources
        original_adapter = workspaces_api.GBrainAdapter
        workspaces_api.compile_project_workspace_sources = fake_compile
        workspaces_api.GBrainAdapter = _FakeGBrainAdapter
        try:
            workspaces_api._run_workspace_knowledge_ingest_job(job.id)
        finally:
            workspaces_api.compile_project_workspace_sources = original_compile
            workspaces_api.GBrainAdapter = original_adapter

        self.db.expire_all()
        refreshed_job = self.db.query(WorkspaceIngestJob).filter(WorkspaceIngestJob.id == job.id).one()
        self.assertEqual(refreshed_job.status, "succeeded")
        self.assertIn('"indexed_files": 1', refreshed_job.result_json)
        serialized = workspaces_api._serialize_ingest_job(self.db, refreshed_job)
        self.assertIsNotNone(serialized.agent_run)
        self.assertEqual(serialized.agent_run.status, "completed")
        self.assertTrue(any(event.event_type == "result" for event in serialized.agent_run.events))
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "indexed")


if __name__ == "__main__":
    unittest.main()
