from __future__ import annotations

import unittest

from core.project_citation import (
    normalize_citation,
    format_citation,
    source_reference_to_dict,
    guess_file_kind_from_source,
    SourceReference,
)


class TestNormalizeCitation(unittest.TestCase):
    def test_page_reference(self):
        ref = normalize_citation("drawing.pdf", file_kind="pdf_drawing", page=9)
        self.assertEqual(ref.reference_type, "page")
        self.assertEqual(ref.page, 9)

    def test_region_reference(self):
        ref = normalize_citation("payment.png", region="金额区域（右下角）")
        self.assertEqual(ref.reference_type, "region")
        self.assertEqual(ref.region, "金额区域（右下角）")

    def test_sheet_row_reference(self):
        ref = normalize_citation("ml.xlsx", sheet="Glass", row=3)
        self.assertEqual(ref.reference_type, "sheet_row")
        self.assertEqual(ref.sheet, "Glass")
        self.assertEqual(ref.row, 3)

    def test_timestamp_reference(self):
        ref = normalize_citation("meeting.mp4", timestamp="01:23:45")
        self.assertEqual(ref.reference_type, "timestamp")

    def test_text_span_reference(self):
        ref = normalize_citation("notes.docx", text_span="hardware color adaptation")
        self.assertEqual(ref.reference_type, "text_span")

    def test_default_text_span(self):
        ref = normalize_citation("file.pdf")
        self.assertEqual(ref.reference_type, "text_span")


class TestFormatCitation(unittest.TestCase):
    def test_page_citation(self):
        ref = normalize_citation("drawing.pdf", page=9)
        text = format_citation(ref)
        self.assertIn("drawing.pdf", text)
        self.assertIn("p.9", text)

    def test_sheet_citation(self):
        ref = normalize_citation("ml.xlsx", sheet="Glass", row=3)
        text = format_citation(ref)
        self.assertIn("ml.xlsx", text)
        self.assertIn("sheet=Glass", text)
        self.assertIn("row=3", text)


class TestGuessFileKind(unittest.TestCase):
    def test_pdf_drawing(self):
        self.assertEqual(guess_file_kind_from_source("Floor Plan.pdf"), "pdf_drawing")
        self.assertEqual(guess_file_kind_from_source("drawing_elevation.pdf"), "pdf_drawing")

    def test_pdf_schedule(self):
        self.assertEqual(guess_file_kind_from_source("Facade Programme Rev04.pdf"), "pdf_schedule")

    def test_image_payment(self):
        self.assertEqual(guess_file_kind_from_source("支付截图.png"), "image_payment")
        self.assertEqual(guess_file_kind_from_source("payment_screenshot.jpg"), "image_payment")

    def test_image_contact_sheet(self):
        self.assertEqual(guess_file_kind_from_source("内部联系单.png"), "image_contact_sheet")

    def test_general_image(self):
        self.assertEqual(guess_file_kind_from_source("photo.jpg"), "image")
        self.assertEqual(guess_file_kind_from_source("screenshot.png"), "image")

    def test_email(self):
        self.assertEqual(guess_file_kind_from_source("email.eml"), "email")

    def test_spreadsheet(self):
        self.assertEqual(guess_file_kind_from_source("ml.xlsx"), "spreadsheet")
        self.assertEqual(guess_file_kind_from_source("data.csv"), "spreadsheet")

    def test_office_doc(self):
        self.assertEqual(guess_file_kind_from_source("notes.docx"), "office_doc")

    def test_meeting_media(self):
        self.assertEqual(guess_file_kind_from_source("meeting.mp4"), "meeting_media")

    def test_unknown(self):
        self.assertIsNone(guess_file_kind_from_source("unknown.xyz"))


class TestSourceReferenceToDict(unittest.TestCase):
    def test_serialization(self):
        ref = normalize_citation("test.pdf", page=5, file_kind="pdf")
        d = source_reference_to_dict(ref)
        self.assertEqual(d["source_file"], "test.pdf")
        self.assertEqual(d["page"], 5)
        self.assertEqual(d["file_kind"], "pdf")
        self.assertEqual(d["reference_type"], "page")


if __name__ == "__main__":
    unittest.main()
