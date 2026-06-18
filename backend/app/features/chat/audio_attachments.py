from __future__ import annotations

from pathlib import Path

from models.attachment import SessionAttachment


AUDIO_EXTENSIONS: set[str] = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
}

VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mov", ".avi", ".wmv", ".mkv", ".webm",
}

AUDIO_VIDEO_EXTENSIONS: set[str] = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


def find_audio_attachments(attachments: list[SessionAttachment]) -> list[SessionAttachment]:
    return [
        attachment for attachment in attachments
        if attachment.stored_path and Path(attachment.stored_path).suffix.lower() in AUDIO_EXTENSIONS
    ]


def is_audio_attachment(attachment: SessionAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    return content_type.startswith("audio/") or Path(attachment.stored_path or attachment.original_name).suffix.lower() in AUDIO_EXTENSIONS


def is_video_attachment(attachment: SessionAttachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    return content_type.startswith("video/") or Path(attachment.stored_path or attachment.original_name).suffix.lower() in VIDEO_EXTENSIONS
