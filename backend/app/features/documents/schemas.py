from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExportDocumentRequest(BaseModel):
    content: str = Field(min_length=1)
    title: str | None = Field(default=None, max_length=200)
    format: Literal["pdf", "docx"]
