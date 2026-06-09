from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


MIN_REPEAT_LENGTH = 15
POOR_REPEAT_RATIO = 0.3
UNUSABLE_REPEAT_RATIO = 0.6


@dataclass
class TranscriptionQualityResult:
    asr_quality: str  # "good" | "fair" | "poor" | "unusable"
    repeated_ratio: float
    has_repeated_text: bool
    repeated_segments: list[str] = field(default_factory=list)
    total_chars: int = 0
    repeated_chars: int = 0


def detect_repeated_text(
    transcript_text: str,
    *,
    min_repeat_length: int = MIN_REPEAT_LENGTH,
) -> TranscriptionQualityResult:
    """Detect repeated phrases in ASR transcript text.

    Uses a multi-strategy approach:
    1. Check if the entire text is mostly the same segment repeated
    2. Check for repeated sentences/lines
    3. Check for overlapping n-gram repetition
    """
    if not transcript_text or not transcript_text.strip():
        return TranscriptionQualityResult(
            asr_quality="unusable",
            repeated_ratio=0.0,
            has_repeated_text=False,
            total_chars=0,
            repeated_chars=0,
        )

    text = transcript_text.strip()
    total_chars = len(text)
    repeated_chars = 0
    repeated_segments: list[str] = []

    def add_segment(seg: str) -> None:
        if seg not in repeated_segments:
            repeated_segments.append(seg[:80] + "..." if len(seg) > 80 else seg)

    # Strategy 1: Split on sentence boundaries and check for repeats
    segments = re.split(r"[。！？\n.!?;；]+", text)
    seg_counts: dict[str, int] = {}
    for seg in segments:
        seg = seg.strip()
        if len(seg) >= min_repeat_length:
            seg_counts[seg] = seg_counts.get(seg, 0) + 1

    for seg, count in seg_counts.items():
        if count >= 2:
            extra = len(seg) * (count - 1)
            if extra > 0:
                repeated_chars += extra
                add_segment(seg)

    # Strategy 2: If no punctuation splits, check for repeated substrings
    if len(segments) <= 2 or all(len(s.strip()) < min_repeat_length for s in segments):
        # Split on common ASR line breaks
        lines = text.splitlines()
        if len(lines) >= 3:
            line_counts: dict[str, int] = {}
            for line in lines:
                line = line.strip()
                if len(line) >= min_repeat_length:
                    line_counts[line] = line_counts.get(line, 0) + 1
            for line, count in line_counts.items():
                if count >= 2:
                    extra = len(line) * (count - 1)
                    repeated_chars += extra
                    add_segment(line)
        # Fallback: check if any significant portion of text is repeated
        if repeated_chars == 0 and total_chars > min_repeat_length * 4:
            quarter = total_chars // 4
            if quarter >= min_repeat_length:
                first_q = text[:quarter]
                rest = text[quarter:]
                extra_occurrences = rest.count(first_q)
                if extra_occurrences >= 1:
                    repeated_chars += len(first_q) * extra_occurrences
                    add_segment(first_q)

    repeated_ratio = repeated_chars / max(total_chars, 1)

    if repeated_ratio >= UNUSABLE_REPEAT_RATIO:
        asr_quality = "unusable"
    elif repeated_ratio >= POOR_REPEAT_RATIO:
        asr_quality = "poor"
    elif repeated_ratio >= 0.1:
        asr_quality = "fair"
    else:
        asr_quality = "good"

    return TranscriptionQualityResult(
        asr_quality=asr_quality,
        repeated_ratio=round(repeated_ratio, 4),
        has_repeated_text=bool(repeated_segments),
        repeated_segments=list(set(repeated_segments))[:10],
        total_chars=total_chars,
        repeated_chars=repeated_chars,
    )


def classify_transcript_quality(transcript_text: str) -> TranscriptionQualityResult:
    """Convenience wrapper for detect_repeated_text with defaults."""
    return detect_repeated_text(transcript_text)


def quality_to_manifest_metadata(quality: TranscriptionQualityResult) -> dict[str, Any]:
    """Convert quality result to manifest metadata dict."""
    return {
        "asr_quality": quality.asr_quality,
        "repeated_ratio": quality.repeated_ratio,
        "has_repeated_text": quality.has_repeated_text,
        "total_chars": quality.total_chars,
        "repeated_chars": quality.repeated_chars,
    }


def get_quality_penalty_factor(asr_quality: str) -> float:
    """Get ranking penalty factor for a given ASR quality level."""
    penalties = {
        "good": 1.0,
        "fair": 0.8,
        "poor": 0.5,
        "unusable": 0.2,
    }
    return penalties.get(asr_quality, 1.0)
