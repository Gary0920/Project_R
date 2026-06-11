from __future__ import annotations

import re
from datetime import datetime, timezone

from app.shared.time.utils import serialize_datetime_utc


TRANSCRIPT_MEDIA_INPUT_TYPES = {"mp3", "wav", "m4a", "ogg", "flac", "mp4", "mov", "avi", "wmv", "mkv", "webm"}

MEETING_SYSTEM_PROMPT = """你是 Project_R 的企业会议纪要助手。你擅长从中文/英文会议转录文本中提取关键信息，生成结构化的会议纪要和行动项。

规则：
1. 只根据转录文本中的依据生成内容，不得编造。
2. 没有明确负责人的行动项，标记为「待确认」。
3. 没有明确截止时间的行动项，截止时间写「待确认」。
4. 没有明确依据的决策、风险、问题，标记为「待确认」。
5. 使用中文输出，专业、简洁、可操作。
6. 辅助总结只能作为整理参考；与一手转录冲突时，以一手转录为准，并把辅助总结独有信息标记为待确认或注明来源。
7. 输出格式为标准的 Markdown，严格按照用户要求的模板分段。"""


def escape_markdown_table_cell(text: str) -> str:
    return text.replace("|", "&#124;")


def transcript_source_label(input_type: str, original_filename: str = "") -> str:
    suffix = f"（{original_filename}）" if original_filename else ""
    normalized = (input_type or "paste").strip().lower()
    if normalized == "paste":
        return "用户粘贴文本"
    if normalized == "txt":
        return f"TXT 上传{suffix}"
    if normalized == "md":
        return f"MD 上传{suffix}"
    if normalized in ("docx", "doc"):
        return f"DOCX 上传{suffix}"
    if normalized in TRANSCRIPT_MEDIA_INPUT_TYPES:
        return f"音视频自动转录{suffix}"
    return f"{normalized.upper()} 输入{suffix}" if normalized else f"文件输入{suffix}"


def transcript_metadata_value(transcript_text: str, field_name: str) -> str:
    pattern = re.compile(rf"^\|\s*{re.escape(field_name)}\s*\|\s*(.*?)\s*\|\s*$", re.MULTILINE)
    match = pattern.search(transcript_text or "")
    return match.group(1).strip() if match else ""


def detect_speakers(text: str) -> tuple[list[dict], list[dict]]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return (
            [{"id": "Speaker 1", "label": "Speaker 1", "ratio": "100%", "duration": "—"}],
            [{"line": 1, "time": "—", "speaker_id": "Speaker 1", "speaker_label": "Speaker 1", "content": text[:200], "confidence": "—", "flag": "—"}],
        )

    speaker_pattern = re.compile(r"^(.{1,30}?)[：:]\s*(.+)", re.UNICODE)
    speaker_n_pattern = re.compile(r"^(Speaker\s*\d+|发言人\s*[A-Za-z\d]+)\s*[：:]\s*(.+)", re.IGNORECASE)
    bracket_pattern = re.compile(r"^\[(.{1,30}?)\]\s*(.+)", re.UNICODE)

    segments: list[dict] = []
    speaker_ids: dict[str, str] = {}
    speaker_line_counts: dict[str, int] = {}
    next_speaker_index = 1

    for line in lines:
        match = speaker_n_pattern.match(line) or bracket_pattern.match(line) or speaker_pattern.match(line)
        if match:
            raw_label = match.group(1).strip()
            content = match.group(2).strip()
        else:
            raw_label = ""
            content = line

        if raw_label:
            if raw_label not in speaker_ids:
                sid = f"Speaker {next_speaker_index}"
                speaker_ids[raw_label] = sid
                speaker_line_counts[sid] = 0
                next_speaker_index += 1
            sid = speaker_ids[raw_label]
        else:
            sid = segments[-1]["speaker_id"] if segments else f"Speaker {next_speaker_index}"
            if sid not in speaker_line_counts:
                speaker_ids[f"Speaker {next_speaker_index}"] = sid
                speaker_line_counts[sid] = 0
                next_speaker_index += 1

        speaker_line_counts[sid] = speaker_line_counts.get(sid, 0) + 1
        cell_content = content[:200].replace("\n", " ").replace("|", "/")
        segments.append({
            "line": len(segments) + 1,
            "time": "—",
            "speaker_id": sid,
            "speaker_label": raw_label or sid,
            "content": cell_content,
            "confidence": "—",
            "flag": "—" if raw_label else "待确认",
        })

    total = sum(speaker_line_counts.values()) or 1
    speakers: list[dict] = []
    for label, sid in speaker_ids.items():
        count = speaker_line_counts.get(sid, 0)
        speakers.append({
            "id": sid,
            "label": label,
            "ratio": f"{round(count / total * 100)}%",
            "duration": "—",
        })

    if not speakers:
        speakers = [{"id": "Speaker 1", "label": "Speaker 1", "ratio": "100%", "duration": "—"}]
    if not segments:
        segments = [{"line": 1, "time": "—", "speaker_id": "Speaker 1", "speaker_label": "Speaker 1", "content": text[:200], "confidence": "—", "flag": "—"}]

    return speakers, segments


