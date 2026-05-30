import unittest
from pathlib import Path

import core.extractor_classifier as classifier


class ExtractorClassifierTests(unittest.TestCase):
    def test_drawing_package_filename_overrides_selectable_pdf_text(self):
        original_diagnose_pdf = classifier._diagnose_pdf
        classifier._diagnose_pdf = lambda path: {
            "has_sidecar_images": False,
            "text_char_count": 5000,
            "page_count": 1,
            "pages_with_text": 1,
        }
        try:
            result = classifier.classify_source_file(
                Path("02-Drawings/A---2204-GENERAL-ARRANGEMENT-LEVEL-06---TYPICAL-06---10-Rev.4.pdf")
            )
        finally:
            classifier._diagnose_pdf = original_diagnose_pdf

        self.assertEqual(result.file_kind, "pdf")
        self.assertEqual(result.extraction_complexity, "vision_required")
        self.assertEqual(result.extractor_profile, "mimo_vision")

    def test_regular_selectable_pdf_with_arrangement_word_stays_text_route(self):
        original_diagnose_pdf = classifier._diagnose_pdf
        classifier._diagnose_pdf = lambda path: {
            "has_sidecar_images": False,
            "text_char_count": 5000,
            "page_count": 1,
            "pages_with_text": 1,
        }
        try:
            result = classifier.classify_source_file(Path("01-Contracts/Payment-Arrangement.pdf"))
        finally:
            classifier._diagnose_pdf = original_diagnose_pdf

        self.assertEqual(result.file_kind, "pdf")
        self.assertEqual(result.extraction_complexity, "simple_text")
        self.assertEqual(result.extractor_profile, "deepseek_text")


if __name__ == "__main__":
    unittest.main()
