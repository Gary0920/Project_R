from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.features.documents.formats import SUPPORTED_OUTPUT_FORMATS
from app.features.documents.registry import render_document

ExportFormat = Literal["pdf", "docx"]
EXPORT_FORMATS: tuple[ExportFormat, ...] = ("pdf", "docx")
MAX_EXPORT_CONTENT_BYTES = 200 * 1024
DEFAULT_EXPORT_TITLE = "Project_R 文档"


class ExportContentError(ValueError):
    pass


def export_content_to_temp_file(
    *,
    content: str,
    title: str | None,
    output_format: ExportFormat,
) -> tuple[Path, str]:
    if output_format not in EXPORT_FORMATS:
        raise ExportContentError("不支持的文件格式")

    normalized_content = content or ""
    if len(normalized_content.encode("utf-8")) > MAX_EXPORT_CONTENT_BYTES:
        raise ExportContentError("文档内容过长")

    safe_title = (title or DEFAULT_EXPORT_TITLE).strip() or DEFAULT_EXPORT_TITLE
    format_spec = SUPPORTED_OUTPUT_FORMATS[output_format]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"project-r-document-{timestamp}{format_spec.extension}"

    temp_dir = Path(tempfile.mkdtemp(prefix="project-r-export-"))
    output_path = temp_dir / filename
    render_document(output_format, safe_title, normalized_content, output_path)
    return output_path, filename


def cleanup_export_temp_file(path: Path) -> None:
    import shutil

    shutil.rmtree(path.parent, ignore_errors=True)
