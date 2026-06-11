from __future__ import annotations

import re
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from app.features.knowledge.gbrain import (
    CRM_CUSTOMER_SOURCE_ID,
    CUSTOMER_INTELLIGENCE_SOURCE_ID,
    CUSTOMER_REFERENCE_SOURCE_ID,
    load_gbrain_settings,
    resolve_gbrain_source_paths,
)
from app.features.knowledge.gbrain.customer_sources import CUSTOMER_REFERENCE_DERIVED
from app.features.knowledge.gbrain.ingest import _relative_posix, _split_frontmatter, _write_markdown


LINK_FIELDS: dict[str, str] = {
    "linked_people": "linked_person",
    "linked_projects": "linked_project",
    "linked_companies": "linked_company",
    "source_events": "source_event",
}
SINGLE_LINK_FIELDS: dict[str, str] = {
    "company": "affiliated_company",
}


@dataclass(frozen=True)
class GraphPage:
    id: str
    title: str
    entity_type: str
    source_id: str
    file: str
    source_file: str
    frontmatter: dict[str, Any]
    body: str


def build_source_graph(
    source_id: str,
    *,
    derived_path: Path | None = None,
    focus: str | None = None,
    entity_type: str | None = None,
    limit: int = 120,
) -> dict[str, Any]:
    source_id = str(source_id or "").strip()
    root = (derived_path or _default_derived_path(source_id)).resolve()
    pages = _load_graph_pages(root, source_id)
    if not pages:
        return {
            "ok": False,
            "source_id": source_id,
            "derived_path": str(root),
            "nodes": [],
            "edges": [],
            "events": [],
            "warnings": ["No readable Markdown pages found for graph source."],
        }

    by_source_file = {_normalize_ref(page.source_file): page for page in pages if page.source_file}
    for page in pages:
        by_source_file.setdefault(_normalize_ref(page.id), page)
    by_title = {_normalize_ref(page.title): page for page in pages if page.title}
    focus_terms = _focus_terms(focus)
    selected_ids = _select_page_ids(pages, focus_terms, entity_type, max(1, min(limit, 500)))

    edges: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    extra_node_ids: set[str] = set()
    synthetic_nodes: dict[str, GraphPage] = {}
    for page in pages:
        if selected_ids and page.id not in selected_ids:
            continue
        page_edges, page_events, referenced_ids, page_synthetic_nodes = _page_relationships(page, by_source_file, by_title)
        edges.extend(page_edges)
        events.extend(page_events)
        extra_node_ids.update(referenced_ids)
        synthetic_nodes.update({node.id: node for node in page_synthetic_nodes})

    node_ids = set(selected_ids) | extra_node_ids
    nodes = [_node_payload(page) for page in pages if page.id in node_ids]
    nodes.extend(_node_payload(page) for page in synthetic_nodes.values() if page.id in node_ids)
    nodes_by_id = {node["id"]: node for node in nodes}
    filtered_edges = [
        edge for edge in _dedupe_edges(edges)
        if edge["from"] in nodes_by_id and edge["to"] in nodes_by_id
    ]
    filtered_events = [
        event for event in events
        if event["entity_id"] in nodes_by_id
    ]
    return {
        "ok": True,
        "source_id": source_id,
        "derived_path": str(root),
        "focus": focus,
        "entity_type": entity_type,
        "nodes": nodes,
        "edges": filtered_edges,
        "events": _dedupe_events(filtered_events),
        "stats": {
            "pages_scanned": len(pages),
            "nodes": len(nodes),
            "edges": len(filtered_edges),
            "events": len(filtered_events),
        },
        "warnings": [],
    }


def build_entity_merge_candidates(
    source_id: str,
    *,
    derived_path: Path | None = None,
    focus: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    source_id = str(source_id or "").strip()
    root = (derived_path or _default_derived_path(source_id)).resolve()
    pages = _load_graph_pages(root, source_id)
    if not pages:
        return {
            "ok": False,
            "source_id": source_id,
            "derived_path": str(root),
            "candidates": [],
            "stats": {"pages_scanned": 0, "candidates": 0},
            "warnings": ["No readable Markdown pages found for entity merge review."],
        }

    by_source_file = {_normalize_ref(page.source_file): page for page in pages if page.source_file}
    for page in pages:
        by_source_file.setdefault(_normalize_ref(page.id), page)
    by_title = {_normalize_ref(page.title): page for page in pages if page.title}
    focus_terms = _focus_terms(focus)
    candidates: dict[str, dict[str, Any]] = {}

    for page in pages:
        if focus_terms and not _page_matches_focus(page, focus_terms):
            continue
        for field in [*LINK_FIELDS.keys(), *SINGLE_LINK_FIELDS.keys()]:
            for raw_ref in _as_list(page.frontmatter.get(field)):
                ref = _clean_ref(raw_ref)
                if not ref or _resolve_ref(raw_ref, by_source_file, by_title):
                    continue
                unresolved = _placeholder_page(source_id, raw_ref)
                if not unresolved:
                    continue
                targets = _candidate_targets(ref, pages)
                candidate = _unresolved_candidate(page, unresolved, field, raw_ref, targets)
                candidates[candidate["id"]] = candidate

    for key, group in _duplicate_page_groups(pages).items():
        if focus_terms and not any(_page_matches_focus(page, focus_terms) for page in group):
            continue
        candidate = _duplicate_candidate(source_id, key, group)
        candidates[candidate["id"]] = candidate

    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            -float(item.get("confidence") or 0),
            str(item.get("candidate_type") or ""),
            str(item.get("title") or "").lower(),
        ),
    )[: max(1, min(limit, 200))]
    return {
        "ok": True,
        "source_id": source_id,
        "derived_path": str(root),
        "focus": focus,
        "candidates": ordered,
        "stats": {
            "pages_scanned": len(pages),
            "candidates": len(ordered),
            "unresolved": sum(1 for item in ordered if item.get("candidate_type") == "unresolved_entity"),
            "duplicates": sum(1 for item in ordered if item.get("candidate_type") == "duplicate_entity_pages"),
        },
        "warnings": [],
    }


