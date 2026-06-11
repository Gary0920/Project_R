from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from core.llm import LLMClient, get_llm_client
from app.features.preprocessing.policy import ensure_profile_allowed, ensure_text_preprocess_model


DEFAULT_MODEL_PROFILE = "deepseek-flash"
DEFAULT_MAX_BODY_CHARS = 24_000
LANGUAGE_POLICY = "bilingual_zh_en_aligned"
SKILL_NAME = "email-thread-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-email-thread-v1"

SYSTEM_PROMPT = """你是 Project_R 的邮件线程提炼 Agent。

你要把 EML 邮件变成可进入项目 GBrain source 的结构化 Markdown。
只提炼邮件中稳定、可追溯、对项目有用的信息，不能编造事实。
输出必须中英文并存，且中英文表达同一事实。
不要输出 YAML frontmatter，不要包裹代码块。
"""


@dataclass(frozen=True)
class EmailExtractionOptions:
    model_profile: str = DEFAULT_MODEL_PROFILE
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS
    temperature: float = 0.1
    llm_enabled: bool = True


@dataclass(frozen=True)
class EmailStructuredExtractionResult:
    markdown: str
    extraction_status: str = "email_thread_structured_extract"
    review_status: str = "approved"
    extractor: str = "project_r_email_thread_mvp"
    language_policy: str = LANGUAGE_POLICY
    subject: str = ""
    sender: str = ""
    recipients: tuple[str, ...] = ()
    message_date: str = ""
    attachment_names: tuple[str, ...] = ()
    model_profile: str | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    sender: str
    recipients: tuple[str, ...]
    message_date: str
    body_text: str
    attachment_names: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedEmailAttachment:
    filename: str
    path: Path
    content_type: str
    size: int


def load_email_extraction_options() -> EmailExtractionOptions:
    model_profile = os.getenv("GBRAIN_EMAIL_EXTRACTOR_MODEL_PROFILE", DEFAULT_MODEL_PROFILE).strip() or DEFAULT_MODEL_PROFILE
    ensure_profile_allowed(model_profile, route_name=SKILL_NAME)
    return EmailExtractionOptions(
        model_profile=model_profile,
        max_body_chars=_env_int("GBRAIN_EMAIL_EXTRACTOR_MAX_BODY_CHARS", DEFAULT_MAX_BODY_CHARS, 4_000, 80_000),
        temperature=_env_float("GBRAIN_EMAIL_EXTRACTOR_TEMPERATURE", 0.1, 0.0, 1.0),
        llm_enabled=_env_bool("GBRAIN_EMAIL_EXTRACTOR_LLM_ENABLED", True),
    )


def extract_email_structured_markdown(
    source_path: Path,
    *,
    options: EmailExtractionOptions | None = None,
    llm_client: LLMClient | None = None,
) -> EmailStructuredExtractionResult:
    options = options or load_email_extraction_options()
    parsed = parse_eml(source_path)
    warnings: list[str] = []
    markdown = ""
    model_profile = provider = model = None
    usage: dict[str, int] = {}

    if options.llm_enabled:
        try:
            client = llm_client or get_llm_client(options.model_profile)
            if client.settings.configured:
                ensure_text_preprocess_model(client.settings, route_name=SKILL_NAME)
                response = client.complete(
                    [{"role": "user", "content": _llm_prompt(source_path.name, parsed, options)}],
                    system_prompt=SYSTEM_PROMPT,
                    temperature=options.temperature,
                )
                markdown = _strip_markdown_wrapper(response.text)
                model_profile = client.settings.profile or options.model_profile
                provider = client.settings.provider
                model = client.settings.model
                usage = response.usage
            else:
                warnings.append(f"email extractor model profile is not configured: {options.model_profile}")
        except Exception as exc:
            warnings.append(f"email LLM extraction failed; deterministic fallback used: {exc}")

    if not markdown.strip():
        markdown = _fallback_markdown(source_path.name, parsed)

    return EmailStructuredExtractionResult(
        markdown=_normalize_markdown(markdown, parsed.subject or source_path.stem),
        subject=parsed.subject,
        sender=parsed.sender,
        recipients=parsed.recipients,
        message_date=parsed.message_date,
        attachment_names=parsed.attachment_names,
        model_profile=model_profile,
        provider=provider,
        model=model,
        token_usage=usage,
        warnings=tuple(warnings),
    )


