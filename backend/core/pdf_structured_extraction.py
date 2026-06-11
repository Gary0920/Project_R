from __future__ import annotations

import base64
import mimetypes
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from core.llm import LLMClient, LLMConfigurationError, get_llm_client
from app.features.preprocessing.policy import ensure_mimo_v2_5_model, ensure_profile_allowed


DEFAULT_MODEL_PROFILE = "mimo-v2-5"
DEFAULT_BATCH_MAX_CHARS = 28_000
DEFAULT_MAX_PAGES = 0
DEFAULT_TEMPERATURE = 0.1
LANGUAGE_POLICY = "bilingual_zh_en_aligned"
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
SKILL_NAME = "pdf-structured-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-pdf-structured-v1"

# Phase 4: PDF subkind detection patterns
_PDF_SUBKIND_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"window.schedule|ws\b", re.IGNORECASE), "drawing_window_schedule", "pdf-drawing-ws"),
    (re.compile(r"facade.supply.programme|programme|排期", re.IGNORECASE), "drawing_schedule", "pdf-drawing-schedule"),
    (re.compile(r"shop.drawing", re.IGNORECASE), "drawing_shop_drawing", "pdf-drawing-sd"),
    (re.compile(r"floor.plan|平面图|elevation|立面图|general.arrangement", re.IGNORECASE), "drawing_general_arrangement", "pdf-drawing-ga"),
]
_SUBKIND_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"

SYSTEM_PROMPT = """你是 Project_R 的 PDF 结构化资料提炼 Agent。

你的任务不是抄写 PDF，也不是把抽取出的碎片文本重新排版，而是把 PDF 中稳定、可复用、可被业务人员检索的问题答案提炼成可审阅 Markdown。

硬性要求：
- 最终知识页必须中英文并存，且中英文表达同一事实；英文不得新增中文没有的信息，中文不得省略英文信息。
- 每个标题、关键结论、表格行、风险项和待审核问题都要有中文与 English 对应表达。
- 保留必要英文标准名、条款名、参数名；中文解释用于业务使用，English 用于检索、复核和与英文源文件对照。
- 不要逐段照抄原文；只允许短语级引用。
- 每条关键要求尽量标注页码，例如 `(p. 12)` 或 `(pp. 12-14)`。
- 对无法确认、疑似表格错位、图示依赖、OCR/抽取异常的内容，必须放入“待审核问题”。
- 不能编造 PDF 中没有的事实。
- 输出 Markdown 正文，不要输出 YAML frontmatter，不要包裹代码块。
"""


# ── Phase 4: Subkind detection ────────────────────────────────────────────


def _detect_pdf_subkind(filename: str) -> tuple[str, str | None]:
    """Detect PDF subkind from filename.

    Returns (subkind, prompt_key) where subkind is one of:
        drawing_window_schedule, drawing_schedule, drawing_shop_drawing,
        drawing_general_arrangement, general_pdf
    And prompt_key is the prompt filename stem (or None for general).
    """
    name = Path(filename).stem.lower().replace("_", " ").replace("-", " ")
    for pattern, subkind, prompt_key in _PDF_SUBKIND_RULES:
        if pattern.search(name):
            return subkind, prompt_key
    return "general_pdf", None


def _load_subkind_prompt(prompt_key: str | None) -> str | None:
    """Load a subkind-specific prompt file from prompts/ directory."""
    if prompt_key is None:
        return None
    prompt_path = _SUBKIND_PROMPT_DIR / f"{prompt_key}.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return None


# ── Phase 4: Validation ───────────────────────────────────────────────────


