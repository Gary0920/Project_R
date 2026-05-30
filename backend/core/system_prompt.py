from __future__ import annotations

from core.intent import IntentType


TEXT_TRANSFORMATION_PROMPT_IDS = {
    "company:company-work-message-polish",
    "company:company-translate-email",
}

FORMAT_GUIDANCE_PROMPT = (
    "输出格式要求：回答可以使用 Markdown 标题、列表、表格和引用块。"
    "当用户要求生成邮件、通知、说明、话术、模板或其他可直接复用的正文时，"
    "请把最终可复制正文单独放入 fenced code block（三个反引号）中，"
    "代码块外只保留必要说明。"
)

DOCUMENT_GENERATION_PROMPT = (
    "文档生成模式：Project_R 会把你的回答自动渲染为可下载的 Word .docx 文件，"
    "因此不要说你无法生成文件、不要提供复制到 Word 的操作步骤、不要提醒用户手动保存。"
    "只输出要写入文档正文的最终内容。"
    "如果用户基于上一轮内容要求生成文档，请只保留可直接放入文档的正文，删除解释、提醒、来源列表和操作说明。"
    "不要使用 fenced code block；可以使用 Markdown 标题、列表和表格表达结构。"
)

TEXT_TRANSFORMATION_REDUCTION_PROMPT = (
    "当前会话选中了文本变换类提示词。"
    "本轮应优先执行用户提供文本的改写、翻译、润色或整理任务，"
    "默认不注入公司知识库、项目资料或外部规范。"
    "除非用户明确使用 /query 或明确要求查询公司资料，否则不要补充用户原文之外的事实、标准号、来源、分类、建议或结论。"
)

EMPTY_KNOWLEDGE_PROMPT = (
    '注意：知识库中未检索到与用户问题直接相关的公司内部资料。'
    '请先如实告知用户"知识库中未找到相关信息"，'
    '并询问用户是否需要基于通用知识来回答。'
    '不要凭借自身知识编造公司内部规定或流程。'
)


def should_reduce_knowledge_context(selected_prompt_id: str | None, forced_knowledge: bool) -> bool:
    if forced_knowledge:
        return False
    return (selected_prompt_id or "").strip() in TEXT_TRANSFORMATION_PROMPT_IDS


def compose_system_prompt(
    base_prompt: str | None,
    rag_sources: list[dict],
    *,
    intent: IntentType | None = None,
    attachment_context: str = "",
    reduce_knowledge_context: bool = False,
    global_base_prompt: str = "",
) -> str | None:
    parts: list[str] = []
    if global_base_prompt:
        parts.append(global_base_prompt)
    if base_prompt and base_prompt.strip():
        parts.append(base_prompt.strip())
    parts.append(FORMAT_GUIDANCE_PROMPT)
    if intent == IntentType.DOCUMENT_GENERATION:
        parts.append(DOCUMENT_GENERATION_PROMPT)
    if reduce_knowledge_context:
        parts.append(TEXT_TRANSFORMATION_REDUCTION_PROMPT)
    if attachment_context:
        parts.append(
            "以下是用户在当前会话上传的临时附件内容。附件只服务本次会话，优先于全局知识库；"
            "如果附件内容不足以回答，请明确说明还缺少哪些资料。\n\n"
            + attachment_context
        )
    if rag_sources:
        parts.append(_knowledge_source_prompt(rag_sources))
        parts.append(
            "回答格式要求：知识库来源会由前端引用来源卡片统一展示。"
            "不要在正文末尾列出来源文件，不要输出“本次使用的来源文件”小节，"
            "也不要为了标注来源而堆叠 `[[文件名]]`。"
            "如果关键信息缺失且会影响结论或表单内容，请先用简短问题向用户澄清，"
            "不要一边提示缺口一边继续生成完整正文。"
        )
    elif intent == IntentType.RAG_QUERY and not reduce_knowledge_context:
        parts.append(EMPTY_KNOWLEDGE_PROMPT)
    return "\n\n".join(parts) if parts else None


def _knowledge_source_prompt(rag_sources: list[dict]) -> str:
    snippets = []
    for index, source in enumerate(rag_sources, start=1):
        snippets.append(
            "\n".join(
                [
                    f"[来源 {index}] {source.get('file', '')} | {source.get('section_path', '')}",
                    str(source.get("content", ""))[:1200],
                ]
            )
        )
    return (
        "以下是 Project_R 从公司知识库检索到的参考片段。回答时优先依据这些片段；如果片段不足以支撑结论，请明确说明缺少哪些资料。\n"
        "请保留证据权威分级：rules 为公司规则/流程，training 为经验分享，standards 为行业规范，sources 只作追溯或旁证。\n\n"
        + "\n\n".join(snippets)
    )
