import hashlib
import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.updates as updates_api
from api.auth import create_jwt
from fastapi.testclient import TestClient
from main import app
from models import Base, SessionLocal, engine
from models.client_update import ClientUpdateRelease
from models.user import User


class ClientUpdatesPhase20Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.package_root = tempfile.TemporaryDirectory()
        self.original_package_root = updates_api.UPDATE_PACKAGES_ROOT
        updates_api.UPDATE_PACKAGES_ROOT = Path(self.package_root.name)
        self.admin = User(username="admin", password_hash="hash", role="admin", nickname="Admin")
        self.employee = User(username="employee", password_hash="hash", role="employee", nickname="Employee")
        self.db.add_all([self.admin, self.employee])
        self.db.commit()
        self.db.refresh(self.admin)
        self.db.refresh(self.employee)
        self.client = TestClient(app)
        self.admin_headers = {"Authorization": f"Bearer {create_jwt(self.admin)}"}
        self.employee_headers = {"Authorization": f"Bearer {create_jwt(self.employee)}"}

    def tearDown(self):
        updates_api.UPDATE_PACKAGES_ROOT = self.original_package_root
        self.package_root.cleanup()
        self.db.close()

    def test_admin_upload_latest_and_authenticated_download(self):
        payload = b"fake-project-r-installer"
        response = self.client.post(
            "/updates/admin/releases",
            data={
                "version": "0.2.0",
                "release_notes": "新增通知中心\n修复文件下载",
                "minimum_supported_version": "0.1.0",
                "platform": "win32",
                "is_force_update": "false",
                "is_active": "true",
            },
            files={"file": ("Project_R-0.2.0.exe", payload, "application/octet-stream")},
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["version"], "0.2.0")
        self.assertEqual(data["size_bytes"], len(payload))
        self.assertEqual(data["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(data["download_url"], "/updates/download/0.2.0?platform=win32")

        latest = self.client.get("/updates/latest?platform=win32&current_version=0.1.0")
        self.assertEqual(latest.status_code, 200)
        self.assertTrue(latest.json()["update_available"])

        same_version = self.client.get("/updates/latest?platform=win32&current_version=0.2.0")
        self.assertEqual(same_version.status_code, 200)
        self.assertFalse(same_version.json()["update_available"])

        unauthenticated = self.client.get("/updates/download/0.2.0?platform=win32")
        self.assertIn(unauthenticated.status_code, {401, 403})

        download = self.client.get("/updates/download/0.2.0?platform=win32", headers=self.employee_headers)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, payload)

    def test_employee_cannot_upload_and_minimum_version_forces_update(self):
        forbidden = self.client.post(
            "/updates/admin/releases",
            data={"version": "0.3.0", "platform": "win32"},
            files={"file": ("Project_R-0.3.0.exe", b"package", "application/octet-stream")},
            headers=self.employee_headers,
        )
        self.assertEqual(forbidden.status_code, 403)

        self.client.post(
            "/updates/admin/releases",
            data={
                "version": "0.3.0",
                "release_notes": "必须升级版本",
                "minimum_supported_version": "0.2.0",
                "platform": "win32",
                "is_force_update": "false",
            },
            files={"file": ("Project_R-0.3.0.exe", b"package-030", "application/octet-stream")},
            headers=self.admin_headers,
        )
        latest = self.client.get("/updates/latest?platform=win32&current_version=0.1.0")
        self.assertEqual(latest.status_code, 200)
        latest_json = latest.json()
        self.assertTrue(latest_json["update_available"])
        self.assertTrue(latest_json["latest"]["is_force_update"])

        release = self.db.query(ClientUpdateRelease).filter(ClientUpdateRelease.version == "0.3.0").one()
        self.assertTrue(Path(release.file_path).exists())


if __name__ == "__main__":
    unittest.main()