def validate_pdf_extraction(
    markdown: str,
    pdf_path: Path,
    subkind: str,
) -> dict[str, Any]:
    """Validate PDF extraction quality.

    Returns dict with:
        review_status: "approved" | "needs_review"
        warnings: list[str]
        checks: dict of check_name → bool
    """
    checks: dict[str, bool] = {}
    warnings: list[str] = []
    md_lower = markdown.lower()

    if subkind == "drawing_window_schedule":
        has_window_id = bool(re.search(r"w\d+", md_lower))
        has_dimension = bool(re.search(r"(width|height|宽|高|尺寸)", md_lower))
        has_page_ref = bool(re.search(r"p\.?\s*\d+|第\d+页|page\s*\d+", md_lower))
        checks["has_window_ids"] = has_window_id
        checks["has_dimensions"] = has_dimension
        checks["has_page_references"] = has_page_ref
        if not has_window_id:
            warnings.append("Window schedule: no W-prefix window IDs found")
        if not has_dimension:
            warnings.append("Window schedule: no width/height dimensions found")

    elif subkind == "drawing_schedule":
        has_duration = bool(re.search(r"(duration|天|天数|工期)", md_lower))
        has_finish = bool(re.search(r"(finish|完成日期|计划完成)", md_lower))
        has_task_name = bool(re.search(r"(task|shop.drawing|任务)", md_lower))
        checks["has_duration"] = has_duration
        checks["has_finish_date"] = has_finish
        checks["has_task_names"] = has_task_name
        if not has_duration and not has_finish:
            warnings.append("Schedule: no Duration or Finish date found")

    elif subkind in ("drawing_general_arrangement", "drawing_shop_drawing"):
        has_page_ref = bool(re.search(r"p\.?\s*\d+|第\d+页|page\s*\d+", md_lower))
        has_level = bool(re.search(r"(level\s+\d+|floor\s+\d+|l\d+|楼层|第.层)", md_lower))
        checks["has_page_references"] = has_page_ref
        checks["has_level_info"] = has_level
        if not has_page_ref:
            warnings.append("Drawing: no page references found")

    review_status = "needs_review" if warnings else "approved"
    return {
        "review_status": review_status,
        "warnings": warnings,
        "checks": checks,
    }


@dataclass(frozen=True)
class PDFExtractionOptions:
    model_profile: str = DEFAULT_MODEL_PROFILE
    batch_max_chars: int = DEFAULT_BATCH_MAX_CHARS
    max_pages: int = DEFAULT_MAX_PAGES
    temperature: float = DEFAULT_TEMPERATURE
    vision_pages: tuple[int, ...] = ()
    vision_page_mode: str = "manual"
    max_vision_pages: int = 8
    vision_dpi: int = 120


@dataclass(frozen=True)
class PDFPageText:
    number: int
    text: str


@dataclass(frozen=True)
class PDFStructuredExtractionResult:
    markdown: str
    page_count: int
    pages_analyzed: int
    extraction_status: str = "pdf_structured_mvp_pending_review"
    review_status: str = "pending_review"
    extractor: str = "project_r_pdf_structured_mvp"
    language_policy: str = LANGUAGE_POLICY
    model_profile: str | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    vision_pages: tuple[int, ...] = ()
    vision_image_count: int = 0
    # Phase 4: PDF subkind and validation
    pdf_subkind: str = "general_pdf"
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _Batch:
    index: int
    start_page: int
    end_page: int
    text: str


def load_pdf_extraction_options() -> PDFExtractionOptions:
    raw_vision_pages = os.getenv("GBRAIN_PDF_EXTRACTOR_VISION_PAGES", "")
    vision_page_mode = "auto" if raw_vision_pages.strip().lower() == "auto" else "manual"
    model_profile = os.getenv("GBRAIN_PDF_EXTRACTOR_MODEL_PROFILE", DEFAULT_MODEL_PROFILE).strip() or DEFAULT_MODEL_PROFILE
    ensure_profile_allowed(model_profile, route_name=SKILL_NAME)
    return PDFExtractionOptions(
        model_profile=model_profile,
        batch_max_chars=_env_int("GBRAIN_PDF_EXTRACTOR_BATCH_MAX_CHARS", DEFAULT_BATCH_MAX_CHARS, 8_000, 80_000),
        max_pages=_env_int("GBRAIN_PDF_EXTRACTOR_MAX_PAGES", DEFAULT_MAX_PAGES, 0, 10_000),
        temperature=_env_float("GBRAIN_PDF_EXTRACTOR_TEMPERATURE", DEFAULT_TEMPERATURE, 0.0, 1.0),
        vision_pages=() if vision_page_mode == "auto" else _parse_page_list(raw_vision_pages),
        vision_page_mode=vision_page_mode,
        max_vision_pages=_env_int("GBRAIN_PDF_EXTRACTOR_MAX_VISION_PAGES", 8, 1, 20),
        vision_dpi=_env_int("GBRAIN_PDF_EXTRACTOR_VISION_DPI", 120, 72, 200),
    )


