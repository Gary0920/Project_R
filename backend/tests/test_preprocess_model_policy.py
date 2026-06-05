import tempfile
import unittest
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

from core.email_structured_extraction import EmailExtractionOptions, extract_email_structured_markdown
from core.image_structured_extraction import ImageStructuredExtractionOptions, extract_image_structured_markdown
from core.llm import LLMResponse, ProviderSettings
from core.media_transcription import MediaTranscriptionOptions, transcribe_media_to_markdown
from core.pdf_structured_extraction import PDFExtractionOptions, extract_pdf_structured_markdown, load_pdf_extraction_options
from core.preprocess_model_policy import PreprocessModelPolicyError
import core.gbrain_ingest as company_ingest
import core.gbrain_project_ingest as project_ingest


class _FakeLLMClient:
    def __init__(self, *, provider: str, model: str, profile: str = "test-profile", supports_vision: bool = True):
        self.settings = ProviderSettings(
            provider=provider,
            api_keys=("test-key",),
            model=model,
            max_tokens=2048,
            base_url="http://test",
            timeout_seconds=1,
            system_prompt=None,
            profile=profile,
            supports_vision=supports_vision,
        )
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        return LLMResponse(
            text="# output\n\n- 中文：测试。\n  English: Test.",
            model=self.settings.model,
            provider=self.settings.provider,
            key_index=0,
            usage={"input_tokens": 1, "output_tokens": 1},
        )


class PreprocessModelPolicyTests(unittest.TestCase):
    def test_mimo_v2_5_pro_profile_is_rejected_before_pdf_extraction(self):
        with patch.dict("os.environ", {"GBRAIN_PDF_EXTRACTOR_MODEL_PROFILE": "mimo-v2-5-pro"}):
            with self.assertRaises(PreprocessModelPolicyError):
                load_pdf_extraction_options()

    def test_pdf_extractor_rejects_non_mimo_v2_5_client_before_reading_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "not-a-real.pdf"
            source.write_bytes(b"not a pdf")

            with self.assertRaises(PreprocessModelPolicyError):
                extract_pdf_structured_markdown(
                    source,
                    options=PDFExtractionOptions(model_profile="mimo-test"),
                    llm_client=_FakeLLMClient(provider="mimo", model="mimo-v2.5-pro", profile="mimo-test"),
                )

    def test_image_extractor_rejects_non_mimo_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "screen.png"
            source.write_bytes(b"\x89PNG\r\n\x1a\nfake")

            with self.assertRaises(PreprocessModelPolicyError):
                extract_image_structured_markdown(
                    source,
                    options=ImageStructuredExtractionOptions(model_profile="deepseek-test", max_raw_bytes=1000),
                    llm_client=_FakeLLMClient(
                        provider="deepseek",
                        model="deepseek-v4-flash",
                        profile="deepseek-test",
                        supports_vision=False,
                    ),
                )

    def test_media_transcription_rejects_non_mimo_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "meeting.mp3"
            source.write_bytes(b"mp3")

            with self.assertRaises(PreprocessModelPolicyError):
                transcribe_media_to_markdown(
                    source,
                    options=MediaTranscriptionOptions(
                        model_profile="deepseek-test",
                        max_raw_bytes=1000,
                        refinement_enabled=False,
                    ),
                    llm_client=_FakeLLMClient(
                        provider="deepseek",
                        model="deepseek-v4-flash",
                        profile="deepseek-test",
                        supports_vision=False,
                    ),
                )

    def test_email_text_extraction_does_not_call_non_deepseek_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "client.eml"
            message = EmailMessage()
            message["From"] = "client@example.com"
            message["To"] = "pm@example.com"
            message["Subject"] = "Apt 5 Window"
            message.set_content("Please confirm type 5 window.")
            source.write_bytes(message.as_bytes())
            client = _FakeLLMClient(provider="mimo", model="mimo-v2.5", profile="mimo-test")

            result = extract_email_structured_markdown(
                source,
                options=EmailExtractionOptions(model_profile="mimo-test", llm_enabled=True),
                llm_client=client,
            )

            self.assertEqual(client.calls, 0)
            self.assertIn("Please confirm type 5 window", result.markdown)
            self.assertTrue(any("must use DeepSeek" in warning for warning in result.warnings))

    def test_legacy_company_pdf_text_route_is_prohibited(self):
        with self.assertRaisesRegex(RuntimeError, "PDF text extraction is prohibited"):
            company_ingest._compile_pdf_source(Path("source.pdf"), Path("target.md"), object(), "now", "sha")

    def test_legacy_project_pdf_text_route_is_prohibited(self):
        with self.assertRaisesRegex(RuntimeError, "PDF text extraction is prohibited"):
            project_ingest._compile_project_pdf_text_source(
                Path("source.pdf"),
                Path("target.md"),
                object(),
                {"root": Path(".")},
                "now",
                "sha",
                object(),
            )


if __name__ == "__main__":
    unittest.main()
