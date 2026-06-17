from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.features.knowledge.gbrain import (
    GBrainAdapter,
    GBrainSettings,
    customer_source_id_for_workspace,
    customer_source_paths_for_workspace,
    load_gbrain_settings,
    project_source_id_for_workspace,
    project_source_paths_for_workspace,
    resolve_gbrain_source_paths,
)
from app.features.knowledge.evidence import enrich_sources_with_evidence
from app.features.knowledge.gbrain.ingest import _split_frontmatter, approve_pending_review_markdown
from models.workspace import Workspace, WorkspaceFile

logger = logging.getLogger(__name__)

MAX_WORKSPACE_SOURCE_BYTES = 512 * 1024
MAX_WORKSPACE_SOURCE_CHARS = 1200
WORKSPACE_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".yaml",
    ".yml",
    ".log",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".py",
}

COMPANY_QUERY_EXPANSION_MAX_CHARS = 900
COMPANY_QUERY_EXPANSION_SCORE_BOOST = 0.08
COMPANY_STANDARD_SOURCE_SCORE_BOOST = 0.05
COMPANY_STANDARD_NOISE_PENALTY = 0.25
COMPANY_RULE_SOURCE_SCORE_BOOST = 0.12
COMPANY_RULE_NOISE_PENALTY = 0.18
COMPANY_EXACT_TITLE_SCORE_BOOST = 0.2
COMPANY_LOCAL_INDEX_MIN_SCORE = 8
COMPANY_LOCAL_INDEX_BASE_SCORE = 1.18
COMPANY_LOCAL_INDEX_MAX_CHARS = 1800
GENERIC_COMPANY_QUERY_EXPANSIONS = {
    "windows external glazed doors AS 2047",
    "glass glazing AS 1288",
    "Australian Standard compliance requirement",
}
COMPANY_QUERY_EXPANSION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("结构图", "窗洞口", "fsl", "ssl", "structural dwg", "structural drawing"),
        "Reading Structural DWG FSL SSL slab thickness step down window opening height",
    ),
    (
        ("窗表", "窗号", "window schedule", "markup", "标注窗"),
        "Markup Window schedule Doris window number takeoff Bluebeam",
    ),
    (
        ("玻璃样品", "样品登记", "替代样品", "审批状态", "sample register", "glass sample"),
        "SampleRegister_Glass glass sample register substitute sample approval status",
    ),
    (
        ("系统性", "文件组织", "组织规则", "file organization", "system thinking"),
        "System Thinking File Organization system rules team workflow",
    ),
    (
        ("书面化", "留痕", "书面记录", "written record"),
        "书面化原则 留痕 written record principle",
    ),
    (
        ("热浸", "heat soak", "hst"),
        "Heat Soak Test",
    ),
    (
        ("防水", "水密", "渗水", "water"),
        "water penetration resistance AS 2047",
    ),
    (
        ("安全", "冲击", "撞击", "人体", "破碎", "伤害", "safety", "impact"),
        "safety glass human impact AS 1288",
    ),
    (
        ("钢化", "强化", "tempered", "toughened"),
        "toughened glass AS 1288",
    ),
    (
        ("夹层", "夹胶", "laminated"),
        "laminated glass AS 1288",
    ),
    (
        ("风压", "风载", "抗风", "wind", "结构", "荷载"),
        "wind load wind pressure N1 N6 C1 C4 AS 2047",
    ),
    (
        ("气密", "空气", "air infiltration", "漏风"),
        "air infiltration air leakage AS 2047",
    ),
    (
        ("标签", "标识", "证书", "认证", "label", "certificate"),
        "labelling certificate AS 2047 compliance",
    ),
    (
        ("门窗", "窗", "门", "外窗", "外门", "windows", "doors", "as 2047", "as2047"),
        "windows external glazed doors AS 2047",
    ),
    (
        ("玻璃", "glazing", "glass", "as 1288", "as1288"),
        "glass glazing AS 1288",
    ),
    (
        ("规范", "标准", "条款", "澳洲", "澳标", "standard", "clause"),
        "Australian Standard compliance requirement",
    ),
)
COMPANY_STANDARD_QUERY_KEYWORDS = (
    "玻璃",
    "门窗",
    "窗户",
    "外窗",
    "外门",
    "防水",
    "水密",
    "气密",
    "风压",
    "风载",
    "热浸",
    "安全",
    "冲击",
    "钢化",
    "夹层",
    "标准",
    "规范",
    "等级",
    "as 1288",
    "as1288",
    "as 2047",
    "as2047",
    "glass",
    "glazing",
    "window",
    "door",
    "water penetration",
    "heat soak",
)
COMPANY_RULE_QUERY_KEYWORDS = (
    "书面化",
    "留痕",
    "流程",
    "原则",
    "规则",
    "制度",
    "作业",
    "接待",
    "sop",
    "procedure",
    "process",
    "principle",
    "policy",
)


