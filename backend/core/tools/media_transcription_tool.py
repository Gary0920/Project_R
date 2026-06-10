"""Reusable media transcription tool.

Wraps `core.media_transcription.transcribe_media_to_markdown()` as a
self-contained tool that does NOT write project files, generate GBrain-ready
output, modify workspace data, or interact with the chat/API layer.

Intended for use by Skill execution, chat handlers, and future automations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.llm import get_llm_client
from core.media_transcription import (
    load_media_transcription_options,
    transcribe_media_to_markdown,
)


@dataclass(frozen=True)
class MediaTranscriptionToolInput:
    """Input for the media transcription tool."""

    media_path: Path
    model_profile: str | None = None


@dataclass(frozen=True)
class MediaTranscriptionToolOutput:
    """Output from the media transcription tool."""

    text: str
    provider: str | None = None
    model: str | None = None
    segments_count: int | None = None
    warnings: list[str] = field(default_factory=list)


_SUPPORTED_EXTENSIONS: set[str] = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac",
    ".mp4", ".mov", ".avi", ".wmv", ".mkv", ".webm",
}


def run_media_transcription_tool(input: MediaTranscriptionToolInput) -> MediaTranscriptionToolOutput:
    """Transcribe a media file to text.

    Raises:
        FileNotFoundError: if media_path does not exist or is not a file.
        ValueError: if the file extension is unsupported.
        RuntimeError: if transcription fails.
    """
    path = input.media_path
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"媒体文件不存在：{path}")

    ext = path.suffix.lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"不支持的媒体格式（{ext}），仅支持：{', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    options = load_media_transcription_options()
    if input.model_profile:
        from dataclasses import replace
        options = replace(options, model_profile=input.model_profile)

    try:
        client = get_llm_client(options.model_profile)
        result = transcribe_media_to_markdown(path, options=options, llm_client=client)
    except Exception as exc:
        raise RuntimeError(f"音频转写失败：{exc}") from exc

    return MediaTranscriptionToolOutput(
        text=result.transcript_text,
        provider=result.provider,
        model=result.model,
        segments_count=result.segment_count,
        warnings=list(result.warnings or []),
    )