def build_transcript_markdown(
    raw_text: str,
    now: datetime,
    input_type: str = "paste",
    original_filename: str = "",
    transcription_status: str = "completed",
    warnings: list[str] | None = None,
) -> str:
    ts = now.strftime("%Y-%m-%d %H:%M UTC")
    source_label = transcript_source_label(input_type, original_filename)
    speakers, segments = detect_speakers(raw_text)
    speaker_count = len(speakers)

    speaker_rows: list[str] = []
    for sp in speakers:
        speaker_rows.append(
            f"| {sp['id']} | {sp['label']} | 未映射 "
            f"| {sp.get('ratio','—')} "
            f"| {sp.get('duration','—')} "
            f"| 待确认 |"
        )

    transcript_rows: list[str] = []
    for seg in segments:
        transcript_rows.append(
            f"| {seg.get('line','—')} "
            f"| {seg['time']} "
            f"| {seg['speaker_id']} "
            f"| {seg['speaker_label']} "
            f"| {seg['content']} "
            f"| {seg.get('confidence','—')} "
            f"| {seg.get('flag','—')} |"
        )

    timeline_rows: list[str] = []
    for seg in segments[:20]:
        summary = seg['content'][:40].replace("\n", " ").replace("|", "/")
        timeline_rows.append(f"| {seg.get('line','—')} | {seg['time']} | {seg['speaker_id']} | {summary} |")

    return (
        "# 会议转录文本\n\n"
        "## 基本信息\n\n"
        f"| 字段 | 值 |\n"
        f"|---|---|\n"
        f"| 转录时间 | {ts} |\n"
        f"| 转录来源 | {source_label} |\n"
        f"| 输入类型 | {input_type} |\n"
        f"| 原始文件名 | {original_filename or '—'} |\n"
        f"| 转录状态 | {transcription_status or 'completed'} |\n"
        f"| 缺失片段 | {escape_markdown_table_cell('; '.join(warnings or []) if transcription_status == 'partial' else '—')} |\n"
        f"| 检测说话人数 | {speaker_count} |\n"
        "\n"
        "## 说话人概览\n\n"
        "| 说话人ID | 显示名称 | 映射状态 | 发言占比 | 发言时长 | 备注 |\n"
        "|---|---|---|---|---|---|\n"
        + "\n".join(speaker_rows) + "\n"
        "\n"
        "## 说话人时间轴\n\n"
        "| 行号 | 时间点 | 说话人ID | 内容摘要 |\n"
        "|---|---|---|---|\n"
        + "\n".join(timeline_rows) + "\n"
        "\n"
        "## 疑似术语纠错\n\n"
        "| 原识别 | 建议修正 | 类型 | 置信度 | 来源时间点 |\n"
        "|---|---|---|---|---|\n"
        "| — | — | — | — | — |\n"
        "\n"
        "## 完整转录\n\n"
        "| 行号 | 时间点 | 说话人ID | 显示名称 | 内容 | 置信度 | 标记 |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(transcript_rows) + "\n"
        "\n"
        "---\n"
        "*本转录由 Project_R 自动生成。说话人映射和术语纠错为初始结果，请人工复核。*\n"
    )


