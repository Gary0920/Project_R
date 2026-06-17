from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

EMAIL_META_KEY = "email_draft"
HEADER_ALIASES = {
    "subject": "subject",
    "to": "to",
    "cc": "cc",
    "bcc": "bcc",
    "from": "from",
}
HEADER_PATTERN = re.compile(
    r"^\s*(Subject|To|Cc|Bcc|From|主题|收件人|抄送|密送|发件人)\s*[:：]\s*(.*?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
BODY_MARKER_PATTERN = re.compile(r"^\s*(Body|正文|Email Body|邮件正文)\s*[:：]\s*$", re.IGNORECASE | re.MULTILINE)
ENGLISH_DRAFT_HEADING = re.compile(r"^#{1,4}\s*\d*\.?\s*English Email Draft\s*$", re.IGNORECASE | re.MULTILINE)
NEXT_HEADING = re.compile(r"^#{1,4}\s+\S+", re.MULTILINE)


@dataclass(frozen=True)
class EmailDraft:
    subject: str
    body: str
    sender: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "subject": self.subject,
            "body": self.body,
        }
        if self.sender:
            payload["from"] = self.sender
        if self.to:
            payload["to"] = ", ".join(self.to)
        if self.cc:
            payload["cc"] = ", ".join(self.cc)
        if self.bcc:
            payload["bcc"] = ", ".join(self.bcc)
        return payload


def build_email_draft(title: str, content: str, metadata: dict[str, Any] | None = None) -> EmailDraft:
    raw = _draft_metadata(metadata)
    parsed = parse_email_draft_text(content, default_subject=title)
    subject = str(raw.get("subject") or parsed.subject or title).strip() or "Project_R 邮件草稿"
    body = str(raw.get("body") or parsed.body or content).strip()
    return EmailDraft(
        subject=_clean_subject(subject),
        body=_clean_email_body(body),
        sender=_clean_scalar(raw.get("from") or parsed.sender),
        to=_address_list(raw.get("to") or parsed.to),
        cc=_address_list(raw.get("cc") or parsed.cc),
        bcc=_address_list(raw.get("bcc") or parsed.bcc),
    )


def parse_email_draft_text(text: str, *, default_subject: str = "Project_R 邮件草稿") -> EmailDraft:
    section = _extract_email_section(_strip_fences(text or ""))
    headers: dict[str, str] = {}
    for match in HEADER_PATTERN.finditer(section):
        key = _normalize_header_key(match.group(1))
        if key and match.group(2).strip():
            headers[key] = match.group(2).strip()
    subject = _clean_subject(headers.get("subject") or default_subject)
    body = _extract_body(section)
    return EmailDraft(
        subject=subject,
        body=_clean_email_body(body),
        sender=_clean_scalar(headers.get("from")),
        to=_address_list(headers.get("to")),
        cc=_address_list(headers.get("cc")),
        bcc=_address_list(headers.get("bcc")),
    )


def email_draft_payload(metadata: dict[str, Any] | None, *, title: str = "", content: str = "") -> dict[str, Any] | None:
    if not metadata and not content:
        return None
    draft = build_email_draft(title or "Project_R 邮件草稿", content, metadata)
    payload = draft.to_payload()
    return payload if payload.get("body") or payload.get("subject") else None


def email_draft_metadata(
    *,
    subject: str = "",
    body: str = "",
    sender: Any = None,
    to: Any = None,
    cc: Any = None,
    bcc: Any = None,
) -> dict[str, Any]:
    draft = {
        "subject": subject,
        "body": body,
        "from": sender,
        "to": to,
        "cc": cc,
        "bcc": bcc,
    }
    return {EMAIL_META_KEY: {key: value for key, value in draft.items() if value}}


def _draft_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get(EMAIL_META_KEY)
    return raw if isinstance(raw, dict) else {}


def _extract_email_section(text: str) -> str:
    match = ENGLISH_DRAFT_HEADING.search(text)
    if not match:
        return text.strip()
    rest = text[match.end():]
    next_heading = NEXT_HEADING.search(rest)
    if next_heading:
        rest = rest[: next_heading.start()]
    return rest.strip()


def _extract_body(section: str) -> str:
    body_marker = BODY_MARKER_PATTERN.search(section)
    if body_marker:
        return section[body_marker.end():].strip()
    lines = []
    for line in section.splitlines():
        if HEADER_PATTERN.match(line):
            continue
        lines.append(line)
    body = "\n".join(lines).strip()
    return body or section.strip()


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    fence = re.fullmatch(r"```[a-zA-Z0-9_-]*\n([\s\S]*?)\n?```", stripped)
    return fence.group(1).strip() if fence else stripped


def _clean_email_body(value: str) -> str:
    text = _strip_fences(value)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _normalize_header_key(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in HEADER_ALIASES:
        return HEADER_ALIASES[lowered]
    mapping = {
        "主题": "subject",
        "收件人": "to",
        "抄送": "cc",
        "密送": "bcc",
        "发件人": "from",
    }
    return mapping.get(value.strip(), "")


def _address_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple)):
        values = [str(item) for item in value]
    else:
        values = [str(value)]
    return [item.strip() for item in values if item and item.strip()]


def _clean_subject(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_scalar(value: Any) -> str:
    return str(value or "").strip()
