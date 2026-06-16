from __future__ import annotations

from app.features.documents.registry import render_document
from app.features.documents.renderers.docx import render_docx
from app.features.documents.renderers.pdf import render_pdf
from app.features.documents.renderers.pptx import render_pptx
from app.features.documents.renderers.text import render_markdown, render_txt
from app.features.documents.renderers.xlsx import render_xlsx


__all__ = [
    "render_document",
    "render_docx",
    "render_markdown",
    "render_txt",
    "render_xlsx",
    "render_pptx",
    "render_pdf",
]
