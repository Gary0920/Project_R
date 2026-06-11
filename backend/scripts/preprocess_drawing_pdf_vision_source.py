from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.knowledge.gbrain.ingest import _sha256_file, _write_markdown
from app.features.knowledge.gbrain.project_ingest import DRAWING_PDF_PREPROCESS_SKILL
from app.features.preprocessing.pdf_structured import PROMPT_VERSION, SKILL_VERSION, extract_pdf_structured_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess one drawing/layout PDF with MiMo vision into GBrain-ready Markdown.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--scope", choices=["project", "customer", "company"], default="project")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-file")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    result = extract_pdf_structured_markdown(source)
    frontmatter = {
        "title": source.stem,
        "source_scope": args.scope,
        "source_id": args.source_id,
        "source_file": args.source_file or source.name,
        "source_file_sha256": _sha256_file(source),
        "source_file_type": "pdf",
        "preprocess_skill": DRAWING_PDF_PREPROCESS_SKILL,
        "preprocess_version": SKILL_VERSION,
        "preprocess_status": "partial" if result.review_status == "pending_review" else "succeeded",
        "model_profile": result.model_profile,
        "prompt_version": PROMPT_VERSION,
        "language_policy": result.language_policy,
        "created_at": args.created_at,
        "extraction_status": result.extraction_status,
        "review_status": result.review_status,
        "extractor": result.extractor,
        "page_count": result.page_count,
        "pages_analyzed": result.pages_analyzed,
        "vision_pages": list(result.vision_pages),
        "vision_image_count": result.vision_image_count,
    }
    if result.warnings:
        frontmatter["extraction_warnings"] = list(result.warnings)
    if not args.dry_run:
        _write_markdown(args.target.resolve(), frontmatter, result.markdown)
    print(json.dumps({"target": str(args.target), "dry_run": args.dry_run, "review_status": result.review_status}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
