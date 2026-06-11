import unittest
from pathlib import Path

import app.features.preprocessing.classifier as classifier


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

    def test_regular_selectable_pdf_uses_mimo_structured_route_with_text_assist(self):
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
        self.assertEqual(result.extraction_complexity, "text_assisted")
        self.assertEqual(result.extractor_profile, "mimo_pdf_structured")

    def test_spreadsheet_files_are_visible_pending_capability(self):
        for path in [
            Path("01-合同与报价/报价表.xlsx"),
            Path("01-合同与报价/价格清单.csv"),
            Path("01-合同与报价/schedule.tsv"),
        ]:
            result = classifier.classify_source_file(path)
            self.assertEqual(result.file_kind, "spreadsheet", path.name)
            self.assertEqual(result.extraction_complexity, "pending_capability", path.name)
            self.assertEqual(result.extractor_profile, "pending_extractor_capability", path.name)

    def test_reference_pdf_samples_route_to_expected_preprocessors_when_available(self):
        root = Path(__file__).resolve().parents[2] / "reference" / "pdf-structured-preprocess"
        if not root.exists():
            self.skipTest("reference PDF samples are not present")

        text_samples = sorted((root / "普通可选中文本 PDF").glob("*.pdf"))
        vision_samples = sorted((root / "视觉版式依赖 PDF").glob("*.pdf"))
        poor_quality_samples = sorted((root / "质量较差 PDF").glob("*.pdf"))
        self.assertGreaterEqual(len(text_samples), 1)
        self.assertGreaterEqual(len(vision_samples), 1)
        self.assertGreaterEqual(len(poor_quality_samples), 1)

        for path in text_samples:
            result = classifier.classify_source_file(path)
            self.assertEqual(result.extraction_complexity, "text_assisted", path.name)
            self.assertEqual(result.extractor_profile, "mimo_pdf_structured", path.name)

        for path in [*vision_samples, *poor_quality_samples]:
            result = classifier.classify_source_file(path)
            self.assertEqual(result.extraction_complexity, "vision_required", path.name)
            self.assertEqual(result.extractor_profile, "mimo_vision", path.name)


if __name__ == "__main__":
    unittest.main()
