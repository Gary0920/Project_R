from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.preprocessing.email_structured import (
    PROMPT_VERSION,
    SKILL_NAME,
    SKILL_VERSION,
    extract_email_attachments,
    extract_email_structured_markdown,
)
from app.features.knowledge.gbrain.ingest import _sha256_file, _write_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess one EML email thread into Project_R GBrain-ready Markdown.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--scope", choices=["project", "customer", "company"], required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-file")
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--extract-attachments-to", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    result = extract_email_structured_markdown(source)
    attachments = ()
    if args.extract_attachments_to and not args.dry_run:
        attachments = extract_email_attachments(source, args.extract_attachments_to.resolve())
    frontmatter = {
        "title": result.subject or source.stem,
        "source_scope": args.scope,
        "source_id": args.source_id,
        "source_file": args.source_file or source.name,
        "source_file_sha256": _sha256_file(source),
        "source_file_type": source.suffix.lower().lstrip(".") or "email",
        "preprocess_skill": SKILL_NAME,
        "preprocess_version": SKILL_VERSION,
        "preprocess_status": "succeeded",
        "model_profile": result.model_profile,
        "prompt_version": PROMPT_VERSION,
        "language_policy": result.language_policy,
        "created_at": args.created_at,
        "extraction_status": result.extraction_status,
        "review_status": result.review_status,
        "extractor": result.extractor,
        "email_subject": result.subject,
        "email_sender": result.sender,
        "email_recipients": list(result.recipients),
        "email_message_date": result.message_date,
        "email_attachments": list(result.attachment_names),
        "email_extracted_attachment_files": [attachment.filename for attachment in attachments],
        "provider": result.provider,
        "model": result.model,
        "token_usage": result.token_usage,
    }
    if result.warnings:
        frontmatter["extraction_warnings"] = list(result.warnings)
    if not args.dry_run:
        _write_markdown(args.target.resolve(), frontmatter, result.markdown)
    print(
        json.dumps(
            {
                "target": str(args.target),
                "dry_run": args.dry_run,
                "subject": result.subject,
                "attachment_count": len(attachments),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
