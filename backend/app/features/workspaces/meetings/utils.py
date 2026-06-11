from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from app.features.workspaces.meetings.markdown import escape_markdown_table_cell
from app.features.workspaces.schemas import DetectedSpeaker, SpeakerMapItem, TermCorrectionItem
from app.shared.time.utils import serialize_datetime_utc


MEETING_TYPE_META_FILENAME = ".meeting-meta.json"
SUPPORTED_MEDIA_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mov", ".avi", ".wmv", ".mkv", ".webm"}


def read_meeting_meta(folder_dir: Path) -> dict[str, str]:
    meta_path = folder_dir / MEETING_TYPE_META_FILENAME
    if not meta_path.exists():
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def write_meeting_meta(folder_dir: Path, *, topic: str, meeting_time: str | None, meeting_type: str) -> None:
    meta_path = folder_dir / MEETING_TYPE_META_FILENAME
    data: dict[str, str] = {
        "topic": topic,
        "meeting_type": meeting_type,
    }
    if meeting_time:
        data["meeting_time"] = meeting_time
    meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def next_version_number(dir_path: Path, prefix: str) -> int:
    highest = 0
    if not dir_path.exists():
        return 1
    pattern = re.compile(rf"^{re.escape(prefix)}-v(\d+)\.md$", re.IGNORECASE)
    for child in dir_path.iterdir():
        if child.is_file():
            match = pattern.match(child.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def read_file_safe(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def meeting_run_lock_path(root: Path, folder_dir: Path) -> Path:
    return folder_dir / ".project-r-meeting-processing.lock"


def acquire_meeting_run_lock(root: Path, folder_dir: Path, *, operation: str, user_id: int) -> Path:
    lock_path = meeting_run_lock_path(root, folder_dir)
    if lock_path.exists():
        raise HTTPException(status_code=409, detail="当前会议已有处理中任务，请等待完成后再操作")
    lock_path.write_text(
        json.dumps(
            {
                "operation": operation,
                "user_id": user_id,
                "created_at": serialize_datetime_utc(datetime.now(timezone.utc)),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return lock_path


def release_meeting_run_lock(lock_path: Path | None) -> None:
    if lock_path and lock_path.exists():
        try:
            lock_path.unlink()
        except OSError:
            pass


def parse_table_row_count(markdown_text: str, section_header: str) -> int:
    lines = markdown_text.split("\n")
    in_section = False
    data_count = 0
    for line in lines:
        if section_header in line and line.startswith("|"):
            in_section = True
            continue
        if in_section:
            if "---" in line:
                continue
            if not line.startswith("|"):
                break
            data_count += 1
    return data_count


def parse_speakers_from_transcript(transcript_text: str) -> list[DetectedSpeaker]:
    speakers: list[DetectedSpeaker] = []
    in_section = False
    for line in transcript_text.split("\n"):
        if "说话人概览" in line and "##" in line:
            in_section = True
            continue
        if in_section:
            if "## " in line and "说话人概览" not in line:
                break
            if line.startswith("|") and "---" not in line and "说话人ID" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:
                    speakers.append(DetectedSpeaker(
                        speaker_id=parts[0],
                        display_name=parts[1] if len(parts) > 1 else parts[0],
                        ratio=parts[3] if len(parts) > 3 else "—",
                        duration=parts[4] if len(parts) > 4 else "—",
                    ))
    return speakers


def speaker_timeline_rows(transcript_text: str, limit: int = 30) -> list[str]:
    rows: list[str] = []
    in_section = False
    for line in transcript_text.splitlines():
        if line.startswith("## ") and "说话人时间轴" in line:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|") or "---" in line or "行号" in line:
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 4:
            rows.append(
                f"| {escape_markdown_table_cell(parts[0])} | {escape_markdown_table_cell(parts[1])} | "
                f"{escape_markdown_table_cell(parts[2])} | {escape_markdown_table_cell(parts[3])} |"
            )
        if len(rows) >= limit:
            break
    return rows


def build_speaker_map_markdown(
    speakers: list[SpeakerMapItem],
    author: str,
    timestamp: str,
    timeline_rows: list[str] | None = None,
) -> str:
    rows = "\n".join(
        f"| {escape_markdown_table_cell(s.speaker_id)} | {escape_markdown_table_cell(s.display_name)} | "
        f"已映射 | {escape_markdown_table_cell(author)} | {timestamp} |"
        for s in speakers
    )
    timeline = "\n".join(timeline_rows or ["| — | — | — | — |"])
    return (
        "# 说话人映射\n\n"
        "## 映射状态\n\n"
        f"- 修改人：{author}\n"
        f"- 修改时间：{timestamp}\n"
        f"- 映射状态：已确认\n\n"
        "## 说话人映射表\n\n"
        "| 说话人ID | 显示名称 | 映射状态 | 修改人 | 修改时间 |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n\n"
        "## 时间轴辅助信息\n\n"
        "| 行号 | 时间点 | 说话人ID | 内容摘要 |\n"
        "|---|---|---|---|\n"
        f"{timeline}\n"
    )


def build_term_corrections_markdown(corrections: list[TermCorrectionItem], timestamp: str) -> str:
    rows = "\n".join(
        f"| {escape_markdown_table_cell(c.original)} | {escape_markdown_table_cell(c.corrected)} | "
        f"{escape_markdown_table_cell(c.type)} | {c.confidence} | 已确认 |"
        for c in corrections
    )
    return (
        "# 术语纠错\n\n"
        f"- 修改时间：{timestamp}\n"
        f"- 纠错数：{len(corrections)}\n\n"
        "## 术语纠错表\n\n"
        "| 原识别 | 建议修正 | 类型 | 置信度 | 状态 |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024) if path.exists() else 0.0


def duration_minutes(path: Path) -> int | None:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return max(1, round(float(proc.stdout.strip()) / 60))
    except Exception:
        return None


def estimate_media_info(size_bytes: int, filename: str) -> dict:
    size_mb_value = size_bytes / (1024 * 1024)
    is_audio_only = Path(filename).suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    if is_audio_only:
        est_minutes = max(1, round(size_mb_value / 1.0))
    else:
        est_minutes = max(1, round(size_mb_value / 8.0))
    is_long = est_minutes > 30
    seg_count = max(1, (est_minutes + 299) // 300)
    warnings: list[str] = []
    if is_long:
        warnings.append(f"媒体时长超过 30 分钟（预估 {est_minutes} 分钟），将自动分段转录（{seg_count} 段）")
    if size_mb_value > 500:
        warnings.append("文件超过 500 MB，转录时间较长，请耐心等待")
    cost_note = f"预估 {est_minutes} 分钟，将使用 MiMo V2.5 模型转录。{'长视频将自动分段处理。' if is_long else ''}"
    return {
        "size_mb": round(size_mb_value, 1),
        "estimated_duration_minutes": est_minutes,
        "is_long_media": is_long,
        "estimated_segments": seg_count,
        "estimated_cost_note": cost_note,
        "warnings": warnings,
    }
