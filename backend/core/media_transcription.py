from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.shared.llm.client import LLMClient, LLMConfigurationError, get_llm_client
from app.features.preprocessing.policy import ensure_mimo_v2_5_model, ensure_profile_allowed, ensure_text_preprocess_model


DEFAULT_MODEL_PROFILE = "mimo-v2-5"
DEFAULT_MAX_RAW_BYTES = 37_000_000
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEGMENT_SECONDS = 300
DEFAULT_FFMPEG_TIMEOUT_SECONDS = 900
TRANSCRIPTION_PROMPT_VERSION = "rules-media-transcription-v1"
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".wmv"}
DEFAULT_TERMINOLOGY = (
    "Project_R",
    "GBrain",
    "MiMo",
    "DeepSeek",
    "Ollama",
    "mxbai-embed-large",
    "BFI",
    "AURA",
    "SPECWISE",
    "SYNOVA",
    "Obsidian",
    "LlamaIndex",
    "Proma",
    "Agent",
    "Skill",
    "RAG",
    "VMU",
    "AS 1288",
    "AS 2047",
    "NAD",
    "Nicholas",
    "Gary",
    "项目组",
    "设计组",
    "业务数字化",
)

SYSTEM_PROMPT = """You are Project_R's meeting transcription agent.

Your job is to produce a faithful transcript for later knowledge extraction.
Do not summarize instead of transcribing. Preserve Chinese, English, names,
project codes, numbers, uncertainty, and speaker changes as far as the media
allows. If timestamps or speakers are uncertain, mark them explicitly.
"""


@dataclass(frozen=True)
class MediaTranscriptionOptions:
    model_profile: str = DEFAULT_MODEL_PROFILE
    max_raw_bytes: int = DEFAULT_MAX_RAW_BYTES
    temperature: float = DEFAULT_TEMPERATURE
    video_fps: float = 0.2
    video_media_resolution: str = "default"
    video_mode: str = "audio_first"
    audio_bitrate: str = "64k"
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS
    ffmpeg_timeout_seconds: int = DEFAULT_FFMPEG_TIMEOUT_SECONDS
    refinement_enabled: bool = True
    refinement_model_profile: str = "deepseek-flash"
    terminology: tuple[str, ...] = DEFAULT_TERMINOLOGY


@dataclass(frozen=True)
class MediaTranscriptionResult:
    transcript_text: str
    transcription_status: str = "auto_transcribed"
    extractor: str = "project_r_mimo_media_transcription_mvp"
    model_profile: str | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    segment_count: int = 1
    refinement_status: str | None = None
    refinement_model_profile: str | None = None
    refinement_provider: str | None = None
    refinement_model: str | None = None
    refinement_token_usage: dict[str, int] = field(default_factory=dict)
    terminology: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def load_media_transcription_options() -> MediaTranscriptionOptions:
    model_profile = os.getenv("GBRAIN_MEDIA_TRANSCRIPTION_MODEL_PROFILE", DEFAULT_MODEL_PROFILE).strip() or DEFAULT_MODEL_PROFILE
    refinement_model_profile = (
        os.getenv("GBRAIN_TRANSCRIPT_REFINEMENT_MODEL_PROFILE", "deepseek-flash").strip() or "deepseek-flash"
    )
    ensure_profile_allowed(model_profile, route_name="meeting-audio-video-transcription")
    ensure_profile_allowed(refinement_model_profile, route_name="meeting-audio-video-transcript-refinement")
    return MediaTranscriptionOptions(
        model_profile=model_profile,
        max_raw_bytes=_env_int("GBRAIN_MEDIA_TRANSCRIPTION_MAX_RAW_BYTES", DEFAULT_MAX_RAW_BYTES, 1_000_000, 200_000_000),
        temperature=_env_float("GBRAIN_MEDIA_TRANSCRIPTION_TEMPERATURE", DEFAULT_TEMPERATURE, 0.0, 1.0),
        video_fps=_env_float("GBRAIN_MEDIA_TRANSCRIPTION_VIDEO_FPS", 0.2, 0.1, 10.0),
        video_media_resolution=os.getenv("GBRAIN_MEDIA_TRANSCRIPTION_VIDEO_RESOLUTION", "default").strip() or "default",
        video_mode=os.getenv("GBRAIN_MEDIA_TRANSCRIPTION_VIDEO_MODE", "audio_first").strip().lower() or "audio_first",
        audio_bitrate=os.getenv("GBRAIN_MEDIA_TRANSCRIPTION_AUDIO_BITRATE", "64k").strip() or "64k",
        segment_seconds=_env_int("GBRAIN_MEDIA_TRANSCRIPTION_SEGMENT_SECONDS", DEFAULT_SEGMENT_SECONDS, 60, 7200),
        ffmpeg_timeout_seconds=_env_int(
            "GBRAIN_MEDIA_TRANSCRIPTION_FFMPEG_TIMEOUT_SECONDS",
            DEFAULT_FFMPEG_TIMEOUT_SECONDS,
            30,
            7200,
        ),
        refinement_enabled=_env_bool("GBRAIN_TRANSCRIPT_REFINEMENT_ENABLED", True),
        refinement_model_profile=refinement_model_profile,
        terminology=_load_terminology(),
    )


