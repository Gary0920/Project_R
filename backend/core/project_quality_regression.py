from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "gbrain_project_quality_regression_cases.json"
MEETING_FILE_KINDS = {"meeting_transcript_docx", "meeting_media"}
ALLOWED_STATUS_CLASSIFICATIONS = {
    "pass",
    "wrong_source",
    "missing_answer_point",
    "missing_citation",
    "known_gap",
    "unexpected_pass",
    "service_unavailable",
}
QueryFn = Callable[[str], dict[str, Any]]

# Patterns that indicate the answer is a negative / "cannot answer" response
_NEGATIVE_ANSWER_PATTERNS = [
    "未找到", "无法确定", "没有找到", "无相关信息", "没有提及",
    "cannot determine", "no information", "not found", "cannot answer",
    "unable to answer", "no specific", "does not contain",
    "too broad", "无法回答", "不确定", "gaps",
    # Extended patterns from WS/Programme regression
    "未能直接找到", "未能找到", "未直接查到", "未找到直接对应",
    "无法确认", "未明确提及", "无法从现有资料中确定",
    "并未找到",
]


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class RegressionCase:
    id: str
    file_kind: str
    expected_status: str
    query: str
    source_file: str
    expected_location: dict
    expected_answer: dict


@dataclass
class RegressionResult:
    case_id: str
    status: str
    first_hit_source: str | None = None
    first_hit_file_kind: str | None = None
    answer_text: str | None = None
    citation: dict | None = None
    missing_terms_all: list[str] = field(default_factory=list)
    missing_terms_any: list[str] = field(default_factory=list)
    meeting_false_positive: bool = False
    answer_points: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class RegressionReport:
    run_id: str
    generated_at: str
    source_id: str
    mode: str
    summary: dict
    results: list[RegressionResult]
    known_gaps: list[str]


# ── Fixture loading ─────────────────────────────────────────────────────


