from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.gbrain import (
    CUSTOMER_INTELLIGENCE_SOURCE_ID,
    CUSTOMER_REFERENCE_SOURCE_ID,
    GBrainAdapter,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    ensure_customer_gbrain_environment,
    load_gbrain_settings,
)
from app.features.knowledge.gbrain.ingest import _commit_derived_changes, _relative_posix, _split_frontmatter, _write_markdown


BACKEND_DIR = Path(__file__).resolve().parents[4]
CUSTOMER_REFERENCE_ROOT = BACKEND_DIR / "workspace_data" / "customer" / "reference"
CUSTOMER_REFERENCE_DERIVED = CUSTOMER_REFERENCE_ROOT / "derived"
CUSTOMER_REFERENCE_MANIFESTS = CUSTOMER_REFERENCE_ROOT / "manifests"
CUSTOMER_CRM_GBRAIN_READY = BACKEND_DIR / "workspace_data" / "_preprocessed" / "customer" / "crm" / "gbrain-ready"
CUSTOMER_INTELLIGENCE_SOURCE_NAME = "Project_R Customer Intelligence"
CUSTOMER_REFERENCE_SOURCE_NAME = "Project_R Legacy Customer Reference"
CUSTOMER_LOCAL_INDEX_MIN_SCORE = 6
CUSTOMER_LOCAL_INDEX_BASE_SCORE = 1.2
CUSTOMER_LOCAL_INDEX_MAX_CHARS = 1800

PROFILE_DIRS = {
    "01_Clients": ("clients", "client_profile"),
    "02_Projects": ("projects", "customer_project_profile"),
    "03_Companies": ("companies", "customer_company_profile"),
}
RAW_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".csv"}
RAW_PENDING_EXTENSIONS = {
    ".png": "pending_vision_extraction",
    ".jpg": "pending_vision_extraction",
    ".jpeg": "pending_vision_extraction",
    ".webp": "pending_vision_extraction",
    ".gif": "pending_vision_extraction",
    ".zip": "pending_archive_extraction",
    ".xls": "pending_spreadsheet_extraction",
    ".xlsx": "pending_spreadsheet_extraction",
}
CUSTOMER_WORKSPACE_PROFILE_DIRS = {
    "01-客户档案": ("clients", "customer_workspace_client_profile"),
    "02-联系人与关系": ("contacts", "customer_workspace_relationship_profile"),
    "03-沟通记录": ("events", "customer_workspace_communication_record"),
}
CUSTOMER_WORKSPACE_RAW_DIR = "raw"
CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME = "customer-workspace-ingest-manifest.json"


@dataclass(frozen=True)
class CustomerCompileResult:
    source_path: Path
    status: str
    target_path: Path | None = None
    error: str | None = None
    source_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def customer_reference_source_plan(root: Path | None = None) -> dict[str, Any]:
    root = root or CUSTOMER_REFERENCE_ROOT
    derived = root / "derived"
    return {
        "source_id": CUSTOMER_REFERENCE_SOURCE_ID,
        "name": CUSTOMER_REFERENCE_SOURCE_NAME,
        "path": str(derived.resolve()),
        "federated": False,
        "operator_command": (
            f"gbrain sources add {CUSTOMER_REFERENCE_SOURCE_ID} "
            f"--path {derived.resolve()} --name \"{CUSTOMER_REFERENCE_SOURCE_NAME}\" --no-federated"
        ),
    }