def build_minutes_prompt(
    transcript_text: str,
    speaker_map_text: str | None = None,
    term_corrections_text: str | None = None,
    auxiliary_summaries_text: str | None = None,
    meeting_type: str | None = None,
) -> str:
    transcript_source = transcript_metadata_value(transcript_text, "转录来源") or "从转录文本基本信息读取，无法判断写「待确认」"
    sections = [
        "# 会议纪要生成",
        "",
        "请根据以下会议转录文本生成正式会议纪要。",
        "如果提供了说话人映射，请使用真实名称而非 Speaker ID。",
    ]
    if speaker_map_text:
        sections.append("\n## 说话人映射参考\n\n" + speaker_map_text)
    if term_corrections_text:
        sections.append("\n## 术语纠错参考\n\n" + term_corrections_text)
    if auxiliary_summaries_text:
        sections.append(
            "\n## 辅助总结参考\n\n"
            "以下材料来自同一会议资料目录的辅助总结，只能作为二级参考；"
            "关键结论必须优先回到一手转录文本，辅助总结独有内容需标注来源或待确认。\n\n"
            + auxiliary_summaries_text
        )
    sections.append("\n## 会议转录文本\n\n" + transcript_text)
    sections.append(
        f"""

## 输出模板

请严格按以下 Markdown 模板输出。不得省略任何段落。没有内容时写「—」或「无」。

### 会议基本信息
| 字段 | 值 |
|---|---|
| 会议主题 | （从内容推断，如无法推断写「待确认」） |
| 会议时间 | （从内容或文件名推断，如无法推断写「待确认」） |
| 参会人 | （列出检测到的说话人，如无法推断写「待确认」） |
| 会议类型 | {meeting_type or '其他'} |
| 转录来源 | {transcript_source} |

### 一句话结论
（用一句话概括会议最核心的结论或决定）

### 会议摘要
（按议题或话题组织，每个议题包含：议题名称、讨论内容、结论）

### 关键决策
| ID | 决策 | 决策背景 | 影响范围 | 来源时间点 | 依据摘录 | 置信度 | 待确认 |
|---|---|---|---|---|---|---|---|
| D1 | ... | ... | ... | 00:00:00/待确认 | ... | 高/中/低 | 是/否 |

### 行动项
| ID | 行动项 | 负责人 | 协作人 | 截止时间 | 优先级 | 状态 | 来源时间点 | 待确认 |
|---|---|---|---|---|---|---|---|---|
| A1 | ... | ...（无则写待确认） | ...（无则写—） | ...（无则写待确认） | 高/中/低 | 待确认/待执行/已完成/已取消 | 00:00:00/待确认 | 是/否 |

### 风险与问题
| ID | 风险或问题 | 类型 | 影响 | 建议下一步 | 负责人 | 来源时间点 | 严重度 |
|---|---|---|---|---|---|---|---|
| R1 | ... | 技术/工期/成本/商务/客户/资料缺口 | ... | ... | ... | 00:00:00/待确认 | 高/中/低 |

### 待确认事项
| ID | 待确认事项 | 为什么需要确认 | 建议确认对象 | 来源时间点 |
|---|---|---|---|---|
| Q1 | ... | ... | ... | 00:00:00/待确认 |

### 资料与证据
| ID | 资料类型 | 文件或来源 | 来源时间点 | 依据摘录 | 说明 |
|---|---|---|---|---|---|
| E1 | 一手转录/辅助总结/用户补充/原始音视频 | ... | 00:00:00/待确认 | ... | ... |

### 可沉淀知识候选
（如果有可以沉淀为公司规则、项目经验或流程改进的知识，列出候选。如果没有写「无」）
- 类型：公司规则候选 / 项目经验候选 / 流程改进候选 / 模板候选
- 内容：...

### 生成说明
- 生成时间：当前时间
- 转录来源：{transcript_source}
- 使用模型：DeepSeek Flash
- 说话人映射：未使用 / 已使用
- 待确认项目：N 项

"""
    )
    return "\n".join(sections)


def build_actions_prompt(
    transcript_text: str,
    speaker_map_text: str | None = None,
    term_corrections_text: str | None = None,
    auxiliary_summaries_text: str | None = None,
) -> str:
    sections = [
        "# 行动项生成",
        "",
        "请根据以下会议转录文本提取行动项。",
        "如果提供了说话人映射，请使用真实名称而非 Speaker ID。",
    ]
    if speaker_map_text:
        sections.append("\n## 说话人映射参考\n\n" + speaker_map_text)
    if term_corrections_text:
        sections.append("\n## 术语纠错参考\n\n" + term_corrections_text)
    if auxiliary_summaries_text:
        sections.append(
            "\n## 辅助总结参考\n\n"
            "以下材料来自同一会议资料目录的辅助总结，只能作为二级参考；"
            "无法在一手转录中确认的行动项必须标记为待确认，并注明来源为辅助总结。\n\n"
            + auxiliary_summaries_text
        )
    sections.append("\n## 会议转录文本\n\n" + transcript_text)
    sections.append(
        """

## 输出模板

请严格按以下 Markdown 模板输出。不得省略任何段落。没有行动项时写「无」。

### 基本信息
| 字段 | 值 |
|---|---|
| 来源会议 | （自动填入） |
| 提取时间 | （当前时间） |
| 行动项总数 | N |

### 行动项总览
| 状态 | 数量 |
|---|---|
| 待确认 | N |
| 待执行 | N |
| 已完成 | 0 |
| 已取消 | 0 |

### 行动项清单
| ID | 状态 | 优先级 | 行动项 | 负责人 | 协作人 | 截止时间 | 依赖条件 | 来源时间点 | 依据摘录 | 待确认原因 |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | 待确认/待执行/已完成/已取消 | 高/中/低 | ... | ...（无则写待确认） | ...（无则写—） | ...（无则写待确认） | ...（无则写—） | 00:00:00/待确认 | ... | ...（无则写—） |

### 按负责人分组
（用二级标题列出每位负责人的行动项）

### 待确认行动项
（单独列出所有标记为「待确认」的行动项）

### 生成说明
- 生成时间：当前时间
- 使用模型：DeepSeek Flash
- 待确认项目：N 项
- 注意：行动项仅供参考，请人工复核后执行

"""
    )
    return "\n".join(sections)


