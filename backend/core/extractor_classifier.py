from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from core.pdf_structured_extraction import _pdf_image_sidecar_candidates


TEXT_EXTENSIONS = {".txt"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
DOCX_EXTENSIONS = {".docx"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
EMAIL_EXTENSIONS = {".eml", ".msg", ".mbox"}
SPREADSHEET_EXTENSIONS = {".csv", ".tsv", ".xls", ".xlsx", ".xlsm"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


@dataclass(frozen=True)
class ExtractorClassification:
    source_scope: str
    file_kind: str
    extraction_complexity: str
    extractor_profile: str
    classifier_reason: str
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_manifest_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source_scope": self.source_scope,
            "file_kind": self.file_kind,
            "extraction_complexity": self.extraction_complexity,
            "extractor_profile": self.extractor_profile,
            "classifier_reason": self.classifier_reason,
        }
        if self.diagnostics:
            metadata["classifier_diagnostics"] = self.diagnostics
        return metadata


def classify_source_file(source_path: Path, *, source_scope: str = "project") -> ExtractorClassification:
    suffix = source_path.suffix.lower()
    if suffix in MARKDOWN_EXTENSIONS:
        return ExtractorClassification(source_scope, "markdown", "simple_text", "deepseek_text", "Markdown source is readable text")
    if suffix in TEXT_EXTENSIONS:
        return ExtractorClassification(source_scope, "text", "simple_text", "deepseek_text", "Text source is readable text")
    if suffix in DOCX_EXTENSIONS:
        return ExtractorClassification(source_scope, "docx", "simple_text", "deepseek_text", "DOCX text/table extraction is supported")
    if suffix in PDF_EXTENSIONS:
        return _classify_pdf(source_path, source_scope=source_scope)
    if suffix in IMAGE_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "image",
            "vision_required",
            "mimo_vision",
            "Images and screenshots require OCR or visual understanding",
        )
    if suffix in AUDIO_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "audio",
            "transcription_required",
            "transcription",
            "Audio requires transcription before knowledge extraction",
        )
    if suffix in VIDEO_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "video",
            "transcription_required",
            "transcription",
            "Video requires transcription and may require future key-frame visual extraction",
        )
    if suffix in EMAIL_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "email",
            "email_thread_required",
            "deepseek_text",
            "Email files require thread parsing before extraction",
        )
    if suffix in SPREADSHEET_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "spreadsheet",
            "pending_capability",
            "pending_extractor_capability",
            "Spreadsheet preprocessing is not enabled in B1; keep pending until spreadsheet-preprocess is implemented",
        )
    if suffix in ARCHIVE_EXTENSIONS:
        return ExtractorClassification(
            source_scope,
            "archive",
            "unsupported",
            "pending_extractor_capability",
            "Archives require an unpacking and recursive classification workflow",
        )
    return ExtractorClassification(
        source_scope,
        "unknown",
        "unsupported",
        "pending_extractor_capability",
        f"Unsupported file extension: {source_path.suffix or '<none>'}",
    )


def _classify_pdf(source_path: Path, *, source_scope: str) -> ExtractorClassification:
    diagnostics = _diagnose_pdf(source_path)
    if _looks_like_drawing_pdf(source_path):
        return ExtractorClassification(
            source_scope,
            "pdf",
            "vision_required",
            "mimo_vision",
            "PDF appears to be a drawing, general arrangement, or drawing-package document",
            diagnostics,
        )
    if diagnostics.get("has_sidecar_images"):
        return ExtractorClassification(
            source_scope,
            "pdf",
            "vision_required",
            "mimo_vision",
            "PDF has image sidecar pages, so layout/vision extraction is required",
            diagnostics,
        )
    if diagnostics.get("text_extraction_error"):
        return ExtractorClassification(
            source_scope,
            "pdf",
            "vision_required",
            "mimo_vision",
            "PDF text extraction failed, so vision/layout extraction is required",
            diagnostics,
        )
    if int(diagnostics.get("text_char_count") or 0) < 80:
        return ExtractorClassification(
            source_scope,
            "pdf",
            "vision_required",
            "mimo_vision",
            "PDF selectable text is too sparse for reliable text-only extraction",
            diagnostics,
        )
    return ExtractorClassification(
        source_scope,
        "pdf",
        "text_assisted",
        "mimo_pdf_structured",
        "PDF has selectable text; text may be used only as auxiliary evidence for MiMo structured preprocessing",
        diagnostics,
    )


def _looks_like_drawing_pdf(source_path: Path) -> bool:
    name_raw = source_path.name.lower()
    name_text = _normalise_pdf_name_for_classifier(source_path.stem)
    strong_markers = (
        "图纸",
        "平面图",
        "立面图",
        "剖面图",
        "大样图",
        "drawing",
        "drawings",
        "general-arrangement",
        "general arrangement",
    )
    if any(marker in name_raw for marker in strong_markers):
        return True

    tokens = set(name_text.split())
    drawing_tokens = {
        "elevation",
        "section",
        "details",
        "facade",
        "plan",
        "layout",
        "detail",
        "level",
        "floor",
        "window",
    }
    package_tokens = {
        "general",
        "arrangement",
        "typical",
        "revision",
        "rev",
        "drawing",
        "drawings",
        "schedule",
        "sheet",
    }
    return bool(tokens & drawing_tokens) and bool(tokens & package_tokens)


def _normalise_pdf_name_for_classifier(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value.lower()).strip()


def _diagnose_pdf(source_path: Path) -> dict[str, Any]:
    sidecar_dirs = [candidate for candidate in _pdf_image_sidecar_candidates(source_path) if candidate.is_dir()]
    diagnostics: dict[str, Any] = {
        "has_sidecar_images": bool(sidecar_dirs),
        "sidecar_dirs": [path.name for path in sidecar_dirs],
    }
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(source_path))
        page_count = len(reader.pages)
        page_texts: list[str] = []
        for page in reader.pages:
            page_texts.append(page.extract_text() or "")
        text = "\n".join(page_texts).strip()
        diagnostics.update(
            {
                "page_count": page_count,
                "text_char_count": len(text),
                "avg_text_chars_per_page": round(len(text) / max(page_count, 1), 2),
                "pages_with_text": sum(1 for value in page_texts if value.strip()),
            }
        )
    except Exception as exc:
        diagnostics["text_extraction_error"] = str(exc)
    return diagnostics