def parse_eml(source_path: Path) -> ParsedEmail:
    message = BytesParser(policy=policy.default).parsebytes(source_path.read_bytes())
    subject = _header(message, "subject")
    sender = _format_addresses(message.get("from", ""))
    recipients = tuple(
        value
        for value in (
            _format_addresses(message.get("to", "")),
            _format_addresses(message.get("cc", "")),
        )
        if value
    )
    body_parts: list[str] = []
    attachment_names: list[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        content_disposition = (part.get_content_disposition() or "").lower()
        filename = part.get_filename()
        if filename:
            attachment_names.append(str(filename))
        if content_disposition == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            body_parts.append(_part_text(part))
        elif content_type == "text/html" and not body_parts:
            body_parts.append(_html_to_text(_part_text(part)))
    return ParsedEmail(
        subject=subject,
        sender=sender,
        recipients=recipients,
        message_date=_message_date(message),
        body_text=_clean_body("\n\n".join(part for part in body_parts if part)),
        attachment_names=tuple(dict.fromkeys(attachment_names)),
    )


def extract_email_attachments(source_path: Path, target_dir: Path) -> tuple[ExtractedEmailAttachment, ...]:
    message = BytesParser(policy=policy.default).parsebytes(source_path.read_bytes())
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[ExtractedEmailAttachment] = []
    seen_names: set[str] = set()
    for part in message.walk() if message.is_multipart() else [message]:
        if part.is_multipart():
            continue
        filename = part.get_filename()
        content_disposition = (part.get_content_disposition() or "").lower()
        if not filename and content_disposition != "attachment":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        safe_name = _safe_attachment_name(filename or "attachment.bin")
        candidate = safe_name
        stem = Path(safe_name).stem or "attachment"
        suffix = Path(safe_name).suffix
        counter = 2
        while candidate.lower() in seen_names:
            candidate = f"{stem}-{counter}{suffix}"
            counter += 1
        seen_names.add(candidate.lower())
        target_path = target_dir / candidate
        target_path.write_bytes(payload)
        extracted.append(
            ExtractedEmailAttachment(
                filename=candidate,
                path=target_path,
                content_type=str(part.get_content_type() or "application/octet-stream"),
                size=len(payload),
            )
        )
    return tuple(extracted)


def _header(message: EmailMessage, name: str) -> str:
    value = message.get(name, "")
    return str(value).strip()


def _safe_attachment_name(value: str) -> str:
    name = Path(value.replace("\\", "/")).name.strip()
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "-", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        return "attachment.bin"
    if len(name) > 160:
        suffix = Path(name).suffix
        stem = Path(name).stem[: max(1, 160 - len(suffix))]
        name = f"{stem}{suffix}"
    return name


def _format_addresses(value: str) -> str:
    addresses = []
    for name, address in getaddresses([value or ""]):
        display = name.strip() or address.strip()
        if address and display != address:
            addresses.append(f"{display} <{address}>")
        elif display:
            addresses.append(display)
    return ", ".join(addresses)


def _message_date(message: EmailMessage) -> str:
    raw = message.get("date", "")
    try:
        return parsedate_to_datetime(str(raw)).isoformat()
    except Exception:
        return str(raw).strip()


def _part_text(part: EmailMessage) -> str:
    try:
        content = part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="ignore")
    return str(content)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return html.unescape(text)


def _clean_body(value: str) -> str:
    lines = []
    previous_blank = False
    for raw_line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", raw_line).strip()
        if not line:
            if not previous_blank:
                lines.append("")
            previous_blank = True
            continue
        lines.append(line)
        previous_blank = False
    return "\n".join(lines).strip()


def _llm_prompt(file_name: str, parsed: ParsedEmail, options: EmailExtractionOptions) -> str:
    body = parsed.body_text[: options.max_body_chars]
    attachments = ", ".join(parsed.attachment_names) if parsed.attachment_names else "none"
    recipients = "; ".join(parsed.recipients) if parsed.recipients else "none"
    return f"""请将下面 EML 邮件提炼为 Project_R 项目 source Markdown。

文件名：{file_name}
Subject: {parsed.subject}
From: {parsed.sender}
To/Cc: {recipients}
Date: {parsed.message_date}
Attachments: {attachments}

输出结构必须包含：
# {parsed.subject or Path(file_name).stem}
## 邮件定位 / Email Positioning
## 项目事实 / Project Facts
## 决策与承诺 / Decisions and Commitments
## 行动项 / Action Items
## 风险与待确认 / Risks and Open Questions
## 附件与引用 / Attachments and References
## 原文摘录 / Source Excerpts

每条事实必须采用中英成对格式：
- 中文：...
  English: ...

不要编造邮件没有的信息；不确定信息放入风险与待确认。

<email_body>
{body}
</email_body>
"""


def _fallback_markdown(file_name: str, parsed: ParsedEmail) -> str:
    recipients = "; ".join(parsed.recipients) if parsed.recipients else "none"
    attachments = ", ".join(parsed.attachment_names) if parsed.attachment_names else "none"
    body_excerpt = "\n".join(f"> {line}" for line in parsed.body_text.splitlines()[:80]) or "> [empty email body]"
    return f"""# {parsed.subject or Path(file_name).stem}

## 邮件定位 / Email Positioning

- 中文：邮件主题为 `{parsed.subject or Path(file_name).stem}`，发件人为 `{parsed.sender or 'unknown'}`，收件/抄送为 `{recipients}`，日期为 `{parsed.message_date or 'unknown'}`。
  English: The email subject is `{parsed.subject or Path(file_name).stem}`, the sender is `{parsed.sender or 'unknown'}`, the recipients/CC are `{recipients}`, and the date is `{parsed.message_date or 'unknown'}`.

## 项目事实 / Project Facts

- 中文：该邮件正文已被解析并保留为项目来源记录；需要人工或后续 LLM 提炼确认具体业务事实。
  English: The email body has been parsed and retained as a project source record; specific business facts require human or later LLM extraction confirmation.

## 决策与承诺 / Decisions and Commitments

- 中文：未在确定性解析中提取稳定决策或承诺，请结合原文复核。
  English: No stable decision or commitment was extracted by deterministic parsing; review the source excerpt.

## 行动项 / Action Items

- 中文：未在确定性解析中提取稳定行动项，请结合原文复核。
  English: No stable action item was extracted by deterministic parsing; review the source excerpt.

## 风险与待确认 / Risks and Open Questions

- 中文：邮件线程语境、附件内容和隐含承诺需要人工复核后再作为业务事实使用。
  English: Email thread context, attachment contents, and implied commitments require human review before being used as business facts.

## 附件与引用 / Attachments and References

- 中文：附件：`{attachments}`。
  English: Attachments: `{attachments}`.

## 原文摘录 / Source Excerpts

{body_excerpt}
"""


def _normalize_markdown(value: str, title: str) -> str:
    text = _strip_markdown_wrapper(value)
    if not text.startswith("#"):
        text = f"# {title}\n\n{text}"
    return text.rstrip() + "\n"


def _strip_markdown_wrapper(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))
