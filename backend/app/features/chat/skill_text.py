from __future__ import annotations

import re


def extract_skill_inputs(content: str, missing_inputs: list[dict]) -> dict:
    extracted: dict[str, str] = {}
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    for item in missing_inputs:
        name = str(item.get("name") or "")
        label = str(item.get("label") or name)
        value = find_labeled_value(lines, name, label)
        if value:
            extracted[name] = value

    if "label_items" in {str(item.get("name") or "") for item in missing_inputs}:
        table_lines = [line for line in lines if "|" in line]
        if len(table_lines) >= 2:
            extracted["label_items"] = "\n".join(table_lines)

    if "template_file" in {str(item.get("name") or "") for item in missing_inputs}:
        lowered = content.lower()
        if "模板" in content or ".xlsx" in lowered or ".xls" in lowered:
            extracted.setdefault("template_file", "default-template")

    return extracted


def missing_input_fields_text(missing_inputs: list[dict]) -> str:
    fields = [
        f"- {item.get('label') or item.get('name') or '待补充字段'}"
        for item in missing_inputs
    ]
    return "\n".join(fields)


def missing_input_instruction(skill_name: str, missing_inputs: list[dict]) -> str:
    normalized_skill = str(skill_name or "").strip()
    missing_names = {str(item.get("name") or "").strip() for item in missing_inputs}
    missing_labels = {str(item.get("label") or "").strip() for item in missing_inputs}
    if normalized_skill == "audio-transcription" or "audio_source" in missing_names or "音频或视频文件" in missing_labels:
        return "请先在当前会话上传或从项目文件中引用一个音频/视频文件，然后重新发送“将这段录音转录成文字”。支持 MP3、WAV、M4A、OGG、FLAC、MP4、MOV 等格式。"
    if normalized_skill in ("term-correction", "术语纠错") or "term_corrections" in missing_names:
        return "请提供术语纠正规则，每行一条，例如：LAM Wiki -> LLM Wiki。"
    fields = "、".join(item.get("label") or item.get("name") or "待补充字段" for item in missing_inputs)
    return f"请补充：{fields}。"


def format_audio_transcription_reply(transcript_text: str, *, reply_extra: str = "") -> str:
    text = (transcript_text or "").strip()
    if not text:
        text = "未识别到可用的转写文本。"
    return (
        "已完成录音转文字。转写内容如下，可直接复制：\n\n"
        f"```text\n{text}\n```"
        f"{reply_extra}"
    )


def find_labeled_value(lines: list[str], name: str, label: str) -> str | None:
    aliases = {name, label}
    if label.endswith("（每行一个标签）"):
        aliases.add(label.removesuffix("（每行一个标签）"))
    for line in lines:
        for alias in aliases:
            if not alias:
                continue
            pattern = rf"^{re.escape(alias)}\s*[:：=]\s*(.+)$"
            match = re.match(pattern, line, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None