def transcribe_media_to_markdown(
    source_path: Path,
    *,
    options: MediaTranscriptionOptions | None = None,
    llm_client: LLMClient | None = None,
) -> MediaTranscriptionResult:
    options = options or load_media_transcription_options()
    client = llm_client or get_llm_client(options.model_profile)
    if not client.settings.configured:
        raise LLMConfigurationError(
            f"Media transcription model profile is not configured: {options.model_profile}"
        )
    ensure_mimo_v2_5_model(client.settings, route_name="meeting-audio-video-transcription")

    warnings: list[str] = []
    media_input_path = source_path
    if source_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS and options.video_mode == "audio_first":
        try:
            media_input_path = _extract_audio_sidecar_for_transcription(source_path, options)
            warnings.append(f"video audio track extracted for transcription: {media_input_path.name}")
        except Exception as exc:
            warnings.append(f"video audio extraction failed; raw video sent instead: {exc}")
            if source_path.stat().st_size > options.max_raw_bytes:
                raise ValueError(
                    "media file is too large for raw video base64 transcription and audio extraction failed; "
                    f"raw size={source_path.stat().st_size}, max={options.max_raw_bytes}"
                ) from exc

    transcript_parts: list[str] = []
    token_usage: dict[str, int] = {}
    segment_count = 1
    force_audio_segments = (
        source_path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
        and media_input_path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
        and options.video_mode == "audio_first"
    )
    if media_input_path.stat().st_size <= options.max_raw_bytes and not force_audio_segments:
        text, usage = _transcribe_single_media_input(client, media_input_path, options, source_path.name)
        transcript_parts.append(text)
        _add_usage(token_usage, usage)
    elif media_input_path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
        segment_paths = _split_audio_for_transcription(media_input_path, options)
        if not segment_paths:
            raise ValueError("media transcription segmentation produced no audio segments")
        segment_count = len(segment_paths)
        warnings.append(f"audio split into {segment_count} segment(s) for transcription")
        for index, segment_path in enumerate(segment_paths, start=1):
            if segment_path.stat().st_size > options.max_raw_bytes:
                raise ValueError(
                    f"audio segment is too large for base64 transcription: {segment_path.name} "
                    f"({segment_path.stat().st_size} bytes)"
                )
            text, usage = _transcribe_single_media_input(
                client,
                segment_path,
                options,
                source_path.name,
                segment_label=f"segment {index}/{segment_count}",
            )
            transcript_parts.append(f"## Segment {index}/{segment_count}\n\n{text.strip()}")
            _add_usage(token_usage, usage)
    else:
        raise ValueError(
            "media input is too large for base64 transcription; configure a public media URL workflow "
            f"or lower the file size below {options.max_raw_bytes} bytes"
        )

    transcript = _normalize_transcript_response("\n\n".join(transcript_parts), source_path.name)
    if not transcript.strip():
        raise ValueError("media transcription returned empty text")
    refinement_status: str | None = None
    refinement_model_profile: str | None = None
    refinement_provider: str | None = None
    refinement_model: str | None = None
    refinement_usage: dict[str, int] = {}
    if options.refinement_enabled:
        try:
            refined = _refine_transcript(transcript, source_path.name, options)
            transcript = refined["text"]
            refinement_status = "speaker_terms_refined"
            refinement_model_profile = refined["profile"]
            refinement_provider = refined["provider"]
            refinement_model = refined["model"]
            refinement_usage = refined["usage"]
        except Exception as exc:
            warnings.append(f"transcript speaker/terminology refinement skipped: {exc}")

    return MediaTranscriptionResult(
        transcript_text=transcript,
        model_profile=client.settings.profile or options.model_profile,
        provider=client.settings.provider,
        model=client.settings.model,
        token_usage=token_usage,
        segment_count=segment_count,
        refinement_status=refinement_status,
        refinement_model_profile=refinement_model_profile,
        refinement_provider=refinement_provider,
        refinement_model=refinement_model,
        refinement_token_usage=refinement_usage,
        terminology=options.terminology,
        warnings=tuple(warnings),
    )


