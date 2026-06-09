import tempfile
import unittest
from pathlib import Path

from core.image_structured_extraction import (
    ImageStructuredExtractionOptions,
    _image_prompt,
    extract_image_structured_markdown,
)
from core.llm import LLMResponse, ProviderSettings


class _FakeImageLLMClient:
    def __init__(self):
        self.settings = ProviderSettings(
            profile="mimo-test",
            provider="mimo",
            api_keys=("test",),
            model="mimo-v2.5",
            max_tokens=1024,
            base_url="https://api.xiaomimimo.com/v1",
            timeout_seconds=30,
            system_prompt=None,
            supports_vision=True,
        )
        self.messages = None

    def complete(self, messages, *, system_prompt=None, temperature=0.0):
        self.messages = messages
        return LLMResponse(
            text="# 审批流程截图\n\n- 中文：截图显示审批需要经理确认。\n  English: The screenshot shows approval requires manager confirmation.",
            model="mimo-v2.5",
            provider="mimo",
            key_index=0,
            usage={"input_tokens": 12, "output_tokens": 8},
        )


class ImageStructuredExtractionTests(unittest.TestCase):
    def test_image_prompt_requires_uncertainty_and_bilingual_output(self):
        prompt = _image_prompt("审批流程.png", "general")

        self.assertIn("不要编造", prompt)
        self.assertIn("中英文对齐", prompt)
        self.assertIn("待确认", prompt)

    def test_extract_image_structured_markdown_uses_vision_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "审批流程.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            client = _FakeImageLLMClient()

            result = extract_image_structured_markdown(
                source,
                options=ImageStructuredExtractionOptions(model_profile="mimo-test", max_raw_bytes=1000),
                llm_client=client,
            )

            self.assertEqual(result.model_profile, "mimo-test")
            self.assertEqual(result.provider, "mimo")
            self.assertEqual(result.model, "mimo-v2.5")
            self.assertIn("manager confirmation", result.markdown)
            content = client.messages[0]["content"]
            self.assertEqual(content[0]["type"], "image_url")
            self.assertTrue(content[0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_rejects_unsupported_or_oversized_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            unsupported = Path(temp_dir) / "image.svg"
            unsupported.write_text("<svg />", encoding="utf-8")
            with self.assertRaises(ValueError):
                extract_image_structured_markdown(unsupported, llm_client=_FakeImageLLMClient())

            oversized = Path(temp_dir) / "image.png"
            oversized.write_bytes(b"x" * 20)
            with self.assertRaises(ValueError):
                extract_image_structured_markdown(
                    oversized,
                    options=ImageStructuredExtractionOptions(model_profile="mimo-test", max_raw_bytes=10),
                    llm_client=_FakeImageLLMClient(),
                )


if __name__ == "__main__":
    unittest.main()
