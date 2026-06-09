from __future__ import annotations

import unittest

from core.meeting_quality import (
    detect_repeated_text,
    classify_transcript_quality,
    quality_to_manifest_metadata,
    get_quality_penalty_factor,
)


class TestDetectRepeatedText(unittest.TestCase):
    def test_empty_transcript(self):
        result = detect_repeated_text("")
        self.assertEqual(result.asr_quality, "unusable")
        self.assertEqual(result.total_chars, 0)

    def test_good_transcript(self):
        text = "This is a normal meeting transcript without any repeated content. Everyone discussed the project plan."
        result = detect_repeated_text(text)
        self.assertEqual(result.asr_quality, "good")
        self.assertFalse(result.has_repeated_text)

    def test_poor_repeated_text(self):
        """>30% repeated content → poor."""
        part = "hello world this is a test segment that repeats over and over. "
        text = part * 5
        result = detect_repeated_text(text)
        self.assertIn(result.asr_quality, ("poor", "unusable"))
        self.assertTrue(result.has_repeated_text)
        self.assertGreater(result.repeated_ratio, 0.1)

    def test_fair_some_repetition(self):
        # Create a text with only mild repetition (~15%)
        text = (
            "Today we discussed the project timeline and budget allocation. "
            "The team agreed on the Q3 milestones for delivery. "
            "We also reviewed the risk register and updated the schedule. "
            "We need to review the design specifications again. "
            "The team agreed on the Q3 milestones for delivery. "
        )
        result = detect_repeated_text(text)
        self.assertEqual(result.asr_quality, "fair")

    def test_chinese_repeated_text(self):
        part = "关于这个项目的设计方案我们需要再次确认。"
        text = part * 4 + "这里有一些新的内容。"
        result = detect_repeated_text(text)
        self.assertIn(result.asr_quality, ("poor", "unusable"))
        self.assertTrue(result.has_repeated_text)

    def test_short_text_no_repeat(self):
        result = detect_repeated_text("Short text", min_repeat_length=5)
        self.assertEqual(result.asr_quality, "good")


class TestClassifyTranscriptQuality(unittest.TestCase):
    def test_convenience_wrapper(self):
        result = classify_transcript_quality("Normal transcript text.")
        self.assertIsNotNone(result)


class TestQualityToManifestMetadata(unittest.TestCase):
    def test_metadata_structure(self):
        result = detect_repeated_text("Some normal text here.")
        meta = quality_to_manifest_metadata(result)
        self.assertIn("asr_quality", meta)
        self.assertIn("repeated_ratio", meta)
        self.assertIn("has_repeated_text", meta)


class TestGetQualityPenaltyFactor(unittest.TestCase):
    def test_good_no_penalty(self):
        self.assertEqual(get_quality_penalty_factor("good"), 1.0)

    def test_fair_slight_penalty(self):
        self.assertEqual(get_quality_penalty_factor("fair"), 0.8)

    def test_poor_half_penalty(self):
        self.assertEqual(get_quality_penalty_factor("poor"), 0.5)

    def test_unusable_heavy_penalty(self):
        self.assertEqual(get_quality_penalty_factor("unusable"), 0.2)

    def test_unknown_default(self):
        self.assertEqual(get_quality_penalty_factor("unknown"), 1.0)


if __name__ == "__main__":
    unittest.main()
