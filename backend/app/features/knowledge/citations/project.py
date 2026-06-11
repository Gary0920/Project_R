from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SourceReference:
    """Unified citation contract for project knowledge source evidence."""

    source_file: str
    """Original source file path (relative to workspace root)."""
    file_kind: str | None = None
    """pdf_drawing | pdf_schedule | image | meeting | email | spreadsheet | ..."""
    reference_type: str = "text_span"
    """page | region | sheet_row | timestamp | text_span"""
    page: int | None = None
    """PDF page number (1-indexed)."""
    region: str | None = None
    """Image region description, e.g. '金额区域（右下角账单详情）'."""
    sheet: str | None = None
    """Spreadsheet sheet name."""
    row: int | None = None
    """Spreadsheet row number (1-indexed)."""
    timestamp: str | None = None
    """Meeting/Media timestamp in 'HH:MM:SS' format."""
    text_span: str | None = None
    """Excerpt of source text for inline evidence."""
    citation_text: str | None = None
    """Full citation text rendered for display."""


def normalize_citation(
    source_file: str,
    *,
    file_kind: str | None = None,
    page: int | None = None,
    region: str | None = None,
    sheet: str | None = None,
    row: int | None = None,
    timestamp: str | None = None,
    text_span: str | None = None,
) -> SourceReference:
    """Create a normalized SourceReference with auto-detected reference_type."""
    if page is not None:
        reference_type = "page"
    elif region:
        reference_type = "region"
    elif sheet and row:
        reference_type = "sheet_row"
    elif timestamp:
        reference_type = "timestamp"
    elif text_span:
        reference_type = "text_span"
    else:
        reference_type = "text_span"

    return SourceReference(
        source_file=source_file,
        file_kind=file_kind,
        reference_type=reference_type,
        page=page,
        region=region,
        sheet=sheet,
        row=row,
        timestamp=timestamp,
        text_span=text_span,
    )


def format_citation(ref: SourceReference) -> str:
    """Format a SourceReference as a human-readable citation string."""
    parts = [ref.source_file]
    if ref.page:
        parts.append(f"p.{ref.page}")
    if ref.region:
        parts.append(ref.region)
    if ref.sheet:
        parts.append(f"sheet={ref.sheet}")
        if ref.row:
            parts.append(f"row={ref.row}")
    if ref.timestamp:
        parts.append(f"@{ref.timestamp}")
    return " / ".join(parts)


def source_reference_to_dict(ref: SourceReference) -> dict[str, Any]:
    """Serialize a SourceReference to a dict for JSON responses."""
    return asdict(ref)


def guess_file_kind_from_source(source_file: str) -> str | None:
    """Guess file_kind from source filename extension and keywords."""
    lower = source_file.lower()
    if any(ext in lower for ext in (".pdf",)):
        if any(kw in lower for kw in ("floor plan", "drawing", "elevation", "平面图", "图纸")):
            return "pdf_drawing"
        if any(kw in lower for kw in ("schedule", "programme", "排期", "ws]")):
            return "pdf_schedule"
        return "pdf"
    if any(ext in lower for ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp")):
        if any(kw in lower for kw in ("支付", "pay", "付款")):
            return "image_payment"
        if any(kw in lower for kw in ("内部联系单", "联系单", "签证")):
            return "image_contact_sheet"
        return "image"
    if ".eml" in lower:
        return "email"
    if any(ext in lower for ext in (".xls", ".xlsx", ".csv")):
        return "spreadsheet"
    if ".docx" in lower:
        return "office_doc"
    if any(ext in lower for ext in (".mp4", ".mp3", ".wav", ".m4a")):
        return "meeting_media"
    return None