def failed_transcript_reason(transcript_text: str) -> str:
    if "转录失败" not in transcript_text and "transcription_status: failed" not in transcript_text.lower():
        return ""
    match = re.search(r"\*\*错误\*\*[：:]\s*(.+)", transcript_text)
    if match:
        return match.group(1).strip()
    match = re.search(r"错误[：:]\s*(.+)", transcript_text)
    if match:
        return match.group(1).strip()
    return "音视频转录失败"


def transcript_status_value(transcript_text: str) -> str:
    if failed_transcript_reason(transcript_text):
        return "failed"
    statuses = [
        match.group(1).strip().lower()
        for match in re.finditer(r"^\|\s*转录状态\s*\|\s*(.*?)\s*\|\s*$", transcript_text or "", re.MULTILINE)
    ]
    if "partial" in statuses:
        return "partial"
    status = statuses[0] if statuses else ""
    if status:
        return status
    if "partial" in (transcript_text or "").lower() or "部分转录" in (transcript_text or ""):
        return "partial"
    return "completed"


def partial_transcript_notice(transcript_text: str) -> str:
    missing = transcript_metadata_value(transcript_text, "缺失片段") or "存在未成功转录的片段，具体时间段待确认"
    return f"| Q-PARTIAL | 转录不完整 | {missing}，纪要和行动项可能缺失上下文 | 会议组织者 | 待确认 |\n"


def build_fallback_minutes(transcript_text: str, timestamp: str, error: str = "") -> str:
    transcript_source = transcript_metadata_value(transcript_text, "转录来源") or "待确认"
    transcription_status = transcript_status_value(transcript_text)
    partial_note = partial_transcript_notice(transcript_text) if transcription_status == "partial" else ""
    return f"""# 会议纪要

## 会议基本信息

| 字段 | 值 |
|---|---|
| 会议主题 | 待确认 |
| 会议时间 | 待确认 |
| 参会人 | 待确认 |
| 会议类型 | 其他 |
| 转录来源 | {transcript_source} |
| 转录状态 | {transcription_status} |

## 一句话结论

待确认（LLM 暂不可用：{error}）

## 会议摘要

待确认

## 关键决策

| ID | 决策 | 决策背景 | 影响范围 | 来源时间点 | 依据摘录 | 置信度 | 待确认 |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | 是 |

## 行动项

| ID | 行动项 | 负责人 | 协作人 | 截止时间 | 优先级 | 状态 | 来源时间点 | 待确认 |
|---|---|---|---|---|---|---|---|---|
| — | — | 待确认 | — | 待确认 | — | 待确认 | — | 是 |

## 风险与问题

| ID | 风险或问题 | 类型 | 影响 | 建议下一步 | 负责人 | 来源时间点 | 严重度 |
|---|---|---|---|---|---|---|---|
| — | — | 资料缺口 | — | 人工复核转录和纪要 | 待确认 | — | 中 |

## 待确认事项

| ID | 待确认事项 | 为什么需要确认 | 建议确认对象 | 来源时间点 |
|---|---|---|---|---|
| Q1 | 全部内容 | LLM 暂不可用，请人工编写纪要 | 会议组织者 | — |
{partial_note}

## 资料与证据

| ID | 资料类型 | 文件或来源 | 来源时间点 | 依据摘录 | 说明 |
|---|---|---|---|---|---|
| E1 | 一手转录 | {transcript_source} | — | — | fallback 仅保留证据入口，需人工复核 |

## 可沉淀知识候选

无（LLM 暂不可用）

## 生成说明

- 生成时间：{timestamp}
- 转录来源：{transcript_source}
- 转录状态：{transcription_status}
- 使用模型：template-fallback
- 待确认项目：全部
"""


