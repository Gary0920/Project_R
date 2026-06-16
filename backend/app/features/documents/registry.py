from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.features.documents.renderers.docx import render_docx
from app.features.documents.renderers.pdf import render_pdf
from app.features.documents.renderers.pptx import render_pptx
from app.features.documents.renderers.text import render_markdown, render_txt
from app.features.documents.renderers.xlsx import render_xlsx


Renderer = Callable[[str, str, Path], Path]


RENDERERS: dict[str, Renderer] = {
    "docx": render_docx,
    "markdown": render_markdown,
    "txt": render_txt,
    "xlsx": render_xlsx,
    "pptx": render_pptx,
    "pdf": render_pdf,
}


def render_document(output_format: str, title: str, content: str, output_path: Path) -> Path:
    renderer = RENDERERS.get(output_format)
    if not renderer:
        raise ValueError(f"Unsupported document output format: {output_format}")
    return renderer(title, content, output_path)
