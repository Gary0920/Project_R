from __future__ import annotations

import re
from dataclasses import dataclass

from app.shared.llm.client import LLMConfigurationError, LLMProviderError, get_llm_client


GBRAIN_THINK_REVIEW_PREFIX = "gbrain_think_review:"
EMPTY_SECTION_VALUES = {"", "无", "none", "无 / none", "- 无", "- none", "- 无 / none"}


@dataclass(frozen=True)
class GBrainReviewSummary:
    topic: str
    admin_summary: str
    question: str
    user_note: str
    business_context: str
    expected_knowledge: str
    source_hint: str
    gaps: tuple[str, ...]
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...]
    citations: tuple[str, ...]
    answer_excerpt: str


def is_gbrain_think_review_source(source: str | None) -> bool:
    return str(source or "").startswith(GBRAIN_THINK_REVIEW_PREFIX)


def summarize_gbrain_review_content(content: str) -> GBrainReviewSummary:
    user_supplement = _parse_user_supplement(_extract_markdown_section(content, "用户补充信息 / User Supplement"))
    question = _extract_markdown_section(content, "原问题 / Original Question")
    answer_excerpt = _extract_markdown_section(content, "原回答摘录 / Answer Excerpt")
    gaps = tuple(_parse_issue_list(_extract_markdown_section(content, "GBrain 缺口 / Gaps")))
    conflicts = tuple(_parse_issue_list(_extract_markdown_section(content, "GBrain 冲突 / Conflicts")))
    warnings = tuple(_filter_secondary_issues(
        [*gaps, *conflicts],
        _parse_issue_list(_extract_markdown_section(content, "GBrain 警告 / Warnings")),
    ))
    citations = tuple(_parse_citation_list(_extract_markdown_section(content, "GBrain 引用来源 / GBrain Citations")))
    topic = _first_line(user_supplement["expected_knowledge"]) or _first_line(gaps[0] if gaps else "") or _first_line(question) or "待补充知识"
    admin_summary = _build_admin_summary(
        topic=topic,
        user_note=user_supplement["user_note"],
        business_context=user_supplement["business_context"],
        expected_knowledge=user_supplement["expected_knowledge"],
        source_hint=user_supplement["source_hint"],
        gaps=gaps,
        conflicts=conflicts,
        warnings=warnings,
        question=question,
    )
    return GBrainReviewSummary(
        topic=topic,
        admin_summary=admin_summary,
        question=question,
        user_note=user_supplement["user_note"],
        business_context=user_supplement["business_context"],
        expected_knowledge=user_supplement["expected_knowledge"],
        source_hint=user_supplement["source_hint"],
        gaps=gaps,
        conflicts=conflicts,
        warnings=warnings,
        citations=citations,
        answer_excerpt=answer_excerpt,
    )


def generate_gbrain_review_draft(content: str, *, model_profile: str | None = None) -> dict[str, str]:
    summary = summarize_gbrain_review_content(content)
    fallback = build_gbrain_review_draft(summary)
    try:
        response = get_llm_client(model_profile).complete(
            [{"role": "user", "content": _draft_prompt(summary)}],
            system_prompt=(
                "你是 Project_R 的公司知识库审核助理。你的任务是把用户反馈和 GBrain 诊断整理成"
                "管理员可编辑的正式知识草稿。必须谨慎，不能把未核实的信息写成事实；缺少依据时要明确"
                "标注需要管理员核实。只输出 Markdown 草稿，不输出解释。"
            ),
            temperature=0.2,
        )
        draft = response.text.strip()
        if draft:
            return {
                "draft": draft,
                "summary": summary.admin_summary,
                "generated_by": response.provider,
                "model": response.model,
            }
    except (LLMConfigurationError, LLMProviderError, RuntimeError):
        pass
    return {
        "draft": fallback,
        "summary": summary.admin_summary,
        "generated_by": "template",
        "model": "",
    }


def build_gbrain_review_draft(summary: GBrainReviewSummary) -> str:
    references = []
    if summary.source_hint:
        references.append(f"- 用户提供线索：{summary.source_hint}")
    references.extend(f"- GBrain 引用：{citation}" for citation in summary.citations)
    risks = []
    risks.extend(f"- 缺口：{item}" for item in summary.gaps)
    risks.extend(f"- 冲突：{item}" for item in summary.conflicts)
    risks.extend(f"- 风险提示：{item}" for item in summary.warnings)
    scenario = summary.business_context or summary.user_note or summary.question or "（请管理员补充该知识适用的业务场景）"
    formal = summary.expected_knowledge or summary.topic or "（请管理员根据正式资料补充可长期复用的知识内容）"
    return "\n".join([
        f"## {summary.topic}",
        "",
        "## 适用场景",
        scenario,
        "",
        "## 正式知识",
        formal,
        "",
        "## 处理原则",
        "1. 以公司正式制度、流程文件或管理员确认的信息为准。",
        "2. 若现有资料不足，应先补充来源，再写入可长期复用的规则。",
        "",
        "## 参考来源",
        "\n".join(references) if references else "（请管理员补充制度文件、资料位置或负责人）",
        "",
        "## 管理员核实记录",
        "\n".join(risks) if risks else "- 本条反馈未包含明确的 GBrain 缺口、冲突或警告。",
    ])


