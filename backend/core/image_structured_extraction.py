from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.llm import LLMClient, LLMConfigurationError, get_llm_client
from core.preprocess_model_policy import ensure_mimo_v2_5_model, ensure_profile_allowed


LANGUAGE_POLICY = "bilingual_zh_en_aligned"
EXTRACTION_STATUS = "image_structured_extract"
EXTRACTOR_NAME = "project_r_mimo_image_extraction_mvp"
SKILL_NAME = "image-screenshot-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-image-screenshot-v1"
DEFAULT_MODEL_PROFILE = "mimo-v2-5"
DEFAULT_MAX_RAW_BYTES = 10_000_000
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


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
    content_blocks: list[dict[str, Any]] = [
        {
            "type": "image_url",
            "image_url": {"url": _data_uri(source_path)},
        },
        {"type": "text", "text": _image_prompt(source_path.name)},
    ]
    response = client.complete(
        [{"role": "user", "content": content_blocks}],
        system_prompt="You extract business knowledge from screenshots and images without inventing facts.",
        temperature=options.temperature,
    )
    markdown = _normalize_markdown(response.text, source_path.stem)
    return ImageStructuredExtractionResult(
        markdown=markdown,
        model_profile=client.settings.profile or options.model_profile,
        provider=client.settings.provider,
        model=response.model or client.settings.model,
        token_usage=response.usage,
    )


def _image_prompt(file_name: str) -> str:
    return f"""请把这张图片或截图提炼为 Project_R 可入库的结构化 Markdown。

文件名：{file_name}

要求：
- 不要编造图片中没有的信息。
- 如果是流程、审批规则、表格、聊天截图、邮件截图或图纸截图，请提取可稳定识别的事实、步骤、字段、责任人、风险和待确认项。
- 所有结论必须中英文对齐，且中英文表达同一事实。
- 看不清的区域写入“待确认 / Review Questions”，不要当作事实。
- 输出 Markdown，不要输出 YAML frontmatter。

建议结构：
# 标题
## 图片定位 / Image Positioning
## 稳定事实 / Stable Facts
## 流程或字段 / Process or Fields
## 风险与待确认 / Risks and Review Questions
## 可沉淀知识候选 / Knowledge Candidates
"""


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