def apply_entity_merge_candidate_action(
    source_id: str,
    candidate_id: str,
    action: str,
    *,
    derived_path: Path | None = None,
    actor: str = "",
) -> dict[str, Any]:
    source_id = str(source_id or "").strip()
    root = (derived_path or _default_derived_path(source_id)).resolve()
    action = str(action or "").strip()
    if action not in {"create_entity_page", "dismiss", "record_alias", "apply_relink_changes"}:
        return {"ok": False, "status": "unsupported_action", "error": f"Unsupported entity merge action: {action}"}

    candidates = build_entity_merge_candidates(source_id, derived_path=root, limit=200).get("candidates", [])
    candidate = next((item for item in candidates if str(item.get("id") or "") == candidate_id), None)
    if not isinstance(candidate, dict):
        return {"ok": False, "status": "candidate_not_found", "error": "Entity merge candidate is no longer available"}

    if action == "dismiss":
        decision = _record_entity_merge_decision(root, candidate, action, actor=actor)
        return {"ok": True, "status": "dismissed", "candidate": candidate, "decision": decision}

    if action == "record_alias":
        alias_result = _record_alias_review(root, candidate, actor=actor)
        if not alias_result.get("ok"):
            return {**alias_result, "candidate": candidate}
        decision = _record_entity_merge_decision(
            root,
            candidate,
            action,
            actor=actor,
            created_file=str(alias_result.get("created_file") or ""),
        )
        return {**alias_result, "candidate": candidate, "decision": decision}

    if action == "apply_relink_changes":
        relink_result = _apply_relink_changes(source_id, root, candidate, actor=actor)
        if not relink_result.get("ok"):
            return {**relink_result, "candidate": candidate}
        decision = _record_entity_merge_decision(
            root,
            candidate,
            action,
            actor=actor,
            created_file=",".join(str(item) for item in relink_result.get("changed_files") or []),
        )
        return {**relink_result, "candidate": candidate, "decision": decision}

    if candidate.get("candidate_type") != "unresolved_entity":
        return {
            "ok": False,
            "status": "unsupported_candidate_type",
            "error": "Only unresolved entity candidates can create an entity page in this MVP",
            "candidate": candidate,
        }
    if candidate.get("suggested_action") not in {"create_entity_page", "create_event_page"}:
        return {
            "ok": False,
            "status": "requires_manual_merge",
            "error": "This candidate points to an existing target and requires a manual merge/relink review",
            "candidate": candidate,
        }

    unresolved = candidate.get("unresolved_node") if isinstance(candidate.get("unresolved_node"), dict) else {}
    source_file = str(unresolved.get("source_file") or candidate.get("title") or "").strip()
    target_path = _safe_entity_page_path(root, source_file, str(candidate.get("title") or "Entity"))
    if target_path.exists():
        return {
            "ok": True,
            "status": "already_exists",
            "candidate": candidate,
            "created_file": _relative_posix(target_path, root),
        }

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_entity_stub_markdown(candidate, actor=actor), encoding="utf-8")
    decision = _record_entity_merge_decision(root, candidate, action, actor=actor, created_file=_relative_posix(target_path, root))
    return {
        "ok": True,
        "status": "created",
        "candidate": candidate,
        "created_file": _relative_posix(target_path, root),
        "decision": decision,
    }


