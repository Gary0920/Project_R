from __future__ import annotations

import unittest
from pathlib import Path

from core.image_structured_extraction import (
    _detect_image_subkind,
    _find_field_value,
    _parse_extracted_fields,
    _enrich_markdown_with_parsed_fields,
    ExtractedImageFields,
)


class TestDetectImageSubkind(unittest.TestCase):
    def test_payment_keywords(self):
        for name in ["支付截图服务器.png", "payment_screenshot.jpg", "付款记录.png", "账单详情.jpg"]:
            with self.subTest(name=name):
                self.assertEqual(_detect_image_subkind(name), "payment")

    def test_contact_sheet_keywords(self):
        for name in ["内部联系单_1.png", "联系单_审批.png", "签证单.jpg", "变更通知.png", "contact_sheet.pdf"]:
            with self.subTest(name=name):
                self.assertEqual(_detect_image_subkind(name), "contact_sheet")

    def test_general_image(self):
        for name in ["photo.jpg", "screenshot.png", "diagram.png", "image001.png"]:
            with self.subTest(name=name):
                self.assertEqual(_detect_image_subkind(name), "general")

    def test_stem_not_extension(self):
        """Detection should work on stem not extension."""
        self.assertEqual(_detect_image_subkind("支付截图"), "payment")


class TestFindFieldValue(unittest.TestCase):
    def test_basic_field(self):
        md = "## Extracted Fields\n- **金额 / Amount**: 68.00\n- **币种 / Currency**: CNY\n"
        self.assertEqual(_find_field_value(md, ["金额", "Amount", "amount"]), "68.00")

    def test_chinese_field(self):
        md = "- **补货原因 / Replenishment Reason**: 材料不足需增补\n"
        self.assertEqual(_find_field_value(md, ["补货原因"]), "材料不足需增补")

    def test_not_found(self):
        md = "- **Some Other Field**: value\n"
        self.assertIsNone(_find_field_value(md, ["金额", "Amount"]))

    def test_na_value(self):
        md = "- **金额 / Amount**: N/A\n"
        self.assertIsNone(_find_field_value(md, ["金额", "Amount"]))

    def test_empty_value(self):
        md = "- **金额 / Amount**: \n"
        self.assertIsNone(_find_field_value(md, ["金额", "Amount"]))


class TestParseExtractedFields(unittest.TestCase):
    def test_parse_payment_fields(self):
        md = """## Extracted Fields
- **金额 / Amount**: 68.00
- **币种 / Currency**: CNY
- **方向 / Direction**: 支出 (outgoing)
- **支付时间 / Payment Time**: 2026-01-15 14:23
- **支付方式 / Payment Method**: 微信支付
- **交易对方 / Counterparty**: XX有限公司
"""
        fields = _parse_extracted_fields(md, "payment")
        self.assertEqual(fields.subkind, "payment")
        self.assertIsNotNone(fields.payment)
        self.assertEqual(fields.payment.amount, "68.00")
        self.assertEqual(fields.payment.currency, "CNY")
        self.assertEqual(fields.payment.direction, "outgoing")
        self.assertEqual(fields.payment.payment_method, "微信支付")

    def test_parse_contact_sheet_fields(self):
        md = """## Extracted Fields
- **单号 / Document Number**: BG0806-LXD01
- **补货原因 / Replenishment Reason**: 现场材料不足
- **补货内容 / Replenishment Items**: 铝材；五金配件
- **审批备注 / Approval Notes**: 已审批
"""
        fields = _parse_extracted_fields(md, "contact_sheet")
        self.assertEqual(fields.subkind, "contact_sheet")
        self.assertIsNotNone(fields.contact_sheet)
        self.assertEqual(fields.contact_sheet.document_number, "BG0806-LXD01")
        self.assertEqual(fields.contact_sheet.replenishment_reason, "现场材料不足")

    def test_general_no_parse(self):
        fields = _parse_extracted_fields("Some general text", "general")
        self.assertEqual(fields.subkind, "general")
        self.assertIsNone(fields.payment)
        self.assertIsNone(fields.contact_sheet)


class TestEnrichMarkdown(unittest.TestCase):
    def test_enrich_payment_markdown(self):
        md = "# Payment Screenshot\n## Description\nSome text.\n"
        fields = _parse_extracted_fields("", "payment")
        # Create enriched fields manually
        from core.image_structured_extraction import PaymentScreenshotFields
        fields = ExtractedImageFields(
            subkind="payment",
            payment=PaymentScreenshotFields(amount="68.00", currency="CNY"),
        )
        enriched = _enrich_markdown_with_parsed_fields(md, fields)
        self.assertIn("## Extracted Fields", enriched)
        self.assertIn("68.00", enriched)
        self.assertIn("CNY", enriched)

    def test_enrich_with_existing_fields_section(self):
        md = "## Extracted Fields\n- **金额**: 68.00\n## Description\n"
        fields = ExtractedImageFields(
            subkind="payment",
            payment=__import__('core.image_structured_extraction', fromlist=['PaymentScreenshotFields']).PaymentScreenshotFields(amount="68.00"),
        )
        enriched = _enrich_markdown_with_parsed_fields(md, fields)
        # Should not duplicate the section
        self.assertEqual(enriched.count("## Extracted Fields"), 1)

    def test_enrich_general_noop(self):
        md = "# General Image\n"
        fields = ExtractedImageFields(subkind="general")
        enriched = _enrich_markdown_with_parsed_fields(md, fields)
        self.assertEqual(enriched, md)

    def test_enrich_contact_sheet_markdown(self):
        md = "# Contact Sheet\n"
        from core.image_structured_extraction import ContactSheetFields
        fields = ExtractedImageFields(
            subkind="contact_sheet",
            contact_sheet=ContactSheetFields(
                document_number="BG0806-LXD01",
                replenishment_items=["铝材", "五金配件"],
            ),
        )
        enriched = _enrich_markdown_with_parsed_fields(md, fields)
        self.assertIn("## Extracted Fields", enriched)
        self.assertIn("BG0806-LXD01", enriched)
        self.assertIn("铝材", enriched)


if __name__ == "__main__":
    unittest.main()
