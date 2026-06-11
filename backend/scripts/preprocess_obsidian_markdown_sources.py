from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.knowledge.gbrain import load_gbrain_settings, resolve_gbrain_source_paths
from app.features.preprocessing.obsidian_markdown import preprocess_obsidian_markdown_tree


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preprocess Obsidian exported Markdown into Project_R GBrain-ready source repos.",
    )
    parser.add_argument("--scope", choices=["company", "customer", "project"], required=True)
    parser.add_argument("--raw-path", type=Path, help="Raw source path. Defaults to known company/CRM paths.")
    parser.add_argument("--preprocessed-root", type=Path, help="Target source root containing gbrain-ready/runs/manifests.")
    parser.add_argument("--source-id", help="GBrain source id recorded in generated frontmatter and manifest.")
    parser.add_argument("--run-id", help="Stable run id. Defaults to UTC timestamp.")
    parser.add_argument("--limit", type=int, help="Limit number of source files for smoke runs.")
    parser.add_argument("--dry-run", action="store_true", help="Read and summarize without writing outputs.")
    args = parser.parse_args()

    raw_path, preprocessed_root, source_id = _resolve_defaults(args.scope, args.raw_path, args.preprocessed_root, args.source_id)
    manifest = preprocess_obsidian_markdown_tree(
        raw_path=raw_path,
        preprocessed_root=preprocessed_root,
        source_scope=args.scope,
        source_id=source_id,
        run_id=args.run_id,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    print(json.dumps({"summary": manifest["summary"], "manifest": _manifest_pointer(manifest)}, ensure_ascii=False, indent=2))
    return 0 if manifest["summary"]["failed"] == 0 else 1


def _resolve_defaults(
    scope: str,
    raw_path: Path | None,
    preprocessed_root: Path | None,
    source_id: str | None,
) -> tuple[Path, Path, str]:
    if scope == "company":
        settings = load_gbrain_settings()
        paths = resolve_gbrain_source_paths("company", settings=settings)
        return (
            (raw_path or paths.raw).resolve(),
            (preprocessed_root or paths.preprocessed_root).resolve(),
            source_id or paths.source_id,
        )
    if scope == "customer":
        default_raw = BACKEND_DIR / "workspace_data" / "customer" / "CRM" / "raw"
        default_root = BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm"
        return (
            (raw_path or default_raw).resolve(),
            (preprocessed_root or default_root).resolve(),
            source_id or "customer-crm",
        )
    if raw_path is None or preprocessed_root is None or not source_id:
        raise SystemExit("project scope requires --raw-path, --preprocessed-root, and --source-id")
    return raw_path.resolve(), preprocessed_root.resolve(), source_id


def _manifest_pointer(manifest: dict[str, object]) -> dict[str, object]:
    return {
        "run_id": manifest.get("run_id"),
        "raw_path": manifest.get("raw_path"),
        "gbrain_ready_path": manifest.get("gbrain_ready_path"),
        "manifests_path": manifest.get("manifests_path"),
        "dry_run": manifest.get("dry_run"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
