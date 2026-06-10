"""Unit tests for media_transcription_tool.py.

No database access required — the tool is a pure wrapper around
core.media_transcription.transcribe_media_to_markdown().
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.tools.media_transcription_tool import (
    MediaTranscriptionToolInput,
    MediaTranscriptionToolOutput,
    run_media_transcription_tool,
)


class MediaTranscriptionToolTests(unittest.TestCase):
    def test_input_validation_missing_file(self):
        """不存在的文件应抛出 FileNotFoundError"""
        with self.assertRaises(FileNotFoundError):
            run_media_transcription_tool(
                MediaTranscriptionToolInput(media_path=Path("/nonexistent/audio.mp3"))
            )

    def test_unsupported_extension(self):
        """不支持的文件扩展名应抛出 ValueError"""
        with self.assertRaises(ValueError):
            run_media_transcription_tool(
                MediaTranscriptionToolInput(media_path=Path(__file__))
            )

    def test_transcription_success(self):
        """正常转写返回 text + metadata"""
        mock_result = MagicMock()
        mock_result.transcript_text = "[00:00] Speaker 1: Hello"
        mock_result.provider = "mimo"
        mock_result.model = "mimo-v2.5"
        mock_result.segment_count = 1
        mock_result.warnings = ()

        with patch("core.tools.media_transcription_tool.transcribe_media_to_markdown", return_value=mock_result), \
             patch("core.tools.media_transcription_tool.load_media_transcription_options"), \
             patch("core.tools.media_transcription_tool.get_llm_client"):
            # Use a real file (this test script itself) as a "media file" after
            # patching out the actual transcription; the extension check is
            # skipped because we're monkey-patching transcribe_media_to_markdown
            # which is called AFTER the extension check. Use a fake mp3 path
            # that exists on disk.
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(b"\x00" * 10)
                tmp_path = Path(tmp.name)
            try:
                output = run_media_transcription_tool(
                    MediaTranscriptionToolInput(media_path=tmp_path)
                )
                self.assertEqual(output.text, "[00:00] Speaker 1: Hello")
                self.assertEqual(output.provider, "mimo")
                self.assertEqual(output.model, "mimo-v2.5")
                self.assertEqual(output.segments_count, 1)
                self.assertEqual(output.warnings, [])
            finally:
                os.unlink(tmp_path)

    def test_transcription_failure_wraps_exception(self):
        """转写失败应包装为 RuntimeError"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(b"\x00" * 10)
            tmp_path = Path(tmp.name)
        try:
            with patch("core.tools.media_transcription_tool.transcribe_media_to_markdown",
                       side_effect=ConnectionError("API unavailable")), \
                 patch("core.tools.media_transcription_tool.load_media_transcription_options"), \
                 patch("core.tools.media_transcription_tool.get_llm_client"):
                with self.assertRaises(RuntimeError) as ctx:
                    run_media_transcription_tool(
                        MediaTranscriptionToolInput(media_path=tmp_path)
                    )
                self.assertIn("音频转写失败", str(ctx.exception))
                self.assertIn("API unavailable", str(ctx.exception.__cause__))
        finally:
            os.unlink(tmp_path)

    def test_output_dataclass(self):
        """输出 dataclass 字段正确"""
        output = MediaTranscriptionToolOutput(
            text="test",
            provider="deepseek",
            model="flash",
            segments_count=3,
            warnings=["w1", "w2"],
        )
        self.assertEqual(output.text, "test")
        self.assertEqual(len(output.warnings), 2)


if __name__ == "__main__":
    unittest.main()
