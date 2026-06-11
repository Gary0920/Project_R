import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path

from app.features.preprocessing.email_structured import EmailExtractionOptions, extract_email_attachments, extract_email_structured_markdown


class EmailStructuredExtractionTests(unittest.TestCase):
    def test_extract_email_structured_markdown_fallback_parses_headers_and_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "client.eml"
            message = EmailMessage()
            message["From"] = "client@example.com"
            message["To"] = "pm@example.com"
            message["Subject"] = "Apt 5 Window"
            message["Date"] = "Fri, 5 Jun 2026 10:00:00 +0800"
            message.set_content("Please confirm type 5 window.")
            source.write_bytes(message.as_bytes())

            result = extract_email_structured_markdown(
                source,
                options=EmailExtractionOptions(llm_enabled=False),
            )

            self.assertEqual(result.subject, "Apt 5 Window")
            self.assertEqual(result.sender, "client@example.com")
            self.assertEqual(result.recipients, ("pm@example.com",))
            self.assertIn("Please confirm type 5 window", result.markdown)
            self.assertEqual(result.language_policy, "bilingual_zh_en_aligned")

    def test_extract_email_attachments_writes_named_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "client.eml"
            message = EmailMessage()
            message["From"] = "client@example.com"
            message["Subject"] = "Attachment"
            message.set_content("See attachment.")
            message.add_attachment("Attachment body", subtype="plain", filename="note.txt")
            source.write_bytes(message.as_bytes())

            attachments = extract_email_attachments(source, Path(temp_dir) / "attachments")

            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0].filename, "note.txt")
            self.assertEqual(attachments[0].path.read_text(encoding="utf-8").strip(), "Attachment body")


if __name__ == "__main__":
    unittest.main()