def build_entity_merge_candidate_preview(
    source_id: str,
    candidate_id: str,
    *,
    derived_path: Path | None = None,
) -> dict[str, Any]:
    source_id = str(source_id or "").strip()
    root = (derived_path or _default_derived_path(source_id)).resolve()
    candidates = build_entity_merge_candidates(source_id, derived_path=root, limit=200).get("candidates", [])
    candidate = next((item for item in candidates if str(item.get("id") or "") == candidate_id), None)
    if not isinstance(candidate, dict):
        return {"ok": False, "status": "candidate_not_found", "error": "Entity merge candidate is no longer available"}

    canonical, aliases = _alias_review_entities(candidate)
    if not canonical or not aliases:
        return {
            "ok": False,
            "status": "preview_not_applicable",
            "error": "This candidate does not contain enough entity pages for a merge preview",
            "candidate": candidate,
        }

    pages = _load_graph_pages(root, source_id)
    alias_tokens = _entity_reference_tokens(
        aliases,
        include_titles=str(candidate.get("candidate_type") or "") != "duplicate_entity_pages",
    )
    canonical_ref = _canonical_reference(canonical)
    relink_changes = _preview_relink_changes(pages, alias_tokens, canonical_ref)
    alias_target = _safe_alias_review_path(root, candidate)
    return {
        "ok": True,
        "status": "preview_ready",
        "source_id": source_id,
        "derived_path": str(root),
        "candidate": candidate,
        "canonical_entity": canonical,
        "alias_entities": aliases,
        "planned_alias_review_file": _relative_posix(alias_target, root),
        "planned_relink_changes": relink_changes,
        "stats": {
            "pages_scanned": len(pages),
            "alias_entities": len(aliases),
            "planned_relink_changes": len(relink_changes),
        },
        "warnings": [
            "Preview only. No files are modified by this operation.",
            "Full entity page merge and citation rewrite still require a later explicit diff approval.",
        ],
    }


def _default_derived_path(source_id: str) -> Path:
    if source_id == CRM_CUSTOMER_SOURCE_ID or source_id == CUSTOMER_INTELLIGENCE_SOURCE_ID:
        crm_workspace = type("CustomerWorkspace", (), {"slug": "CRM", "name": "CRM", "storage_path": ""})()
        return resolve_gbrain_source_paths("customer", workspace=crm_workspace).gbrain_ready
    if source_id == CUSTOMER_REFERENCE_SOURCE_ID:
        return CUSTOMER_REFERENCE_DERIVED
    settings = load_gbrain_settings()
    if source_id == settings.company_source_id:
        return resolve_gbrain_source_paths("company", settings=settings).gbrain_ready
    raise ValueError(f"Unknown graph source path for {source_id!r}")


def _load_graph_pages(root: Path, source_id: str) -> list[GraphPage]:
    if not root.exists():
        return []
    pages: list[GraphPage] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: str(item).lower()):
        if ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frontmatter, body = _split_frontmatter(text)
        frontmatter = _graph_metadata(frontmatter, body)
        rel = _relative_posix(path, root)
        title = str(frontmatter.get("title") or frontmatter.get("name") or path.stem).strip() or path.stem
        entity_type = str(frontmatter.get("content_kind") or frontmatter.get("type") or "page").strip() or "page"
        source_file = str(frontmatter.get("project_r_source_file") or frontmatter.get("source_file") or "").strip()
        pages.append(
            GraphPage(
                id=rel,
                title=title,
                entity_type=entity_type,
                source_id=source_id,
                file=f"gbrain:{source_id}/{rel}",
                source_file=source_file,
                frontmatter=frontmatter,
                body=body,
            )
        )
    return pages


def _select_page_ids(
    pages: list[GraphPage],
    focus_terms: list[str],
    entity_type: str | None,
    limit: int,
) -> set[str]:
    scored: list[tuple[int, str]] = []
    entity_type_norm = str(entity_type or "").strip().lower()
    for page in pages:
        if entity_type_norm and entity_type_norm not in page.entity_type.lower():
            continue
        score = 1
        haystack = f"{page.title} {page.id} {page.source_file} {page.body[:1200]}".lower()
        for term in focus_terms:
            if term in page.title.lower():
                score += 12
            elif term in page.source_file.lower() or term in page.id.lower():
                score += 8
            elif term in haystack:
                score += 2
        if focus_terms and score <= 1:
            continue
        scored.append((score, page.id))
    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return {page_id for _, page_id in scored[:limit]}


def _page_relationships(
    page: GraphPage,
    by_source_file: dict[str, GraphPage],
    by_title: dict[str, GraphPage],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], list[GraphPage]]:
    edges: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    referenced_ids: set[str] = set()
    synthetic_nodes: list[GraphPage] = []
    for field, relation_type in LINK_FIELDS.items():
        for raw_ref in _as_list(page.frontmatter.get(field)):
            target = _resolve_ref(raw_ref, by_source_file, by_title)
            if not target:
                target = _placeholder_page(page.source_id, raw_ref)
                synthetic_nodes.append(target)
            if not target:
                continue
            referenced_ids.add(target.id)
            edges.append(_edge_payload(page, target, relation_type, field, raw_ref))
            if field == "source_events":
                events.append(_event_payload(page, target, raw_ref))
    for field, relation_type in SINGLE_LINK_FIELDS.items():
        raw_value = page.frontmatter.get(field)
        if not raw_value:
            continue
        target = _resolve_ref(raw_value, by_source_file, by_title)
        if not target:
            target = _placeholder_page(page.source_id, raw_value)
            synthetic_nodes.append(target)
        if not target:
            continue
        referenced_ids.add(target.id)
        edges.append(_edge_payload(page, target, relation_type, field, raw_value))
    return edges, events, referenced_ids, synthetic_nodes