def _transcribe_single_media_input(
    client: LLMClient,
    media_input_path: Path,
    options: MediaTranscriptionOptions,
    source_name: str,
    *,
    segment_label: str | None = None,
) -> tuple[str, dict[str, int]]:
    content_blocks = _build_media_content_blocks(media_input_path, options)
    content_blocks.append({"type": "text", "text": _transcription_prompt(source_name, segment_label=segment_label)})
    response = client.complete(
        [{"role": "user", "content": content_blocks}],
        system_prompt=SYSTEM_PROMPT,
        temperature=options.temperature,
    )
    return response.text.strip(), response.usage


def _build_media_content_blocks(source_path: Path, options: MediaTranscriptionOptions) -> list[dict[str, Any]]:
    suffix = source_path.suffix.lower()
    data_uri = _data_uri(source_path)
    if suffix in SUPPORTED_AUDIO_EXTENSIONS:
        return [{"type": "input_audio", "input_audio": {"data": data_uri}}]
    if suffix in SUPPORTED_VIDEO_EXTENSIONS:
        return [
            {
                "type": "video_url",
                "video_url": {"url": data_uri},
                "fps": options.video_fps,
                "media_resolution": options.video_media_resolution,
            }
        ]
    raise ValueError(f"unsupported media transcription format: {source_path.suffix}")


def _extract_audio_sidecar_for_transcription(source_path: Path, options: MediaTranscriptionOptions) -> Path:
    ffmpeg = _resolve_ffmpeg()
    target_dir = Path(tempfile.gettempdir()) / "project_r_media_transcription"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{source_path.stem}-{source_path.stat().st_mtime_ns}.mp3"
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        options.audio_bitrate,
        str(target_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=options.ffmpeg_timeout_seconds,
    )
    if completed.returncode != 0 or not target_path.exists() or target_path.stat().st_size == 0:
        detail = (completed.stderr or completed.stdout or "ffmpeg audio extraction failed").strip()
        raise RuntimeError(detail[-600:])
    if target_path.stat().st_size > options.max_raw_bytes:
        raise ValueError(f"extracted audio is too large for base64 transcription: {target_path.stat().st_size} bytes")
    return target_path


def _split_audio_for_transcription(source_path: Path, options: MediaTranscriptionOptions) -> list[Path]:
    ffmpeg = _resolve_ffmpeg()
    target_dir = Path(tempfile.gettempdir()) / "project_r_media_transcription" / f"{source_path.stem}-segments-{source_path.stat().st_mtime_ns}"
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(path for path in target_dir.glob("segment-*.mp3") if path.stat().st_size > 0)
    if existing:
        return existing
    output_pattern = target_dir / "segment-%03d.mp3"
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        options.audio_bitrate,
        "-f",
        "segment",
        "-segment_time",
        str(options.segment_seconds),
        "-reset_timestamps",
        "1",
        str(output_pattern),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=options.ffmpeg_timeout_seconds,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "ffmpeg audio segmentation failed").strip()
        raise RuntimeError(detail[-600:])
    return sorted(path for path in target_dir.glob("segment-*.mp3") if path.stat().st_size > 0)


