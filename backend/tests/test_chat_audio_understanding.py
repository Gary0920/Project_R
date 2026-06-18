from pathlib import Path

from app.features.chat import audio_understanding
from app.features.chat.audio_attachments import find_audio_attachments, is_audio_attachment, is_video_attachment
from app.features.preprocessing.tools.media_transcription import MediaTranscriptionToolOutput
from models.attachment import SessionAttachment


def _attachment(name: str, path: Path, content_type: str = "application/octet-stream") -> SessionAttachment:
    return SessionAttachment(
        session_id=1,
        user_id=1,
        original_name=name,
        stored_path=str(path),
        content_type=content_type,
        size=1,
    )


def test_audio_attachment_detection_excludes_video(tmp_path: Path):
    audio = _attachment("meeting.m4a", tmp_path / "meeting.m4a", "audio/mp4")
    video = _attachment("meeting.mp4", tmp_path / "meeting.mp4", "video/mp4")

    assert is_audio_attachment(audio) is True
    assert is_video_attachment(video) is True
    assert find_audio_attachments([audio, video]) == [audio]


def test_transcribe_audio_attachments_builds_chat_context(monkeypatch, tmp_path: Path):
    audio_path = tmp_path / "meeting.wav"
    audio_path.write_bytes(b"fake audio")
    attachment = _attachment("meeting.wav", audio_path, "audio/wav")

    calls = []

    def fake_transcription(input):
        calls.append(input)
        return MediaTranscriptionToolOutput(
            text="会议提到下周三提交预算。",
            provider="mimo",
            model="mimo-asr",
            warnings=["low-volume"],
        )

    monkeypatch.setattr(audio_understanding, "run_media_transcription_tool", fake_transcription)

    result = audio_understanding.transcribe_audio_attachments_for_chat(
        [attachment],
        model_profile="mimo-asr",
    )

    assert len(calls) == 1
    assert calls[0].media_path == audio_path
    assert calls[0].model_profile == "mimo-asr"
    assert result.transcript_count == 1
    assert "[音频理解] meeting.wav" in result.context
    assert "下周三提交预算" in result.context
    assert result.warnings == ["low-volume"]