def extract_pdf_structured_markdown(
    source_path: Path,
    *,
    options: PDFExtractionOptions | None = None,
    llm_client: LLMClient | None = None,
) -> PDFStructuredExtractionResult:
    options = options or load_pdf_extraction_options()
    client = llm_client or get_llm_client(options.model_profile)
    if not client.settings.configured:
        raise LLMConfigurationError(
            f"PDF structured extraction model profile is not configured: {options.model_profile}"
        )
    ensure_mimo_v2_5_model(client.settings, route_name=SKILL_NAME)

    pages = _read_pdf_pages(source_path)
    selected_pages = pages[: options.max_pages] if options.max_pages > 0 else pages
    if not selected_pages:
        raise ValueError("PDF reader returned no pages")

    batches = _build_batches(selected_pages, options.batch_max_chars)
    warnings: list[str] = []
    summaries: list[str] = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for batch in batches:
        response = client.complete(
            [{"role": "user", "content": _batch_prompt(source_path.name, batch, len(batches))}],
            system_prompt=SYSTEM_PROMPT,
            temperature=options.temperature,
        )
        summaries.append(_strip_markdown_wrapper(response.text))
        _merge_usage(usage, response.usage)

    vision_pages = options.vision_pages
    if options.vision_page_mode == "auto":
        vision_pages = _select_vision_pages(selected_pages, options.max_vision_pages)
    image_inputs = _load_optional_page_images(
        source_path,
        vision_pages,
        options,
        client.settings.supports_vision,
        warnings,
    )
    final_prompt = _final_prompt(
        source_path.name,
        page_count=len(pages),
        pages_analyzed=len(selected_pages),
        summaries=summaries,
        used_vision=bool(image_inputs),
        vision_pages=vision_pages,
    )
    final_message: dict[str, Any] = {"role": "user", "content": final_prompt}
    if image_inputs:
        final_message["content"] = _build_vision_content_blocks(final_prompt, image_inputs, client.settings.provider)

    try:
        final_response = client.complete(
            [final_message],
            system_prompt=SYSTEM_PROMPT,
            temperature=options.temperature,
        )
    except Exception as exc:
        if not image_inputs:
            raise
        warnings.append(f"vision-assisted final synthesis failed and retried without images: {exc}")
        final_response = client.complete(
            [{"role": "user", "content": final_prompt}],
            system_prompt=SYSTEM_PROMPT,
            temperature=options.temperature,
        )
    _merge_usage(usage, final_response.usage)
    markdown = _normalize_final_markdown(_strip_markdown_wrapper(final_response.text), source_path.stem)
    _assert_bilingual_markdown(markdown)

    # Phase 4: Subkind detection + validation
    pdf_subkind, prompt_key = _detect_pdf_subkind(source_path.name)
    validation = validate_pdf_extraction(markdown, source_path, pdf_subkind)
    all_warnings = list(warnings) + validation.get("warnings", [])
    review_status = validation.get("review_status", "pending_review")

    return PDFStructuredExtractionResult(
        markdown=markdown,
        page_count=len(pages),
        pages_analyzed=len(selected_pages),
        review_status=review_status,
        model_profile=client.settings.profile or options.model_profile,
        provider=client.settings.provider,
        model=client.settings.model,
        token_usage=usage,
        warnings=tuple(all_warnings),
        vision_pages=vision_pages,
        vision_image_count=len(image_inputs),
        pdf_subkind=pdf_subkind,
        validation=validation,
    )


