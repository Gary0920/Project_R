from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.features.knowledge.project_query.intent import ProjectQueryIntent


SLUG_TO_KIND_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"floor.plan|平面图|窗表", re.IGNORECASE), "pdf_drawing"),
    (re.compile(r"window.schedule|[-_.\s]ws|ws$|[Ww][Ss]\b", re.IGNORECASE), "pdf_drawing"),
    (re.compile(r"facade.supply.programme|排期|programme", re.IGNORECASE), "pdf_schedule"),
    (re.compile(r"内部联系单|补货|变更|签证", re.IGNORECASE), "image_contact_sheet"),
    (re.compile(r"支付截图|payment.screenshot|账单", re.IGNORECASE), "image_payment"),
    (re.compile(r"会议|meeting|audio|transcript|video", re.IGNORECASE), "meeting"),
    (re.compile(r"\.eml|email|skylight|glass", re.IGNORECASE), "email"),
    (re.compile(r"材料清单|ml[^a-z]|bom", re.IGNORECASE), "spreadsheet"),
    (re.compile(r"注意事项|notice|rooster", re.IGNORECASE), "office_doc"),
]

CATEGORY_DIR_TO_KIND: dict[str, str] = {
    "technical": "pdf_drawing",
    "meetings": "meeting",
    "changes": "image_contact_sheet",
    "unfiled": "image",
    "production": "office_doc",
    "contracts": "office_contract",
}

MEETING_FILE_KINDS = {"meeting", "meeting_transcript_docx", "meeting_media"}


@dataclass
class RankedSource:
    """A single source with adjusted ranking score."""

    source_index: int
    original_score: float
    adjusted_score: float
    source_file: str
    inferred_file_kind: str | None
    boost_reason: str | None = None


def infer_file_kind_from_slug(slug: str) -> str | None:
    """Infer the file_kind of a source from its slug / filename.

    Uses keyword matching on the slug text.
    """
    for pattern, kind in SLUG_TO_KIND_RULES:
        if pattern.search(slug):
            return kind
    return None


def infer_file_kind_from_source(source: dict) -> str | None:
    """Infer file_kind from a think response source dict.

    Checks multiple fields in order of reliability:
        1. file_kind (if present)
        2. tags
        3. file/slug keyword matching
        4. section_path
    """
    # Direct field (most reliable)
    for key in ("file_kind", "source_file_kind", "kind"):
        value = source.get(key)
        if isinstance(value, str) and value:
            return value

    # Tags
    tags = source.get("tags") or ""
    if isinstance(tags, str):
        for tag, kind in [
            ("pdf_drawing", "pdf_drawing"),
            ("pdf_schedule", "pdf_schedule"),
            ("meeting", "meeting"),
            ("email", "email"),
            ("spreadsheet", "spreadsheet"),
            ("image", "image"),
        ]:
            if tag in tags:
                return kind

    # File path / slug
    file_path = str(source.get("file") or source.get("source_file") or "")
    slug = file_path.split("/")[-1] if "/" in file_path else file_path
    inferred = infer_file_kind_from_slug(slug)
    if inferred:
        return inferred

    # Section path
    section = str(source.get("section_path") or "")
    for dir_name, kind in CATEGORY_DIR_TO_KIND.items():
        if dir_name in section.lower():
            return kind

    return None


def adjust_project_ranking(
    sources: list[dict],
    intent: ProjectQueryIntent,
) -> list[RankedSource]:
    """Adjust source ranking based on query intent.

    Strategy:
        - Boost sources matching the intent's file_kind_hint (factor=1.5)
        - Penalize meeting sources for non-meeting queries (factor=0.6)
        - Penalize low-confidence sources
        - Return RankedSource objects with original and adjusted scores

    Args:
        sources: List of source dicts from GBrain think/search response.
            Expected to contain 'file', 'score' (0-1), and optional 'file_kind' / 'tags'.
        intent: The classified query intent.

    Returns:
        List of RankedSource, sorted by adjusted_score descending.
    """
    if not sources:
        return []

    ranked: list[RankedSource] = []
    file_kind_hint = intent.file_kind_hint
    is_meeting_query = file_kind_hint in MEETING_FILE_KINDS if file_kind_hint else False
    confidence = intent.confidence

    for index, source in enumerate(sources):
        original_score = float(source.get("score") or 1.0 - (index * 0.01))
        inferred_kind = infer_file_kind_from_source(source)
        boost_reason = None
        adjusted = original_score

        # 1. Exact file_kind match boost
        if file_kind_hint and inferred_kind:
            if _kinds_match(file_kind_hint, inferred_kind):
                if confidence == "high":
                    adjusted *= 1.5
                    boost_reason = f"matched file_kind={inferred_kind} (boost 1.5x)"
                elif confidence == "medium":
                    adjusted *= 1.3
                    boost_reason = f"matched file_kind={inferred_kind} (boost 1.3x)"

        # 2. Meeting penalty for non-meeting queries
        if not is_meeting_query and inferred_kind in MEETING_FILE_KINDS:
            # Check for ASR quality penalty
            asr_quality = str(source.get("asr_quality", "") or "").lower()
            if asr_quality in ("poor", "unusable"):
                quality_factor = 0.3 if asr_quality == "unusable" else 0.5
                adjusted *= quality_factor
                boost_reason = (boost_reason or "") + f" | {asr_quality} quality penalty ({quality_factor}x)"
            else:
                adjusted *= 0.6
                boost_reason = (boost_reason or "") + " | meeting penalty (0.6x)"

        # 3. Low confidence baseline — slight penalty
        if confidence == "low":
            adjusted *= 0.9

        ranked.append(RankedSource(
            source_index=index,
            original_score=original_score,
            adjusted_score=adjusted,
            source_file=str(source.get("file") or source.get("source_file") or ""),
            inferred_file_kind=inferred_kind,
            boost_reason=boost_reason,
        ))

    # Sort by adjusted_score descending
    ranked.sort(key=lambda r: r.adjusted_score, reverse=True)
    return ranked


def _kinds_match(hint: str, actual: str) -> bool:
    """Check if two file_kind values match semantically."""
    if hint == actual:
        return True
    # pdf_drawing / pdf_schedule both start with pdf_
    if hint.startswith("pdf_") and actual.startswith("pdf_"):
        return True
    if hint.startswith("image_") and actual.startswith("image_"):
        return True
    if hint.startswith("meeting") and actual.startswith("meeting"):
        return True
    # Broader: pdf_drawing matches pdf category
    if hint == "pdf_drawing" and actual in ("pdf", "pdf_schedule"):
        return True
    if actual == "pdf_drawing" and hint in ("pdf", "pdf_schedule"):
        return True
    return False


def apply_ranking_to_sources(
    sources: list[dict],
    ranked: list[RankedSource],
) -> list[dict]:
    """Apply the adjusted ranking back to the source dicts, sorted by adjusted score.

    Modifies source dicts in-place to add ranking metadata.
    """
    # Build a mapping: source_index → RankedSource
    rank_by_index = {r.source_index: r for r in ranked}
    result: list[dict] = []
    for rank in ranked:
        if rank.source_index < len(sources):
            source = dict(sources[rank.source_index])
            source["adjusted_score"] = rank.adjusted_score
            source["original_score"] = rank.original_score
            source["file_kind"] = rank.inferred_file_kind or source.get("file_kind")
            source["boost_reason"] = rank.boost_reason
            result.append(source)
    return result
