from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LANGUAGE_POLICY = "bilingual_zh_en_aligned"
EXTRACTION_STATUS = "meeting_transcript_structured_pending_review"
EXTRACTOR_NAME = "project_r_meeting_transcript_mvp"
SKILL_NAME = "meeting-audio-video-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-meeting-audio-video-v1"

TRANSCRIPT_SIDECAR_SUFFIXES = (
    ".transcript.md",
    ".transcript.txt",
    ".transcript.vtt",
    ".transcript.srt",
    ".transcript.json",
    ".auto.transcript.md",
    ".auto.transcript.txt",
    ".zh-CN.transcript.md",
    ".zh-CN.transcript.txt",
    ".zh.transcript.md",
    ".zh.transcript.txt",
    ".en.transcript.md",
    ".en.transcript.txt",
    ".vtt",
    ".srt",
)


@dataclass(frozen=True)
class MeetingStructuredExtractionResult:
    markdown: str
    extraction_status: str = EXTRACTION_STATUS
    review_status: str = "pending_review"
    extractor: str = EXTRACTOR_NAME
    language_policy: str = LANGUAGE_POLICY
    transcript_file: str | None = None
    transcription_status: str = "transcript_sidecar_provided"
    segment_count: int = 0
    action_item_count: int = 0
    decision_count: int = 0
    risk_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def find_transcript_sidecar(media_path: Path) -> Path | None:
    candidates = _transcript_sidecar_candidates(media_path)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def find_transcript_sidecars_for_media_files(root: Path, media_extensions: set[str]) -> set[Path]:
    sidecars: set[Path] = set()
    for media_path in root.rglob("*"):
        if media_path.is_file() and media_path.suffix.lower() in media_extensions:
            sidecar = find_transcript_sidecar(media_path)
            if sidecar is not None:
                sidecars.add(sidecar.resolve())
    return sidecars


def extract_meeting_structured_markdown(
    *,
    title: str,
    transcript_path: Path,
    source_media_path: Path | None = None,
    source_label: str | None = None,
) -> MeetingStructuredExtractionResult:
    raw_text = _read_transcript(transcript_path)
    cleaned_text = _normalize_transcript_text(raw_text)
    segments = _extract_segments(cleaned_text)
    action_items = _select_candidates(cleaned_text, ACTION_KEYWORDS, limit=8)
    decisions = _select_candidates(cleaned_text, DECISION_KEYWORDS, limit=8)
    risks = _select_candidates(cleaned_text, RISK_KEYWORDS, limit=8)
    warnings: list[str] = []
    if not cleaned_text:
        warnings.append("transcript sidecar is empty")
    if not segments:
        warnings.append("no timestamped transcript segments detected")

    markdown = _build_meeting_markdown(
        title=title,
        transcript_text=cleaned_text,
        source_media_path=source_media_path,
        transcript_path=transcript_path,
        source_label=source_label,
        segments=segments,
        action_items=action_items,
        decisions=decisions,
        risks=risks,
        warnings=warnings,
    )
    return MeetingStructuredExtractionResult(
        markdown=markdown,
        transcript_file=transcript_path.name,
        segment_count=len(segments),
        action_item_count=len(action_items),
        decision_count=len(decisions),
        risk_count=len(risks),
        warnings=tuple(warnings),
    )


def _transcript_sidecar_candidates(media_path: Path) -> list[Path]:
    candidates = [media_path.with_name(media_path.stem + suffix) for suffix in TRANSCRIPT_SIDECAR_SUFFIXES]
    transcript_dir = media_path.with_suffix("")
    candidates.extend(
        [
            transcript_dir / "transcript.md",
            transcript_dir / "transcript.txt",
            transcript_dir / "transcript.vtt",
            transcript_dir / "transcript.srt",
        ]
    )
    return candidates