def _read_pdf_pages(source_path: Path) -> list[PDFPageText]:
    reader = PdfReader(str(source_path))
    pages: list[PDFPageText] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = _clean_page_text(page.extract_text() or "")
        if not text:
            text = "[No selectable text was extracted from this page; use vision/OCR evidence where available.]"
        pages.append(PDFPageText(page_number, text))
    return pages


def _clean_page_text(text: str) -> str:
    text = text.replace("\x00", " ")
    cleaned_lines: list[str] = []
    previous_blank = False
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t\f\v]+", " ", raw_line).strip()
        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False
    return "\n".join(cleaned_lines).strip()


def _build_batches(pages: list[PDFPageText], batch_max_chars: int) -> list[_Batch]:
    batches: list[_Batch] = []
    current: list[str] = []
    start_page = pages[0].number
    end_page = pages[0].number
    current_len = 0

    for page in pages:
        block = f"\n\n[Page {page.number}]\n{page.text}"
        if current and current_len + len(block) > batch_max_chars:
            batches.append(
                _Batch(
                    index=len(batches) + 1,
                    start_page=start_page,
                    end_page=end_page,
                    text="".join(current).strip(),
                )
            )
            current = []
            current_len = 0
            start_page = page.number

        current.append(block)
        current_len += len(block)
        end_page = page.number

    if current:
        batches.append(
            _Batch(
                index=len(batches) + 1,
                start_page=start_page,
                end_page=end_page,
                text="".join(current).strip(),
            )
        )
    return batches


def _batch_prompt(file_name: str, batch: _Batch, batch_count: int) -> str:
    return f"""请对下面 PDF 页文本做“中间提炼笔记”，用于后续合成最终知识页。

文件名：{file_name}
批次：{batch.index}/{batch_count}
页码范围：p. {batch.start_page} - p. {batch.end_page}

请输出以下结构：
## 页码范围
## 本批主要章节/条款
## 关键要求与参数
## 表格/图示信息
## 适用条件与风险
## 待审核问题

只提炼与业务检索有用的信息，不要照抄原文。

<pdf_page_text>
{batch.text}
</pdf_page_text>
"""


