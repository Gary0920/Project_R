from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from pathlib import Path
from typing import Any

from app.features.documents.email_draft import build_email_draft


def render_eml(title: str, content: str, output_path: Path, metadata: dict[str, Any] | None = None) -> Path:
    draft = build_email_draft(title, content, metadata)
    message = EmailMessage(policy=SMTP)
    message["Subject"] = draft.subject
    message["Date"] = formatdate(localtime=True)
    if draft.sender:
        message["From"] = draft.sender
    if draft.to:
        message["To"] = ", ".join(draft.to)
    if draft.cc:
        message["Cc"] = ", ".join(draft.cc)
    if draft.bcc:
        message["Bcc"] = ", ".join(draft.bcc)
    message.set_content(draft.body, charset="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes(policy=SMTP))
    return output_path
