from __future__ import annotations

from pathlib import Path

from app.features.documents.content_parser import clean_markdown, clean_plain_text


def render_txt(title: str, content: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(clean_plain_text(content), encoding="utf-8")
    return output_path


def render_markdown(title: str, content: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(clean_markdown(title, content), encoding="utf-8")
    return output_path
