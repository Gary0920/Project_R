from __future__ import annotations

from pathlib import Path

from models.attachment import SessionAttachment


AUDIO_VIDEO_EXTENSIONS: set[str] = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".mp4", ".mov", ".avi", ".wmv", ".mkv", ".webm",
}


def find_audio_attachments(attachments: list[SessionAttachment]) -> list[SessionAttachment]:
    return [
        attachment for attachment in attachments
        if attachment.stored_path and Path(attachment.stored_path).suffix.lower() in AUDIO_VIDEO_EXTENSIONS
    ]
