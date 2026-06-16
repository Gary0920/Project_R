from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException


@dataclass(frozen=True)
class OutputFormat:
    key: str
    extension: str
    mime_type: str
    display_name: str
    aliases: tuple[str, ...] = ()
    is_text: bool = False


SUPPORTED_OUTPUT_FORMATS: dict[str, OutputFormat] = {
    "docx": OutputFormat(
        key="docx",
        extension=".docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        display_name="Word 文档",
        aliases=("doc", "word"),
    ),
    "markdown": OutputFormat(
        key="markdown",
        extension=".md",
        mime_type="text/markdown; charset=utf-8",
        display_name="Markdown 文件",
        aliases=("md",),
        is_text=True,
    ),
    "txt": OutputFormat(
        key="txt",
        extension=".txt",
        mime_type="text/plain; charset=utf-8",
        display_name="纯文本文件",
        aliases=("text",),
        is_text=True,
    ),
    "xlsx": OutputFormat(
        key="xlsx",
        extension=".xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        display_name="Excel 文件",
        aliases=("excel", "xls"),
    ),
    "pptx": OutputFormat(
        key="pptx",
        extension=".pptx",
        mime_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        display_name="演示文稿",
        aliases=("ppt", "powerpoint"),
    ),
    "pdf": OutputFormat(
        key="pdf",
        extension=".pdf",
        mime_type="application/pdf",
        display_name="PDF 文件",
        aliases=(),
    ),
}


def normalize_output_format(value: str) -> OutputFormat:
    normalized = (value or "").strip().lower().lstrip(".")
    for output_format in SUPPORTED_OUTPUT_FORMATS.values():
        if normalized == output_format.key or normalized in output_format.aliases:
            return output_format
    raise HTTPException(status_code=400, detail="不支持的文件格式")