def build_fallback_actions(timestamp: str) -> str:
    return f"""# 行动项

## 基本信息

| 字段 | 值 |
|---|---|
| 来源会议 | 待确认 |
| 提取时间 | {timestamp} |
| 行动项总数 | 0 |

## 行动项总览

| 状态 | 数量 |
|---|---|
| 待确认 | 0 |
| 待执行 | 0 |
| 已完成 | 0 |
| 已取消 | 0 |

## 行动项清单

| ID | 状态 | 优先级 | 行动项 | 负责人 | 协作人 | 截止时间 | 依赖条件 | 来源时间点 | 依据摘录 | 待确认原因 |
|---|---|---|---|---|---|---|---|---|---|---|
| — | 待确认 | — | — | 待确认 | — | 待确认 | — | — | — | LLM 暂不可用，请人工从转录文本提取 |

## 待确认行动项

全部行动项需人工复核。

## 生成说明

- 生成时间：{timestamp}
- 使用模型：template-fallback
- 待确认项目：全部
- 注意：行动项仅供参考，请人工复核后执行
"""


def compose_gbrain_ready_meeting(
    meeting_folder_name: str,
    minutes_md: str,
    transcript_md: str,
    actions_md: str = "",
    *,
    source_scope: str = "",
    source_context: str = "full_meeting",
) -> str:
    generated_at = serialize_datetime_utc(datetime.now(timezone.utc))
    is_actions_only = source_context == "action_items_only"

    lines = [
        "---",
        "schema: project_r_meeting_gbrain_ready_v1",
        f"title: {meeting_folder_name}",
        f"source_context: {source_context}",
        f"source_scope: {source_scope or 'workspace'}",
        "source_priority: transcript_first" if not is_actions_only else "source_priority: actions_only",
        "generated_by: Project_R meeting workflow",
        f"generated_at: {generated_at}",
        "---",
        "",
        f"# {meeting_folder_name}",
    ]

    if is_actions_only:
        lines.extend([
            "",
            "> ⚠️ 本页面仅包含行动项，不包含完整会议纪要和转录文本。",
            "> 如需要完整会议知识，建议录入完整会议资料（minutes-latest.md + transcript-latest.md）。",
            "",
            "---",
            "",
            "## Source Context / 来源说明",
            "",
            f"- source_context: `{source_context}` — 仅行动项，低上下文完整度",
            f"- source_scope: `{source_scope or 'workspace'}`",
            "- 行动项由 Project_R 从会议转录文本或辅助总结中提炼生成。",
            "- 没有转录文本和会议纪要上下文，行动项的负责人和截止时间均以原始文件标注为准。",
            "",
            "## 行动项内容",
            "",
        ])
        if actions_md:
            lines.append(actions_md.lstrip("# ").strip())
        else:
            lines.append("（无行动项内容）")
    else:
        lines.extend([
            "",
            "> 本页面由 Project_R 自动编译生成。来源：会议文件夹中的 latest 版本。会议纪要是整理结果，不是一手转录；事实判断优先回到一手转录证据。",
            "",
            "---",
            "",
            "## Source Context / 来源说明",
            "",
            f"- source_context: `{source_context}`",
            f"- source_scope: `{source_scope or 'workspace'}`",
            "- 一手证据：`transcript-latest.md`",
            "- 整理结果：`minutes-latest.md`",
            "- 行动项辅助：`actions-latest.md`",
            "- 原始音视频不直接作为 GBrain 正文；如需核验，应回到工作区原始资料。",
            "",
            "## 会议摘要",
            "",
            "摘要、决策、行动项、风险和待确认事项来自下方会议纪要与行动项结构化内容；所有无法在转录中确认的内容应以待确认处理。",
            "",
            "## 会议纪要",
            "",
            minutes_md.lstrip("# ").strip() if minutes_md else "（无纪要内容）",
            "",
            "## 决策 / 行动项 / 风险 / 待确认事项",
            "",
            "详见会议纪要和行动项章节中的结构化表格；引用时应优先使用表格中的来源时间点和依据摘录。",
            "",
            "## 转录文本",
            "",
            transcript_md.lstrip("# ").strip() if transcript_md else "（无转录）",
            "",
            "## 一手转录来源引用",
            "",
            "- 文件：`transcript-latest.md`",
            "- 引用粒度：时间戳 / 说话人 / 内容行",
        ])
        if actions_md:
            lines.extend(["", "---", "", "## 行动项（辅助参考）", "", actions_md.lstrip("# ").strip()])

    lines.append("")
    return "\n\n".join(lines)
