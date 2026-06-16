import os
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.NamedTemporaryFile(delete=False).name}"

from app.features.documents.generation import create_generated_file
from app.features.skills.dispatcher import SkillDispatcher
from app.features.skills.document_tools import DOCUMENT_RENDER_TOOL
from app.features.skills.runner import SkillDefinition, SkillRunner
from models import Base, SessionLocal, engine
from models.generated_file import GeneratedFile
from models.session import ChatSession
from models.skill_run import SkillRun
from models.user import User


class EmailGeneratedFileTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.temp = tempfile.TemporaryDirectory()
        self.user = User(username="email-user", password_hash="hash", role="employee", nickname="Email")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.session = ChatSession(user_id=self.user.id, title="Email session")
        self.db.add(self.session)
        self.db.commit()
        self.db.refresh(self.session)
        SkillRunner._instance = None

    def tearDown(self):
        self.temp.cleanup()
        self.db.close()
        SkillRunner._instance = None

    def test_generated_eml_file_can_be_parsed(self):
        payload = create_generated_file(
            self.db,
            self.user.id,
            self.session.id,
            "客户邮件草稿",
            "This body should be replaced by metadata.",
            output_format="email",
            generated_files_root=Path(self.temp.name),
            metadata={
                "email_draft": {
                    "subject": "Window delivery update",
                    "to": ["builder@example.com", "consultant@example.com"],
                    "body": "Hi Team,\n\nWe are reviewing the delivery status and will revert shortly.",
                }
            },
        )
        record = self.db.get(GeneratedFile, payload["id"])
        self.assertIsNotNone(record)

        message = BytesParser(policy=policy.default).parsebytes(Path(record.path).read_bytes())

        self.assertEqual(message["Subject"], "Window delivery update")
        self.assertIn("builder@example.com", message["To"])
        self.assertIn("consultant@example.com", message["To"])
        self.assertIn("delivery status", message.get_body(preferencelist=("plain",)).get_content())
        self.assertEqual(payload["email_draft"]["body"], "Hi Team,\n\nWe are reviewing the delivery status and will revert shortly.")

    def test_dispatcher_document_render_tool_generates_eml_from_fields(self):
        runner = SkillRunner.get()
        runner._skills["email-render-test"] = SkillDefinition(
            name="email-render-test",
            display_name="邮件草稿测试",
            description="Render an email draft from collected fields",
            category="test",
            priority="low",
            trigger=[],
            inputs=[
                {"name": "subject", "type": "string", "label": "Subject", "required": True},
                {"name": "recipient", "type": "string", "label": "Recipient", "required": True},
                {"name": "body", "type": "text", "label": "Body", "required": True},
            ],
            outputs=[{"type": "file", "format": "eml"}],
            references=[],
            execution={
                "mode": "dispatcher",
                "steps": [
                    {
                        "id": "render",
                        "label": "生成邮件草稿",
                        "tool": DOCUMENT_RENDER_TOOL,
                        "format": "eml",
                        "title_template": "{subject}",
                        "content_field": "body",
                        "subject_field": "subject",
                        "to_field": "recipient",
                        "body_field": "body",
                    }
                ],
            },
            governance={"risk_level": "low", "allowed_tools": [DOCUMENT_RENDER_TOOL]},
            path="skills/builtin/email-render-test/SKILL.md",
        )
        run = SkillRun(
            skill_name="email-render-test",
            user_id=self.user.id,
            session_id=self.session.id,
            status="ready",
            inputs_json='{"subject":"Glass sample update","recipient":"builder@example.com","body":"Hi Team,\\n\\nPlease see the update below."}',
            missing_inputs_json="[]",
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)

        completed_run = SkillDispatcher().execute(self.db, run, generated_root=Path(self.temp.name))

        self.assertEqual(completed_run.status, "completed")
        self.assertIsNotNone(completed_run.generated_file_id)
        record = self.db.get(GeneratedFile, completed_run.generated_file_id)
        self.assertTrue(record.filename.endswith(".eml"))
        message = BytesParser(policy=policy.default).parsebytes(Path(record.path).read_bytes())
        self.assertEqual(message["Subject"], "Glass sample update")
        self.assertEqual(message["To"], "builder@example.com")


if __name__ == "__main__":
    unittest.main()