def _unresolved_candidate(
    page: GraphPage,
    unresolved: GraphPage,
    field: str,
    raw_ref: Any,
    targets: list[GraphPage],
) -> dict[str, Any]:
    has_targets = bool(targets)
    suggested_action = "link_to_existing_entity" if has_targets else "create_entity_page"
    if "source_event" in unresolved.entity_type:
        suggested_action = "create_event_page"
    target_nodes = [_node_payload(target) for target in targets[:5]]
    return {
        "id": f"{page.source_id}:unresolved:{_candidate_key(page.id + '|' + field + '|' + _clean_ref(raw_ref))}",
        "source_id": page.source_id,
        "candidate_type": "unresolved_entity",
        "title": unresolved.title,
        "entity_type": unresolved.entity_type,
        "confidence": 0.86 if has_targets else 0.64,
        "suggested_action": suggested_action,
        "reason": "frontmatter reference cannot be resolved to an existing source page",
        "unresolved_node": _node_payload(unresolved),
        "target_nodes": target_nodes,
        "evidence_edges": [_edge_payload(page, unresolved, LINK_FIELDS.get(field) or SINGLE_LINK_FIELDS.get(field) or field, field, raw_ref)],
        "citations": [_node_payload(page)["citation"]],
        "review_source": f"gbrain_entity_merge:{page.source_id}:{_candidate_key(unresolved.title)}",
    }


def _duplicate_candidate(source_id: str, key: str, pages: list[GraphPage]) -> dict[str, Any]:
    title = pages[0].title
    return {
        "id": f"{source_id}:duplicate:{key}",
        "source_id": source_id,
        "candidate_type": "duplicate_entity_pages",
        "title": title,
        "entity_type": pages[0].entity_type,
        "confidence": 0.72,
        "suggested_action": "merge_duplicate_pages",
        "reason": "multiple source pages share the same normalized title",
        "unresolved_node": None,
        "target_nodes": [_node_payload(page) for page in pages[:8]],
        "evidence_edges": [],
        "citations": [_node_payload(page)["citation"] for page in pages[:8]],
        "review_source": f"gbrain_entity_merge:{source_id}:duplicate:{key}",
    }


def _candidate_targets(ref: str, pages: list[GraphPage]) -> list[GraphPage]:
    ref_key = _entity_key(Path(ref).stem or ref)
    if not ref_key:
        return []
    exact: list[GraphPage] = []
    fuzzy: list[GraphPage] = []
    for page in pages:
        title_key = _entity_key(page.title)
        source_key = _entity_key(Path(page.source_file).stem) if page.source_file else ""
        if ref_key in {title_key, source_key}:
            exact.append(page)
        elif len(ref_key) >= 4 and (ref_key in title_key or title_key in ref_key):
            fuzzy.append(page)
    return exact[:5] or fuzzy[:5]


def _duplicate_page_groups(pages: list[GraphPage]) -> dict[str, list[GraphPage]]:
    groups: dict[str, list[GraphPage]] = {}
    for page in pages:
        key = _entity_key(page.title)
        if len(key) < 3 or key in {"page", "note", "meeting", "event"}:
            continue
        groups.setdefault(f"{page.entity_type}:{key}", []).append(page)
    return {key: group for key, group in groups.items() if len(group) > 1}


def _page_matches_focus(page: GraphPage, focus_terms: list[str]) -> bool:
    haystack = f"{page.title} {page.id} {page.source_file} {page.body[:1200]}".lower()
    return any(term in haystack for term in focus_terms)


def _entity_key(value: str) -> str:
    value = _clean_ref(value).lower()
    value = re.sub(r"\.md$", "", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)
    return value


def _candidate_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "-", value.lower()).strip("-")[:160]


def _safe_entity_page_path(root: Path, source_file: str, title: str) -> Path:
    ref = _clean_ref(source_file).replace("\\", "/").strip("/")
    if not ref:
        ref = title
    if not ref.lower().endswith(".md"):
        ref = f"{ref}.md"
    parts = []
    for part in PurePosixPath(ref).parts:
        if part in {"", ".", ".."}:
            continue
        parts.append(_safe_path_part(part))
    if not parts:
        parts = [_safe_path_part(f"{title}.md")]
    target = (root / Path(*parts)).resolve()
    target.relative_to(root)
    return target


def _safe_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"|?*\x00-\x1f]', "-", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "entity.md"


