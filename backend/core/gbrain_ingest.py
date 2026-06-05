from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from core.docx_text_preprocess import preprocess_docx_text
from core.gbrain import GBrainSettings, ensure_gbrain_environment, load_gbrain_settings, resolve_gbrain_source_paths
from core.meeting_structured_extraction import (
    MeetingStructuredExtractionResult,
    PROMPT_VERSION as MEETING_PROMPT_VERSION,
    SKILL_NAME as MEETING_PREPROCESS_SKILL,
    SKILL_VERSION as MEETING_PREPROCESS_VERSION,
    extract_meeting_structured_markdown,
    find_transcript_sidecar,
    find_transcript_sidecars_for_media_files,
)
from core.pdf_structured_extraction import (
    PDFStructuredExtractionResult,
    PROMPT_VERSION as PDF_PROMPT_VERSION,
    SKILL_NAME as PDF_PREPROCESS_SKILL,
    SKILL_VERSION as PDF_PREPROCESS_VERSION,
    extract_pdf_structured_markdown,
    _pdf_image_sidecar_candidates,
)


TEXT_EXTENSIONS = {".md", ".markdown", ".txt"}
DOCX_EXTENSIONS = {".docx"}
PDF_EXTENSIONS = {".pdf"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
PENDING_REVIEW_DIR = ".pending_review"
PDF_STRUCTURED_EXTRACTION_REQUIRED = (
    "pdf requires model-assisted structured extraction; pure text extraction is disabled by default"
)
MEDIA_TRANSCRIPTION_REQUIRED = (
    "audio/video transcription is pending; add a same-name transcript sidecar or configure a transcription provider"
)


@dataclass(frozen=True)
class CompiledSource:
    source_path: Path
    status: str
    target_path: Path | None = None
    error: str | None = None
    source_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


PDFExtractor = Callable[..., PDFStructuredExtractionResult]
MeetingExtractor = Callable[..., MeetingStructuredExtractionResult]


def compile_company_wiki_sources(
    settings: GBrainSettings | None = None,
    *,
    pdf_extractor: PDFExtractor | None = None,
    meeting_extractor: MeetingExtractor | None = None,
    enable_pdf_structured_extraction: bool | None = None,
) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    source_paths = resolve_gbrain_source_paths("company", settings=settings)
    environment = ensure_gbrain_environment(settings)
    settings = replace(
        settings,
        derived_path=source_paths.gbrain_ready,
        manifests_path=source_paths.manifests,
    )
    started_at = _utc_now()
    results: list[CompiledSource] = []
    pdf_enabled = (
        _env_bool("GBRAIN_PDF_STRUCTURED_EXTRACTION_ENABLED", False)
        if enable_pdf_structured_extraction is None
        else enable_pdf_structured_extraction
    )

    pdf_image_sidecar_dirs = _pdf_image_sidecar_dirs(settings.raw_path)
    transcript_sidecar_files = find_transcript_sidecars_for_media_files(settings.raw_path, MEDIA_EXTENSIONS)
    for source_path in _iter_raw_source_files(
        settings.raw_path,
        pdf_image_sidecar_dirs,
        excluded_files=transcript_sidecar_files,
    ):
        results.append(
            _compile_one_source(
                source_path,
                settings,
                started_at,
                pdf_extractor=pdf_extractor,
                meeting_extractor=meeting_extractor,
                enable_pdf_structured_extraction=pdf_enabled,
            )
        )

    manifest = {
        "schema_version": 1,
        "source_id": settings.company_source_id,
        "source_scope": "company",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "raw_path": str(settings.raw_path.resolve()),
        "gbrain_ready_path": str(settings.derived_path.resolve()),
        "derived_path": str(settings.derived_path.resolve()),
        "legacy_derived_path": str((source_paths.legacy_derived or source_paths.gbrain_ready).resolve()),
        "runs_path": str(source_paths.runs.resolve()),
        "manifests_path": str(settings.manifests_path.resolve()),
        "environment_ok": environment["ok"],
        "items": [_result_to_manifest_item(result, settings) for result in results],
        "summary": {
            "total": len(results),
            "compiled": sum(1 for result in results if result.status == "compiled"),
            "skipped": sum(1 for result in results if result.status == "skipped"),
            "failed": sum(1 for result in results if result.status == "failed"),
        },
    }
    manifest_path = settings.manifests_path / "company-wiki-ingest-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    git_status = _commit_derived_changes(settings.derived_path, manifest["summary"], settings.local_git_enabled)
    manifest["local_git"] = git_status
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _compile_one_source(
    source_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    *,
    pdf_extractor: PDFExtractor | None = None,
    meeting_extractor: MeetingExtractor | None = None,
    enable_pdf_structured_extraction: bool = False,
) -> CompiledSource:
    suffix = source_path.suffix.lower()
    try:
        source_hash = _sha256_file(source_path)
        if suffix in TEXT_EXTENSIONS:
            target_path = _target_path(source_path, settings, "rules")
            _compile_text_source(source_path, target_path, settings, ingested_at, source_hash)
            return CompiledSource(source_path, "compiled", target_path, source_sha256=source_hash)
        if suffix in DOCX_EXTENSIONS:
            target_path = _target_path(source_path, settings, "meetings")
            _compile_docx_source(source_path, target_path, settings, ingested_at, source_hash)
            return CompiledSource(source_path, "compiled", target_path, source_sha256=source_hash)
        if suffix in PDF_EXTENSIONS:
            if not enable_pdf_structured_extraction:
                return CompiledSource(
                    source_path,
                    "skipped",
                    error=PDF_STRUCTURED_EXTRACTION_REQUIRED,
                    source_sha256=source_hash,
                    metadata={"extraction_status": "pending_structured_extraction"},
                )
            result = (pdf_extractor or extract_pdf_structured_markdown)(source_path)
            approved_target_path = _target_path(source_path, settings, "standards")
            target_path = (
                _pending_review_path(approved_target_path, settings)
                if result.review_status == "pending_review"
                else approved_target_path
            )
            _compile_pdf_structured_source(
                source_path,
                target_path,
                settings,
                ingested_at,
                source_hash,
                result,
            )
            if target_path != approved_target_path and approved_target_path.exists():
                approved_target_path.unlink()
            return CompiledSource(
                source_path,
                "compiled",
                target_path,
                source_sha256=source_hash,
                metadata={
                    "extraction_status": result.extraction_status,
                    "review_status": result.review_status,
                    "extractor": result.extractor,
                    "language_policy": result.language_policy,
                    "page_count": result.page_count,
                    "pages_analyzed": result.pages_analyzed,
                    "model_profile": result.model_profile,
                    "provider": result.provider,
                    "model": result.model,
                    "token_usage": result.token_usage,
                    "warnings": list(result.warnings),
                    "vision_pages": list(result.vision_pages),
                    "vision_image_count": result.vision_image_count,
                    "approved_target_file": _relative_posix(approved_target_path, settings.derived_path),
                },
            )
        if suffix in MEDIA_EXTENSIONS:
            transcript_path = find_transcript_sidecar(source_path)
            if transcript_path is not None:
                result = (meeting_extractor or extract_meeting_structured_markdown)(
                    title=source_path.stem,
                    transcript_path=transcript_path,
                    source_media_path=source_path,
                    source_label=_relative_posix(source_path, settings.raw_path),
                )
                approved_target_path = _target_path(source_path, settings, "meetings")
                target_path = (
                    _pending_review_path(approved_target_path, settings)
                    if result.review_status == "pending_review"
                    else approved_target_path
                )
                _compile_meeting_structured_source(
                    source_path,
                    transcript_path,
                    target_path,
                    settings,
                    ingested_at,
                    source_hash,
                    result,
                )
                return CompiledSource(
                    source_path,
                    "compiled",
                    target_path,
                    source_sha256=source_hash,
                    metadata={
                        "extraction_status": result.extraction_status,
                        "review_status": result.review_status,
                        "extractor": result.extractor,
                        "language_policy": result.language_policy,
                        "transcription_status": result.transcription_status,
                        "transcript_file": _relative_posix(transcript_path, settings.raw_path),
                        "segment_count": result.segment_count,
                        "action_item_count": result.action_item_count,
                        "decision_count": result.decision_count,
                        "risk_count": result.risk_count,
                        "warnings": list(result.warnings),
                        "approved_target_file": _relative_posix(approved_target_path, settings.derived_path),
                    },
                )
            return CompiledSource(
                source_path,
                "skipped",
                error=MEDIA_TRANSCRIPTION_REQUIRED,
                source_sha256=source_hash,
                metadata={
                    "extraction_status": "pending_meeting_transcription",
                    "transcription_status": "pending_transcription",
                },
            )
        return CompiledSource(
            source_path,
            "skipped",
            error=f"unsupported file extension: {source_path.suffix}",
            source_sha256=source_hash,
        )
    except Exception as exc:  # pragma: no cover - defensive manifest path
        return CompiledSource(source_path, "failed", error=str(exc))


def _compile_text_source(
    source_path: Path,
    target_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    source_hash: str,
) -> None:
    text = source_path.read_text(encoding="utf-8-sig")
    frontmatter, body = _split_frontmatter(text)
    title = frontmatter.get("title") or source_path.stem
    merged = {
        **frontmatter,
        "title": title,
        "project_r_source_file": _relative_posix(source_path, settings.raw_path),
        "project_r_source_sha256": source_hash,
        "project_r_ingested_at": ingested_at,
        "extraction_status": frontmatter.get("extraction_status", "native_text"),
    }
    _write_markdown(target_path, merged, body.strip() + "\n")


def _compile_docx_source(
    source_path: Path,
    target_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    source_hash: str,
) -> None:
    title = source_path.stem
    result = preprocess_docx_text(
        source_path=source_path,
        source_scope="company",
        source_id=settings.company_source_id,
        source_file=_relative_posix(source_path, settings.raw_path),
        source_sha256=source_hash,
        created_at=ingested_at,
        title=title,
        content_kind="meeting_transcript",
        document_type="meeting",
        extra_frontmatter={
            "type": "meeting",
            "project_r_source_file": _relative_posix(source_path, settings.raw_path),
            "project_r_source_sha256": source_hash,
            "project_r_ingested_at": ingested_at,
            "extraction_status": "docx_text_extracted",
            "tags": ["会议", "真实样本"],
        },
    )
    frontmatter = {
        **result.frontmatter,
        "source_domain": "project_r_raw",
        "authority_level": "source_record",
    }
    _write_markdown(target_path, frontmatter, result.markdown)


def _compile_pdf_structured_source(
    source_path: Path,
    target_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    source_hash: str,
    extraction: PDFStructuredExtractionResult,
) -> None:
    title = source_path.stem
    frontmatter = {
        "title": title,
        "type": "reference",
        "content_kind": "external_standard_structured_extract",
        "source_domain": "external_standard",
        "authority_level": "external_reference",
        "project_r_source_file": _relative_posix(source_path, settings.raw_path),
        "project_r_source_sha256": source_hash,
        "project_r_ingested_at": ingested_at,
        "source_file": _relative_posix(source_path, settings.raw_path),
        "source_file_sha256": source_hash,
        "source_file_type": "pdf",
        "preprocess_skill": PDF_PREPROCESS_SKILL,
        "preprocess_version": PDF_PREPROCESS_VERSION,
        "preprocess_status": "partial" if extraction.review_status == "pending_review" else "succeeded",
        "prompt_version": PDF_PROMPT_VERSION,
        "extraction_status": extraction.extraction_status,
        "review_status": extraction.review_status,
        "extractor": extraction.extractor,
        "language_policy": extraction.language_policy,
        "page_count": extraction.page_count,
        "pages_analyzed": extraction.pages_analyzed,
        "model_profile": extraction.model_profile,
        "provider": extraction.provider,
        "model": extraction.model,
        "vision_pages": list(extraction.vision_pages),
        "vision_image_count": extraction.vision_image_count,
        "tags": ["标准", "PDF结构化提炼", "真实样本"],
    }
    if extraction.warnings:
        frontmatter["extraction_warnings"] = list(extraction.warnings)
    _write_markdown(target_path, frontmatter, extraction.markdown)


def _compile_meeting_structured_source(
    source_path: Path,
    transcript_path: Path,
    target_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    source_hash: str,
    extraction: MeetingStructuredExtractionResult,
) -> None:
    title = source_path.stem
    frontmatter = {
        "title": title,
        "type": "meeting",
        "content_kind": "meeting_structured_extract",
        "source_domain": "project_r_raw",
        "authority_level": "source_record_pending_review",
        "project_r_source_file": _relative_posix(source_path, settings.raw_path),
        "project_r_transcript_file": _relative_posix(transcript_path, settings.raw_path),
        "project_r_source_sha256": source_hash,
        "project_r_ingested_at": ingested_at,
        "source_file": _relative_posix(source_path, settings.raw_path),
        "source_file_sha256": source_hash,
        "source_file_type": source_path.suffix.lower().lstrip(".") or "media",
        "preprocess_skill": MEETING_PREPROCESS_SKILL,
        "preprocess_version": MEETING_PREPROCESS_VERSION,
        "preprocess_status": "partial" if extraction.review_status == "pending_review" else "succeeded",
        "prompt_version": MEETING_PROMPT_VERSION,
        "extraction_status": extraction.extraction_status,
        "review_status": extraction.review_status,
        "extractor": extraction.extractor,
        "language_policy": extraction.language_policy,
        "transcription_status": extraction.transcription_status,
        "segment_count": extraction.segment_count,
        "action_item_count": extraction.action_item_count,
        "decision_count": extraction.decision_count,
        "risk_count": extraction.risk_count,
        "tags": ["会议", "音视频转写", "待审核"],
    }
    if extraction.warnings:
        frontmatter["extraction_warnings"] = list(extraction.warnings)
    _write_markdown(target_path, frontmatter, extraction.markdown)


def approve_pending_review_markdown(
    settings: GBrainSettings,
    pending_relative_path: str,
    *,
    content: str | None = None,
    reviewer_id: int | None = None,
) -> dict[str, Any]:
    pending_path = (settings.derived_path / pending_relative_path).resolve()
    derived_root = settings.derived_path.resolve()
    try:
        pending_path.relative_to(derived_root)
    except ValueError as exc:
        raise ValueError("pending review path escapes derived root") from exc
    if PENDING_REVIEW_DIR not in pending_path.relative_to(derived_root).parts:
        raise ValueError("path is not inside the pending review area")
    if not pending_path.exists():
        raise FileNotFoundError(pending_path)

    original_text = pending_path.read_text(encoding="utf-8")
    next_text = content if content is not None else original_text
    next_frontmatter, next_body = _split_frontmatter(next_text)
    original_frontmatter, _ = _split_frontmatter(original_text)
    frontmatter = {**original_frontmatter, **next_frontmatter}
    frontmatter["review_status"] = "approved"
    frontmatter["project_r_reviewed_at"] = _utc_now()
    if reviewer_id is not None:
        frontmatter["project_r_reviewer_id"] = reviewer_id

    relative = pending_path.relative_to(derived_root)
    final_parts = [part for part in relative.parts if part != PENDING_REVIEW_DIR]
    final_path = derived_root.joinpath(*final_parts)
    _write_markdown(final_path, frontmatter, next_body.strip() + "\n")
    try:
        pending_path.unlink()
    except OSError:
        pass

    git_status = _commit_derived_changes(
        settings.derived_path,
        {"compiled": 1, "skipped": 0, "failed": 0},
        settings.local_git_enabled,
    )
    return {
        "approved_file": _relative_posix(final_path, settings.derived_path),
        "pending_file": pending_relative_path,
        "local_git": git_status,
    }


def _compile_pdf_source(
    source_path: Path,
    target_path: Path,
    settings: GBrainSettings,
    ingested_at: str,
    source_hash: str,
) -> None:
    raise RuntimeError(
        "PDF text extraction is prohibited as a direct GBrain-ready route; "
        "use pdf-structured-preprocess with MiMo V2.5 and text only as auxiliary evidence"
    )


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not match:
        return {}, text
    raw_frontmatter, body = match.groups()
    parsed = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(parsed, dict):
        return {}, body
    return parsed, body


def _write_markdown(path: Path, frontmatter: dict[str, Any], body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized_frontmatter = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    path.write_text(f"---\n{serialized_frontmatter}\n---\n\n{body}", encoding="utf-8")


def _target_path(source_path: Path, settings: GBrainSettings, category: str) -> Path:
    return settings.derived_path / category / f"{_safe_filename(source_path.stem)}.md"


def _pending_review_path(approved_target_path: Path, settings: GBrainSettings) -> Path:
    relative = approved_target_path.resolve().relative_to(settings.derived_path.resolve())
    return settings.derived_path / PENDING_REVIEW_DIR / relative


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip().strip(".")
    return cleaned or "untitled"


def _markdown_table(rows: list[list[str]]) -> str:
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    separator = ["---"] * width
    body = normalized[1:]
    table_rows = [header, separator, *body]
    return "\n".join("| " + " | ".join(row) + " |" for row in table_rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _result_to_manifest_item(result: CompiledSource, settings: GBrainSettings) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_file": _relative_posix(result.source_path, settings.raw_path),
        "status": result.status,
        "source_sha256": result.source_sha256,
    }
    if result.target_path is not None:
        item["target_file"] = _relative_posix(result.target_path, settings.derived_path)
    if result.error:
        item["error"] = result.error
    item.update({key: value for key, value in result.metadata.items() if value not in (None, [], {})})
    return item


def _iter_raw_source_files(
    raw_path: Path,
    pdf_image_sidecar_dirs: list[Path],
    *,
    excluded_files: set[Path] | None = None,
) -> list[Path]:
    excluded = {path.resolve() for path in (excluded_files or set())}
    source_files: list[Path] = []
    for source_path in sorted(raw_path.rglob("*")):
        if not source_path.is_file():
            continue
        if source_path.resolve() in excluded:
            continue
        if _is_relative_to_any(source_path, pdf_image_sidecar_dirs):
            continue
        source_files.append(source_path)
    return source_files


def _pdf_image_sidecar_dirs(raw_path: Path) -> list[Path]:
    directories: list[Path] = []
    for pdf_path in raw_path.rglob("*.pdf"):
        for candidate in _pdf_image_sidecar_candidates(pdf_path):
            if candidate.is_dir() and candidate not in directories:
                directories.append(candidate)
    return directories


def _is_relative_to_any(path: Path, parents: list[Path]) -> bool:
    resolved_path = path.resolve()
    for parent in parents:
        try:
            resolved_path.relative_to(parent.resolve())
            return True
        except ValueError:
            continue
    return False


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _commit_derived_changes(derived_path: Path, summary: dict[str, Any], enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "committed": False, "reason": "local git is disabled"}

    git_dir = derived_path / ".git"
    if not git_dir.exists():
        return {"enabled": False, "committed": False, "reason": "derived path is not a git repository"}

    add = subprocess.run(["git", "add", "-A"], cwd=derived_path, capture_output=True, text=True, check=False)
    if add.returncode != 0:
        return {"enabled": True, "committed": False, "error": (add.stderr or add.stdout).strip()}

    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=derived_path, check=False)
    if diff.returncode == 0:
        return {"enabled": True, "committed": False, "reason": "no derived changes"}

    message = (
        "Compile company-wiki sources "
        f"({summary['compiled']} compiled, {summary['skipped']} skipped, {summary['failed']} failed)"
    )
    commit = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Project_R GBrain Adapter",
            "-c",
            "user.email=project-r-gbrain@local",
            "commit",
            "-m",
            message,
        ],
        cwd=derived_path,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "enabled": True,
        "committed": commit.returncode == 0,
        "message": message,
        "output": (commit.stdout or commit.stderr).strip(),
        "error": None if commit.returncode == 0 else (commit.stderr or commit.stdout).strip(),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