class KnowledgeSources:
    def __init__(self, gbrain_factory: Callable[[], GBrainAdapter] = GBrainAdapter):
        self.gbrain_factory = gbrain_factory

    def search(
        self,
        db: Session,
        content: str,
        *,
        workspace_id: int | None,
        forced_company_query: bool,
        reduce_knowledge_context: bool,
    ) -> list[dict]:
        if reduce_knowledge_context:
            return []

        workspace_sources = self.search_workspace_sources(db, workspace_id, content)
        company_sources = self.search_company_sources(content) if forced_company_query else []
        if workspace_sources or company_sources:
            return workspace_sources + company_sources

        return []

    def think(self, db: Session, content: str, *, workspace_id: int | None = None) -> dict:
        settings = load_gbrain_settings()
        source_id = settings.company_source_id
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first() if workspace_id is not None else None
        if workspace and str(workspace.workspace_kind or "project") == "project":
            try:
                project_source_id = project_source_id_for_workspace(workspace)
            except ValueError:
                project_source_id = ""
            if project_source_id:
                source_id = project_source_id
        elif workspace and str(workspace.workspace_kind or "") == "customer":
            try:
                source_id = customer_source_id_for_workspace(workspace)
            except ValueError:
                source_id = ""

        adapter = self.gbrain_factory()
        try:
            response = adapter.think(content, source_id=source_id)
        except Exception as exc:
            logger.warning("GBrain think failed for %s: %s", source_id, exc)
            return {
                "ok": False,
                "status": "adapter_error",
                "source_id": source_id,
                "reply": "GBrain think 调用失败，请管理员检查知识库服务配置。",
                "sources": [],
                "error": str(exc),
            }
        if response.get("status") != "ok":
            return {
                "ok": False,
                "status": response.get("status") or "error",
                "source_id": source_id,
                "reply": self._think_unavailable_message(response),
                "sources": self._think_diagnostic_sources(response, source_id),
                "error": response.get("error"),
            }

        result = response.get("result")
        if not isinstance(result, dict) or result.get("error"):
            return {
                "ok": False,
                "status": "gbrain_error",
                "source_id": source_id,
                "reply": self._think_unavailable_message(result if isinstance(result, dict) else response),
                "sources": self._think_diagnostic_sources(result if isinstance(result, dict) else response, source_id),
                "error": result.get("error") if isinstance(result, dict) else "invalid GBrain think response",
            }

        answer = result.get("answer") if isinstance(result.get("answer"), str) else ""
        sources = self._normalize_think_sources(result, source_id)
        try:
            enrich_sources_with_evidence(sources, settings=settings, workspace=workspace)
        except Exception as exc:
            logger.warning("GBrain evidence enrichment failed: %s", exc)

        # Phase 2: Project query intent classification + ranking adjustment
        intent_result: dict[str, Any] | None = None
        if sources and workspace and str(workspace.workspace_kind or "project") == "project":
            try:
                from app.features.knowledge.project_query.intent import classify_project_query
                from app.features.knowledge.project_query.ranking import adjust_project_ranking, apply_ranking_to_sources

                intent = classify_project_query(content)
                if intent.confidence != "low":
                    ranked = adjust_project_ranking(sources, intent)
                    reordered = apply_ranking_to_sources(sources, ranked)
                    if reordered:
                        sources = reordered
                    intent_result = {
                        "file_kind_hint": intent.file_kind_hint,
                        "source_category_hint": intent.source_category_hint,
                        "confidence": intent.confidence,
                        "matched_patterns": intent.matched_patterns,
                    }
            except Exception as exc:
                logger.warning("Project query intent/ranking failed: %s", exc)

        if answer and sources:
            answer = answer.rstrip() + "\n\n引用与缺口： " + " ".join(f"来源 {index}" for index in range(1, len(sources) + 1))
        metadata: dict[str, Any] = {
            "gaps": result.get("gaps") if isinstance(result.get("gaps"), list) else [],
            "conflicts": result.get("conflicts") if isinstance(result.get("conflicts"), list) else [],
            "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
            "diagnostics": result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {},
        }
        if intent_result:
            metadata["project_query_intent"] = intent_result
        return {
            "ok": True,
            "status": "ok",
            "source_id": source_id,
            "reply": answer or "GBrain think 未返回可用回答。",
            "sources": sources,
            "model": str(result.get("modelUsed") or "think"),
            "metadata": metadata,
        }

    def search_workspace_sources(self, db: Session, workspace_id: int | None, content: str) -> list[dict]:
        if workspace_id is None:
            return []
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not workspace or not workspace.storage_path:
            return []

        scoped_gbrain_sources = self.search_scoped_workspace_gbrain_sources(workspace, content)
        if scoped_gbrain_sources:
            return scoped_gbrain_sources

        root = Path(workspace.storage_path).resolve()
        if not root.exists():
            return []

        query_terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_+-]{2,}|[一-鿿]{2,}", content)}
        if not query_terms:
            return []

        files = (
            db.query(WorkspaceFile)
            .filter(
                WorkspaceFile.workspace_id == workspace_id,
                WorkspaceFile.deleted_at.is_(None),
                WorkspaceFile.rag_status == "indexed",
            )
            .order_by(WorkspaceFile.updated_at.desc(), WorkspaceFile.id.desc())
            .limit(80)
            .all()
        )
        scored: list[tuple[int, WorkspaceFile, str]] = []
        for meta in files:
            path = (root / meta.relative_path).resolve()
            try:
                if (
                    not path.is_relative_to(root)
                    or not path.exists()
                    or not path.is_file()
                    or path.stat().st_size > MAX_WORKSPACE_SOURCE_BYTES
                ):
                    continue
            except OSError:
                continue
            filename_text = f"{meta.original_name} {meta.relative_path}".lower()
            text = ""
            if path.suffix.lower() in WORKSPACE_TEXT_EXTENSIONS:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    text = ""
            haystack = f"{filename_text}\n{text[:MAX_WORKSPACE_SOURCE_CHARS * 2].lower()}"
            score = sum(3 if term in filename_text else 1 for term in query_terms if term in haystack)
            if score:
                excerpt = text.strip()[:MAX_WORKSPACE_SOURCE_CHARS] if text.strip() else f"文件名匹配：{meta.relative_path}"
                scored.append((score, meta, excerpt))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "file": f"workspace:{workspace_id}/{meta.relative_path}",
                "source_title": meta.original_name,
                "section_path": f"{workspace.name} / {Path(meta.relative_path).parent.as_posix()}",
                "type": "workspace_file",
                "authority_level": str(workspace.workspace_kind or "workspace"),
                "tags": "workspace",
                "content": excerpt,
                "score": float(-score),
            }
            for score, meta, excerpt in scored[:5]
        ]

    def search_project_gbrain_sources(self, workspace: Workspace, content: str) -> list[dict]:
        if str(workspace.workspace_kind or "project") != "project":
            return []
        try:
            source_id = project_source_id_for_workspace(workspace)
        except ValueError:
            return []
        adapter = self.gbrain_factory()
        try:
            response = adapter.query(content, source_id=source_id, limit=5, detail="medium")
        except Exception as exc:
            logger.warning("GBrain project source query failed for %s: %s", source_id, exc)
            return []
        if response.get("status") != "ok":
            if response.get("status") not in {"auth_required", "disabled", "not_configured"}:
                logger.warning(
                    "GBrain project source query returned %s for %s: %s",
                    response.get("status"),
                    source_id,
                    response.get("error"),
                )
            return []
        sources = self._normalize_gbrain_results(
            response.get("result"),
            default_source_id=source_id,
            result_type="gbrain_project_source",
            default_authority_level="project",
            default_tags=f"project,{workspace.brand},{workspace.slug}",
        )
        return self._enrich_project_source_locations(workspace, sources)

    def search_scoped_workspace_gbrain_sources(self, workspace: Workspace, content: str) -> list[dict]:
        workspace_kind = str(workspace.workspace_kind or "project")
        if workspace_kind == "project":
            return self.search_project_gbrain_sources(workspace, content)
        if workspace_kind != "customer":
            return []
        try:
            source_id = customer_source_id_for_workspace(workspace)
        except ValueError:
            return []
        adapter = self.gbrain_factory()
        try:
            response = adapter.query(content, source_id=source_id, limit=5, detail="medium")
        except Exception as exc:
            logger.warning("GBrain customer source query failed for %s: %s", source_id, exc)
            return []
        if response.get("status") != "ok":
            if response.get("status") not in {"auth_required", "disabled", "not_configured"}:
                logger.warning(
                    "GBrain customer source query returned %s for %s: %s",
                    response.get("status"),
                    source_id,
                    response.get("error"),
                )
            return []
        sources = self._normalize_gbrain_results(
            response.get("result"),
            default_source_id=source_id,
            result_type="gbrain_customer_source",
            default_authority_level="customer",
            default_tags=f"customer,{workspace.slug}",
        )
        return self._enrich_customer_source_locations(workspace, sources)

    def search_company_sources(self, content: str) -> list[dict]:
        adapter = self.gbrain_factory()
        best_sources: dict[tuple[str, str], dict] = {}
        query_variants = self._company_query_variants(content)
        for query_index, query in enumerate(query_variants):
            try:
                response = adapter.query(query, limit=8, detail="medium")
            except Exception as exc:
                logger.warning("GBrain company-wiki query failed: %s", exc)
                continue
            if response.get("status") != "ok":
                if response.get("status") in {"auth_required", "disabled", "not_configured"}:
                    return []
                else:
                    logger.warning(
                        "GBrain company-wiki query returned %s: %s",
                        response.get("status"),
                        response.get("error"),
                    )
                    continue
            sources = self._normalize_gbrain_results(response.get("result"))
            if not sources:
                continue
            for source in sources:
                if query_index > 0:
                    source["score"] = self._score(source.get("score")) + COMPANY_QUERY_EXPANSION_SCORE_BOOST
                source["score"] = self._adjust_company_score(content, source)
                key = (source.get("file", ""), source.get("section_path", ""))
                previous = best_sources.get(key)
                if previous is None or self._score(source.get("score")) > self._score(previous.get("score")):
                    best_sources[key] = source
        if _env_bool("GBRAIN_COMPANY_LOCAL_INDEX_ENABLED", True):
            for source in self._local_company_sources(content, query_variants):
                key = (source.get("file", ""), source.get("section_path", ""))
                previous = best_sources.get(key)
                if previous is None or self._score(source.get("score")) > self._score(previous.get("score")):
                    best_sources[key] = source
        return sorted(best_sources.values(), key=lambda source: self._score(source.get("score")), reverse=True)

    def _company_query_variants(self, content: str) -> list[str]:
        primary = content.strip()
        if not primary:
            return []
        variants = [primary]
        if not _env_bool("GBRAIN_COMPANY_QUERY_EXPANSION_ENABLED", True):
            return variants
        if not _contains_cjk(primary):
            return variants

        specific_queries: list[str] = []
        generic_queries: list[str] = []
        lowered = primary.lower()
        if _is_rule_like_query(primary):
            title_query = _compact_company_rule_question(primary)
            if title_query:
                specific_queries.append(title_query)
        for needles, expanded_query in COMPANY_QUERY_EXPANSION_RULES:
            if any(needle.lower() in lowered for needle in needles):
                if expanded_query in GENERIC_COMPANY_QUERY_EXPANSIONS:
                    generic_queries.append(expanded_query)
                else:
                    specific_queries.append(expanded_query)
        queries = specific_queries or generic_queries
        for expanded_query in _dedupe_terms(queries):
            variants.append(expanded_query[:COMPANY_QUERY_EXPANSION_MAX_CHARS])
        return variants

    def _normalize_gbrain_results(
        self,
        result: Any,
        *,
        default_source_id: str = "company-wiki",
        result_type: str = "gbrain_company_wiki",
        default_authority_level: str = "company-wiki",
        default_tags: str = "company-wiki",
    ) -> list[dict]:
        items = self._gbrain_items(result)
        sources: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            content = self._first_text(item, "content", "chunk_text", "text", "snippet", "summary", "excerpt", "body")
            if not content:
                continue
            source_id = str(item.get("source_id") or default_source_id)
            slug = self._first_text(item, "slug", "path", "file", "id")
            title = self._first_text(item, "source_title", "title", "name") or slug or source_id
            section_path = self._first_text(item, "section_path", "heading", "path", "slug") or title
            sources.append(
                {
                    "file": f"gbrain:{source_id}/{slug}" if slug else f"gbrain:{source_id}",
                    "source_title": title,
                    "section_path": section_path,
                    "type": result_type,
                    "authority_level": str(item.get("authority_level") or item.get("type") or default_authority_level),
                    "tags": item.get("tags") or default_tags,
                    "content": content,
                    "score": self._score(item.get("score")),
                }
            )
        return sources

    def _local_company_sources(self, content: str, query_variants: list[str]) -> list[dict]:
        settings = load_gbrain_settings()
        derived_root = settings.derived_path
        if not derived_root.exists():
            return []
        tokens = _company_local_query_tokens([content, *query_variants])
        if not tokens:
            return []
        scored: list[tuple[float, str, str, str, str]] = []
        for path in derived_root.rglob("*.md"):
            if any(part in {".git", ".pending_review"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                frontmatter, body = _split_frontmatter(text)
                rel = path.relative_to(derived_root).as_posix()
            except Exception:
                continue
            title = str(frontmatter.get("title") or Path(rel).stem).strip()
            source_file = str(frontmatter.get("project_r_source_file") or "").strip()
            title_haystack = f"{title} {source_file} {rel}".lower()
            body_haystack = body[:8000].lower()
            match_score = 0
            for token in tokens:
                if token in title_haystack:
                    match_score += 5
                elif token in body_haystack:
                    match_score += 1
            if match_score < COMPANY_LOCAL_INDEX_MIN_SCORE:
                continue
            excerpt = _best_company_local_excerpt(body, tokens) or body.strip()[:COMPANY_LOCAL_INDEX_MAX_CHARS]
            slug = _local_company_slug(rel)
            scored.append(
                (
                    COMPANY_LOCAL_INDEX_BASE_SCORE + min(match_score, 60) / 100,
                    rel,
                    title,
                    excerpt[:COMPANY_LOCAL_INDEX_MAX_CHARS],
                    slug,
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "file": f"gbrain:{settings.company_source_id}/{slug}",
                "source_title": title,
                "section_path": rel.removesuffix(".md"),
                "type": "gbrain_company_wiki_local_index",
                "authority_level": "company-wiki",
                "tags": "company-wiki,local-index",
                "content": excerpt,
                "score": score,
                "derived_file": rel,
            }
            for score, rel, title, excerpt, slug in scored[:5]
        ]

    def _normalize_think_sources(self, result: dict, source_id: str) -> list[dict]:
        sources: list[dict] = []
        citations = result.get("citations")
        if isinstance(citations, list):
            for index, citation in enumerate(citations, start=1):
                if not isinstance(citation, dict):
                    continue
                citation_source_id = self._citation_source_id(citation, source_id)
                slug = self._first_text(citation, "page_slug", "slug", "page")
                if not slug and self._first_text(citation, "source") != citation_source_id:
                    slug = self._first_text(citation, "source")
                if not slug:
                    continue
                row_num = citation.get("row_num")
                section_path = f"{slug}#row-{row_num}" if row_num is not None else slug
                sources.append(
                    {
                        "file": f"gbrain:{citation_source_id}/{slug}",
                        "source_id": citation_source_id,
                        "source_title": "引用来源",
                        "section_path": section_path,
                        "type": "gbrain_think_citation",
                        "authority_level": citation_source_id,
                        "tags": "gbrain,think,citation",
                        "content": "",
                        "metadata_only": True,
                        "page_slug": slug,
                        "row_num": row_num if row_num is not None else None,
                        "source_slug": slug,
                        "score": max(0.0, 1.0 - (index * 0.01)),
                    }
                )

        for key, title, tag in (
            ("gaps", "GBrain 缺口分析 / Gap Analysis", "gap"),
            ("conflicts", "GBrain 冲突提示 / Conflict Notes", "conflict"),
            ("warnings", "GBrain 运行警告 / Runtime Warnings", "warning"),
        ):
            values = result.get(key)
            if isinstance(values, list) and values:
                sources.append(
                    {
                        "file": f"gbrain:{source_id}/__think_{key}__",
                        "source_title": title,
                        "section_path": title,
                        "type": f"gbrain_think_{tag}",
                        "authority_level": source_id,
                        "tags": f"gbrain,think,{tag}",
                        "content": "\n".join(f"- {value}" for value in values if str(value).strip()),
                        "score": 0.0,
                    }
                )
        return sources

    def _citation_source_id(self, citation: dict, default_source_id: str) -> str:
        source_id = self._first_text(citation, "source_id", "sourceId", "source_scope")
        if source_id:
            return source_id
        source_value = self._first_text(citation, "source")
        if source_value in {"company-wiki", "company", "project", "customer", "crm", "customer-crm"}:
            return source_value
        return default_source_id

    def _enrich_project_source_locations(self, workspace: Workspace, sources: list[dict]) -> list[dict]:
        return self._enrich_workspace_source_locations(workspace, sources, project_source_paths_for_workspace(workspace)["derived"])

    def _enrich_customer_source_locations(self, workspace: Workspace, sources: list[dict]) -> list[dict]:
        return self._enrich_workspace_source_locations(workspace, sources, customer_source_paths_for_workspace(workspace)["derived"])

    def _enrich_workspace_source_locations(self, workspace: Workspace, sources: list[dict], derived_root: Path) -> list[dict]:
        if not sources:
            return sources
        markdown_index = self._project_markdown_index(derived_root)
        for source in sources:
            match = self._match_project_markdown(source, derived_root, markdown_index)
            if match is None:
                continue
            rel_path, path, frontmatter, lines = match
            content = str(source.get("content") or "")
            line_number = _locate_excerpt_line(lines, content)
            page_number = _nearest_page_marker(lines, line_number)
            source_file = str(frontmatter.get("project_r_source_file") or "")
            source["derived_file"] = rel_path
            if source_file:
                source["source_file"] = source_file
            if line_number is not None:
                source["source_line"] = line_number
            if page_number is not None:
                source["source_page"] = page_number
            locator_parts = [rel_path]
            if line_number is not None:
                locator_parts.append(f"line {line_number}")
            if page_number is not None:
                locator_parts.append(f"page {page_number}")
            source["source_locator"] = " · ".join(locator_parts)
            source["content"] = _append_location_to_content(
                content,
                derived_file=rel_path,
                source_file=source_file,
                line_number=line_number,
                page_number=page_number,
            )
        return sources

    def _project_markdown_index(self, derived_root: Path) -> dict[str, tuple[str, Path, dict, list[str]]]:
        index: dict[str, tuple[str, Path, dict, list[str]]] = {}
        if not derived_root.exists():
            return index
        for path in derived_root.rglob("*.md"):
            if any(part in {".git", ".pending_review"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                frontmatter, _ = _split_frontmatter(text)
                rel = path.relative_to(derived_root).as_posix()
            except Exception:
                continue
            lines = text.splitlines()
            keys = {
                rel.lower(),
                rel.removesuffix(".md").lower(),
                _slug_key(rel.removesuffix(".md")),
            }
            title = str(frontmatter.get("title") or "").strip()
            if title:
                keys.add(title.lower())
                keys.add(_slug_key(title))
            source_file = str(frontmatter.get("project_r_source_file") or "").strip()
            if source_file:
                keys.add(source_file.lower())
                keys.add(Path(source_file).stem.lower())
                keys.add(_slug_key(Path(source_file).stem))
            for key in keys:
                if key:
                    index.setdefault(key, (rel, path, frontmatter, lines))
        return index

    def _match_project_markdown(
        self,
        source: dict,
        derived_root: Path,
        index: dict[str, tuple[str, Path, dict, list[str]]],
    ) -> tuple[str, Path, dict, list[str]] | None:
        file_value = str(source.get("file") or "")
        slug = file_value.split("/", 1)[1] if file_value.startswith("gbrain:") and "/" in file_value else file_value
        candidates = [
            str(source.get("section_path") or ""),
            str(source.get("source_title") or ""),
            slug,
            f"{slug}.md" if slug and not slug.endswith(".md") else slug,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            for key in (candidate.lower(), candidate.removesuffix(".md").lower(), _slug_key(candidate)):
                match = index.get(key)
                if match:
                    return match
            path = (derived_root / candidate).with_suffix(".md") if not candidate.endswith(".md") else derived_root / candidate
            try:
                if path.exists() and path.is_file():
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    frontmatter, _ = _split_frontmatter(text)
                    return path.relative_to(derived_root).as_posix(), path, frontmatter, text.splitlines()
            except Exception:
                continue
        return None

    def _think_diagnostic_sources(self, response: dict | None, source_id: str) -> list[dict]:
        if not isinstance(response, dict):
            return []
        message = response.get("error") or response.get("status")
        if not message:
            return []
        return [
            {
                "file": f"gbrain:{source_id}/__think_status__",
                "source_title": "GBrain think 状态",
                "section_path": str(response.get("status") or "unavailable"),
                "type": "gbrain_think_status",
                "authority_level": source_id,
                "tags": "gbrain,think,status",
                "content": str(message),
                "score": 0.0,
            }
        ]

    @staticmethod
    def _think_unavailable_message(response: dict | None) -> str:
        status = response.get("status") if isinstance(response, dict) else None
        error = response.get("error") if isinstance(response, dict) else None
        if status == "disabled":
            return "GBrain think 尚未启用。当前仍可使用普通 `/query` 检索知识库。"
        if status == "source_scope_unverified":
            return "GBrain think 暂未开放，因为当前需要先确认 source scope 不会跨项目串库。"
        if status == "oauth_required":
            return "GBrain think 需要配置 source-scoped OAuth client 后才能使用。"
        if error:
            return f"GBrain think 暂不可用：{error}"
        return "GBrain think 暂不可用，请管理员检查知识库服务配置。"

    def _adjust_company_score(self, query: str, source: dict) -> float:
        score = self._score(source.get("score"))
        file = str(source.get("file") or "").lower()
        section_path = str(source.get("section_path") or "").lower()
        title = str(source.get("source_title") or "").lower()
        haystack = f"{file} {section_path} {title}"
        if _query_mentions_source_title(query, title, file):
            score += COMPANY_EXACT_TITLE_SCORE_BOOST
        if _is_standard_like_query(query):
            if "/standards/" in haystack or "as 1288" in haystack or "as_2047" in haystack or "as 2047" in haystack:
                score += COMPANY_STANDARD_SOURCE_SCORE_BOOST
            if "/meetings/" in haystack or "会议" in haystack:
                score -= COMPANY_STANDARD_NOISE_PENALTY
        if _is_rule_like_query(query):
            if "/rules/" in haystack:
                score += COMPANY_RULE_SOURCE_SCORE_BOOST
            if "/meetings/" in haystack or "会议" in haystack:
                score -= COMPANY_RULE_NOISE_PENALTY
        return score

    @staticmethod
    def _gbrain_items(result: Any) -> list[Any]:
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            for key in ("items", "results", "matches", "chunks", "sources"):
                value = result.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _first_text(item: dict, *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _score(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def _slug_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")


def _local_company_slug(rel_path: str) -> str:
    path = PurePosixPath(rel_path).with_suffix("")
    parts = [
        re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "-", part.lower().replace("+", "")).strip("-")
        for part in path.parts
    ]
    return "/".join(part for part in parts if part)


def _locate_excerpt_line(lines: list[str], excerpt: str) -> int | None:
    needles = [
        _normalize_locator_text(line)
        for line in excerpt.splitlines()
        if len(_normalize_locator_text(line)) >= 24
    ]
    if not needles:
        compact_excerpt = _normalize_locator_text(excerpt)
        if compact_excerpt:
            needles = [compact_excerpt[:120]]
    for index, line in enumerate(lines, start=1):
        haystack = _normalize_locator_text(line)
        if not haystack:
            continue
        if any(needle and (needle in haystack or haystack in needle) for needle in needles):
            return index
    return None


def _nearest_page_marker(lines: list[str], line_number: int | None) -> int | None:
    search_lines = lines[:40] if line_number is None else lines[max(0, line_number - 40) : line_number]
    for line in reversed(search_lines):
        match = re.search(r"(?:^#+\s*)?(?:Page|p\.)\s*(\d{1,5})\b", line, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _append_location_to_content(
    content: str,
    *,
    derived_file: str,
    source_file: str,
    line_number: int | None,
    page_number: int | None,
) -> str:
    details = [f"- derived: `{derived_file}`"]
    if source_file:
        details.append(f"- source: `{source_file}`")
    if line_number is not None:
        details.append(f"- line: `{line_number}`")
    if page_number is not None:
        details.append(f"- page: `{page_number}`")
    return content.rstrip() + "\n\n定位 / Location\n" + "\n".join(details)


def _normalize_locator_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[`*_>#\-\[\]]+", " ", value)).strip().lower()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _is_standard_like_query(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(keyword in lowered for keyword in COMPANY_STANDARD_QUERY_KEYWORDS)


def _is_rule_like_query(text: str) -> bool:
    lowered = " ".join(text.lower().split())
    return any(keyword in lowered for keyword in COMPANY_RULE_QUERY_KEYWORDS)


def _query_mentions_source_title(query: str, title: str, file: str) -> bool:
    query_compact = _compact_title_match_text(query)
    candidates = [
        _compact_title_match_text(title),
        _compact_title_match_text(Path(file).stem),
    ]
    for candidate in candidates:
        if len(candidate) >= 4 and candidate in query_compact:
            return True
    return False


def _compact_title_match_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def _compact_company_rule_question(text: str) -> str:
    original = text.strip()
    compact = re.sub(r"[\s。！？!?；;：:,，]+$", "", original)
    suffixes = (
        "有哪些要求",
        "有什么要求",
        "有什麼要求",
        "是什么",
        "是什麼",
        "有哪些",
        "有什么",
        "有什麼",
        "怎么做",
        "怎麼做",
        "如何做",
        "如何",
        "怎么",
        "怎麼",
    )
    for suffix in suffixes:
        if compact.endswith(suffix):
            compact = compact[: -len(suffix)].strip()
            break
    compact = compact.strip(" 的：:,，")
    if compact == original or not _contains_cjk(compact):
        return ""
    return compact if len(_compact_title_match_text(compact)) >= 4 else ""


def _company_local_query_tokens(values: list[str]) -> list[str]:
    tokens: set[str] = set()
    for value in values:
        lowered = value.lower()
        for match in re.findall(r"[a-z0-9_+-]{3,}", lowered):
            tokens.add(match)
        for segment in re.findall(r"[\u4e00-\u9fff]{2,}", value):
            if len(segment) <= 4:
                tokens.add(segment)
                continue
            for size in (2, 3, 4):
                for index in range(0, len(segment) - size + 1):
                    tokens.add(segment[index : index + size])
    stopwords = {
        "什么",
        "如何",
        "怎么",
        "为什么",
        "需要",
        "应该",
        "哪些",
        "要求",
        "规则",
        "流程",
        "status",
        "rules",
        "system",
    }
    return sorted(
        (token for token in tokens if token not in stopwords and len(token) >= 2),
        key=lambda token: (-len(token), token),
    )


def _best_company_local_excerpt(body: str, tokens: list[str]) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", body) if paragraph.strip()]
    best: tuple[int, str] | None = None
    lowered_tokens = [token.lower() for token in tokens]
    for paragraph in paragraphs[:80]:
        if re.fullmatch(r"#{1,6}\s+.+", paragraph):
            continue
        lowered = paragraph.lower()
        score = sum(1 for token in lowered_tokens if token in lowered)
        if score and (best is None or score > best[0]):
            best = (score, paragraph)
    return best[1] if best else ""


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        normalized = " ".join(term.strip().split())
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


PROJECT_PENDING_REVIEW_PREFIX = "gbrain_project_pending_review:"


def approve_knowledge_review_to_gbrain(
    review: Any,
    settings: GBrainSettings | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    if str(review.source or "").startswith("gbrain_pending_review:"):
        pending_path = str(review.source).split(":", 1)[1]
        result = approve_pending_review_markdown(
            settings,
            pending_path,
            content=review.content,
            reviewer_id=getattr(review, "reviewer_id", None),
        )
        result.update({"scope": "company", "source_id": settings.company_source_id})
        return result
    if str(review.source or "").startswith(PROJECT_PENDING_REVIEW_PREFIX):
        return approve_project_pending_review_to_gbrain(review, settings=settings, db=db)
    return append_approved_knowledge(review, settings)


def approve_project_pending_review_to_gbrain(
    review: Any,
    *,
    settings: GBrainSettings | None = None,
    db: Session | None,
) -> dict[str, Any]:
    if db is None:
        raise ValueError("project pending review approval requires a database session")
    source = str(review.source or "")
    remainder = source[len(PROJECT_PENDING_REVIEW_PREFIX) :]
    try:
        workspace_id_raw, pending_path = remainder.split(":", 1)
        workspace_id = int(workspace_id_raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid project pending review source") from exc
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise ValueError(f"project workspace not found: {workspace_id}")

    base_settings = settings or load_gbrain_settings()
    paths = project_source_paths_for_workspace(workspace)
    project_settings = GBrainSettings(
        enabled=base_settings.enabled,
        base_url=base_settings.base_url,
        service_bearer_token=base_settings.service_bearer_token,
        timeout_seconds=base_settings.timeout_seconds,
        home_path=base_settings.home_path,
        company_source_id=project_source_id_for_workspace(workspace),
        company_source_name=base_settings.company_source_name,
        raw_path=paths["raw"],
        derived_path=paths["derived"],
        manifests_path=paths["manifests"],
        local_git_enabled=base_settings.local_git_enabled,
        cli_workdir=base_settings.cli_workdir,
        bun_executable=base_settings.bun_executable,
        http_bind=base_settings.http_bind,
    )
    result = approve_pending_review_markdown(
        project_settings,
        pending_path,
        content=review.content,
        reviewer_id=getattr(review, "reviewer_id", None),
    )
    result.update(
        {
            "scope": "project",
            "workspace_id": workspace.id,
            "source_id": project_source_id_for_workspace(workspace),
        }
    )
    approved_path = paths["derived"] / str(result.get("approved_file") or "")
    try:
        text = approved_path.read_text(encoding="utf-8")
        frontmatter, _ = _split_frontmatter(text)
        source_file = frontmatter.get("project_r_source_file")
        if isinstance(source_file, str):
            result["source_file"] = source_file
    except OSError:
        pass
    return result


def append_approved_knowledge(review: Any, settings: GBrainSettings | None = None) -> dict[str, Any]:
    settings = settings or load_gbrain_settings()
    source_paths = resolve_gbrain_source_paths("company", settings=settings)
    gbrain_ready = source_paths.gbrain_ready
    rules_dir = gbrain_ready / "reviews"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "知识审核沉淀.md"
    marker = f"<!-- knowledge_review:{review.id} -->"
    if target.exists():
        text = target.read_text(encoding="utf-8")
        if marker in text:
            return {
                "approved_file": target.relative_to(gbrain_ready).as_posix(),
                "pending_file": None,
                "scope": "company",
                "source_id": settings.company_source_id,
            }
    else:
        text = (
            "---\n"
            "title: 知识审核沉淀\n"
            "type: review_log\n"
            "authority_level: internal_reviewed\n"
            "tags:\n"
            "  - 知识审核\n"
            "review_status: approved\n"
            "---\n\n"
            "# 知识审核沉淀\n"
        )

    reviewed_at = review.reviewed_at or datetime.now(timezone.utc)
    section = (
        f"\n\n## 审核知识 {review.id}\n\n"
        f"{marker}\n\n"
        f"- 来源：{review.source or 'knowledge_review'}\n"
        f"- 审核时间：{reviewed_at.isoformat()}\n\n"
        f"{review.content.strip()}\n"
    )
    target.write_text(text.rstrip() + section, encoding="utf-8")
    return {
        "approved_file": target.relative_to(gbrain_ready).as_posix(),
        "pending_file": None,
        "scope": "company",
        "source_id": settings.company_source_id,
    }