def _entity_stub_markdown(candidate: dict[str, Any], *, actor: str = "") -> str:
    title = str(candidate.get("title") or "Untitled Entity").strip()
    entity_type = str(candidate.get("entity_type") or "entity_profile").replace("_unresolved", "")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    evidence_edges = candidate.get("evidence_edges") if isinstance(candidate.get("evidence_edges"), list) else []
    citations = candidate.get("citations") if isinstance(candidate.get("citations"), list) else []
    evidence_lines = "\n".join(f"- {str(edge.get('evidence') or '').strip()}" for edge in evidence_edges if isinstance(edge, dict) and str(edge.get("evidence") or "").strip())
    citation_lines = "\n".join(
        f"- {str(citation.get('file') or citation.get('source_file') or citation.get('title') or '').strip()}"
        for citation in citations
        if isinstance(citation, dict)
    )
    actor_line = f"project_r_created_by: {actor}\n" if actor else ""
    return (
        "---\n"
        f"title: {title}\n"
        f"content_kind: {entity_type or 'entity_profile'}\n"
        "graph_status: pending_enrichment\n"
        "project_r_creation_reason: entity_merge_candidate\n"
        f"project_r_entity_candidate_id: {candidate.get('id')}\n"
        f"project_r_created_at: {now}\n"
        f"{actor_line}"
        "---\n\n"
        f"# {title}\n\n"
        "## 中文\n\n"
        "该实体页由 Project_R 根据 GBrain 图谱中的未解析引用自动建立。当前仅作为实体占位页，事实信息需要管理员后续补充、合并或重新提炼。\n\n"
        "## English\n\n"
        "This entity page was created by Project_R from an unresolved reference in the GBrain graph. It is currently a placeholder entity page and requires an administrator to enrich, merge, or re-extract the facts later.\n\n"
        "## Evidence / 证据\n\n"
        f"{evidence_lines or '- No direct evidence text was captured.'}\n\n"
        "## Citations / 引用\n\n"
        f"{citation_lines or '- No citation was captured.'}\n"
    )


def _record_alias_review(root: Path, candidate: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    canonical, aliases = _alias_review_entities(candidate)
    if not canonical or not aliases:
        return {
            "ok": False,
            "status": "alias_not_applicable",
            "error": "This candidate does not contain enough entity pages to record an alias review",
        }
    target_path = _safe_alias_review_path(root, candidate)
    status = "alias_already_exists" if target_path.exists() else "alias_recorded"
    if not target_path.exists():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_alias_review_markdown(candidate, canonical, aliases, actor=actor), encoding="utf-8")
    return {
        "ok": True,
        "status": status,
        "created_file": _relative_posix(target_path, root),
        "canonical_entity": canonical,
        "alias_entities": aliases,
    }