def compile_customer_reference_sources(root: Path | None = None) -> dict[str, Any]:
    root = root or CUSTOMER_REFERENCE_ROOT
    derived = root / "derived"
    manifests = root / "manifests"
    derived.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    _ensure_local_git_repo(derived)
    started_at = _utc_now()

    results: list[CustomerCompileResult] = []
    for source_dir_name, (target_dir_name, profile_kind) in PROFILE_DIRS.items():
        source_dir = root / source_dir_name
        for source_path in _iter_files(source_dir, {".md", ".markdown"}):
            results.append(_compile_profile_markdown(source_path, root, derived, target_dir_name, profile_kind, started_at))

    raw_root = root / "04_Raw"
    for source_path in _iter_files(raw_root, RAW_TEXT_EXTENSIONS | set(RAW_PENDING_EXTENSIONS)):
        if source_path.suffix.lower() in RAW_TEXT_EXTENSIONS:
            results.append(_compile_raw_text(source_path, root, derived, started_at))
        else:
            results.append(
                CustomerCompileResult(
                    source_path=source_path,
                    status=RAW_PENDING_EXTENSIONS.get(source_path.suffix.lower(), "pending_extractor_capability"),
                    source_sha256=_sha256(source_path),
                    metadata={
                        "source_area": "04_Raw",
                        "file_kind": source_path.suffix.lower().lstrip(".") or "unknown",
                        "reason": "customer raw source requires Project_R extractor before GBrain sync",
                    },
                )
            )

    summary = _summary(results)
    manifest = {
        "schema_version": 1,
        "source_id": CUSTOMER_REFERENCE_SOURCE_ID,
        "source_scope": "restricted_customer_intelligence",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "root": str(root.resolve()),
        "derived_path": str(derived.resolve()),
        "items": [_manifest_item(result, root, derived) for result in results],
        "summary": summary,
    }
    manifest_path = manifests / "customer-reference-ingest-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    settings = load_gbrain_settings()
    git_status = _commit_derived_changes(derived, summary, settings.local_git_enabled)
    manifest["local_git"] = git_status
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def compile_customer_workspace_sources(
    workspace: Any,
    *,
    source_path: str | None = None,
    recursive: bool = True,
) -> dict[str, Any]:
    settings = load_gbrain_settings()
    environment = ensure_customer_gbrain_environment(workspace, settings)
    paths = customer_source_paths_for_workspace(workspace)
    source_id = customer_source_id_for_workspace(workspace)
    root = paths["root"]
    derived = paths["derived"]
    manifests = paths["manifests"]
    runs = paths["runs"]
    derived.mkdir(parents=True, exist_ok=True)
    manifests.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    source_path_filter = _normalized_ingest_path(source_path)
    if source_path_filter:
        target = (root / source_path_filter).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("ingest path escapes customer workspace root") from exc
        if not target.exists():
            raise FileNotFoundError(f"ingest path does not exist: {source_path_filter}")

    results: list[CustomerCompileResult] = []
    for source_dir_name, (target_dir_name, profile_kind) in CUSTOMER_WORKSPACE_PROFILE_DIRS.items():
        source_dir = root / source_dir_name
        for candidate_path in _iter_files(source_dir, {".md", ".markdown", ".txt", ".csv"}):
            if not _is_in_ingest_scope(candidate_path, root, source_path_filter=source_path_filter, recursive=recursive):
                continue
            results.append(_compile_customer_workspace_text(candidate_path, root, derived / target_dir_name, profile_kind, started_at))

    raw_root = root / CUSTOMER_WORKSPACE_RAW_DIR
    for candidate_path in _iter_files(raw_root, RAW_TEXT_EXTENSIONS | set(RAW_PENDING_EXTENSIONS)):
        if not _is_in_ingest_scope(candidate_path, root, source_path_filter=source_path_filter, recursive=recursive):
            continue
        if candidate_path.suffix.lower() in RAW_TEXT_EXTENSIONS:
            results.append(_compile_customer_workspace_text(candidate_path, root, derived / "raw-events", "customer_workspace_raw_text_event", started_at))
        else:
            results.append(
                CustomerCompileResult(
                    source_path=candidate_path,
                    status="pending_extractor_capability",
                    source_sha256=_sha256(candidate_path),
                    metadata={
                        "source_area": CUSTOMER_WORKSPACE_RAW_DIR,
                        "file_kind": candidate_path.suffix.lower().lstrip(".") or "unknown",
                        "pending_reason": RAW_PENDING_EXTENSIONS.get(candidate_path.suffix.lower(), "pending_extractor_capability"),
                        "reason": "customer workspace source requires Project_R extractor before GBrain sync",
                    },
                )
            )

    summary = _summary(results)
    manifest = {
        "schema_version": 1,
        "source_id": source_id,
        "source_scope": "restricted_customer_intelligence",
        "workspace_id": getattr(workspace, "id", None),
        "workspace_name": getattr(workspace, "name", ""),
        "workspace_slug": getattr(workspace, "slug", ""),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "root": str(root.resolve()),
        "raw_path": str(paths["raw"].resolve()),
        "ingest_path": source_path_filter,
        "ingest_recursive": recursive,
        "gbrain_ready_path": str(paths["gbrain_ready"].resolve()),
        "derived_path": str(derived.resolve()),
        "legacy_derived_path": str(paths["legacy_derived"].resolve()) if paths.get("legacy_derived") else None,
        "runs_path": str(runs.resolve()),
        "manifests_path": str(manifests.resolve()),
        "environment_ok": environment["ok"],
        "items": [_manifest_item(result, root, derived) for result in results],
        "summary": summary,
    }
    manifest_path = manifests / CUSTOMER_WORKSPACE_INGEST_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    git_status = _commit_derived_changes(derived, summary, settings.local_git_enabled)
    manifest["local_git"] = git_status
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def ensure_and_sync_customer_reference(*, full: bool = False, no_embed: bool = False) -> dict[str, Any]:
    plan = customer_reference_source_plan()
    adapter = GBrainAdapter()
    registration = adapter.ensure_source(plan)
    sync_result = (
        adapter.sync_registered_source(plan, full=full, no_pull=True, no_embed=no_embed)
        if registration.get("ok")
        else {"status": "skipped", "ok": False, "error": "customer-reference source registration failed"}
    )
    think_client = adapter.ensure_think_source_client(CUSTOMER_REFERENCE_SOURCE_ID)
    return {
        "ok": bool(registration.get("ok") and sync_result.get("status") == "ok" and think_client.get("ok")),
        "source_id": CUSTOMER_REFERENCE_SOURCE_ID,
        "plan": plan,
        "registration": registration,
        "sync": sync_result,
        "think_client": {
            key: value
            for key, value in think_client.items()
            if key not in {"client_secret"}
        },
    }


