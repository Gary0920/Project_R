from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ── Pattern definitions ──────────────────────────────────────────────────

# Each rule: (file_kind_hint, source_category_hint, confidence, patterns)
# Patterns are matched case-insensitively against the query text.

IntentRule = tuple[str | None, str | None, str, list[str]]

INTENT_RULES: list[IntentRule] = [
    # pdf_schedule — 排期/工期 (before drawing: "排期中的图纸" → schedule, not drawing)
    ("pdf_schedule", "technical", "high", [
        "排期", "工期", "计划完成", "天才能完成",
        "duration", "finish", "predecessor", "start.*finish",
    ]),
    # pdf_drawing — 图纸/平面图/窗表
    ("pdf_drawing", "technical", "high", [
        "图纸", "平面图", "窗号", "立面图", "剖面图", "大样图",
        "floor plan", "drawing", "elevation", "window schedule",
        "窗",  # "窗的宽高尺寸" → drawing
    ]),
    # image_payment — 支付/金额截图
    ("image_payment", "unfiled", "high", [
        "支付", "金额", "花费", "付款", "账单",
        "pay", "screenshot", "payment", "amount",
    ]),
    # image_contact_sheet — 内部联系单/补货/签证
    ("image_contact_sheet", "changes", "high", [
        "内部联系单", "补货", "签证", "联系单",
        "BG0806", "增补",
    ]),
    # meeting — 会议
    ("meeting", "meetings", "high", [
        "会议", "提出", "讨论", "decided", "meeting",
    ]),
    # email — 邮件
    ("email", "unfiled", "high", [
        "邮件", "daisy", "skylight", "email", "推荐.*glass",
    ]),
    # spreadsheet — 材料清单/表格
    ("spreadsheet", "production", "high", [
        "材料清单", "玻璃规格", "GL01", "GL02",
        "ml", "bom", "材料列表",
    ]),
    # office_doc — 注意事项/Office文档
    ("office_doc", "production", "medium", [
        "注意事项", "适配颜色", "五金", "rooster",
        "notes", "notice", "注意事项文件",
    ]),
    # office_contract — 合同/报价
    ("office_contract", "contracts", "medium", [
        "合同", "报价", "quotation", "contract",
    ]),
]

# When confidence=medium, also check that at least 2 patterns match
MEDIUM_CONFIDENCE_MIN_MATCHES = 2


@dataclass
class ProjectQueryIntent:
    """The classified intent of a project workspace query."""

    file_kind_hint: str | None = None
    """Inferred file kind for retrieval boosting."""
    source_category_hint: str | None = None
    """Project directory category (technical/meetings/changes/production/unfiled/contracts)."""
    confidence: str = "low"
    """high / medium / low"""
    matched_patterns: list[str] = field(default_factory=list)
    """Which pattern strings matched."""
    raw_query: str = ""
    """The original query text."""


def classify_project_query(query: str) -> ProjectQueryIntent:
    """Classify a project workspace query into a file-kind intent.

    Uses keyword pattern matching against the query text.
    Returns the best-matching intent (highest confidence → most patterns matched).
    """
    if not query or not query.strip():
        return ProjectQueryIntent(raw_query=query)

    normalized = _normalize_query(query)
    candidates: list[tuple[ProjectQueryIntent, int]] = []

    for file_kind_hint, category_hint, confidence, patterns in INTENT_RULES:
        matched = [p for p in patterns if re.search(re.escape(p), normalized, re.IGNORECASE)]
        if not matched:
            continue
        if confidence == "medium" and len(matched) < MEDIUM_CONFIDENCE_MIN_MATCHES:
            continue
        candidates.append((
            ProjectQueryIntent(
                file_kind_hint=file_kind_hint,
                source_category_hint=category_hint,
                confidence=confidence,
                matched_patterns=matched,
                raw_query=query,
            ),
            len(matched),
        ))

    if not candidates:
        return ProjectQueryIntent(raw_query=query, confidence="low")

    # Sort by: confidence weight first (high=3, medium=2, low=1), then pattern count
    confidence_weight = {"high": 3, "medium": 2, "low": 1}

    def _sort_key(item: tuple[ProjectQueryIntent, int]) -> tuple:
        intent, match_count = item
        return (confidence_weight.get(intent.confidence, 0), match_count)

    candidates.sort(key=_sort_key, reverse=True)
    return candidates[0][0]


def _normalize_query(query: str) -> str:
    """Normalize query for pattern matching."""
    # Collapse whitespace
    text = re.sub(r"\s+", " ", query.strip())
    # Keep Chinese characters, alphanumeric, and common punctuation
    # Don't strip too aggressively — keep spaces for English multi-word matching
    return text


def intent_to_ranking_boost(intent: ProjectQueryIntent) -> dict[str, Any]:
    """Convert an intent to ranking boost parameters.

    Returns a dict suitable for passing to adjust_project_ranking().
    """
    boost: dict[str, Any] = {
        "file_kind_hint": intent.file_kind_hint,
        "confidence": intent.confidence,
    }
    if intent.confidence == "high":
        boost["boost_factor"] = 1.5
        boost["penalty_factor"] = 0.6
    elif intent.confidence == "medium":
        boost["boost_factor"] = 1.3
        boost["penalty_factor"] = 0.8
    else:
        boost["boost_factor"] = 1.0
        boost["penalty_factor"] = 1.0
    return boost
