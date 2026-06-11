from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.features.knowledge.gbrain import (
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
)
from models.workspace import Workspace


def has_markdown_files(path: Path) -> bool:
    if not path.exists():
        return False
    return any(item.is_file() and item.suffix.lower() in {".md", ".markdown"} for item in path.rglob("*"))


def workspace_gbrain_read_path(paths: dict[str, Path]) -> Path:
    ready = paths["gbrain_ready"]
    legacy = paths.get("legacy_derived")
    if has_markdown_files(ready) or legacy is None:
        return ready
    if has_markdown_files(legacy):
        return legacy
    return ready


def workspace_gbrain_graph_scope(workspace: Workspace) -> dict[str, object]:
    if workspace.workspace_kind == "project":
        paths = project_source_paths_for_workspace(workspace)
        return {
            "source_id": project_source_id_for_workspace(workspace),
            "derived_path": workspace_gbrain_read_path(paths),
            "gbrain_ready_path": paths["gbrain_ready"],
            "legacy_derived_path": paths.get("legacy_derived"),
            "source_scope": "project",
            "intelligence_kind": "project_event_graph",
        }
    if workspace.workspace_kind == "customer":
        paths = customer_source_paths_for_workspace(workspace)
        return {
            "source_id": customer_source_id_for_workspace(workspace),
            "derived_path": workspace_gbrain_read_path(paths),
            "gbrain_ready_path": paths["gbrain_ready"],
            "legacy_derived_path": paths.get("legacy_derived"),
            "source_scope": "customer",
            "intelligence_kind": "customer_intelligence",
        }
    raise HTTPException(status_code=400, detail="当前工作区不支持 GBrain 图谱")


def workspace_profile_cards(graph: dict[str, object]) -> list[dict[str, object]]:
    nodes = [node for node in graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    events = [event for event in graph.get("events", []) if isinstance(event, dict)]
    relation_count: dict[str, int] = {}
    event_count: dict[str, int] = {}
    for edge in edges:
        for key in ("from", "to"):
            node_id = str(edge.get(key) or "")
            if node_id:
                relation_count[node_id] = relation_count.get(node_id, 0) + 1
    for event in events:
        node_id = str(event.get("entity_id") or "")
        if node_id:
            event_count[node_id] = event_count.get(node_id, 0) + 1

    def card_priority(node: dict[str, object]) -> tuple[int, int, str]:
        node_id = str(node.get("id") or "")
        kind = str(node.get("entity_type") or "").lower()
        type_score = 0
        if any(token in kind for token in ("client", "customer", "contact", "person", "company")):
            type_score = 3
        elif "project" in kind:
            type_score = 2
        elif "event" in kind:
            type_score = 1
        return (type_score, relation_count.get(node_id, 0) + event_count.get(node_id, 0), str(node.get("title") or "").lower())

    cards: list[dict[str, object]] = []
    for node in sorted(nodes, key=card_priority, reverse=True)[:8]:
        node_id = str(node.get("id") or "")
        cards.append(
            {
                "id": node_id,
                "title": str(node.get("title") or ""),
                "entity_type": str(node.get("entity_type") or "page"),
                "relation_count": relation_count.get(node_id, 0),
                "event_count": event_count.get(node_id, 0),
                "citation": node.get("citation") if isinstance(node.get("citation"), dict) else None,
            }
        )
    return cards
