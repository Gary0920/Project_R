from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm import LLMClient, LLMConfigurationError, get_llm_client
from app.features.preprocessing.policy import ensure_mimo_v2_5_model, ensure_profile_allowed


LANGUAGE_POLICY = "bilingual_zh_en_aligned"
EXTRACTION_STATUS = "image_structured_extract"
EXTRACTOR_NAME = "project_r_mimo_image_extraction_mvp"
SKILL_NAME = "image-screenshot-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-image-screenshot-v1"
DEFAULT_MODEL_PROFILE = "mimo-v2-5"
DEFAULT_MAX_RAW_BYTES = 10_000_000
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}

# Phase 3 D5: Image subkind detection patterns
_PAYMENT_FILENAME_PATTERNS = {"支付", "付款", "pay", "payment", "账单"}
_CONTACT_SHEET_FILENAME_PATTERNS = {"内部联系单", "联系单", "签证", "变更", "contact", "variation"}


@dataclass(frozen=True)
class ImageStructuredExtractionOptions:
    model_profile: str = DEFAULT_MODEL_PROFILE
    max_raw_bytes: int = DEFAULT_MAX_RAW_BYTES
    temperature: float = 0.0


@dataclass(frozen=True)
class ImageStructuredExtractionResult:
    markdown: str
    extraction_status: str = EXTRACTION_STATUS
    review_status: str = "approved"
    extractor: str = EXTRACTOR_NAME
    language_policy: str = LANGUAGE_POLICY
    image_kind: str = "screenshot_or_image"
    model_profile: str | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


def load_image_extraction_options() -> ImageStructuredExtractionOptions:
    model_profile = os.getenv("GBRAIN_IMAGE_EXTRACTOR_MODEL_PROFILE", DEFAULT_MODEL_PROFILE).strip() or DEFAULT_MODEL_PROFILE
    ensure_profile_allowed(model_profile, route_name=SKILL_NAME)
    return ImageStructuredExtractionOptions(
        model_profile=model_profile,
        max_raw_bytes=_env_int("GBRAIN_IMAGE_EXTRACTOR_MAX_RAW_BYTES", DEFAULT_MAX_RAW_BYTES, 100_000, 50_000_000),
        temperature=_env_float("GBRAIN_IMAGE_EXTRACTOR_TEMPERATURE", 0.0, 0.0, 1.0),
    )


# ── Phase 3 D5: Image subkind detection ─────────────────────────────────


def _detect_image_subkind(filename: str) -> str:
    """Detect image subkind from filename.

    Returns one of: "payment", "contact_sheet", "general".
    """
    name_lower = filename.lower().replace("-", " ").replace("_", " ")
    for pattern in _PAYMENT_FILENAME_PATTERNS:
        if pattern in name_lower:
            return "payment"
    for pattern in _CONTACT_SHEET_FILENAME_PATTERNS:
        if pattern in name_lower:
            return "contact_sheet"
    return "general"


# ── Phase 3 D5: Field schemas ────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentScreenshotFields:
    amount: str | None = None
    currency: str | None = None
    direction: str | None = None  # "outgoing" | "incoming"
    payment_time: str | None = None
    payment_method: str | None = None
    counterparty: str | None = None


@dataclass(frozen=True)
class ContactSheetFields:
    document_number: str | None = None
    replenishment_reason: str | None = None
    replenishment_items: list[str] = field(default_factory=list)
    approval_notes: str | None = None


@dataclass(frozen=True)
class ExtractedImageFields:
    subkind: str = "general"
    payment: PaymentScreenshotFields | None = None
    contact_sheet: ContactSheetFields | None = None


# ── Phase 3 D5: Specialized prompts ──────────────────────────────────────


