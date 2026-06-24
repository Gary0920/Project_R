from __future__ import annotations

import re
from typing import Any

from app.features.chat.intent import IntentType
from app.features.prompts.system_prompt import compose_system_prompt

QUERY_ANSWER_SYNTHESIS_PROMPT = """
你是 Project_R 的知识库问答写作层。GBrain Think 已完成检索，并给出初步结论草稿。

你的任务：基于「Think 草稿」和「检索来源片段」，写出可直接指导业务推进的详细回答。

硬性要求：
1. 只能使用草稿和来源片段中的事实，不得编造公司规则、流程细节、责任方或未出现的标准号。
2. 把 Think 草稿中的每个步骤展开为可执行说明；必要时用二级要点补充具体操作、注意事项、并行关系。
3. 保留 Think 草稿的步骤顺序与核心结论，不要压缩成只有标题的大纲。
4. 来源引用由前端「引用来源」卡片展示：正文不要列出来源文件清单，不要输出「引用与缺口」尾巴，不要用 [[文件名]] 堆叠引用。
5. 若存在资料缺口、冲突或警告，在回答末尾单独用「## 待确认项」列出，并说明应向谁确认或需补充什么资料。
6. 输出使用 Markdown，风格清晰、专业、便于转发。
"""


def is_diagnostic_think_source(source: dict) -> bool:
    file_value = str(source.get("file") or "")
    source_type = str(source.get("type") or "")
    if source_type in {"gbrain_think_status"}:
        return True
    return "__think_gaps__" in file_value or "__think_status__" in file_value


def sources_for_synthesis(sources: list[dict]) -> list[dict]:
    return [source for source in sources if not is_diagnostic_think_source(source)]


def build_query_synthesis_system_prompt(
    *,
    req: Any,
    rag_sources: list[dict],
    think_draft: str,
    gaps: list[str],
    conflicts: list[str],
    warnings: list[str],
    load_global_base_prompt: Any,
    compose_system_prompt_fn=compose_system_prompt,
) -> str:
    sections = [
        compose_system_prompt_fn(
            req.system_prompt,
            rag_sources,
            intent=IntentType.RAG_QUERY,
            reduce_knowledge_context=False,
            global_base_prompt=load_global_base_prompt(),
        ),
        QUERY_ANSWER_SYNTHESIS_PROMPT.strip(),
        "## GBrain Think 初步草稿\n" + (think_draft.strip() or "（Think 未返回草稿，请仅依据来源片段回答。）"),
    ]
    if gaps:
        sections.append("## 资料缺口\n" + "\n".join(f"- {item}" for item in gaps))
    if conflicts:
        sections.append("## 资料冲突\n" + "\n".join(f"- {item}" for item in conflicts))
    effective_warnings = filter_secondary_issues([*gaps, *conflicts], warnings)
    if effective_warnings:
        sections.append("## 检索警告\n" + "\n".join(f"- {item}" for item in effective_warnings))
    return "\n\n".join(section for section in sections if section and section.strip())


def synthesize_query_answer(
    *,
    llm_client: Any,
    req: Any,
    knowledge_query: str,
    think_draft: str,
    response_sources: list[dict],
    metadata: dict | None,
    load_global_base_prompt: Any,
    thinking: bool = False,
) -> Any:
    meta = metadata or {}
    gaps = [str(item).strip() for item in (meta.get("gaps") or []) if str(item).strip()]
    conflicts = [str(item).strip() for item in (meta.get("conflicts") or []) if str(item).strip()]
    warnings = [str(item).strip() for item in (meta.get("warnings") or []) if str(item).strip()]
    rag_sources = sources_for_synthesis(response_sources)
    system_prompt = build_query_synthesis_system_prompt(
        req=req,
        rag_sources=rag_sources,
        think_draft=think_draft,
        gaps=gaps,
        conflicts=conflicts,
        warnings=warnings,
        load_global_base_prompt=load_global_base_prompt,
    )
    return llm_client.complete(
        [{"role": "user", "content": knowledge_query.strip() or think_draft.strip() or "请根据知识库资料回答。"}],
        system_prompt=system_prompt,
        thinking=thinking,
    )


def filter_secondary_issues(primary: list[str], secondary: list[str]) -> list[str]:
    primary_keys = {issue_key(item) for item in primary if issue_key(item)}
    return [item for item in secondary if issue_key(item) and issue_key(item) not in primary_keys]


def issue_key(value: str) -> str:
    return re.sub(r"[\s。．.，,、；;：:！!？?（）()\[\]【】\"'`_-]+", "", str(value or "").strip().lower())
