import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

import api.documents as documents_api
from app.features.documents.renderer import render_docx
from fastapi import HTTPException
from fastapi.responses import FileResponse
from models import Base, SessionLocal, engine
from models.generated_file import GeneratedFile
from models.user import User


class DocumentsPhase11Tests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp = tempfile.TemporaryDirectory()
        self.user = User(username="doc", password_hash="hash", role="employee", nickname="Doc")
        self.admin = User(username="admin-doc", password_hash="hash", role="admin", nickname="Admin")
        self.other = User(username="other-doc", password_hash="hash", role="employee", nickname="Other")
        self.db.add_all([self.user, self.admin, self.other])
        self.db.commit()
        self.db.refresh(self.user)
        self.db.refresh(self.admin)
        self.db.refresh(self.other)

    def tearDown(self):
        self.temp.cleanup()
        self.db.close()

    def create_file_record(self, user_id: int, file_id: str = "file-1", age_hours: int = 1):
        path = Path(self.temp.name) / f"{file_id}.docx"
        path.write_bytes(b"docx")
        record = GeneratedFile(
            id=file_id,
            user_id=user_id,
            session_id=None,
            filename=f"{file_id}.docx",
            path=str(path),
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            created_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
        )
        self.db.add(record)
        self.db.commit()
        return record

    def test_download_generated_file_requires_owner(self):
        record = self.create_file_record(self.user.id)

        response = documents_api.download_generated_file(record.id, self.user, self.db)

        self.assertIsInstance(response, FileResponse)
        with self.assertRaises(HTTPException) as exc:
            documents_api.download_generated_file(record.id, self.other, self.db)
        self.assertEqual(exc.exception.status_code, 404)

    def test_cleanup_generated_files_is_admin_only_and_removes_expired(self):
        expired = self.create_file_record(self.user.id, "expired", age_hours=72)
        fresh = self.create_file_record(self.user.id, "fresh", age_hours=1)

        with self.assertRaises(HTTPException) as exc:
            documents_api.cleanup_generated_files(self.user, self.db)

        self.assertEqual(exc.exception.status_code, 403)
        result = documents_api.cleanup_generated_files(self.admin, self.db)

        self.assertEqual(result["removed"], 1)
        self.assertIsNone(self.db.get(GeneratedFile, expired.id))
        self.assertIsNotNone(self.db.get(GeneratedFile, fresh.id))
        self.assertFalse(Path(expired.path).exists())
        self.assertTrue(Path(fresh.path).exists())

    def test_docx_renderer_strips_markdown_wrappers_and_source_list(self):
        path = Path(self.temp.name) / "rendered.docx"
        render_docx(
            "用车申请",
            (
                "说明：下面是模板。\n\n"
                "```markdown\n"
                "# 用车申请\n\n"
                "**申请人**：张三\n\n"
                "| 字段 | 内容 |\n"
                "| --- | --- |\n"
                "| 用车类型 | 临时用车 |\n"
                "\n"
                "```\n\n"
                "本次回答使用的来源文件：\n"
                "- [[用车申请]]\n"
            ),
            path,
        )

        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("用车申请", document_xml)
        self.assertIn("申请人", document_xml)
        self.assertNotIn("```", document_xml)
        self.assertNotIn("**", document_xml)
        self.assertNotIn("[[用车申请]]", document_xml)


if __name__ == "__main__":
    unittest.main()