def _image_prompt(file_name: str, subkind: str) -> str:
    base = f"""请把这张图片或截图提炼为 Project_R 可入库的结构化 Markdown。

文件名：{file_name}

要求：
- 不要编造图片中没有的信息。
- 所有结论必须中英文对齐，且中英文表达同一事实。
- 看不清的区域写入"待确认 / Review Questions"，不要当作事实。
- 输出 Markdown，不要输出 YAML frontmatter。

"""

    if subkind == "payment":
        return base + """**本图片是支付截图或账单截图。**

请按以下结构输出：

# 标题

## 图片定位 / Image Positioning
（图片类型、来源、区域说明）

## Extracted Fields
- **金额 / Amount**: （数字，如 68.00）
- **币种 / Currency**: （如 CNY / USD）
- **方向 / Direction**: 支出 (outgoing) 或 收入 (incoming)
- **支付时间 / Payment Time**: （YYYY-MM-DD HH:MM）
- **支付方式 / Payment Method**: （如 微信支付 / 银行转账 / 支付宝）
- **交易对方 / Counterparty**: （对方名称）

## Description
（自然语言描述图片整体内容）

## Source Evidence
- **Source**: {file_name}
- **Region**: （金额所在区域描述）

## Preprocess Notes
（不确定点、缺失字段、待确认事项）
"""
    elif subkind == "contact_sheet":
        return base + """**本图片是内部联系单、签证或变更通知单。**

请按以下结构输出：

# 标题

## 图片定位 / Image Positioning
（图片类型、来源、区域说明）

## Extracted Fields
- **单号 / Document Number**: （如 BG0806-LXD01）
- **补货原因 / Replenishment Reason**: （补货或变更原因描述）
- **补货内容 / Replenishment Items**: （逐项列出补货或变更内容）
- **审批备注 / Approval Notes**: （审批意见或备注）

## Description
（自然语言描述图片整体内容）

## Source Evidence
- **Source**: {file_name}
- **Region**: （关键字段所在区域描述）

## Preprocess Notes
（不确定点、缺失字段、待确认事项）
"""
    else:
        return base + """建议结构：
# 标题
## 图片定位 / Image Positioning
## 稳定事实 / Stable Facts
## 流程或字段 / Process or Fields
## 风险与待确认 / Risks and Review Questions
## 可沉淀知识候选 / Knowledge Candidates
"""


# ── Phase 3 D5: Field post-processing ────────────────────────────────────


def _parse_extracted_fields(markdown: str, subkind: str) -> ExtractedImageFields:
    """Parse structured fields from the MiMo-generated markdown.

    Uses simple keyword matching on the markdown content.
    """
    md_lower = markdown.lower()

    if subkind == "payment":
        return _parse_payment_fields(markdown, md_lower)
    elif subkind == "contact_sheet":
        return _parse_contact_sheet_fields(markdown, md_lower)
    return ExtractedImageFields(subkind="general")


def _parse_payment_fields(markdown: str, md_lower: str) -> ExtractedImageFields:
    amount = _find_field_value(markdown, ["金额", "Amount", "amount"])
    currency = _find_field_value(markdown, ["币种", "Currency", "currency"])
    direction_raw = _find_field_value(markdown, ["方向", "Direction", "direction"])
    direction = None
    if direction_raw:
        dr = direction_raw.lower()
        if any(w in dr for w in ("支出", "outgoing", "转出", "付款")):
            direction = "outgoing"
        elif any(w in dr for w in ("收入", "incoming", "转入", "收款")):
            direction = "incoming"
    payment_time = _find_field_value(markdown, ["支付时间", "Payment Time", "payment time"])
    payment_method = _find_field_value(markdown, ["支付方式", "Payment Method", "payment method"])
    counterparty = _find_field_value(markdown, ["交易对方", "Counterparty", "counterparty"])

    # Normalize amount: extract first decimal number
    if amount:
        import re

        match = re.search(r"(\d+[,.]?\d*)", amount.replace(",", ""))
        if match:
            amount = match.group(1)

    return ExtractedImageFields(
        subkind="payment",
        payment=PaymentScreenshotFields(
            amount=amount,
            currency=currency,
            direction=direction,
            payment_time=payment_time,
            payment_method=payment_method,
            counterparty=counterparty,
        ),
    )


def _parse_contact_sheet_fields(markdown: str, md_lower: str) -> ExtractedImageFields:
    doc_number = _find_field_value(markdown, ["单号", "Document Number", "document number"])
    reason = _find_field_value(markdown, ["补货原因", "Replenishment Reason", "replenishment reason"])

    items: list[str] = []
    items_raw = _find_field_value(markdown, ["补货内容", "Replenishment Items", "replenishment items"])
    if items_raw:
        import re

        items = [line.strip().lstrip("-* ") for line in items_raw.split("\n") if line.strip()]
        if not items:
            items = [items_raw]

    approval = _find_field_value(markdown, ["审批备注", "Approval Notes", "approval notes"])

    return ExtractedImageFields(
        subkind="contact_sheet",
        contact_sheet=ContactSheetFields(
            document_number=doc_number,
            replenishment_reason=reason,
            replenishment_items=items,
            approval_notes=approval,
        ),
    )


