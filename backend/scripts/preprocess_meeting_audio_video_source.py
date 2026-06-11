from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.features.knowledge.gbrain.ingest import _sha256_file, _write_markdown
from app.features.preprocessing.media_transcription import TRANSCRIPTION_PROMPT_VERSION, transcribe_media_to_markdown
from app.features.preprocessing.meeting_structured import (
    PROMPT_VERSION,
    SKILL_NAME,
    SKILL_VERSION,
    extract_meeting_structured_markdown,
    find_transcript_sidecar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Preprocess one meeting audio/video file into GBrain-ready Markdown.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--scope", choices=["company", "project", "customer"], required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--source-file")
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--enable-transcription", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    transcript = args.transcript.resolve() if args.transcript else find_transcript_sidecar(source)
    transcription = None
    generated_transcript = None
    if transcript is None and args.enable_transcription:
        transcription = transcribe_media_to_markdown(source)
        generated_transcript = source.with_name(f"{source.stem}.auto.transcript.md")
        if not args.dry_run:
            generated_transcript.write_text(transcription.transcript_text, encoding="utf-8")
        transcript = generated_transcript
    if transcript is None:
        raise SystemExit("missing transcript sidecar; pass --transcript or --enable-transcription")

    result = extract_meeting_structured_markdown(
        title=source.stem,
        transcript_path=transcript,
        source_media_path=source,
        source_label=args.source_file or source.name,
    )
    frontmatter = {
        "title": source.stem,
        "source_scope": args.scope,
        "source_id": args.source_id,
        "source_file": args.source_file or source.name,
        "source_file_sha256": _sha256_file(source),
        "source_file_type": source.suffix.lower().lstrip(".") or "media",
        "preprocess_skill": SKILL_NAME,
        "preprocess_version": SKILL_VERSION,
        "preprocess_status": "partial" if result.review_status == "pending_review" else "succeeded",
        "prompt_version": PROMPT_VERSION,
        "language_policy": result.language_policy,
        "created_at": args.created_at,
        "extraction_status": result.extraction_status,
        "review_status": result.review_status,
        "extractor": result.extractor,
        "transcript_file": transcript.name,
        "transcription_status": transcription.transcription_status if transcription else result.transcription_status,
        "transcription_prompt_version": TRANSCRIPTION_PROMPT_VERSION if transcription else None,
        "generated_transcript_file": generated_transcript.name if generated_transcript else None,
        "segment_count": result.segment_count,
        "action_item_count": result.action_item_count,
        "decision_count": result.decision_count,
        "risk_count": result.risk_count,
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
                "transcript": str(transcript),
                "transcription_status": frontmatter["transcription_status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