def _draft_prompt(summary: GBrainReviewSummary) -> str:
    return "\n".join([
        "请根据以下审核材料生成一版正式知识草稿。",
        "",
        "要求：",
        "- 只输出 Markdown。",
        "- 使用清晰标题：知识主题、适用场景、正式知识、处理原则、参考来源、管理员核实记录。",
        "- 不要复制 trace、source id、模型诊断原文。",
        "- 不要把未核实内容写成确定事实；需要核实的部分写入管理员核实记录。",
        "",
        f"缺口主题：{summary.topic}",
        f"管理员摘要：{summary.admin_summary}",
        f"用户原问题：{summary.question or '未记录'}",
        f"用户自由说明：{summary.user_note or '未填写'}",
        f"业务场景：{summary.business_context or '未填写'}",
        f"期望补充知识：{summary.expected_knowledge or '未填写'}",
        f"参考来源线索：{summary.source_hint or '未提供'}",
        "GBrain 缺口：",
        "\n".join(f"- {item}" for item in summary.gaps) or "- 无",
        "GBrain 冲突：",
        "\n".join(f"- {item}" for item in summary.conflicts) or "- 无",
        "GBrain 风险提示：",
        "\n".join(f"- {item}" for item in summary.warnings) or "- 无",
        "GBrain 引用来源：",
        "\n".join(f"- {item}" for item in summary.citations) or "- 无",
    ])


def _build_admin_summary(
    *,
    topic: str,
    user_note: str,
    business_context: str,
    expected_knowledge: str,
    source_hint: str,
    gaps: tuple[str, ...],
    conflicts: tuple[str, ...],
    warnings: tuple[str, ...],
    question: str,
) -> str:
    user_intent = expected_knowledge or user_note or business_context or question or "用户希望管理员判断是否需要补充公司知识。"
    system_signal = gaps[0] if gaps else conflicts[0] if conflicts else warnings[0] if warnings else topic
    source_text = f"参考线索：{source_hint}" if source_hint else "用户未提供明确参考来源。"
    return f"用户需要确认“{_first_line(user_intent)}”；GBrain 判断的主要问题是“{_first_line(system_signal)}”。{source_text}"


def _extract_markdown_section(content: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*\n+([\s\S]*?)(?=\n##\s+|$)", re.M)
    match = pattern.search(content)
    return (match.group(1) if match else "").strip()


def _parse_issue_list(section: str) -> list[str]:
    return [
        line
        for line in (item.strip().lstrip("-* ").strip() for item in section.splitlines())
        if line and line.lower() not in EMPTY_SECTION_VALUES
    ]


def _parse_citation_list(section: str) -> list[str]:
    citations: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^\d+\.\s+`([^`]+)`", line.strip())
        if match:
            citations.append(match.group(1))
        if len(citations) >= 4:
            break
    return citations


def _parse_user_supplement(section: str) -> dict[str, str]:
    return {
        "business_context": _extract_bullet_value(section, "业务场景 / Business Context"),
        "expected_knowledge": _extract_bullet_value(section, "期望补充知识 / Expected Knowledge"),
        "source_hint": _extract_bullet_value(section, "可参考来源 / Source Hint"),
        "user_note": _extract_bullet_value(section, "自由说明 / User Note"),
    }


def _extract_bullet_value(section: str, label: str) -> str:
    prefix = f"- {label}:"
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix):].strip()
            return "" if value.lower() in EMPTY_SECTION_VALUES else value
    return ""


def _filter_secondary_issues(primary: list[str], secondary: list[str]) -> list[str]:
    primary_keys = {_issue_key(item) for item in primary if _issue_key(item)}
    return [item for item in secondary if _issue_key(item) and _issue_key(item) not in primary_keys]


def _first_line(value: str) -> str:
    return next((line.strip() for line in str(value or "").splitlines() if line.strip()), "")


def _issue_key(value: str) -> str:
    return re.sub(r"[\s。．.，,、；;：:！!？?（）()[\]【】\"'`_-]", "", str(value or "").lower())
