import os
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.documents as documents_api
from app.features.documents.export_content_service import ExportContentError, export_content_to_temp_file
from app.features.documents.schemas import ExportDocumentRequest
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from models.user import User
from pydantic import ValidationError


class DocumentsExportTests(unittest.TestCase):
    def setUp(self):
        self.user = User(id=1, username="export-user", password_hash="hash", role="employee", nickname="Export")
        self.temp_paths: list[Path] = []

    def tearDown(self):
        for path in self.temp_paths:
            if path.exists():
                if path.is_dir():
                    import shutil

                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)

    def test_export_content_service_pdf(self):
        path, filename = export_content_to_temp_file(
            content="## 测试\n\n这是一段中文正文。",
            title="测试文档",
            output_format="pdf",
        )
        self.temp_paths.append(path.parent)
        self.assertTrue(path.exists())
        self.assertTrue(filename.endswith(".pdf"))
        self.assertGreater(path.stat().st_size, 100)

    def test_export_content_service_docx(self):
        path, filename = export_content_to_temp_file(
            content="## 测试\n\n这是一段中文正文。",
            title="测试文档",
            output_format="docx",
        )
        self.temp_paths.append(path.parent)
        self.assertTrue(path.exists())
        self.assertTrue(filename.endswith(".docx"))
        with ZipFile(path) as archive:
            self.assertIn("word/document.xml", archive.namelist())

    def test_export_content_service_rejects_oversized_content(self):
        with self.assertRaises(ExportContentError):
            export_content_to_temp_file(
                content="x" * (200 * 1024 + 1),
                title="过大",
                output_format="pdf",
            )

    def test_export_document_route_returns_file(self):
        body = ExportDocumentRequest(
            content="Subject: Hello\n\nDear client,\n\nThis is a test.",
            title="Email Draft",
            format="pdf",
        )
        response = documents_api.export_document_content(body, BackgroundTasks(), self.user)
        self.assertIsInstance(response, FileResponse)
        path = Path(str(response.path))
        self.temp_paths.append(path.parent)
        self.assertTrue(path.exists())

    def test_export_document_route_rejects_empty_content(self):
        with self.assertRaises(ValidationError):
            ExportDocumentRequest(content="", title=None, format="docx")

    def test_export_document_route_rejects_oversized_content(self):
        with self.assertRaises(HTTPException) as exc:
            documents_api.export_document_content(
                ExportDocumentRequest(content="x" * (200 * 1024 + 1), title=None, format="docx"),
                BackgroundTasks(),
                self.user,
            )
        self.assertEqual(exc.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
