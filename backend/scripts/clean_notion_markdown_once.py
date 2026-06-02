from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RAW_PATH = BASE_DIR / "workspace_data" / "global" / "company-wiki" / "raw"
DEFAULT_MANIFEST_PATH = BASE_DIR / "workspace_data" / "global" / "company-wiki" / "manifests"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".svg")
NOISE_URL_MARKERS = (
    "notion.so",
    "notion.site",
    "notion-static.com",
    "prod-files-secure",
    "amazonaws.com",
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="One-time cleaner for legacy Notion-exported Markdown before Project_R GBrain ingest."
    )
    parser.add_argument("--raw-path", default=str(DEFAULT_RAW_PATH))
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raw_path = Path(args.raw_path).resolve()
    manifest_dir = Path(args.manifest_dir).resolve()
    if not raw_path.exists() or not raw_path.is_dir():
        raise SystemExit(f"raw path not found: {raw_path}")

    started_at = utc_now()
    items: list[dict[str, Any]] = []
    totals = {
        "files": 0,
        "changed": 0,
        "frontmatter_removed": 0,
        "image_embeds_removed": 0,
        "html_images_removed": 0,
        "noise_url_lines_removed": 0,
        "horizontal_rules_removed": 0,
        "wikilinks_normalized": 0,
    }

    for path in sorted(raw_path.rglob("*.md")):
        if not path.is_file():
            continue
        totals["files"] += 1
        original = path.read_text(encoding="utf-8-sig")
        cleaned, stats = clean_markdown(original)
        changed = cleaned != original
        if changed and not args.dry_run:
            path.write_text(cleaned, encoding="utf-8")
        for key in totals:
            if key in stats:
                totals[key] += int(stats[key])
        if changed:
            totals["changed"] += 1
        items.append(
            {
                "file": path.relative_to(raw_path).as_posix(),
                "changed": changed,
                "sha256_before": sha256_text(original),
                "sha256_after": sha256_text(cleaned),
                **stats,
            }
        )

    manifest = {
        "schema_version": 1,
        "tool": "clean_notion_markdown_once",
        "dry_run": bool(args.dry_run),
        "started_at": started_at,
        "finished_at": utc_now(),
        "raw_path": str(raw_path),
        "summary": totals,
        "items": items,
    }
    if not args.dry_run:
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "notion-markdown-cleanup-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def clean_markdown(text: str) -> tuple[str, dict[str, int]]:
    stats = {
        "frontmatter_removed": 0,
        "image_embeds_removed": 0,
        "html_images_removed": 0,
        "noise_url_lines_removed": 0,
        "horizontal_rules_removed": 0,
        "wikilinks_normalized": 0,
    }
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value, removed_frontmatter = strip_leading_frontmatter(value)
    stats["frontmatter_removed"] = int(removed_frontmatter)

    html_image_pattern = re.compile(r"<img\b[^>]*>", flags=re.IGNORECASE)
    value, count = html_image_pattern.subn("", value)
    stats["html_images_removed"] += count

    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)

    markdown_image_pattern = re.compile(r"!\[[^\]]*]\([^)]+\)")
    value, count = markdown_image_pattern.subn("", value)
    stats["image_embeds_removed"] += count

    reference_image_pattern = re.compile(r"!\[[^\]]*]\[[^\]]*]")
    value, count = reference_image_pattern.subn("", value)
    stats["image_embeds_removed"] += count

    obsidian_embed_pattern = re.compile(r"!\[\[[^\]]+]]")
    value, count = obsidian_embed_pattern.subn("", value)
    stats["image_embeds_removed"] += count

    wikilink_pattern = re.compile(r"(?<!!)\[\[([^]|]+)(?:\|([^]]+))?]]")

    def wikilink_replacement(match: re.Match[str]) -> str:
        stats["wikilinks_normalized"] += 1
        return (match.group(2) or match.group(1)).strip()

    value = wikilink_pattern.sub(wikilink_replacement, value)

    cleaned_lines: list[str] = []
    for line in value.split("\n"):
        if is_noise_url_line(line):
            stats["noise_url_lines_removed"] += 1
            continue
        if line.strip() == "---":
            stats["horizontal_rules_removed"] += 1
            continue
        line = normalize_markdown_links(line)
        cleaned_lines.append(line.rstrip())

    value = "\n".join(cleaned_lines)
    value = re.sub(r"\n{3,}", "\n\n", value).strip() + "\n"
    return value, stats


def strip_leading_frontmatter(text: str) -> tuple[str, bool]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text, False
    max_scan = min(len(lines), 80)
    for index in range(1, max_scan):
        if lines[index].strip() != "---":
            continue
        block = "\n".join(lines[1:index])
        if ":" not in block:
            return text, False
        return "\n".join(lines[index + 1 :]).lstrip("\n"), True
    return text, False


def is_noise_url_line(line: str) -> bool:
    lowered = line.lower()
    if any(marker in lowered for marker in NOISE_URL_MARKERS):
        return True
    urls = re.findall(r"https?://[^\s)>]+", line)
    if not urls:
        return False
    for url in urls:
        url_lower = url.lower().split("?", 1)[0].rstrip(".,;")
        if url_lower.endswith(IMAGE_EXTENSIONS):
            return True
    return False


def normalize_markdown_links(line: str) -> str:
    def replace(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        return label or ""

    return re.sub(r"\[([^\]]+)]\((https?://[^)]+)\)", replace, line)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