def _alias_review_entities(candidate: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    candidate_type = str(candidate.get("candidate_type") or "")
    targets = [item for item in candidate.get("target_nodes") or [] if isinstance(item, dict)]
    unresolved = candidate.get("unresolved_node") if isinstance(candidate.get("unresolved_node"), dict) else None
    if candidate_type == "duplicate_entity_pages" and len(targets) >= 2:
        ordered = sorted(targets, key=_canonical_entity_rank)
        return ordered[0], ordered[1:]
    if candidate_type == "unresolved_entity" and unresolved and targets:
        return targets[0], [unresolved]
    return None, []


def _canonical_entity_rank(node: dict[str, Any]) -> tuple[int, int, int, str]:
    title_key = _entity_key(str(node.get("title") or ""))
    identifier = str(node.get("id") or node.get("source_file") or node.get("file") or "").replace("\\", "/")
    stem_key = _entity_key(Path(identifier).stem)
    lower = identifier.lower()
    noisy = any(token in lower for token in ("duplicate", "copy", "副本", "重复"))
    return (
        1 if noisy else 0,
        0 if title_key and stem_key == title_key else 1,
        len(identifier),
        identifier.lower(),
    )


def _entity_reference_tokens(nodes: list[dict[str, Any]], *, include_titles: bool = True) -> set[str]:
    tokens: set[str] = set()
    for node in nodes:
        raw_values = [node.get("id"), node.get("source_file"), node.get("file")]
        if include_titles:
            raw_values.append(node.get("title"))
        for raw in raw_values:
            value = _clean_ref(raw)
            if not value:
                continue
            tokens.add(_normalize_ref(value))
            if value.lower().endswith(".md"):
                tokens.add(_normalize_ref(value[:-3]))
            stem = Path(value).stem
            if stem:
                tokens.add(_normalize_ref(stem))
    return {token for token in tokens if token}


def _canonical_reference(node: dict[str, Any]) -> str:
    value = str(node.get("source_file") or node.get("id") or node.get("title") or "").strip()
    value = _clean_ref(value).replace("\\", "/").strip()
    return value or str(node.get("title") or "").strip()


def _preview_relink_changes(
    pages: list[GraphPage],
    alias_tokens: set[str],
    canonical_ref: str,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for page in pages:
        for field in [*LINK_FIELDS.keys(), *SINGLE_LINK_FIELDS.keys()]:
            raw_values = _as_list(page.frontmatter.get(field))
            if not raw_values:
                continue
            for index, raw_value in enumerate(raw_values):
                if _normalize_ref(str(raw_value)) not in alias_tokens and _normalize_ref(Path(_clean_ref(raw_value)).stem) not in alias_tokens:
                    continue
                changes.append(
                    {
                        "file": page.file,
                        "source_file": page.source_file,
                        "page_id": page.id,
                        "page_title": page.title,
                        "field": field,
                        "index": index,
                        "current_ref": str(raw_value),
                        "proposed_ref": canonical_ref,
                        "diff_preview": f"{field}: {raw_value} -> {canonical_ref}",
                        "citation": _node_payload(page)["citation"],
                    }
                )
    return changes[:200]


def _apply_relink_changes(source_id: str, root: Path, candidate: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
    preview = build_entity_merge_candidate_preview(source_id, str(candidate.get("id") or ""), derived_path=root)
    if not preview.get("ok"):
        return preview
    changes = [item for item in preview.get("planned_relink_changes") or [] if isinstance(item, dict)]
    if not changes:
        return {
            "ok": True,
            "status": "no_relink_changes",
            "changed_files": [],
            "applied_changes": [],
            "preview": preview,
        }

    changes_by_page: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        page_id = str(change.get("page_id") or "").strip()
        if page_id:
            changes_by_page.setdefault(page_id, []).append(change)

    applied_changes: list[dict[str, Any]] = []
    changed_files: list[str] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for page_id, page_changes in changes_by_page.items():
        path = (root / page_id).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if not path.exists() or ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = _split_frontmatter(text)
        if not frontmatter:
            continue
        changed = False
        for change in page_changes:
            field = str(change.get("field") or "")
            current_ref = str(change.get("current_ref") or "")
            proposed_ref = str(change.get("proposed_ref") or "")
            if field not in LINK_FIELDS and field not in SINGLE_LINK_FIELDS:
                continue
            if _replace_frontmatter_reference(frontmatter, field, current_ref, proposed_ref):
                applied_changes.append(change)
                changed = True
        if changed:
            frontmatter["project_r_entity_relink_last_candidate_id"] = candidate.get("id")
            frontmatter["project_r_entity_relink_last_applied_at"] = now
            if actor:
                frontmatter["project_r_entity_relink_last_applied_by"] = actor
            _write_markdown(path, frontmatter, body)
            changed_files.append(_relative_posix(path, root))

    return {
        "ok": True,
        "status": "relink_applied" if applied_changes else "no_relink_changes",
        "changed_files": changed_files,
        "applied_changes": applied_changes,
        "preview": preview,
    }


def _replace_frontmatter_reference(frontmatter: dict[str, Any], field: str, current_ref: str, proposed_ref: str) -> bool:
    if not proposed_ref or field not in frontmatter:
        return False
    value = frontmatter.get(field)
    if isinstance(value, list):
        changed = False
        next_values = []
        for item in value:
            if _same_reference(item, current_ref):
                next_values.append(proposed_ref)
                changed = True
            else:
                next_values.append(item)
        if changed:
            frontmatter[field] = next_values
        return changed
    if _same_reference(value, current_ref):
        frontmatter[field] = proposed_ref
        return True
    return False


def _same_reference(left: Any, right: Any) -> bool:
    return _normalize_ref(str(left)) == _normalize_ref(str(right))


def _safe_alias_review_path(root: Path, candidate: dict[str, Any]) -> Path:
    candidate_id = str(candidate.get("id") or candidate.get("title") or "entity-alias")
    title = str(candidate.get("title") or "entity-alias")
    filename = _candidate_key(f"{candidate_id}-{title}") or "entity-alias"
    target = (root / "entity-overrides" / "aliases" / f"{filename}.md").resolve()
    target.relative_to(root)
    return target


def _alias_review_markdown(
    candidate: dict[str, Any],
    canonical: dict[str, Any],
    aliases: list[dict[str, Any]],
    *,
    actor: str = "",
) -> str:
    title = str(candidate.get("title") or canonical.get("title") or "Entity alias review").strip()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    alias_titles = [str(item.get("title") or item.get("id") or "").strip() for item in aliases if item]
    alias_ids = [str(item.get("id") or item.get("file") or "").strip() for item in aliases if item]
    citations = candidate.get("citations") if isinstance(candidate.get("citations"), list) else []
    evidence_edges = candidate.get("evidence_edges") if isinstance(candidate.get("evidence_edges"), list) else []
    citation_lines = "\n".join(
        f"- {str(citation.get('file') or citation.get('source_file') or citation.get('title') or '').strip()}"
        for citation in citations
        if isinstance(citation, dict)
    )
    evidence_lines = "\n".join(
        f"- {str(edge.get('evidence') or edge.get('relation_type') or '').strip()}"
        for edge in evidence_edges
        if isinstance(edge, dict) and str(edge.get("evidence") or edge.get("relation_type") or "").strip()
    )
    alias_lines = "".join(
        f"- {item.get('title') or item.get('id')} ({item.get('id') or item.get('file')})\n"
        for item in aliases
    )
    alias_frontmatter = "\n".join(f"  - {item}" for item in alias_titles if item) or "  - ''"
    alias_id_frontmatter = "\n".join(f"  - {item}" for item in alias_ids if item) or "  - ''"
    return (
        "---\n"
        f"title: Entity alias review - {title}\n"
        "content_kind: entity_alias_override\n"
        "graph_status: admin_alias_review\n"
        f"source_id: {candidate.get('source_id')}\n"
        f"canonical_entity: {canonical.get('title') or canonical.get('id')}\n"
        f"canonical_entity_id: {canonical.get('id') or canonical.get('file')}\n"
        "alias_entities:\n"
        f"{alias_frontmatter}\n"
        "alias_entity_ids:\n"
        f"{alias_id_frontmatter}\n"
        f"project_r_entity_candidate_id: {candidate.get('id')}\n"
        f"project_r_created_at: {now}\n"
        f"project_r_created_by: {actor}\n"
        "---\n\n"
        f"# Entity alias review - {title}\n\n"
        "## 中文\n\n"
        "管理员已确认这些实体应作为同一业务对象的别名线索处理。该页面是 GBrain 可读取的审核沉淀，不会自动删除、覆盖或合并原始实体页；后续完整实体合并和引用改写仍需通过 diff 审核执行。\n\n"
        "## English\n\n"
        "An administrator confirmed these entities as alias evidence for the same business object. This page is a GBrain-readable review record and does not automatically delete, overwrite, or merge the original entity pages. Full entity merging and citation rewrites still require a separate diff review.\n\n"
        "## Canonical entity / 主实体\n\n"
        f"- {canonical.get('title') or canonical.get('id')} ({canonical.get('id') or canonical.get('file')})\n\n"
        "## Alias entities / 别名实体\n\n"
        f"{alias_lines or '- No alias entity was captured.'}\n"
        "## Evidence / 证据\n\n"
        f"{evidence_lines or '- Duplicate title or unresolved reference candidate generated by Project_R graph review.'}\n\n"
        "## Citations / 引用\n\n"
        f"{citation_lines or '- No citation was captured.'}\n"
    )


def _record_entity_merge_decision(
    root: Path,
    candidate: dict[str, Any],
    action: str,
    *,
    actor: str = "",
    created_file: str = "",
) -> dict[str, Any]:
    state_dir = root / ".project-r"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "entity-merge-decisions.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"decisions": []}
    except json.JSONDecodeError:
        payload = {"decisions": []}
    if not isinstance(payload, dict):
        payload = {"decisions": []}
    decisions = payload.get("decisions") if isinstance(payload.get("decisions"), list) else []
    decision = {
        "candidate_id": candidate.get("id"),
        "source_id": candidate.get("source_id"),
        "title": candidate.get("title"),
        "candidate_type": candidate.get("candidate_type"),
        "action": action,
        "created_file": created_file,
        "actor": actor,
        "decided_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    decisions = [item for item in decisions if not (isinstance(item, dict) and item.get("candidate_id") == candidate.get("id"))]
    decisions.append(decision)
    payload["decisions"] = decisions[-500:]
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**decision, "path": _relative_posix(state_path, root)}


def _node_payload(page: GraphPage) -> dict[str, Any]:
    return {
        "id": page.id,
        "title": page.title,
        "entity_type": page.entity_type,
        "source_id": page.source_id,
        "file": page.file,
        "source_file": page.source_file,
        "citation": {
            "source_id": page.source_id,
            "file": page.file,
            "source_file": page.source_file,
            "title": page.title,
        },
    }


def _edge_payload(
    source: GraphPage,
    target: GraphPage,
    relation_type: str,
    field: str,
    raw_ref: Any,
) -> dict[str, Any]:
    return {
        "id": f"{source.id}->{relation_type}->{target.id}",
        "from": source.id,
        "to": target.id,
        "relation_type": relation_type,
        "source_field": field,
        "confidence": 1.0,
        "evidence": str(raw_ref),
        "citation": {
            "source_id": source.source_id,
            "file": source.file,
            "source_file": source.source_file,
            "title": source.title,
        },
    }


def _event_payload(entity: GraphPage, event: GraphPage, raw_ref: Any) -> dict[str, Any]:
    return {
        "id": f"{entity.id}::event::{event.id}",
        "entity_id": entity.id,
        "event_id": event.id,
        "title": event.title,
        "date": _extract_date(event.title) or _extract_date(str(raw_ref)) or "",
        "source_file": event.source_file,
        "citation": {
            "source_id": entity.source_id,
            "file": event.file,
            "source_file": event.source_file,
            "title": event.title,
        },
    }


def _resolve_ref(
    raw_ref: Any,
    by_source_file: dict[str, GraphPage],
    by_title: dict[str, GraphPage],
) -> GraphPage | None:
    ref = _clean_ref(raw_ref)
    if not ref:
        return None
    normalized = _normalize_ref(ref)
    candidates = [
        normalized,
        _normalize_ref(ref + ".md"),
        _normalize_ref(ref.replace("\\", "/")),
    ]
    for candidate in candidates:
        if candidate in by_source_file:
            return by_source_file[candidate]
    title = Path(ref).stem or ref
    exact = by_title.get(_normalize_ref(title))
    if exact:
        return exact
    ref_tokens = _name_tokens(title)
    if ref_tokens:
        for page in by_title.values():
            title_tokens = _name_tokens(page.title)
            if ref_tokens and ref_tokens.issubset(title_tokens):
                return page
    ref_key = _entity_key(title)
    if len(ref_key) >= 4:
        for page in by_title.values():
            title_key = _entity_key(page.title)
            if ref_key in title_key or title_key in ref_key:
                return page
    return None


def _graph_metadata(frontmatter: dict[str, Any], body: str) -> dict[str, Any]:
    metadata = dict(frontmatter)
    for key, raw_value in _source_metadata_fields(body).items():
        if key in metadata:
            continue
        if key in LINK_FIELDS or key in {"tags"}:
            metadata[key] = _split_metadata_values(raw_value)
        elif key in SINGLE_LINK_FIELDS:
            metadata[key] = raw_value.strip()
        elif key in {"type", "name"} and raw_value.strip():
            metadata.setdefault(key, raw_value.strip())
    return metadata


def _source_metadata_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_section = False
    current_key = ""
    current_lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "## Source Metadata":
            in_section = True
            continue
        if in_section and stripped.startswith("## ") and stripped != "## Source Metadata":
            break
        if not in_section:
            continue
        match = re.match(r"- \*\*([A-Za-z0-9_-]+):\*\*\s*(.*)$", stripped)
        if match:
            if current_key:
                fields[current_key] = "\n".join(current_lines).strip()
            current_key = match.group(1).strip()
            current_lines = [match.group(2).strip()]
        elif current_key and stripped:
            current_lines.append(stripped)
    if current_key:
        fields[current_key] = "\n".join(current_lines).strip()
    return fields


def _split_metadata_values(value: str) -> list[str]:
    cleaned = value.replace("、", ",").replace("；", ",").replace(";", ",")
    parts: list[str] = []
    for line in cleaned.splitlines():
        line = re.sub(r"^\s*-\s*", "", line).strip()
        if not line:
            continue
        parts.extend(part.strip() for part in line.split(","))
    return [part for part in parts if part]


def _name_tokens(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]{1,}|[\u4e00-\u9fff]{2,}", value)
        if len(token.strip("' -")) >= 2
    }


def _placeholder_page(source_id: str, raw_ref: Any) -> GraphPage | None:
    ref = _clean_ref(raw_ref)
    if not ref:
        return None
    title = Path(ref).stem or ref
    entity_type = _entity_type_from_ref(ref)
    identifier = "unresolved/" + re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "-", ref.lower()).strip("-")
    return GraphPage(
        id=identifier,
        title=title,
        entity_type=entity_type,
        source_id=source_id,
        file=f"gbrain:{source_id}/{identifier}",
        source_file=ref,
        frontmatter={
            "title": title,
            "content_kind": entity_type,
            "graph_status": "unresolved_entity",
        },
        body="",
    )


def _entity_type_from_ref(ref: str) -> str:
    normalized = ref.replace("\\", "/")
    if normalized.startswith("01_Clients/"):
        return "client_profile_unresolved"
    if normalized.startswith("02_Projects/"):
        return "customer_project_profile_unresolved"
    if normalized.startswith("03_Companies/"):
        return "customer_company_profile_unresolved"
    if normalized.startswith("04_Raw/"):
        return "customer_source_event_unresolved"
    return "unresolved_entity"


def _clean_ref(raw_ref: Any) -> str:
    value = str(raw_ref or "").strip()
    wiki = re.fullmatch(r"\[\[([^|\]]+)(?:\|[^\]]+)?]]", value)
    if wiki:
        value = wiki.group(1).strip()
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2].split("|", 1)[0].strip()
    return value


def _normalize_ref(value: str) -> str:
    value = _clean_ref(value).replace("\\", "/").strip().lower()
    value = re.sub(r"\.md$", "", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _focus_terms(focus: str | None) -> list[str]:
    if not focus:
        return []
    terms = [focus.strip().lower()]
    terms.extend(token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9&.'-]{1,}|[\u4e00-\u9fff]{2,}", focus))
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered[:20]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _extract_date(value: str) -> str | None:
    match = re.search(r"(20\d{2})[-_年 ]?(\d{2})[-_月 ]?(\d{2})", value)
    if not match:
        match = re.search(r"\b(\d{2})(\d{2})(\d{2})\b", value)
        if not match:
            return None
        year = int(match.group(1))
        return f"20{year:02d}-{match.group(2)}-{match.group(3)}"
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for edge in edges:
        deduped[str(edge["id"])] = edge
    return sorted(deduped.values(), key=lambda item: (item["from"], item["relation_type"], item["to"]))


def _dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for event in events:
        deduped[str(event["id"])] = event
    return sorted(deduped.values(), key=lambda item: (str(item.get("date") or ""), item["title"]))
