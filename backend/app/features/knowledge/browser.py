from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import (
    customer_source_id_for_workspace,
    load_gbrain_settings,
    project_source_id_for_workspace,
)
from app.features.knowledge.sources import KnowledgeSources
from models.workspace import Workspace


@dataclass(frozen=True)
class KnowledgeScope:
    scope: str
    source_id: str
    label: str
    description: str
    workspace_kind: str


def source_scopes_for_workspace(workspace: Workspace | None) -> list[KnowledgeScope]:
    settings = load_gbrain_settings()
    if workspace and str(workspace.workspace_kind or "") == "customer":
        try:
            source_id = customer_source_id_for_workspace(workspace)
        except ValueError:
            source_id = ""
        return [
            KnowledgeScope(
                scope="customer",
                source_id=source_id,
                label="当前客户情报",
                description="只检索当前 CRM 客户情报 source，不叠加公司知识或项目资料。",
                workspace_kind="customer",
            )
        ]
    if workspace and str(workspace.workspace_kind or "project") == "project":
        try:
            project_source_id = project_source_id_for_workspace(workspace)
        except ValueError:
            project_source_id = ""
        return [
            KnowledgeScope(
                scope="company",
                source_id=settings.company_source_id,
                label="公司知识",
                description="公司全局知识库 company-wiki。",
                workspace_kind="project",
            ),
            KnowledgeScope(
                scope="project",
                source_id=project_source_id,
                label=f"当前项目资料：{workspace.name}",
                description="当前项目 GBrain-ready source。",
                workspace_kind="project",
            ),
        ]
    return [
        KnowledgeScope(
            scope="company",
            source_id=settings.company_source_id,
            label="公司知识",
            description="个人工作台只检索公司知识库 company-wiki。",
            workspace_kind="user",
        )
    ]


def serialize_source_scopes(scopes: list[KnowledgeScope]) -> list[dict[str, str]]:
    return [
        {
            "scope": item.scope,
            "label": item.label,
            "description": item.description,
            "workspace_kind": item.workspace_kind,
        }
        for item in scopes
    ]


def search_knowledge_for_workspace(
    db: Session,
    query: str,
    *,
    workspace: Workspace | None,
    source_scope: str = "all",
    limit: int = 10,
    knowledge_sources: KnowledgeSources | None = None,
) -> list[dict[str, Any]]:
    sources = knowledge_sources or KnowledgeSources()
    normalized_scope = (source_scope or "all").strip().lower()
    workspace_kind = str(workspace.workspace_kind or "project") if workspace else "user"

    results: list[dict[str, Any]] = []
    if workspace_kind == "customer":
        if normalized_scope in {"all", "customer"} and workspace is not None:
            results.extend(_tag_results(sources.search_scoped_workspace_gbrain_sources(workspace, query), "customer"))
    elif workspace_kind == "project":
        if normalized_scope in {"all", "project"} and workspace is not None:
            results.extend(_tag_results(sources.search_project_gbrain_sources(workspace, query), "project"))
        if normalized_scope in {"all", "company"}:
            results.extend(_tag_results(sources.search_company_sources(query), "company"))
    else:
        if normalized_scope in {"all", "company"}:
            results.extend(_tag_results(sources.search_company_sources(query), "company"))

    return _dedupe_results(results)[:limit]


def _tag_results(items: list[dict], scope: str) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for item in items:
        next_item = dict(item)
        next_item["scope"] = scope
        tagged.append(next_item)
    return tagged


def _dedupe_results(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            str(item.get("scope") or ""),
            str(item.get("file") or ""),
            str(item.get("section_path") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