def _read_transcript(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return _read_json_transcript(path)
    return path.read_text(encoding="utf-8-sig", errors="ignore")


def _read_json_transcript(path: Path) -> str:
    import json

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        if isinstance(data.get("text"), str):
            return data["text"]
        segments = data.get("segments")
        if isinstance(segments, list):
            lines: list[str] = []
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                start = _format_seconds(segment.get("start"))
                speaker = str(segment.get("speaker") or "").strip()
                prefix = f"[{start}] " if start else ""
                if speaker:
                    prefix += f"{speaker}: "
                lines.append(prefix + text)
            return "\n".join(lines)
    if isinstance(data, list):
        return "\n".join(str(item) for item in data)
    return ""


def _normalize_transcript_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit():
            continue
        lines.append(line)
    return "\n".join(lines).strip()


TIMESTAMP_PATTERN = re.compile(
    r"(?P<timestamp>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[\.,]\d{1,3})?)(?:\s*-->\s*(?P<end>(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[\.,]\d{1,3})?))?"
)


def _extract_segments(text: str) -> list[str]:
    segments: list[str] = []
    pending_timestamp = ""
    for line in text.splitlines():
        match = TIMESTAMP_PATTERN.search(line)
        if match and "-->" in line:
            pending_timestamp = match.group("timestamp")
            continue
        if match:
            segments.append(line)
            continue
        if pending_timestamp:
            segments.append(f"[{pending_timestamp}] {line}")
            pending_timestamp = ""
    return segments[:40]


ACTION_KEYWORDS = (
    "行动项",
    "action",
    "todo",
    "to-do",
    "负责",
    "owner",
    "请",
    "需要",
    "跟进",
    "follow up",
    "deadline",
    "完成",
)
DECISION_KEYWORDS = (
    "决定",
    "确认",
    "同意",
    "approved",
    "decided",
    "confirmed",
    "agree",
    "agreed",
)
RISK_KEYWORDS = (
    "风险",
    "问题",
    "阻塞",
    "不确定",
    "待确认",
    "issue",
    "risk",
    "blocked",
    "concern",
    "unclear",
)


def _select_candidates(text: str, keywords: tuple[str, ...], *, limit: int) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for line in text.splitlines():
        compact = " ".join(line.split())
        if not compact:
            continue
        lowered = compact.lower()
        if any(keyword in lowered for keyword in lowered_keywords):
            key = re.sub(r"\W+", "", lowered)
            if key and key not in seen:
                seen.add(key)
                results.append(compact)
        if len(results) >= limit:
            break
    return results


def _build_meeting_markdown(
    *,
    title: str,
    transcript_text: str,
    source_media_path: Path | None,
    transcript_path: Path,
    source_label: str | None,
    segments: list[str],
    action_items: list[str],
    decisions: list[str],
    risks: list[str],
    warnings: list[str],
) -> str:
    source_name = source_label or (source_media_path.name if source_media_path else transcript_path.name)
    transcript_excerpt = "\n".join(f"> {line}" for line in transcript_text.splitlines()[:80]) or "> [empty transcript]"
    segment_excerpt = segments[:20] or transcript_text.splitlines()[:20]
    return (
        f"# {title}\n\n"
        "## 审核状态 / Review Status\n\n"
        "- 中文：本页由 Project_R 会议转写提炼 MVP 生成，必须经管理员审核后才能进入正式查询面。\n"
        "  English: This page was generated by the Project_R meeting transcript extraction MVP and must be reviewed by an administrator before entering the searchable knowledge surface.\n\n"
        "## 原始资料 / Source Material\n\n"
        f"- 中文：原始音视频或会议资料：`{source_name}`。\n"
        f"  English: Original audio/video or meeting source: `{source_name}`.\n"
        f"- 中文：转写侧车文件：`{transcript_path.name}`。\n"
        f"  English: Transcript sidecar file: `{transcript_path.name}`.\n\n"
        "## 会议主题 / Meeting Topic\n\n"
        f"- 中文：待审核主题候选：{title}。\n"
        f"  English: Topic candidate pending review: {title}.\n\n"
        "## 关键决策 / Key Decisions\n\n"
        f"{_bilingual_candidate_lines(decisions, empty_zh='未从转写中稳定识别决策，请人工审核。', empty_en='No stable decision candidate was detected from the transcript; human review is required.')}\n\n"
        "## 行动项 / Action Items\n\n"
        f"{_bilingual_candidate_lines(action_items, checkbox=True, empty_zh='未从转写中稳定识别行动项，请人工审核。', empty_en='No stable action item candidate was detected from the transcript; human review is required.')}\n\n"
        "## 风险与待确认 / Risks and Open Questions\n\n"
        f"{_bilingual_candidate_lines(risks, empty_zh='未从转写中稳定识别风险或待确认事项，请人工审核。', empty_en='No stable risk or open-question candidate was detected from the transcript; human review is required.')}\n\n"
        "## 可沉淀公司知识候选 / Company Knowledge Candidates\n\n"
        "- 中文：需要管理员判断本次会议是否包含可沉淀为公司规则、流程、模板或项目经验的内容。\n"
        "  English: An administrator must decide whether this meeting contains content that should become company rules, processes, templates, or project lessons.\n\n"
        "## 时间戳转写摘录 / Timestamped Transcript Excerpt\n\n"
        f"{_bilingual_segment_lines(segment_excerpt)}\n\n"
        "## 原始转写 / Verbatim Transcript\n\n"
        f"{transcript_excerpt}\n\n"
        "## 提炼警告 / Extraction Warnings\n\n"
        f"{_warning_lines(warnings)}\n"
    )


def _bilingual_candidate_lines(
    values: list[str],
    *,
    checkbox: bool = False,
    empty_zh: str,
    empty_en: str,
) -> str:
    if not values:
        return f"- 中文：{empty_zh}\n  English: {empty_en}"
    prefix = "- [ ]" if checkbox else "-"
    return "\n".join(
        f"{prefix} 中文：原文候选：{value}\n  English: Original transcript candidate: {value}"
        for value in values
    )


def _bilingual_segment_lines(values: list[str]) -> str:
    if not values:
        return "- 中文：未检测到带时间戳的转写片段。\n  English: No timestamped transcript segment was detected."
    return "\n".join(
        f"- 中文：转写片段：{value}\n  English: Transcript segment: {value}"
        for value in values[:20]
    )


def _warning_lines(values: list[str]) -> str:
    if not values:
        return "- 中文：无自动检测警告。\n  English: No automatic extraction warning was detected."
    return "\n".join(
        f"- 中文：{value}\n  English: {value}"
        for value in values
    )


def _format_seconds(value: Any) -> str:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return ""
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"
