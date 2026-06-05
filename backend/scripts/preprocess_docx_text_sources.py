from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.docx_text_preprocess import preprocess_docx_text
from core.gbrain_ingest import _sha256_file, _write_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess one DOCX file into Project_R GBrain-ready Markdown.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--scope", choices=["company", "project", "customer"], required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-file", help="Source-relative path recorded in frontmatter.")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    result = preprocess_docx_text(
        source_path=source,
        source_scope=args.scope,
        source_id=args.source_id,
        source_file=args.source_file or source.name,
        source_sha256=_sha256_file(source),
        created_at=args.created_at,
    )
    if not args.dry_run:
        _write_markdown(args.target.resolve(), result.frontmatter, result.markdown)
    print(json.dumps({"target": str(args.target), "dry_run": args.dry_run, "metadata": result.metadata}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