def load_fixture(path: Path | str = FIXTURE_PATH) -> list[RegressionCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases_raw = raw.get("cases", [])
    cases: list[RegressionCase] = []
    for item in cases_raw:
        cases.append(
            RegressionCase(
                id=str(item.get("id", "")),
                file_kind=str(item.get("file_kind", "")),
                expected_status=str(item.get("expected_status", "known_gap")),
                query=str(item.get("query", "")),
                source_file=str(item.get("source_file", "")),
                expected_location=item.get("expected_location", {}),
                expected_answer=item.get("expected_answer", {}),
            )
        )
    return cases


# ── Answer matching ─────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Lowercase, strip leading/trailing whitespace, collapse spaces."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _check_terms(text: str, terms_all: list[str], terms_any: list[str]) -> tuple[list[str], list[str]]:
    """Return (missing_all, missing_any) given the text."""
    normalized = _normalize_text(text)
    missing_all = [t for t in terms_all if t.lower() not in normalized]
    missing_any = [t for t in terms_any if t.lower() not in normalized]
    return missing_all, missing_any


def _first_hit_source_file(sources: list[dict]) -> str | None:
    if not sources:
        return None
    raw = _source_identifier(sources[0])
    return str(raw) if raw else None


def _first_hit_file_kind(sources: list[dict]) -> str | None:
    if not sources:
        return None
    return sources[0].get("file_kind") or sources[0].get("source_file_kind") or None


def _extract_answer_text(think_response: dict) -> str:
    # GBrain adapter returns result.answer (raw MCP)
    # KnowledgeSources normalizes to reply at top level
    result = think_response.get("result")
    if isinstance(result, dict):
        inner = result.get("answer") or ""
        if inner:
            return str(inner).strip()
    reply = think_response.get("reply") or think_response.get("answer") or ""
    return str(reply).strip()


def _extract_sources(think_response: dict, *, answer_text: str = "") -> list[dict]:
    # GBrain adapter returns result.citations (raw MCP)
    result = think_response.get("result")
    if isinstance(result, dict):
        citations = result.get("citations")
        if isinstance(citations, list) and citations:
            return [_normalize_source_ref(citation) for citation in citations if isinstance(citation, dict)]

    # Fallback: parse inline citations from answer text like [slug] or [path/file]
    if answer_text:
        inline_sources = _parse_inline_citations(answer_text)
        if inline_sources:
            return inline_sources

    raw = think_response.get("sources") or think_response.get("source_list") or []
    return list(raw) if isinstance(raw, list) else []


def _source_identifier(source: dict) -> str:
    for key in ("file", "source_file", "page_slug", "slug", "page", "source", "title", "source_title"):
        value = source.get(key)
        if value:
            return str(value)
    return ""


def _normalize_source_ref(source: dict) -> dict:
    normalized = dict(source)
    identifier = _source_identifier(normalized)
    if identifier and not normalized.get("file"):
        normalized["file"] = identifier
    return normalized


_INLINE_CITATION_RE = re.compile(r"\[([^\]]+?)\]")


def _normalize_source_slug(slug: str) -> str:
    """Normalize a source file path or slug for matching.

    Handles mappings like:
      '99-未归档文件/支付截图服务器.png' → '支付截图服务器'
      'production/260506-注意事项-bg0812-rooster' → '260506-注意事项-bg0812-rooster'
      'changes/邱智勇提交的内部联系单_1' → '邱智勇提交的内部联系单_1'
    """
    slug = slug.replace("\\", "/").strip()
    # Remove common prefixes and extensions
    slug = slug.replace("gbrain:", "").replace("workspace:", "")
    slug = slug.split("/")[-1] if "/" in slug else slug
    slug = slug.rsplit(".", 1)[0] if "." in slug else slug
    # Strip brackets, parentheses, and other punctuation for matching
    for ch in "[]()（）【】":
        slug = slug.replace(ch, "")
    return slug.lower().replace("-", "").replace(" ", "").replace("_", "")


def _source_matches_expected(first_hit_source: str | None, expected_source: str) -> bool:
    """Check if a first_hit_source matches the expected source_file from fixture."""
    if not first_hit_source:
        return False
    normalized_hit = _normalize_source_slug(first_hit_source)
    normalized_expected = _normalize_source_slug(expected_source)
    return normalized_hit == normalized_expected or normalized_expected in normalized_hit or normalized_hit in normalized_expected


def _parse_inline_citations(text: str) -> list[dict]:
    """Parse inline citation markers like [unfiled/支付截图服务器] from answer text."""
    matches = _INLINE_CITATION_RE.findall(text)
    sources: list[dict] = []
    seen: set[str] = set()
    for match in matches:
        slug = match.strip()
        # Filter out non-path markers (e.g. "p. 9", "GBrain")
        if not slug or slug in ("p", "page", "GBrain", "gaps"):
            continue
        if any(c in slug for c in ("/", "\\", ".")) or len(slug) > 10:
            if slug not in seen:
                seen.add(slug)
                sources.append({"file": slug, "source_title": slug})
    return sources


def _is_meeting_source(source_file: str | None) -> bool:
    if not source_file:
        return False
    lower = source_file.lower()
    return any(marker in lower for marker in ["会议", "meeting", "audio", "transcript", ".mp4", ".mp3"])


# ── Core scoring ─────────────────────────────────────────────────────────


def score_case(
    case: RegressionCase,
    answer_text: str,
    sources: list[dict],
    *,
    service_unavailable: bool = False,
) -> RegressionResult:
    """Score one regression case against the GBrain think response.

    Returns a RegressionResult with the primary status classification.
    Classification priority (first match wins):
        service_unavailable > wrong_source > meeting_false_positive
        > missing_answer_point > missing_citation > known_gap/unexpected_pass > pass
    """
    result = RegressionResult(
        case_id=case.id,
        status="pass",
        answer_text=answer_text,
        first_hit_source=_first_hit_source_file(sources),
        first_hit_file_kind=_first_hit_file_kind(sources),
        citation=_extract_location_from_answer(answer_text, case.expected_location),
    )

    # Service unavailable
    if service_unavailable or not answer_text:
        result.status = "service_unavailable"
        result.error = "GBrain returned empty or error response"
        return result

    # Known gap: track but don't fail
    if case.expected_status == "known_gap":
        first_hit = result.first_hit_source or ""
        terms_all = case.expected_answer.get("required_terms_all", [])
        terms_any = case.expected_answer.get("required_terms_any", [])
        missing_all, missing_any = _check_terms(answer_text, terms_all, terms_any)

        # Negative answer detection: "未找到/无法确定/无法找到" → stay known_gap
        answer_lower = answer_text.lower()
        has_negative = any(p.lower() in answer_lower for p in _NEGATIVE_ANSWER_PATTERNS)

        # Check if fixture explicitly suppresses unexpected_pass (observational known_gap)
        suppress: bool = case.expected_answer.get("suppress_unexpected_pass", False)

        # Only mark unexpected_pass if ALL conditions are met:
        #   terms match + source matches expected + NOT negative + NOT suppressed
        source_matches = _source_matches_expected(first_hit, case.source_file)
        if not missing_all and not missing_any and first_hit and not has_negative and not suppress and source_matches:
            result.status = "unexpected_pass"
        else:
            result.status = "known_gap"
        result.missing_terms_all = missing_all
        result.missing_terms_any = missing_any
        return result

    # Wrong source: first hit doesn't match expected source or kind
    first_hit_source = result.first_hit_source or ""
    expected_source = case.source_file
    expected_kind = case.file_kind

    # Check meeting false positive: non-meeting question hitting meeting source
    is_meeting_query = case.file_kind in MEETING_FILE_KINDS
    first_hit_kind = result.first_hit_file_kind or ""
    first_hit_is_meeting = (
        first_hit_kind in MEETING_FILE_KINDS
        or _is_meeting_source(first_hit_source)
    )
    if not is_meeting_query and first_hit_is_meeting:
        result.meeting_false_positive = True

    # Negative answer detection: should_pass questions getting "not found" cannot pass
    if case.expected_status == "should_pass":
        answer_lower = answer_text.lower()
        is_negative = any(p.lower() in answer_lower for p in _NEGATIVE_ANSWER_PATTERNS)
        if is_negative:
            result.status = "missing_answer_point"
            result.error = "Answer is a negative/gap response (contains '未找到'/'cannot answer' etc.)"
            terms_all = case.expected_answer.get("required_terms_all", [])
            terms_any = case.expected_answer.get("required_terms_any", [])
            result.missing_terms_all, result.missing_terms_any = _check_terms(answer_text, terms_all, terms_any)
            return result

    # Wrong source: expected_kind vs first_hit_kind mismatch
    if expected_kind and first_hit_kind and not _kinds_match(expected_kind, first_hit_kind):
        result.status = "wrong_source"
        result.error = f"Expected file_kind={expected_kind}, got first_hit_kind={first_hit_kind}"
        terms_all = case.expected_answer.get("required_terms_all", [])
        terms_any = case.expected_answer.get("required_terms_any", [])
        result.missing_terms_all, result.missing_terms_any = _check_terms(answer_text, terms_all, terms_any)
        return result

    # Check answer terms
    terms_all = case.expected_answer.get("required_terms_all", [])
    terms_any = case.expected_answer.get("required_terms_any", [])
    missing_all, missing_any = _check_terms(answer_text, terms_all, terms_any)

    if missing_all:
        result.status = "missing_answer_point"
        result.missing_terms_all = missing_all
        result.missing_terms_any = missing_any
        return result

    # Source requirement: should_pass must have matching source
    if case.expected_status == "should_pass":
        if not result.first_hit_source:
            result.status = "missing_citation"
            result.error = "should_pass requires non-empty source evidence"
            return result
        if not _source_matches_expected(result.first_hit_source, case.source_file):
            result.status = "wrong_source"
            result.error = f"Expected source={case.source_file}, got first_hit={result.first_hit_source}"
            return result

    # Citation check
    if not result.citation or not result.citation.get("matched"):
        result.status = "missing_citation"
        return result

    # All checks passed
    return result


def _kinds_match(expected: str, actual: str) -> bool:
    """Check if two file_kind values match (e.g. image == image, pdf_drawing ≈ pdf_drawing)."""
    if expected == actual:
        return True
    # Broader grouping: pdf_drawing can match pdf_drawing / pdf / pdf_schedule
    if expected.startswith("pdf_") and actual in ("pdf",):
        return True
    if actual.startswith("pdf_") and expected in ("pdf",):
        return True
    # meeting_transcript_docx vs meeting_media are both meeting
    if expected.startswith("meeting_") and actual.startswith("meeting_"):
        return True
    return False


def _extract_location_from_answer(answer_text: str, expected_location: dict) -> dict | None:
    """Try to find location evidence in the answer text.

    Returns a dict with {matched: bool, location_type: str, evidence: str | None}.
    Currently checks if page number / sheet name / region appears in answer text.
    """
    location_type = expected_location.get("type", "unknown")
    location_value = expected_location.get("value", "")
    strict = expected_location.get("strict", False)

    if location_type == "unknown" or not location_value:
        return {"matched": True, "location_type": location_type, "evidence": None}

    if location_type == "page":
        # Look for page number reference
        page_str = str(location_value)
        if page_str in answer_text or f"p.{page_str}" in answer_text or f"p {page_str}" in answer_text or f"第{page_str}页" in answer_text:
            return {"matched": True, "location_type": "page", "evidence": page_str}
        # Broader: look for "page" + number
        if re.search(rf"(?:page|p\.?)\s*{re.escape(page_str)}", answer_text, re.IGNORECASE):
            return {"matched": True, "location_type": "page", "evidence": page_str}

    if location_type in ("sheet", "region", "text_span", "timestamp"):
        value_lower = str(location_value).lower()
        if value_lower in answer_text.lower():
            return {"matched": True, "location_type": location_type, "evidence": str(location_value)}

    if strict:
        return {"matched": False, "location_type": location_type, "evidence": None}

    # Non-strict: skip citation failure if location is hard to verify in answer text alone
    return {"matched": True, "location_type": location_type, "evidence": None}


# ── Runner ────────────────────────────────────────────────────────────────


def run_regression(
    cases: list[RegressionCase],
    query_fn: QueryFn,
    *,
    mode: str = "query",
    source_id: str = "",
) -> RegressionReport:
    """Run regression against a live query function.

    Args:
        cases: List of regression cases to evaluate.
        query_fn: Callable that takes a query string and returns a dict
            compatible with GBrain think response format
            {ok, reply, sources: [{file, file_kind, ...}], ...}.
        mode: 'query' or 'think'.
        source_id: GBrain source ID being tested.

    Returns:
        RegressionReport with per-case results and aggregated summary.
    """
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    results: list[RegressionResult] = []

    for case in cases:
        try:
            response = query_fn(case.query)
        except Exception as exc:
            results.append(
                RegressionResult(
                    case_id=case.id,
                    status="service_unavailable",
                    error=str(exc),
                )
            )
            continue

        # GBrain adapter returns status="ok" but may not set ok=True explicitly
        response_status = response.get("status", "")
        ok = bool(response.get("ok")) or response_status == "ok"
        service_unavailable = not ok or response_status in ("adapter_error", "error", "unreachable")

        answer_text = _extract_answer_text(response) if not service_unavailable else ""
        sources = _extract_sources(response, answer_text=answer_text) if not service_unavailable else []

        result = score_case(
            case,
            answer_text,
            sources,
            service_unavailable=service_unavailable,
        )
        results.append(result)

    summary = _build_summary(results, cases)
    known_gaps = [r.case_id for r in results if r.status == "known_gap"]

    return RegressionReport(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_id=source_id,
        mode=mode,
        summary=summary,
        results=results,
        known_gaps=known_gaps,
    )


def _build_summary(results: list[RegressionResult], cases: list[RegressionCase]) -> dict:
    counts: Counter[str] = Counter()
    for r in results:
        counts[r.status] += 1

    should_pass_cases = [c for c in cases if c.expected_status == "should_pass"]
    should_pass_results = [r for r in results if r.case_id in {c.id for c in should_pass_cases}]
    should_pass_ok = sum(1 for r in should_pass_results if r.status == "pass")
    should_pass_total = len(should_pass_cases)

    meeting_fp_count = sum(1 for r in results if r.meeting_false_positive)

    return {
        "total": len(cases),
        "pass": counts.get("pass", 0),
        "fail": counts.get("wrong_source", 0)
        + counts.get("missing_answer_point", 0)
        + counts.get("missing_citation", 0),
        "wrong_source": counts.get("wrong_source", 0),
        "missing_answer_point": counts.get("missing_answer_point", 0),
        "missing_citation": counts.get("missing_citation", 0),
        "known_gap": counts.get("known_gap", 0),
        "unexpected_pass": counts.get("unexpected_pass", 0),
        "service_unavailable": counts.get("service_unavailable", 0),
        "meeting_false_positive": meeting_fp_count,
        "should_pass_ok": should_pass_ok,
        "should_pass_total": should_pass_total,
        "pass_rate_should_pass": f"{should_pass_ok}/{should_pass_total} = {100 * should_pass_ok / max(should_pass_total, 1):.0f}%",
    }


# ── Report serialization ────────────────────────────────────────────────


def regression_report_to_dict(report: RegressionReport) -> dict:
    return {
        "run_id": report.run_id,
        "generated_at": report.generated_at,
        "source_id": report.source_id,
        "mode": report.mode,
        "summary": report.summary,
        "results": [
            {
                "case_id": r.case_id,
                "status": r.status,
                "first_hit_source": r.first_hit_source,
                "first_hit_file_kind": r.first_hit_file_kind,
                "answer_text": r.answer_text[:500] if r.answer_text else None,
                "citation": r.citation,
                "missing_terms_all": r.missing_terms_all,
                "missing_terms_any": r.missing_terms_any,
                "meeting_false_positive": r.meeting_false_positive,
                "error": r.error,
            }
            for r in report.results
        ],
        "known_gaps": report.known_gaps,
    }
