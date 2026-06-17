from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from app.features.knowledge.gbrain import (
    GBrainSettings,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from app.features.knowledge.gbrain.ingest import _split_frontmatter

MAX_EVIDENCE_EXCERPT_CHARS = 800
SOURCE_SLUG_FIELDS = ("source_slug", "page_slug", "slug")
FRONTMATTER_SLUG_FIELDS = (
    "gbrain_source_slug",
    "project_r_source_slug",
    "source_slug",
    "page_slug",
    "slug",
)
FRONTMATTER_SOURCE_ID_FIELDS = ("gbrain_source_id", "source_id", "project_r_source_id")
FRONTMATTER_ORIGINAL_FILE_FIELDS = ("project_r_source_file", "source_file", "original_source_file")


def enrich_sources_with_evidence(
    sources: list[dict],
    *,
    settings: GBrainSettings,
    workspace: Any | None,
) -> list[dict]:
    for source in sources:
        try:
            enrich_source_with_evidence(source, settings=settings, workspace=workspace)
        except Exception:
            source["metadata_only"] = True
            source.setdefault("evidence_excerpt", None)
            source.setdefault("display_title", _safe_display_fallback(source))
    return sources


def enrich_source_with_evidence(source: dict, *, settings: GBrainSettings, workspace: Any | None) -> dict:
    source_id = _source_id(source)
    slug = _source_slug(source)
    source["source_slug"] = slug or None
    source["page_slug"] = str(source.get("page_slug") or slug or "").strip() or None
    source["metadata_only"] = True
    source.setdefault("evidence_excerpt", None)
    source.setdefault("original_source_file", None)
    source.setdefault("locator_label", _locator_label(source))
    source.setdefault("display_title", _safe_display_fallback(source))
    if not source_id or not slug:
        return source

    root = _allowed_root_for_source(source_id, settings=settings, workspace=workspace)
    if root is None:
        return source

    match = _find_markdown(root, slug, source_id=source_id)
    if match is None:
        return source

    rel_path, path = match
    text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, body = _split_frontmatter(text)
    excerpt = _evidence_excerpt(body, source.get("row_num"))
    if not excerpt:
        return source

    original_source_file = _safe_original_source_file(frontmatter)
    source.update(
        {
            "derived_file": rel_path,
            "display_title": _display_title(frontmatter, original_source_file, rel_path),
            "evidence_excerpt": excerpt,
            "metadata_only": False,
            "original_source_file": original_source_file,
            "locator_label": _locator_label(source, rel_path=rel_path),
        }
    )
    if original_source_file:
        source["source_file"] = original_source_file
    if not str(source.get("content") or "").strip():
        source["content"] = excerpt
    return source


def _allowed_root_for_source(source_id: str, *, settings: GBrainSettings, workspace: Any | None) -> Path | None:
    normalized = source_id.strip().lower()
    if normalized in {settings.company_source_id.lower(), "company", "company-wiki"}:
        return settings.derived_path

    workspace_kind = str(getattr(workspace, "workspace_kind", "") or "").strip().lower()
    if workspace is not None and workspace_kind == "project":
        try:
            if normalized == project_source_id_for_workspace(workspace).lower():
                return project_source_paths_for_workspace(workspace)["derived"]
        except ValueError:
            return None

    if workspace is not None and workspace_kind == "customer":
        try:
            customer_source_id = customer_source_id_for_workspace(workspace).lower()
        except ValueError:
            customer_source_id = ""
        if normalized in {customer_source_id, "customer", "crm", "customer-crm"}:
            return customer_source_paths_for_workspace(workspace)["derived"]

    return None


def _find_markdown(root: Path, slug: str, *, source_id: str) -> tuple[str, Path] | None:
    resolved_root = root.resolve()
    if not resolved_root.exists():
        return None

    direct = _safe_markdown_path(resolved_root, slug)
    if direct is not None and direct.exists() and direct.is_file():
        return direct.relative_to(resolved_root).as_posix(), direct

    slug_key = _slug_key(slug)
    exact_index: dict[str, list[tuple[str, Path]]] = {}
    original_stems: dict[str, list[tuple[str, Path]]] = {}

    for path in resolved_root.rglob("*.md"):
        if any(part in {".git", ".pending_review"} for part in path.parts):
            continue
        try:
            rel = path.relative_to(resolved_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="ignore")
            frontmatter, _ = _split_frontmatter(text)
        except Exception:
            continue
        _add_index(exact_index, rel.lower(), rel, path)
        _add_index(exact_index, rel.removesuffix(".md").lower(), rel, path)
        _add_index(exact_index, _slug_key(rel.removesuffix(".md")), rel, path)
        if _frontmatter_source_matches(frontmatter, source_id):
            for field in FRONTMATTER_SLUG_FIELDS:
                value = str(frontmatter.get(field) or "").strip()
                if value:
                    _add_index(exact_index, value.lower(), rel, path)
                    _add_index(exact_index, _slug_key(value), rel, path)
        original = _safe_original_source_file(frontmatter)
        if original:
            _add_index(original_stems, Path(original).stem.lower(), rel, path)

    match = _unique_match(exact_index.get(slug.lower()))
    if match is not None:
        return match
    match = _unique_match(exact_index.get(slug_key))
    if match is not None:
        return match
    return _unique_match(original_stems.get(Path(slug).stem.lower()))


def _safe_markdown_path(root: Path, slug: str) -> Path | None:
    clean = slug.strip().replace("\\", "/").strip("/")
    if not clean or PurePosixPath(clean).is_absolute() or ".." in PurePosixPath(clean).parts:
        return None
    candidate = root / clean
    if candidate.suffix.lower() != ".md":
        candidate = candidate.with_suffix(".md")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
        return resolved
    except Exception:
        return None


def _frontmatter_source_matches(frontmatter: dict[str, Any], source_id: str) -> bool:
    for field in FRONTMATTER_SOURCE_ID_FIELDS:
        if str(frontmatter.get(field) or "").strip().lower() == source_id.lower():
            return True
    return False


def _evidence_excerpt(body: str, row_num: object) -> str:
    lines = body.splitlines()
    row = _row_number(row_num)
    paragraph = _paragraph_near_row(lines, row) if row is not None else ""
    if not paragraph:
        paragraph = _first_body_paragraph(lines)
    return _trim_excerpt(paragraph)


def _paragraph_near_row(lines: list[str], row: int) -> str:
    index = max(0, min(len(lines) - 1, row - 1))
    for cursor in range(index, min(len(lines), index + 8)):
        if _usable_body_line(lines[cursor]):
            return _collect_paragraph(lines, cursor)
    for cursor in range(index - 1, max(-1, index - 8), -1):
        if _usable_body_line(lines[cursor]):
            return _collect_paragraph(lines, cursor)
    return ""


def _first_body_paragraph(lines: list[str]) -> str:
    for index, line in enumerate(lines):
        if _usable_body_line(line):
            return _collect_paragraph(lines, index)
    return ""


def _collect_paragraph(lines: list[str], index: int) -> str:
    start = index
    while start > 0 and _usable_body_line(lines[start - 1]):
        start -= 1
    end = index + 1
    while end < len(lines) and _usable_body_line(lines[end]):
        end += 1
    return "\n".join(line.strip() for line in lines[start:end]).strip()


def _usable_body_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if re.match(r"^[A-Za-z0-9_ -]{1,40}:\s*.*$", stripped) and len(stripped) < 100:
        return False
    if stripped in {"---", "..."}:
        return False
    return True


def _trim_excerpt(text: str) -> str:
    clean = re.sub(r"\n{3,}", "\n\n", text.strip())
    if len(clean) <= MAX_EVIDENCE_EXCERPT_CHARS:
        return clean
    return clean[:MAX_EVIDENCE_EXCERPT_CHARS].rstrip() + "..."


def _source_id(source: dict) -> str:
    for key in ("source_id", "authority_level"):
        value = str(source.get(key) or "").strip()
        if value:
            return value
    file_value = str(source.get("file") or "")
    if file_value.startswith("gbrain:"):
        remainder = file_value.removeprefix("gbrain:")
        if "/" in remainder:
            return remainder.split("/", 1)[0]
    return ""


def _source_slug(source: dict) -> str:
    for key in SOURCE_SLUG_FIELDS:
        value = str(source.get(key) or "").strip()
        if value:
            return value.replace("\\", "/").strip("/")
    file_value = str(source.get("file") or "")
    if file_value.startswith("gbrain:") and "/" in file_value:
        return file_value.split("/", 1)[1].replace("\\", "/").strip("/")
    return ""


def _locator_label(source: dict, *, rel_path: str | None = None) -> str:
    row = source.get("row_num")
    page_slug = str(source.get("page_slug") or source.get("source_slug") or "").strip()
    parts = []
    if rel_path:
        parts.append(rel_path)
    elif page_slug:
        parts.append(page_slug)
    if row not in (None, "", "page"):
        parts.append(f"第 {row} 行")
    return " · ".join(parts) if parts else "引用坐标"


def _display_title(frontmatter: dict[str, Any], original_source_file: str, rel_path: str) -> str:
    title = str(frontmatter.get("title") or "").strip()
    if title:
        return title
    if original_source_file:
        return Path(original_source_file).stem
    return Path(rel_path).stem or "引用来源"


def _safe_display_fallback(source: dict) -> str:
    original = str(source.get("original_source_file") or source.get("source_file") or "").strip()
    if original:
        return Path(original.replace("\\", "/")).stem
    return "引用来源"


def _safe_original_source_file(frontmatter: dict[str, Any]) -> str:
    for field in FRONTMATTER_ORIGINAL_FILE_FIELDS:
        value = str(frontmatter.get(field) or "").strip()
        if not value:
            continue
        normalized = value.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("/"):
            return Path(normalized).name
        clean = normalized.strip("/")
        if ".." in PurePosixPath(clean).parts:
            return Path(clean).name
        return clean
    return ""


def _add_index(index: dict[str, list[tuple[str, Path]]], key: str, rel: str, path: Path) -> None:
    if key:
        index.setdefault(key, []).append((rel, path))


def _unique_match(matches: list[tuple[str, Path]] | None) -> tuple[str, Path] | None:
    if not matches:
        return None
    unique = {(rel, path) for rel, path in matches}
    if len(unique) != 1:
        return None
    return next(iter(unique))


def _row_number(value: object) -> int | None:
    if value in (None, "", "page"):
        return None
    try:
        row = int(str(value))
    except (TypeError, ValueError):
        return None
    return row if row > 0 else None


def _slug_key(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", value.lower()).strip("-")
