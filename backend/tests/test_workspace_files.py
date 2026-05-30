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
from models.workspace import WorkspaceFile, WorkspaceMember
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
        self.db.add_all([self.user, self.other])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.other)

    def tearDown(self):
        workspaces_api.WORKSPACES_ROOT = self.original_root
        self.temp_root.cleanup()
        self.db.close()

    def workspace_root(self, workspace):
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
        root = self.workspace_root(workspace)
        self.assertEqual((root / response.path).read_text(encoding="utf-8"), "hello")
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == response.file_id).first()
        self.assertEqual(meta.rag_status, "pending")
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
        self.assertTrue((root / uploaded.path).exists())
        self.db.refresh(meta)
        self.assertIsNone(meta.deleted_at)
        self.assertEqual(meta.rag_status, "pending")

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
        meta = self.db.query(WorkspaceFile).filter(WorkspaceFile.id == uploaded.file_id).first()
        self.assertEqual(meta.rag_status, "indexed")


if __name__ == "__main__":
    unittest.main()
