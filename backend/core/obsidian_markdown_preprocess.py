from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


SKILL_NAME = "markdown-source-preprocess"
SKILL_VERSION = "1.0.0"
PROMPT_VERSION = "rules-obsidian-v1"
SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt"}
IGNORED_PARTS = {".git", ".trash", "99-archive", "derived", "manifests", "runs", "gbrain-ready"}

CUSTOMER_CATEGORY_MAP = {
    "01_Clients": ("clients", "customer_person_source_record"),
    "02_Projects": ("projects", "customer_project_source_record"),
    "03_Companies": ("companies", "customer_company_source_record"),
    "04_Raw": ("raw-events", "customer_raw_source_record"),
}

NOISE_FRONTMATTER_KEYS = {
    "cssclasses",
    "cssclass",
    "publish",
    "draft",
    "share",
    "dg-publish",
    "dg-home",
}


@dataclass(frozen=True)
class PreprocessOutput:
    source_path: Path
    target_path: Path | None
    status: str
    source_sha256: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def preprocess_obsidian_markdown_tree(
    *,
    raw_path: Path,
    preprocessed_root: Path,
    source_scope: str,
    source_id: str,
    run_id: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Clean Obsidian exported Markdown into GBrain-ready Markdown.

    This function intentionally does not register or sync GBrain sources. It only
    reads raw source files, writes process manifests, and writes final Markdown
    to the supplied source repo root.
    """

    scope = _normalize_scope(source_scope)
    raw_path = raw_path.resolve()
    preprocessed_root = preprocessed_root.resolve()
    gbrain_ready = preprocessed_root / "gbrain-ready"
    runs = preprocessed_root / "runs"
    manifests = preprocessed_root / "manifests"
    run_id = run_id or _default_run_id()
    started_at = _utc_now()

    files = _iter_source_files(raw_path)
    if limit is not None:
        files = files[: max(0, limit)]

    results: list[PreprocessOutput] = []
    used_targets: set[Path] = set()
    for source_path in files:
        results.append(
            _preprocess_one_file(
                source_path=source_path,
                raw_path=raw_path,
                gbrain_ready=gbrain_ready,
                source_scope=scope,
                source_id=source_id,
                run_id=run_id,
                created_at=started_at,
                used_targets=used_targets,
                dry_run=dry_run,
            )
        )

    summary = _summary(results)
    manifest = {
        "schema_version": 1,
        "source_id": source_id,
        "source_scope": scope,
        "preprocess_skill": SKILL_NAME,
        "preprocess_version": SKILL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model_profile": "none",
        "run_id": run_id,
        "dry_run": dry_run,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "raw_path": str(raw_path),
        "preprocessed_root": str(preprocessed_root),
        "gbrain_ready_path": str(gbrain_ready),
        "runs_path": str(runs),
        "manifests_path": str(manifests),
        "items": [_manifest_item(result, raw_path, gbrain_ready) for result in results],
        "summary": summary,
    }

    if not dry_run:
        runs.mkdir(parents=True, exist_ok=True)
        manifests.mkdir(parents=True, exist_ok=True)
        run_manifest_path = runs / run_id / "obsidian-markdown-preprocess-manifest.json"
        run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2)
        run_manifest_path.write_text(serialized, encoding="utf-8")
        manifest_path = manifests / f"obsidian-markdown-preprocess-{run_id}.json"
        latest_path = manifests / "latest-obsidian-markdown-preprocess.json"
        manifest_path.write_text(serialized, encoding="utf-8")
        latest_path.write_text(serialized, encoding="utf-8")

    return manifest


def clean_obsidian_markdown(
    text: str,
    *,
    source_path: Path,
    source_scope: str,
    source_id: str,
    source_file: str,
    source_sha256: str,
    run_id: str,
    created_at: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    original_frontmatter, body = _split_frontmatter(text)
    title = str(original_frontmatter.get("title") or original_frontmatter.get("name") or source_path.stem).strip()
    title = title or source_path.stem
    useful_frontmatter = _useful_frontmatter(original_frontmatter)

    cleanup = _clean_body(body)
    metadata = {
        "original_frontmatter_keys": sorted(str(key) for key in original_frontmatter.keys()),
        "preserved_frontmatter_keys": sorted(str(key) for key in useful_frontmatter.keys()),
        "removed_embed_count": len(cleanup["embeds"]),
        "wikilink_count": len(cleanup["wikilinks"]),
        "removed_html_count": cleanup["removed_html_count"],
        "removed_noise_line_count": cleanup["removed_noise_line_count"],
    }

    content_kind = _content_kind(source_scope, source_file, original_frontmatter)
    frontmatter = {
        "title": title,
        "source_scope": source_scope,
        "source_id": source_id,
        "content_kind": content_kind,
        "authority_level": _authority_level(source_scope),
        "source_file": source_file,
        "source_file_sha256": source_sha256,
        "source_file_type": "markdown" if source_path.suffix.lower() != ".txt" else "text",
        "preprocess_skill": SKILL_NAME,
        "preprocess_version": SKILL_VERSION,
        "preprocess_status": "succeeded",
        "model_profile": "none",
        "prompt_version": PROMPT_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "obsidian_wikilink_count": len(cleanup["wikilinks"]),
        "obsidian_embed_removed_count": len(cleanup["embeds"]),
        "review_status": "approved",
    }

    sections = [
        f"# {title}",
        "## Source Summary",
        _source_summary(source_scope, source_file, content_kind),
    ]
    if useful_frontmatter:
        sections.extend(["## Source Metadata", _frontmatter_as_markdown(useful_frontmatter)])
    sections.extend(["## Cleaned Content", cleanup["body"] or "_No readable body content after cleanup._"])
    if cleanup["wikilinks"]:
        sections.extend(["## Obsidian Links Preserved", _links_as_markdown(cleanup["wikilinks"])])
    if cleanup["embeds"]:
        sections.extend(["## Removed Embed References", _list_as_markdown(cleanup["embeds"])])
    sections.extend(
        [
            "## Preprocess Notes",
            _preprocess_notes(metadata),
        ]
    )
    return frontmatter, "\n\n".join(section.strip() for section in sections if section is not None).strip() + "\n", metadata


def _preprocess_one_file(
    *,
    source_path: Path,
    raw_path: Path,
    gbrain_ready: Path,
    source_scope: str,
    source_id: str,
    run_id: str,
    created_at: str,
    used_targets: set[Path],
    dry_run: bool,
) -> PreprocessOutput:
    try:
        source_sha256 = _sha256(source_path)
        rel = _relative_posix(source_path, raw_path)
        text = source_path.read_text(encoding="utf-8-sig", errors="replace")
        frontmatter, markdown, metadata = clean_obsidian_markdown(
            text,
            source_path=source_path,
            source_scope=source_scope,
            source_id=source_id,
            source_file=rel,
            source_sha256=source_sha256,
            run_id=run_id,
            created_at=created_at,
        )
        target_path = _target_path(gbrain_ready, source_path, raw_path, source_scope, used_targets)
        if not dry_run:
            _write_markdown(target_path, frontmatter, markdown)
        return PreprocessOutput(
            source_path=source_path,
            target_path=target_path,
            status="compiled",
            source_sha256=source_sha256,
            metadata=metadata,
        )
    except Exception as exc:
        return PreprocessOutput(source_path=source_path, target_path=None, status="failed", error=str(exc))


def _clean_body(body: str) -> dict[str, Any]:
    body = body.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    embeds: list[str] = []
    wikilinks: list[dict[str, str]] = []
    removed_html_count = 0
    removed_noise_line_count = 0

    def remove_obsidian_embed(match: re.Match[str]) -> str:
        embeds.append(match.group(1).strip())
        return ""

    body = re.sub(r"!\[\[([^\]]+)]]", remove_obsidian_embed, body)

    def remove_markdown_image(match: re.Match[str]) -> str:
        target = (match.group(2) or "").strip()
        if target:
            embeds.append(target)
        return ""

    body = re.sub(r"!\[([^\]]*)]\(([^)]*)\)", remove_markdown_image, body)
    body, html_count = re.subn(r"<span\b[^>]*>", "", body, flags=re.IGNORECASE)
    removed_html_count += html_count
    body, html_count = re.subn(r"</span>", "", body, flags=re.IGNORECASE)
    removed_html_count += html_count
    body, html_count = re.subn(r"<!--.*?-->", "", body, flags=re.DOTALL)
    removed_html_count += html_count

    def replace_wikilink(match: re.Match[str]) -> str:
        raw = match.group(1).strip()
        if not raw:
            return ""
        target, _, alias = raw.partition("|")
        target = target.strip()
        label = (alias or target.rsplit("/", 1)[-1]).strip()
        if target:
            wikilinks.append({"target": target, "label": label})
        return label

    body = re.sub(r"\[\[(.*?)]]", replace_wikilink, body)

    cleaned_lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"-{3,}", stripped):
            removed_noise_line_count += 1
            continue
        if re.fullmatch(r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?", stripped, flags=re.IGNORECASE):
            removed_noise_line_count += 1
            continue
        cleaned_lines.append(line.rstrip())

    cleaned = "\n".join(cleaned_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return {
        "body": cleaned,
        "embeds": _dedupe_strings(embeds),
        "wikilinks": _dedupe_links(wikilinks),
        "removed_html_count": removed_html_count,
        "removed_noise_line_count": removed_noise_line_count,
    }


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not match:
        return {}, text
    raw_frontmatter, body = match.groups()
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(parsed, dict):
        return {}, body
    return parsed, body


def _useful_frontmatter(frontmatter: dict[str, Any]) -> dict[str, Any]:
    useful: dict[str, Any] = {}
    for key, value in frontmatter.items():
        key_text = str(key)
        if key_text in NOISE_FRONTMATTER_KEYS:
            continue
        if value in (None, "", [], {}):
            continue
        useful[key_text] = _normalize_frontmatter_value(value)
    return useful


def _normalize_frontmatter_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\[\[(.*?)]]", _frontmatter_wikilink_label, value)
    if isinstance(value, list):
        return [_normalize_frontmatter_value(item) for item in value if item not in (None, "")]
    if isinstance(value, dict):
        return {str(key): _normalize_frontmatter_value(item) for key, item in value.items() if item not in (None, "")}
    return value


def _frontmatter_wikilink_label(match: re.Match[str]) -> str:
    raw = match.group(1).strip()
    target, _, alias = raw.partition("|")
    return (alias or target).rsplit("/", 1)[-1].strip()


def _frontmatter_as_markdown(frontmatter: dict[str, Any]) -> str:
    rows: list[str] = []
    for key, value in frontmatter.items():
        rows.append(f"- **{key}:** {_value_as_text(value)}")
    return "\n".join(rows) if rows else "_No useful source metadata._"


def _value_as_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_value_as_text(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_value_as_text(item)}" for key, item in value.items())
    return str(value)


def _source_summary(source_scope: str, source_file: str, content_kind: str) -> str:
    scope_text = {
        "company": "Company-wide knowledge source prepared for the company-wiki GBrain source.",
        "customer": "Restricted CRM customer intelligence source prepared for a customer GBrain source.",
        "project": "Project workspace source prepared for a project-scoped GBrain source.",
    }.get(source_scope, f"{source_scope} source prepared for GBrain.")
    return "\n".join(
        [
            f"- Scope: {scope_text}",
            f"- Original file: `{source_file}`",
            f"- Content kind: `{content_kind}`",
            "- Processing: Obsidian export cleanup only; no model rewriting was applied.",
        ]
    )


def _links_as_markdown(links: list[dict[str, str]]) -> str:
    return "\n".join(f"- {link['label']} -> `{link['target']}`" for link in links)


def _list_as_markdown(values: list[str]) -> str:
    return "\n".join(f"- `{value}`" for value in values)


def _preprocess_notes(metadata: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"- Obsidian wikilinks converted to readable text: {metadata['wikilink_count']}",
            f"- Embed/image references removed from body: {metadata['removed_embed_count']}",
            f"- HTML/export noise fragments removed: {metadata['removed_html_count']}",
            f"- Horizontal rule or export noise lines removed: {metadata['removed_noise_line_count']}",
            "- Source file was not modified.",
        ]
    )


def _content_kind(source_scope: str, source_file: str, frontmatter: dict[str, Any]) -> str:
    if source_scope == "customer":
        first_part = Path(source_file).parts[0] if Path(source_file).parts else ""
        return CUSTOMER_CATEGORY_MAP.get(first_part, ("raw-events", "customer_raw_source_record"))[1]
    if source_scope == "company":
        return str(frontmatter.get("content_kind") or frontmatter.get("type") or "company_obsidian_markdown_source")
    return str(frontmatter.get("content_kind") or frontmatter.get("type") or "project_obsidian_markdown_source")


def _authority_level(source_scope: str) -> str:
    if source_scope == "customer":
        return "customer_source_record"
    if source_scope == "company":
        return "company_source_record"
    return "project_source_record"


def _target_path(
    gbrain_ready: Path,
    source_path: Path,
    raw_path: Path,
    source_scope: str,
    used_targets: set[Path],
) -> Path:
    rel = source_path.resolve().relative_to(raw_path.resolve())
    if source_scope == "customer":
        first_part = rel.parts[0] if rel.parts else ""
        target_dir = CUSTOMER_CATEGORY_MAP.get(first_part, ("raw-events", "customer_raw_source_record"))[0]
        stem_source = "__".join(rel.with_suffix("").parts)
        base = gbrain_ready / target_dir
    else:
        base = gbrain_ready / ("rules" if source_scope == "company" else "source-records")
        stem_source = "__".join(rel.with_suffix("").parts)
    digest = hashlib.sha1(rel.as_posix().encode("utf-8")).hexdigest()[:8]
    target = base / f"{_safe_filename(stem_source)}-{digest}.md"
    while target in used_targets:
        digest = hashlib.sha1(f"{rel.as_posix()}::{len(used_targets)}".encode("utf-8")).hexdigest()[:8]
        target = base / f"{_safe_filename(stem_source)}-{digest}.md"
    used_targets.add(target)
    return target


def _write_markdown(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{serialized}\n---\n\n{body}", encoding="utf-8")


def _iter_source_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in IGNORED_PARTS for part in rel_parts):
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _summary(results: Iterable[PreprocessOutput]) -> dict[str, int]:
    items = list(results)
    return {
        "total": len(items),
        "compiled": sum(1 for item in items if item.status == "compiled"),
        "failed": sum(1 for item in items if item.status == "failed"),
        "skipped": sum(1 for item in items if item.status == "skipped"),
    }


def _manifest_item(result: PreprocessOutput, raw_path: Path, gbrain_ready: Path) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_file": _relative_posix(result.source_path, raw_path),
        "status": result.status,
        "source_sha256": result.source_sha256,
    }
    if result.target_path is not None:
        item["target_file"] = _relative_posix(result.target_path, gbrain_ready)
    if result.error:
        item["error"] = result.error
    item.update({key: value for key, value in result.metadata.items() if value not in (None, [], {})})
    return item


def _normalize_scope(value: str) -> str:
    scope = value.strip().lower().replace("_", "-")
    if scope in {"company", "customer", "project"}:
        return scope
    raise ValueError("source_scope must be one of: company, customer, project")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff()[\]. -]+", "-", value, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
    return cleaned[:140] or "obsidian-source"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for link in links:
        key = (link["target"], link["label"])
        if key not in seen:
            seen.add(key)
            result.append(link)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
