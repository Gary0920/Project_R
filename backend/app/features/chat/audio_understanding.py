from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.features.preprocessing.tools.media_transcription import (
    MediaTranscriptionToolInput,
    run_media_transcription_tool,
)
from models.attachment import SessionAttachment


MAX_AUDIO_UNDERSTANDING_CHARS = 12000


@dataclass(frozen=True)
class AudioUnderstandingResult:
    context: str
    transcript_count: int
    warnings: list[str] = field(default_factory=list)


def transcribe_audio_attachments_for_chat(
    attachments: list[SessionAttachment],
    *,
    model_profile: str | None = None,
    max_chars: int = MAX_AUDIO_UNDERSTANDING_CHARS,
) -> AudioUnderstandingResult:
    chunks: list[str] = []
    warnings: list[str] = []
    used = 0
    for attachment in attachments:
        path = Path(attachment.stored_path)
        if not path.exists():
            warnings.append(f"音频附件不存在：{attachment.original_name}")
            continue
        try:
            result = run_media_transcription_tool(MediaTranscriptionToolInput(media_path=path, model_profile=model_profile))
        except Exception as exc:
            warnings.append(f"{attachment.original_name} 转写失败：{exc}")
            continue
        text = result.text.strip()
        if not text:
            warnings.append(f"{attachment.original_name} 转写为空")
            continue
        header = f"[音频理解] {attachment.original_name}"
        block = f"{header}\n{text}"
        remaining = max_chars - used
        if remaining <= 0:
            warnings.append("音频转写上下文已达到长度上限，后续音频未注入。")
            break
        excerpt = block[:remaining]
        chunks.append(excerpt)
        used += len(excerpt)
        warnings.extend(result.warnings or [])
    return AudioUnderstandingResult(
        context="\n\n".join(chunks),
        transcript_count=len(chunks),
        warnings=warnings,
    )