def _select_vision_pages(pages: list[PDFPageText], limit: int) -> tuple[int, ...]:
    if not pages or limit <= 0:
        return ()

    selected: list[int] = []

    def add(page_number: int) -> None:
        if 1 <= page_number <= pages[-1].number and page_number not in selected:
            selected.append(page_number)

    add(pages[0].number)

    for page in pages[:12]:
        lowered = page.text.lower()
        if "contents" in lowered or "table of contents" in lowered:
            add(page.number)
            if len(selected) >= max(2, limit // 3):
                break

    if limit >= 4:
        evenly_spaced = [
            pages[round((len(pages) - 1) * ratio)].number
            for ratio in (0.25, 0.5, 0.75)
            if len(pages) > 1
        ]
        for page_number in evenly_spaced:
            add(page_number)

    scored: list[tuple[int, int]] = []
    for page in pages:
        lowered = page.text.lower()
        score = 0
        score += 4 * len(re.findall(r"\b(table|figure|appendix|diagram|schedule)\b", lowered))
        score += 3 * len(re.findall(r"\b(requirement|test|classification|performance|design|installation)\b", lowered))
        score += min(6, len(re.findall(r"\d+(?:\.\d+)?", page.text)) // 10)
        if len(page.text) < 700:
            score += 2
        if score > 0:
            scored.append((score, page.number))

    for _, page_number in sorted(scored, reverse=True):
        add(page_number)
        if len(selected) >= limit:
            break

    return tuple(sorted(selected[:limit]))


def _final_prompt(
    file_name: str,
    *,
    page_count: int,
    pages_analyzed: int,
    summaries: list[str],
    used_vision: bool,
    vision_pages: tuple[int, ...],
) -> str:
    joined_summaries = "\n\n---\n\n".join(
        f"## Batch {index}\n{summary}" for index, summary in enumerate(summaries, start=1)
    )
    vision_page_note = ", ".join(str(page) for page in vision_pages) if vision_pages else "none"
    vision_note = (
        f"已附加选定页面图片（页码：{vision_page_note}），请结合图片检查封面、目录、表格或版式。"
        if used_vision
        else f"本次未附加页面图片（请求页码：{vision_page_note}）；请基于文本中间提炼结果输出，并标注版式/表格不确定性。"
    )
    return f"""请把 PDF 中间提炼笔记合成为一篇 Project_R / GBrain 可导入的结构化 Markdown 知识页。

文件名：{file_name}
总页数：{page_count}
已分析页数：{pages_analyzed}
视觉辅助：{vision_note}
语言规则：最终知识页必须中英文并存，且中英文表达同一事实。任何中文事实都必须有 English 等义表达；任何 English fact 都必须有中文等义表达。不要让两个语言版本的信息不对称。

输出必须使用以下一级结构：
# {Path(file_name).stem}

## 审核状态 / Review Status
使用项目符号，每条采用 `- 中文：...` 下一行 `  English: ...` 的成对格式。说明这是 PDF 结构化提炼 MVP 生成，状态为 pending_review，并列出原始页数、已分析页数、是否使用视觉辅助、视觉辅助页码。

## 文档定位 / Document Positioning
使用成对段落或表格说明文档类型、适用范围、在公司业务中大概用于什么场景。每个信息单元必须中英对齐。

## 核心结论 / Key Conclusions
用 5-10 条总结最值得检索的内容。每条必须采用：
`- 中文：... (p. X)`
`  English: ... (p. X)`

## 章节与条款结构 / Section and Clause Structure
按章节、条款或主题整理。每项尽量带页码。每项必须中英对齐。

## 关键要求与参数 / Key Requirements and Parameters
优先用表格整理技术要求、限制、数值、测试/合规要求。表格必须包含这些列：
`| 类别 / Category | 中文要求 / Chinese Requirement | English Equivalent | 页码 / Pages |`

## Project_R 业务使用建议 / Project_R Business Use
说明销售、项目、技术、采购或质量人员何时应该查这份资料。每条必须中英对齐。

## 风险与适用边界 / Risks and Applicability Boundaries
说明误用风险、过期风险、需要专业确认的部分。每条必须中英对齐。

## 待审核问题 / Review Questions
列出无法确认、疑似表格错位、图示依赖、需要人工复核的点。每条必须中英对齐。

不要输出 YAML frontmatter。不要输出代码块。不要逐段复刻原文。
如果某个信息无法可靠翻译成另一种语言，不要单语输出；请把它放进“待审核问题 / Review Questions”。

<batch_summaries>
{joined_summaries}
</batch_summaries>
"""


def _load_optional_page_images(
    source_path: Path,
    page_numbers: tuple[int, ...],
    options: PDFExtractionOptions,
    supports_vision: bool,
    warnings: list[str],
) -> list[dict[str, str]]:
    if not page_numbers:
        return []
    if not supports_vision:
        warnings.append("vision pages requested but selected model profile does not support vision")
        return []

    sidecar_images = _load_sidecar_page_images(source_path, page_numbers, warnings)
    if sidecar_images:
        return sidecar_images

    try:
        import fitz  # type: ignore
    except Exception:
        warnings.append("vision pages requested but PyMuPDF is not installed")
        return []

    images: list[dict[str, str]] = []
    try:
        document = fitz.open(str(source_path))
        for page_number in page_numbers:
            if page_number < 1 or page_number > document.page_count:
                warnings.append(f"vision page out of range: {page_number}")
                continue
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(dpi=options.vision_dpi, alpha=False)
            images.append(
                {
                    "media_type": "image/png",
                    "data": base64.b64encode(pixmap.tobytes("png")).decode("ascii"),
                }
            )
    except Exception as exc:
        warnings.append(f"failed to render PDF vision pages: {exc}")
    return images


def _load_sidecar_page_images(
    source_path: Path,
    page_numbers: tuple[int, ...],
    warnings: list[str],
) -> list[dict[str, str]]:
    image_dir = _find_pdf_image_sidecar_dir(source_path)
    if image_dir is None:
        return []

    indexed: dict[int, Path] = {}
    for candidate in image_dir.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        page_number = _page_number_from_image_name(candidate.stem)
        if page_number is not None and page_number not in indexed:
            indexed[page_number] = candidate

    images: list[dict[str, str]] = []
    for page_number in page_numbers:
        image_path = indexed.get(page_number)
        if image_path is None:
            warnings.append(f"vision sidecar image not found for page {page_number}")
            continue
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        images.append(
            {
                "media_type": media_type,
                "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            }
        )
    return images


def _find_pdf_image_sidecar_dir(source_path: Path) -> Path | None:
    for candidate in _pdf_image_sidecar_candidates(source_path):
        if candidate.is_dir():
            return candidate
    return None


def _pdf_image_sidecar_candidates(source_path: Path) -> list[Path]:
    return [
        source_path.with_suffix(""),
        source_path.parent / _slug_for_sidecar(source_path.stem),
    ]


def _slug_for_sidecar(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z]+", "-", value).strip("-")
    return slug or "untitled"


def _page_number_from_image_name(stem: str) -> int | None:
    match = re.search(r"(\d+)$", stem)
    if not match:
        return None
    try:
        page_number = int(match.group(1))
    except ValueError:
        return None
    return page_number if page_number > 0 else None


def _build_vision_content_blocks(
    text: str,
    images: list[dict[str, str]],
    provider: str,
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if provider == "claude":
        blocks.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data"],
                },
            }
            for image in images
        )
    else:
        blocks.extend(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image['media_type']};base64,{image['data']}"},
            }
            for image in images
        )
    return blocks