def _find_field_value(markdown: str, field_names: list[str]) -> str | None:
    """Find a field value in markdown.

    Searches for `- **...field_name...**: value` patterns where field_name
    can be a substring within the `**...**` delimiters (markdown may have
    bilingual headers like `- **金额 / Amount**: 68.00`).
    """
    import re

    for line in markdown.split("\n"):
        line_stripped = line.strip()
        # Match: `- **...**: value`
        m = re.match(r"-\s\*\*(.+?)\*\*\s*:\s*(.+)", line_stripped)
        if not m:
            continue
        label = m.group(1).strip()
        value = m.group(2).strip()
        # Check if any field_name appears in the label
        for field_name in field_names:
            if field_name.lower() in label.lower():
                if value and value not in ("N/A", "无", ""):
                    return value
    return None


def _enrich_markdown_with_parsed_fields(markdown: str, fields: ExtractedImageFields) -> str:
    """Append parsed fields summary to the markdown if not already present."""
    if fields.subkind == "general":
        return markdown

    lines: list[str] = []
    if fields.payment:
        p = fields.payment
        lines.append(f"- **金额 / Amount**: {p.amount or '未提取'}")
        lines.append(f"- **币种 / Currency**: {p.currency or '未提取'}")
        lines.append(f"- **方向 / Direction**: {p.direction or '未提取'}")
        lines.append(f"- **支付时间**: {p.payment_time or '未提取'}")
        lines.append(f"- **支付方式**: {p.payment_method or '未提取'}")
        lines.append(f"- **交易对方**: {p.counterparty or '未提取'}")
    elif fields.contact_sheet:
        cs = fields.contact_sheet
        lines.append(f"- **单号 / Document Number**: {cs.document_number or '未提取'}")
        lines.append(f"- **补货原因**: {cs.replenishment_reason or '未提取'}")
        items_str = "; ".join(cs.replenishment_items) if cs.replenishment_items else "未提取"
        lines.append(f"- **补货内容**: {items_str}")
        lines.append(f"- **审批备注**: {cs.approval_notes or '未提取'}")

    if not lines:
        return markdown

    if "## Extracted Fields" not in markdown and "## Extracted Fields" not in markdown:
        enriched = markdown.rstrip() + "\n\n## Extracted Fields\n" + "\n".join(lines) + "\n"
        return enriched

    return markdown


def extract_image_structured_markdown(
    source_path: Path,
    *,
    options: ImageStructuredExtractionOptions | None = None,
    llm_client: LLMClient | None = None,
) -> ImageStructuredExtractionResult:
    options = options or load_image_extraction_options()
    if source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(f"unsupported image extraction format: {source_path.suffix}")
    if source_path.stat().st_size > options.max_raw_bytes:
        raise ValueError(
            f"image file is too large for base64 vision extraction: {source_path.stat().st_size} bytes"
        )
    client = llm_client or get_llm_client(options.model_profile)
    if not client.settings.configured:
        raise LLMConfigurationError(f"Image extraction model profile is not configured: {options.model_profile}")
    ensure_mimo_v2_5_model(client.settings, route_name=SKILL_NAME)

    # Phase 3 D5: Detect subkind for specialized prompt
    subkind = _detect_image_subkind(source_path.stem)

    content_blocks: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": _data_uri(source_path)},
        },
        {"type": "text", "text": _image_prompt(source_path.name, subkind)},
    ]
    response = client.complete(
        [{"role": "user", "content": content_blocks}],
        system_prompt="You extract business knowledge from screenshots and images without inventing facts.",
        temperature=options.temperature,
    )
    markdown = _normalize_markdown(response.text, source_path.stem)

    # Phase 3 D5: Parse and enrich with structured fields
    if subkind in ("payment", "contact_sheet"):
        fields = _parse_extracted_fields(markdown, subkind)
        markdown = _enrich_markdown_with_parsed_fields(markdown, fields)
    else:
        fields = ExtractedImageFields(subkind="general")

    return ImageStructuredExtractionResult(
        markdown=markdown,
        image_kind=subkind,
        model_profile=client.settings.profile or options.model_profile,
        provider=client.settings.provider,
        model=response.model or client.settings.model,
        token_usage=response.usage,
    )





def _normalize_markdown(value: str, fallback_title: str) -> str:
    text = value.strip().strip("`").strip()
    if text.lower().startswith("markdown"):
        text = text[len("markdown") :].strip()
    if not text.startswith("#"):
        text = f"# {fallback_title}\n\n{text}"
    return text.rstrip() + "\n"


def _data_uri(source_path: Path) -> str:
    media_type = mimetypes.guess_type(source_path.name)[0] or "image/png"
    encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


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
