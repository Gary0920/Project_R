from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.features.knowledge.gbrain import (
    GBrainSettings,
    customer_source_id_for_workspace,
    project_source_id_for_workspace,
)


@dataclass(frozen=True)
class ThinkTarget:
    source_id: str
    apply_project_ranking: bool = False


@dataclass(frozen=True)
class ThinkPlan:
    mode: str
    primary: ThinkTarget
    secondary: ThinkTarget | None = None


def build_think_plan(workspace: Any | None, settings: GBrainSettings) -> ThinkPlan:
    workspace_kind = str(getattr(workspace, "workspace_kind", "") or "project") if workspace else ""

    if workspace and workspace_kind == "project":
        try:
            project_source_id = project_source_id_for_workspace(workspace)
        except ValueError:
            project_source_id = ""
        if project_source_id:
            return ThinkPlan(
                mode="project_with_company",
                primary=ThinkTarget(project_source_id, apply_project_ranking=True),
                secondary=ThinkTarget(settings.company_source_id, apply_project_ranking=False),
            )
        return ThinkPlan(mode="single", primary=ThinkTarget(settings.company_source_id))

    if workspace and workspace_kind == "customer":
        try:
            customer_source_id = customer_source_id_for_workspace(workspace)
        except ValueError:
            customer_source_id = ""
        return ThinkPlan(mode="single", primary=ThinkTarget(customer_source_id))

    return ThinkPlan(mode="single", primary=ThinkTarget(settings.company_source_id))


def execute_think_plan(
    content: str,
    *,
    workspace: Any | None,
    settings: GBrainSettings,
    think_for_source: Callable[..., dict],
) -> dict:
    plan = build_think_plan(workspace, settings)
    primary = think_for_source(
        content,
        source_id=plan.primary.source_id,
        settings=settings,
        workspace=workspace,
        apply_project_ranking=plan.primary.apply_project_ranking,
    )

    if plan.mode != "project_with_company" or plan.secondary is None:
        return single_think_response(primary)

    secondary = think_for_source(
        content,
        source_id=plan.secondary.source_id,
        settings=settings,
        workspace=workspace,
        apply_project_ranking=plan.secondary.apply_project_ranking,
    )
    return merge_project_company_think(primary, secondary)


def single_think_response(partial: dict) -> dict:
    if not partial.get("ok"):
        return {
            "ok": False,
            "status": partial.get("status") or "error",
            "source_id": partial.get("source_id"),
            "reply": partial.get("error_reply") or think_unavailable_message(None),
            "sources": partial.get("sources") or [],
            "error": partial.get("error"),
        }
    answer = partial.get("raw_answer") or ""
    sources = partial.get("sources") or []
    return {
        "ok": True,
        "status": "ok",
        "source_id": partial.get("source_id"),
        "reply": append_think_source_summary(answer or "GBrain think 未返回可用回答。", sources),
        "sources": sources,
        "model": partial.get("model") or "think",
        "metadata": partial.get("metadata") or {},
    }


def merge_project_company_think(project_partial: dict, company_partial: dict) -> dict:
    # company-wiki 仅在两路都成功时叠加；任一不可用则按项目单 source 行为返回，避免回归
    if not project_partial.get("ok") or not company_partial.get("ok"):
        return single_think_response(project_partial)

    merged_sources = dedupe_think_sources(
        list(project_partial.get("sources") or []) + list(company_partial.get("sources") or [])
    )
    answer = combine_project_company_answer(
        project_partial.get("raw_answer") or "",
        company_partial.get("raw_answer") or "",
    )
    metadata = merge_think_metadata(
        project_partial.get("metadata") or {},
        company_partial.get("metadata") or {},
    )
    return {
        "ok": True,
        "status": "ok",
        "source_id": project_partial.get("source_id"),
        "source_ids": [project_partial.get("source_id"), company_partial.get("source_id")],
        "reply": append_think_source_summary(answer or "GBrain think 未返回可用回答。", merged_sources),
        "sources": merged_sources,
        "model": project_partial.get("model") or "think",
        "metadata": metadata,
    }


def append_think_source_summary(answer: str, sources: list[dict]) -> str:
    source_lines: list[str] = []
    diagnostic_lines: list[str] = []
    for source in sources:
        source_type = str(source.get("type") or "")
        if source_type == "gbrain_think_citation":
            source_index = len(source_lines) + 1
            file_value = str(source.get("file") or "").strip()
            section = str(source.get("section_path") or "").strip()
            line = f"- 来源 {source_index}: {file_value or section or 'GBrain citation'}"
            if section and section != file_value:
                line += f" ({section})"
            source_lines.append(line)
            continue
        if source_type in {"gbrain_think_gap", "gbrain_think_conflict", "gbrain_think_warning"}:
            title = str(source.get("source_title") or "").strip()
            content = str(source.get("content") or "").strip()
            if title or content:
                diagnostic_lines.append(f"- {title or source_type}: {content}".rstrip())

    if not source_lines and not diagnostic_lines:
        return answer
    sections = [answer.rstrip()]
    if source_lines:
        sections.append("引用来源\n" + "\n".join(source_lines))
    if diagnostic_lines:
        sections.append("GBrain 诊断\n" + "\n".join(diagnostic_lines))
    return "\n\n".join(sections)


def combine_project_company_answer(project_answer: str, company_answer: str) -> str:
    parts: list[str] = []
    if project_answer.strip():
        parts.append(project_answer.rstrip())
    if company_answer.strip():
        parts.append("【公司知识库补充】\n" + company_answer.rstrip())
    return "\n\n".join(parts)


def dedupe_think_sources(sources: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for source in sources:
        key = (str(source.get("file") or ""), str(source.get("section_path") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return unique


def merge_think_metadata(primary: dict, secondary: dict) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "gaps": list(primary.get("gaps") or []) + list(secondary.get("gaps") or []),
        "conflicts": list(primary.get("conflicts") or []) + list(secondary.get("conflicts") or []),
        "warnings": list(primary.get("warnings") or []) + list(secondary.get("warnings") or []),
        "diagnostics": primary.get("diagnostics") or secondary.get("diagnostics") or {},
    }
    if primary.get("project_query_intent"):
        merged["project_query_intent"] = primary["project_query_intent"]
    return merged


def think_unavailable_message(response: dict | None) -> str:
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
