from __future__ import annotations

from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
from pathlib import Path
from typing import Any

from app.features.documents.content_parser import clean_plain_text


EMAIL_META_KEY = "email_draft"


def render_eml(title: str, content: str, output_path: Path, metadata: dict[str, Any] | None = None) -> Path:
    draft = _draft_metadata(metadata)
    subject = str(draft.get("subject") or title).strip() or "Project_R 邮件草稿"
    body = str(draft.get("body") or content).strip()
    message = EmailMessage(policy=SMTP)
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    _set_address_header(message, "From", draft.get("from"))
    _set_address_header(message, "To", draft.get("to"))
    _set_address_header(message, "Cc", draft.get("cc"))
    _set_address_header(message, "Bcc", draft.get("bcc"))
    message.set_content(clean_plain_text(body), charset="utf-8")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(message.as_bytes(policy=SMTP))
    return output_path


def email_draft_payload(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    draft = _draft_metadata(metadata)
    if not draft:
        return None
    payload: dict[str, Any] = {}
    for key in ("subject", "body", "from", "to", "cc", "bcc"):
        value = draft.get(key)
        if value:
            payload[key] = value
    return payload or None


def _draft_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get(EMAIL_META_KEY)
    return raw if isinstance(raw, dict) else {}


def _set_address_header(message: EmailMessage, header: str, value: Any) -> None:
    addresses = _address_list(value)
    if addresses:
        message[header] = ", ".join(addresses)


def _address_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple)):
        values = [str(item) for item in value]
    else:
        values = [str(value)]
    return [item.strip() for item in values if item.strip()]