def _strip_markdown_wrapper(text: str) -> str:
    value = text.strip()
    fence_match = re.match(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", value, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        value = fence_match.group(1).strip()
    value = re.sub(r"^---\s*\n.*?\n---\s*\n", "", value, flags=re.DOTALL).strip()
    return value


def _normalize_final_markdown(markdown: str, title: str) -> str:
    if not markdown.lstrip().startswith("# "):
        markdown = f"# {title}\n\n{markdown.strip()}"
    return markdown.rstrip() + "\n"


def _assert_bilingual_markdown(markdown: str) -> None:
    has_cjk = re.search(r"[\u4e00-\u9fff]", markdown) is not None
    english_markers = len(re.findall(r"\bEnglish\b|English Equivalent|Review Status|Key Conclusions", markdown))
    chinese_markers = len(re.findall(r"中文|中英|审核状态|核心结论", markdown))
    if not has_cjk or english_markers < 3 or chinese_markers < 3:
        raise ValueError("PDF structured extraction did not satisfy bilingual zh/en alignment policy")


def _merge_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    total["input_tokens"] = int(total.get("input_tokens", 0)) + int(usage.get("input_tokens", 0))
    total["output_tokens"] = int(total.get("output_tokens", 0)) + int(usage.get("output_tokens", 0))


def _parse_page_list(raw: str) -> tuple[int, ...]:
    pages: list[int] = []
    for part in raw.split(","):
        value = part.strip()
        if not value:
            continue
        try:
            page = int(value)
        except ValueError:
            continue
        if page > 0 and page not in pages:
            pages.append(page)
    return tuple(pages[:5])


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(max(value, minimum), maximum)
