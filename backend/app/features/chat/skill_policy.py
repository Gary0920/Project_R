from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


def skill_outputs_chat_text(skill) -> bool:
    mode = str((skill.execution or {}).get("mode") or "")
    if mode:
        return mode == "llm_chat_text"
    return any(str(output.get("type") or "") == "chat_text" for output in skill.outputs)


def ensure_llm_chat_text_skill_allowed(skill) -> None:
    mode = str((skill.execution or {}).get("mode") or "")
    if mode != "llm_chat_text":
        return
    allowed_tools = {
        str(tool).strip()
        for tool in ((skill.governance or {}).get("allowed_tools") or (skill.execution or {}).get("allowed_tools") or [])
        if str(tool).strip()
    }
    if "llm.complete" not in allowed_tools:
        raise HTTPException(status_code=500, detail="Skill 执行策略缺少 llm.complete 授权")


def chat_text_skill_input_payload(skill, content: str) -> dict[str, str]:
    for item in skill.inputs:
        if str(item.get("type") or "") == "text":
            return {str(item.get("name") or "input"): content}
    return {"input": content}


def load_skill_prompt(skill, *, base_dir: Path) -> str:
    skill_file = base_dir / skill.path
    prompt_file = skill_file.parent / "prompt.md"
    try:
        return prompt_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def compose_skill_base_prompt(base_prompt: str | None, display_name: str, skill_prompt: str) -> str:
    parts: list[str] = []
    if base_prompt and base_prompt.strip():
        parts.append(base_prompt.strip())
    parts.append(
        f"当前启用的业务 Skill：{display_name}。"
        "请严格按该 Skill 的目的、输出结构和风险边界处理用户请求。"
    )
    if skill_prompt:
        parts.append("以下是该 Skill 的专用指令：\n\n" + skill_prompt)
    return "\n\n".join(parts)
