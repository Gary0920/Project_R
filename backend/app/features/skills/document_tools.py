from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.features.documents.generation import create_generated_file
from app.features.documents.formats import normalize_output_format
from app.features.skills.runner import SkillDefinition
from models.skill_run import SkillRun


DOCUMENT_RENDER_TOOL = "project_r.document.render"


def render_document_tool(
    *,
    db: Session,
    run: SkillRun,
    skill: SkillDefinition,
    step: dict[str, Any],
    inputs: dict[str, Any],
    generated_root: Path,
) -> dict[str, Any]:
    output_format = _resolve_output_format(skill, step)
    content = _resolve_content(step, inputs)
    title = _resolve_title(skill, step, inputs)
    payload = create_generated_file(
        db,
        run.user_id,
        run.session_id,
        title,
        content,
        output_format=output_format,
        generated_files_root=generated_root,
    )
    run.generated_file_id = payload["id"]
    db.flush()
    return {"generated_file": payload}


def default_document_tools() -> dict[str, Any]:
    return {DOCUMENT_RENDER_TOOL: render_document_tool}


def _resolve_output_format(skill: SkillDefinition, step: dict[str, Any]) -> str:
    explicit = str(step.get("format") or "").strip()
    if explicit:
        return normalize_output_format(explicit).key
    for output in skill.outputs:
        if str(output.get("type") or "") == "file":
            return normalize_output_format(str(output.get("format") or "docx")).key
    return "docx"


def _resolve_content(step: dict[str, Any], inputs: dict[str, Any]) -> str:
    field = str(step.get("content_field") or step.get("input_field") or "").strip()
    if field:
        value = inputs.get(field)
        if value is None or str(value).strip() == "":
            raise ValueError(f"Document render content field is empty: {field}")
        return str(value)
    for value in inputs.values():
        if isinstance(value, str) and value.strip():
            return value
    raise ValueError("Document render requires a non-empty text input")


def _resolve_title(skill: SkillDefinition, step: dict[str, Any], inputs: dict[str, Any]) -> str:
    title_template = str(step.get("title_template") or "").strip()
    if title_template:
        return _format_template(title_template, inputs)
    title_field = str(step.get("title_field") or "").strip()
    if title_field and inputs.get(title_field):
        return str(inputs[title_field])
    return skill.display_name or skill.name


def _format_template(template: str, inputs: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return str(inputs.get(key) or "")

    return re.sub(r"\{([^{}]+)\}", replace, template).strip() or "Project_R 生成文件"
