from __future__ import annotations

from typing import Callable

from fastapi import HTTPException

from app.features.chat.schemas import TransformTextRequest
from app.shared.llm.client import LLMClient, LLMResponse


ALLOWED_TRANSFORM_ACTIONS = {"rewrite", "translate", "summarize", "expand"}


def transform_chat_text(
    req: TransformTextRequest,
    *,
    get_llm_client: Callable[[str | None], LLMClient],
) -> LLMResponse:
    action = req.action.strip().lower()
    if action not in ALLOWED_TRANSFORM_ACTIONS:
        raise HTTPException(status_code=400, detail="不支持的文本变换类型")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="缺少需要处理的文本")
    client = get_llm_client(req.model_profile or req.provider)
    return client.complete(
        [{"role": "user", "content": _build_user_prompt(action, text, req)}],
        system_prompt=_system_prompt(action),
        thinking=req.thinking,
    )


def _system_prompt(action: str) -> str:
    base = (
        "你是 Project_R 的企业文本变换助手。"
        "只输出处理后的正文，不要解释过程，不要添加免责声明。"
        "保持原文事实，不编造信息。"
        "输出必须清晰、结构化、可执行；涉及项目沟通时保留责任边界、条件限制、下一步动作和待确认点。"
        "如果内容明显是项目邮件，邮件主题必须以完整项目名称开头；若原文没有项目名称，不要编造项目名称。"
    )
    if action == "translate":
        return base + "翻译时保留专有名词、编号、日期、金额和项目引用。"
    if action == "summarize":
        return base + "总结时保留关键结论、风险、下一步动作。"
    if action == "expand":
        return base + "扩写时让表达更完整，但不要增加未经确认的新事实。"
    return base + "改写时提升清晰度、语气和可读性。"


def _build_user_prompt(action: str, text: str, req: TransformTextRequest) -> str:
    target = (req.target_language or "").strip()
    tone = (req.tone or "").strip()
    if action == "translate":
        language = target or "中文"
        return f"请把下面文本翻译成{language}，保留格式和事实：\n\n{text}"
    if action == "summarize":
        return f"请总结下面文本，输出简洁要点：\n\n{text}"
    if action == "expand":
        tone_part = f"语气要求：{tone}\n" if tone else ""
        return f"请扩写下面文本，使其更完整、自然、适合业务沟通。\n{tone_part}\n{text}"
    tone_part = f"语气要求：{tone}\n" if tone else ""
    return f"请改写下面文本，使其更清晰、专业、自然。\n{tone_part}\n{text}"