def search_customer_reference_sources(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    adapter = GBrainAdapter()
    response = adapter.query(query, source_id=CUSTOMER_REFERENCE_SOURCE_ID, limit=max(limit, 8), detail="medium")
    native = response.get("result") if isinstance(response.get("result"), list) else []
    sources: list[dict[str, Any]] = []
    for item in native:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "file": f"gbrain:{CUSTOMER_REFERENCE_SOURCE_ID}/{item.get('slug') or item.get('page_id') or ''}",
                "source_title": str(item.get("title") or item.get("slug") or "GBrain customer source"),
                "content": str(item.get("chunk_text") or ""),
                "score": float(item.get("score") or 0.0),
                "type": "gbrain_customer_reference",
                "metadata": item,
            }
        )
    sources.extend(
        _local_customer_sources(
            query,
            derived=CUSTOMER_REFERENCE_DERIVED,
            source_id=CUSTOMER_REFERENCE_SOURCE_ID,
            source_type="gbrain_customer_reference_local_index",
        )
    )
    return _dedupe_ranked_sources(sources)[:limit]


def search_customer_intelligence_sources(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    adapter = GBrainAdapter()
    response = adapter.query(query, source_id=CUSTOMER_INTELLIGENCE_SOURCE_ID, limit=max(limit, 8), detail="medium")
    native = response.get("result") if isinstance(response.get("result"), list) else []
    sources: list[dict[str, Any]] = []
    for item in native:
        if not isinstance(item, dict):
            continue
        sources.append(
            {
                "file": f"gbrain:{CUSTOMER_INTELLIGENCE_SOURCE_ID}/{item.get('slug') or item.get('page_id') or ''}",
                "source_title": str(item.get("title") or item.get("slug") or "GBrain customer source"),
                "content": str(item.get("chunk_text") or ""),
                "score": float(item.get("score") or 0.0),
                "type": "gbrain_customer_intelligence",
                "metadata": item,
            }
        )
    sources.extend(
        _local_customer_sources(
            query,
            derived=CUSTOMER_CRM_GBRAIN_READY,
            source_id=CUSTOMER_INTELLIGENCE_SOURCE_ID,
            source_type="gbrain_customer_intelligence_local_index",
        )
    )
    return _dedupe_ranked_sources(sources)[:limit]


def _compile_profile_markdown(
    source_path: Path,
    root: Path,
    derived: Path,
    target_dir_name: str,
    profile_kind: str,
    ingested_at: str,
) -> CustomerCompileResult:
    try:
        source_hash = _sha256(source_path)
        text = source_path.read_text(encoding="utf-8", errors="replace")
        original_frontmatter, body = _split_frontmatter(text)
        title = str(original_frontmatter.get("name") or original_frontmatter.get("title") or source_path.stem)
        target_path = _unique_target_path(derived / target_dir_name, source_path, root)
        frontmatter = {
            **original_frontmatter,
            "title": title,
            "type": original_frontmatter.get("type") or profile_kind,
            "content_kind": profile_kind,
            "source_scope": "restricted_customer_intelligence",
            "authority_level": "customer_reference_profile",
            "project_r_source_file": _relative_posix(source_path, root),
            "project_r_source_sha256": source_hash,
            "project_r_ingested_at": ingested_at,
            "extraction_status": "curated_customer_markdown",
            "review_status": "approved",
        }
        _write_markdown(target_path, frontmatter, body.strip() + "\n")
        return CustomerCompileResult(
            source_path=source_path,
            status="compiled",
            target_path=target_path,
            source_sha256=source_hash,
            metadata={"content_kind": profile_kind},
        )
    except Exception as exc:
        return CustomerCompileResult(source_path=source_path, status="failed", error=str(exc))


def _local_customer_sources(
    query: str,
    *,
    derived: Path,
    source_id: str,
    source_type: str,
) -> list[dict[str, Any]]:
    if not derived.exists():
        return []
    tokens = _customer_query_tokens(query)
    if not tokens:
        return []

    results: list[dict[str, Any]] = []
    for path in sorted(derived.rglob("*.md"), key=lambda item: str(item).lower()):
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter, body = _split_frontmatter(text)
        rel = _relative_posix(path, derived)
        title = str(frontmatter.get("title") or path.stem)
        haystack_title = f"{title} {rel}".lower()
        haystack_body = body.lower()
        score = 0
        query_lower = query.lower()
        title_lower = title.lower()
        if title_lower and (title_lower == query_lower.strip() or title_lower in query_lower):
            score += 18
        for token in tokens:
            token_lower = token.lower()
            if token_lower in haystack_title:
                score += 6
            if token_lower in haystack_body:
                score += 1
        if score < CUSTOMER_LOCAL_INDEX_MIN_SCORE:
            continue
        excerpt = _best_excerpt(body, tokens)
        results.append(
            {
                "file": f"gbrain:{source_id}/{rel}",
                "source_title": title,
                "content": excerpt,
                "score": CUSTOMER_LOCAL_INDEX_BASE_SCORE + min(score, 40) / 100,
                "type": source_type,
                "metadata": {
                    "source_id": source_id,
                    "local_path": rel,
                    "content_kind": frontmatter.get("content_kind"),
                    "local_score": score,
                },
            }
        )
    return results


def _customer_query_tokens(query: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9&.'-]{1,}|[\u4e00-\u9fff]{2,}", query)
    tokens: list[str] = []
    for token in raw_tokens:
        clean = token.strip(" .,'\"")
        if len(clean) < 2:
            continue
        tokens.append(clean)
        if re.search(r"[\u4e00-\u9fff]", clean):
            for size in (2, 3, 4):
                tokens.extend(clean[index : index + size] for index in range(0, max(0, len(clean) - size + 1)))
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(token)
    return ordered[:80]


def _best_excerpt(body: str, tokens: list[str]) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", body) if paragraph.strip()]
    if not paragraphs:
        return body[:CUSTOMER_LOCAL_INDEX_MAX_CHARS]
    ranked = sorted(
        paragraphs,
        key=lambda paragraph: sum(1 for token in tokens if token.lower() in paragraph.lower()),
        reverse=True,
    )
    excerpt = "\n\n".join(ranked[:3]).strip()
    return excerpt[:CUSTOMER_LOCAL_INDEX_MAX_CHARS]


def _dedupe_ranked_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for source in sources:
        key = str(source.get("file") or source.get("source_title") or "")
        existing = deduped.get(key)
        if existing is None or float(source.get("score") or 0) > float(existing.get("score") or 0):
            deduped[key] = source
    return sorted(deduped.values(), key=lambda item: float(item.get("score") or 0), reverse=True)


def _compile_raw_text(source_path: Path, root: Path, derived: Path, ingested_at: str) -> CustomerCompileResult:
    try:
        source_hash = _sha256(source_path)
        raw = source_path.read_text(encoding="utf-8", errors="replace")
        body = _clean_raw_text(raw, source_path.suffix.lower())
        title = source_path.stem
        target_path = _unique_target_path(derived / "raw-events", source_path, root)
        frontmatter = {
            "title": title,
            "type": "customer_raw_event",
            "content_kind": "customer_raw_text_event",
            "source_scope": "restricted_customer_intelligence",
            "authority_level": "customer_source_record",
            "project_r_source_file": _relative_posix(source_path, root),
            "project_r_source_sha256": source_hash,
            "project_r_ingested_at": ingested_at,
            "extraction_status": "raw_text_cleaned",
            "review_status": "approved",
            "tags": ["customer-intelligence", "raw-event"],
        }
        markdown = f"# {title}\n\n{body.strip()}\n"
        _write_markdown(target_path, frontmatter, markdown)
        return CustomerCompileResult(
            source_path=source_path,
            status="compiled",
            target_path=target_path,
            source_sha256=source_hash,
            metadata={"content_kind": "customer_raw_text_event"},
        )
    except Exception as exc:
        return CustomerCompileResult(source_path=source_path, status="failed", error=str(exc))


def _compile_customer_workspace_text(
    source_path: Path,
    root: Path,
    target_dir: Path,
    profile_kind: str,
    ingested_at: str,
) -> CustomerCompileResult:
    try:
        source_hash = _sha256(source_path)
        raw = source_path.read_text(encoding="utf-8", errors="replace")
        original_frontmatter, body = _split_frontmatter(raw)
        if source_path.suffix.lower() == ".csv":
            body = _clean_raw_text(body or raw, ".csv")
        title = str(original_frontmatter.get("name") or original_frontmatter.get("title") or source_path.stem)
        target_path = _unique_target_path(target_dir, source_path, root)
        frontmatter = {
            **original_frontmatter,
            "title": title,
            "type": original_frontmatter.get("type") or profile_kind,
            "content_kind": profile_kind,
            "source_scope": "restricted_customer_intelligence",
            "authority_level": "customer_workspace_source_record",
            "project_r_source_file": _relative_posix(source_path, root),
            "project_r_source_sha256": source_hash,
            "project_r_ingested_at": ingested_at,
            "extraction_status": "customer_workspace_text_compiled",
            "review_status": "approved",
            "tags": ["customer-intelligence", "customer-workspace"],
        }
        markdown = body.strip()
        if not markdown.startswith("#"):
            markdown = f"# {title}\n\n{markdown}"
        _write_markdown(target_path, frontmatter, markdown.strip() + "\n")
        return CustomerCompileResult(
            source_path=source_path,
            status="compiled",
            target_path=target_path,
            source_sha256=source_hash,
            metadata={"content_kind": profile_kind},
        )
    except Exception as exc:
        return CustomerCompileResult(source_path=source_path, status="failed", error=str(exc))


def _iter_files(root: Path, extensions: set[str]) -> list[Path]:
    if not root.exists():
        return []
    ignored_parts = {"derived", "manifests", ".git", ".trash", "99-archive"}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignored_parts for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in extensions:
            files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _is_in_ingest_scope(path: Path, root: Path, *, source_path_filter: str, recursive: bool) -> bool:
    if not source_path_filter:
        return True
    target = (root / source_path_filter).resolve()
    resolved = path.resolve()
    if target.is_file():
        return resolved == target
    if not target.is_dir():
        return False
    if not recursive and resolved.parent != target:
        return False
    try:
        resolved.relative_to(target)
        return True
    except ValueError:
        return False


def _normalized_ingest_path(source_path: str | None) -> str:
    if source_path is None:
        return ""
    return source_path.replace("\\", "/").strip("/")


def _clean_raw_text(text: str, suffix: str) -> str:
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", "", text)
    text = re.sub(r"!\[\[[^\]]+]]", "", text)
    text = re.sub(r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if suffix == ".csv":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 80:
            lines = lines[:80] + ["..."]
        return "## CSV Text Preview\n\n```csv\n" + "\n".join(lines) + "\n```"
    return text.strip()


def _unique_target_path(target_dir: Path, source_path: Path, root: Path) -> Path:
    relative = source_path.relative_to(root)
    stem = _slugify("__".join(relative.with_suffix("").parts))
    digest = hashlib.sha1(_relative_posix(source_path, root).encode("utf-8")).hexdigest()[:8]
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{stem}-{digest}.md"


def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    return value[:120] or "customer-source"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _summary(results: list[CustomerCompileResult]) -> dict[str, int]:
    statuses = {result.status for result in results}
    summary = {status: sum(1 for result in results if result.status == status) for status in sorted(statuses)}
    summary["total"] = len(results)
    summary["compiled"] = sum(1 for result in results if result.status == "compiled")
    summary["skipped"] = 0
    summary["failed"] = sum(1 for result in results if result.status == "failed")
    return summary


def _ensure_local_git_repo(path: Path) -> None:
    if (path / ".git").exists():
        return
    subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=False)


def _manifest_item(result: CustomerCompileResult, root: Path, derived: Path) -> dict[str, Any]:
    item = {
        "source_file": _relative_posix(result.source_path, root),
        "status": result.status,
        "source_sha256": result.source_sha256,
        **result.metadata,
    }
    if result.target_path is not None:
        item["target_file"] = _relative_posix(result.target_path, derived)
    if result.error:
        item["error"] = result.error
    return item


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