def _resolve_ffmpeg() -> str:
    configured = os.getenv("PROJECT_R_FFMPEG_BIN", "").strip()
    if configured:
        return configured
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return "ffmpeg"


def _data_uri(source_path: Path) -> str:
    media_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _transcription_prompt(file_name: str, *, segment_label: str | None = None) -> str:
    segment_text = f"\n当前分段：{segment_label}\n" if segment_label else ""
    return f"""请把这个会议音视频转写为 Markdown，供后续 Project_R 知识提炼使用。

文件名：{file_name}
{segment_text}

要求：
- 优先输出逐段转写，不要只总结。
- 如能识别时间，请使用 `[HH:MM:SS] Speaker: text` 格式。
- 说话人无法识别时可写 `Speaker 1`、`Speaker 2` 或 `Unknown`。
- 保留中文、英文、项目名、人名、客户名、型号、金额、日期、行动项和风险。
- 听不清的地方标记 `[听不清]` 或 `[unclear]`，不要编造。
- 如果视频画面包含白板、PPT、图纸或屏幕共享，请在末尾增加 `## Visual Notes`，列出能可靠识别的画面信息。
- 只输出 transcript Markdown，不要输出 YAML frontmatter。
"""


def _normalize_transcript_response(value: str, file_name: str) -> str:
    text = value.strip().strip("`").strip()
    if text.lower().startswith("markdown"):
        text = text[len("markdown") :].strip()
    if not text.startswith("#"):
        text = f"# {Path(file_name).stem} Transcript\n\n{text}"
    return text.rstrip() + "\n"


def _refine_transcript(transcript: str, file_name: str, options: MediaTranscriptionOptions) -> dict[str, Any]:
    client = get_llm_client(options.refinement_model_profile)
    if not client.settings.configured:
        raise LLMConfigurationError(
            f"Transcript refinement model profile is not configured: {options.refinement_model_profile}"
        )
    ensure_text_preprocess_model(client.settings, route_name="meeting-audio-video-transcript-refinement")
    glossary = "\n".join(f"- {term}" for term in options.terminology)
    prompt = f"""请对下面的会议转写做“说话人标签统一 + 术语纠错”，不要总结，不要新增事实。

文件名：{file_name}

术语表：
{glossary}

处理规则：
- 保留所有原始时间戳和原文含义。
- 将同一个人/同一类说话人尽量统一为 `Speaker 1`、`Speaker 2`，如果原文明确出现姓名，可写 `Speaker 1 (Gary)`。
- 不确定说话人时保留 `Unknown`，不要编造姓名。
- 只在上下文强支持时纠正常见同音/ASR 错词，例如 GBrain、MiMo、DeepSeek、Obsidian、LlamaIndex、Project_R、RAG、Agent、Skill、NAD、Nicholas。
- 听不清处保留 `[听不清]`、`[unclear]` 或 `[疑似：...]`。
- 输出 Markdown，必须包含：
  1. `## Speaker Map / 说话人映射`
  2. `## Corrected Transcript / 术语纠错后转写`
  3. `## Terminology Correction Log / 术语纠错记录`

原始转写：
<transcript>
{transcript[:60000]}
</transcript>
"""
    response = client.complete(
        [{"role": "user", "content": prompt}],
        system_prompt="You refine meeting transcripts without adding facts.",
        temperature=0.0,
    )
    text = _normalize_transcript_response(response.text, file_name)
    return {
        "text": text,
        "profile": client.settings.profile or options.refinement_model_profile,
        "provider": client.settings.provider,
        "model": response.model or client.settings.model,
        "usage": response.usage,
    }


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        total[key] = int(total.get(key, 0)) + int(value or 0)


def _load_terminology() -> tuple[str, ...]:
    raw = os.getenv("GBRAIN_TRANSCRIPT_TERMINOLOGY", "")
    if not raw.strip():
        return DEFAULT_TERMINOLOGY
    terms: list[str] = []
    for item in raw.replace("\n", ",").split(","):
        term = item.strip()
        if term and term not in terms:
            terms.append(term)
    return tuple(terms) or DEFAULT_TERMINOLOGY


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}
