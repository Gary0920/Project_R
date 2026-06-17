import unittest

from app.features.documents.email_draft import build_email_draft, email_draft_metadata, parse_email_draft_text


class EmailDraftParserTests(unittest.TestCase):
    def test_parse_client_reply_markdown_section(self):
        draft = parse_email_draft_text(
            """
## 1. Reply Strategy

中文策略说明。

## 2. English Email Draft

Subject: Lucerna Apartments - Site Glazing Issue Review
To: Builder PM
Cc: Consultant
Body:

Hi John,

We acknowledge the concern raised and will review the site photos first.
At this stage, any cost or programme impact remains subject to confirmation.

Kind regards,
BFI

## 3. 中文说明

说明。
""",
            default_subject="Fallback",
        )

        self.assertEqual(draft.subject, "Lucerna Apartments - Site Glazing Issue Review")
        self.assertEqual(draft.to, ["Builder PM"])
        self.assertEqual(draft.cc, ["Consultant"])
        self.assertIn("cost or programme impact remains subject to confirmation", draft.body)
        self.assertNotIn("中文说明", draft.body)

    def test_parse_chinese_headers(self):
        draft = parse_email_draft_text(
            """
主题：Project A - 现场问题复核
收件人：client@example.com
抄送：pm@example.com; consultant@example.com
正文：
您好，我们会先复核现场照片和图纸版本，再确认下一步。
""",
        )

        self.assertEqual(draft.subject, "Project A - 现场问题复核")
        self.assertEqual(draft.to, ["client@example.com"])
        self.assertEqual(draft.cc, ["pm@example.com", "consultant@example.com"])
        self.assertIn("复核现场照片", draft.body)

    def test_metadata_overrides_parsed_fields_without_inventing_project_name(self):
        draft = build_email_draft(
            "客户回复",
            "Subject: Generic update\n\nHi Team,\nWe will review and revert.",
            email_draft_metadata(body="Hi Team,\nPlease see the confirmed position below."),
        )

        self.assertEqual(draft.subject, "Generic update")
        self.assertIn("confirmed position", draft.body)
        self.assertNotIn("Project", draft.subject)


if __name__ == "__main__":
    unittest.main()
