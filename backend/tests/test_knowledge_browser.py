import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

from api.auth import create_jwt
import api.rag as rag_api
from fastapi.testclient import TestClient
from main import app
from models import Base, SessionLocal, engine
from models.user import User
from models.workspace import Workspace, WorkspaceMember


class KnowledgeBrowserTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user = User(username="employee", password_hash="hash", role="employee", nickname="Employee")
        self.admin = User(username="admin", password_hash="hash", role="admin", nickname="Admin")
        self.db.add_all([self.user, self.admin])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.admin)
        self.project = Workspace(
            name="项目-会议类型保存",
            slug="BG007",
            description="",
            created_by=self.admin.id,
            storage_path=str(Path(tempfile.gettempdir()) / "project-r-test-project"),
            brand="BFI",
            workspace_kind="project",
            is_hidden=False,
        )
        self.customer = Workspace(
            name="CRM",
            slug="CRM",
            description="",
            created_by=self.admin.id,
            storage_path=str(Path(tempfile.gettempdir()) / "project-r-test-crm"),
            brand="CRM",
            workspace_kind="customer",
            is_hidden=False,
        )
        self.db.add_all([self.project, self.customer])
        self.db.commit()
        self.db.refresh(self.project)
        self.db.refresh(self.customer)
        self.db.add(WorkspaceMember(workspace_id=self.customer.id, user_id=self.user.id, role="member"))
        self.db.commit()
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {create_jwt(self.user)}"}
        self.original_search = rag_api.search_knowledge_for_workspace

    def tearDown(self):
        rag_api.search_knowledge_for_workspace = self.original_search
        self.db.close()

    def test_project_sources_list_company_and_project_scope(self):
        response = self.client.get(f"/knowledge/sources?workspace_id={self.project.id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_kind"], "project")
        scopes = {item["scope"]: item["source_id"] for item in data["scopes"]}
        self.assertEqual(scopes["company"], "company-wiki")
        self.assertEqual(scopes["project"], "project-bfi-1")

    def test_customer_sources_do_not_include_company_scope(self):
        response = self.client.get(f"/knowledge/sources?workspace_id={self.customer.id}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["workspace_kind"], "customer")
        self.assertEqual([item["scope"] for item in data["scopes"]], ["customer"])

    def test_employee_search_uses_feature_service_and_serializes_results(self):
        calls = []

        def fake_search(db, query, *, workspace, source_scope="all", limit=10, knowledge_sources=None):
            calls.append({"query": query, "workspace_kind": workspace.workspace_kind if workspace else None, "source_scope": source_scope, "limit": limit})
            return [
                {
                    "scope": "project",
                    "file": "gbrain:project-bfi-1/meetings/kickoff",
                    "source_title": "Kickoff",
                    "section_path": "meetings/kickoff",
                    "type": "gbrain_project_source",
                    "content": "项目启动会决定。",
                    "score": 0.91,
                    "tags": "project,BFI,BG007",
                }
            ]

        rag_api.search_knowledge_for_workspace = fake_search

        response = self.client.get(
            f"/knowledge/search?workspace_id={self.project.id}&q=启动会&source_scope=project&limit=5",
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(calls, [{"query": "启动会", "workspace_kind": "project", "source_scope": "project", "limit": 5}])
        self.assertEqual(data["workspace_kind"], "project")
        self.assertEqual(data["results"][0]["scope"], "project")
        self.assertEqual(data["results"][0]["source_id"], "project-bfi-1")
        self.assertEqual(data["results"][0]["excerpt"], "项目启动会决定。")


if __name__ == "__main__":
    unittest.main()
