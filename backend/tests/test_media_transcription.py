import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.llm import LLMResponse, ProviderSettings
from core.media_transcription import MediaTranscriptionOptions, transcribe_media_to_markdown


class FakeLLMClient:
    def __init__(self):
        self.settings = ProviderSettings(
            provider="mimo",
            api_keys=("test-key",),
            model="mimo-v2.5",
            max_tokens=2048,
            base_url="http://test",
            timeout_seconds=1,
            system_prompt=None,
            profile="mimo-test",
            supports_vision=True,
        )
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        return LLMResponse(
            text="[00:00] Speaker 1: Project_R 和 GBrain 需要跟进。",
            model="mimo-v2.5",
            provider="mimo",
            key_index=1,
            usage={"input_tokens": 1, "output_tokens": 2},
        )


class MediaTranscriptionTests(unittest.TestCase):
    def test_large_video_audio_first_uses_extracted_audio_before_size_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video = root / "long-meeting.mp4"
            audio = root / "long-meeting.mp3"
            video.write_bytes(b"0" * 5000)
            audio.write_bytes(b"mp3")
            client = FakeLLMClient()
            options = MediaTranscriptionOptions(
                model_profile="mimo-test",
                max_raw_bytes=1000,
                refinement_enabled=False,
            )

            with patch("core.media_transcription._extract_audio_sidecar_for_transcription", return_value=audio), patch(
                "core.media_transcription._split_audio_for_transcription",
                return_value=[audio],
            ):
                result = transcribe_media_to_markdown(video, options=options, llm_client=client)

            self.assertEqual(client.calls, 1)
            self.assertIn("video audio track extracted", result.warnings[0])
            self.assertIn("Project_R", result.transcript_text)

    def test_refinement_can_record_speaker_and_term_pass_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / "meeting.mp3"
            audio.write_bytes(b"mp3")
            client = FakeLLMClient()
            options = MediaTranscriptionOptions(model_profile="mimo-test", max_raw_bytes=1000, refinement_enabled=True)

            with patch(
                "core.media_transcription._refine_transcript",
                return_value={
                    "text": "# meeting Transcript\n\n## Speaker Map / 说话人映射\n- Speaker 1: Unknown\n\n## Corrected Transcript / 术语纠错后转写\n[00:00] Speaker 1: Project_R 和 GBrain 需要跟进。\n",
                    "profile": "deepseek-test",
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "usage": {"input_tokens": 3, "output_tokens": 4},
                },
            ):
                result = transcribe_media_to_markdown(audio, options=options, llm_client=client)

            self.assertEqual(result.refinement_status, "speaker_terms_refined")
            self.assertEqual(result.refinement_model_profile, "deepseek-test")
            self.assertIn("Speaker Map", result.transcript_text)


if __name__ == "__main__":
    unittest.main()
