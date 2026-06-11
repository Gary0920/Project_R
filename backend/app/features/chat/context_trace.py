from __future__ import annotations

from typing import Any


def build_context_trace(
    *,
    session: Any,
    req: Any | None,
    attachments: list[Any],
    sources: list[dict],
    intent: Any,
    provider: str | None,
    model: str | None,
    requested_model: str | None = None,
    reduce_knowledge_context: bool = False,
    extra: dict | None = None,
) -> dict:
    system_prompt = getattr(req, "system_prompt", None) if req else None
    return {
        "schema_version": 1,
        "workspace_id": session.workspace_id,
        "intent": intent.value if hasattr(intent, "value") else str(intent),
        "model": {
            "provider": provider,
            "model": model,
            "requested_model": requested_model,
            "thinking": bool(getattr(req, "thinking", False)) if req else False,
            "web_search": bool(getattr(req, "web_search", False)) if req else False,
        },
        "prompt": {
            "selected_prompt_id": getattr(req, "selected_prompt_id", None) if req else None,
            "selected_skill": getattr(req, "selected_skill", None) if req else None,
            "system_prompt_provided": bool(system_prompt and system_prompt.strip()),
            "system_prompt_preview": trace_preview(system_prompt, 220),
        },
        "attachments": [attachment_trace_dict(attachment) for attachment in attachments],
        "knowledge": {
            "reduce_context": reduce_knowledge_context,
            "source_count": len(sources),
            "sources": [source_trace_dict(source, index) for index, source in enumerate(sources[:12], start=1)],
        },
        **(extra or {}),
    }


def attachment_trace_dict(attachment: Any) -> dict:
    return {
        "id": attachment.id,
        "session_id": attachment.session_id,
        "message_id": attachment.message_id,
        "name": attachment.original_name,
        "content_type": attachment.content_type,
        "size": attachment.size,
    }


def source_trace_dict(source: dict, index: int) -> dict:
    return {
        "index": index,
        "file": source.get("file"),
        "source_title": source.get("source_title"),
        "section_path": source.get("section_path"),
        "score": source.get("score"),
        "source_file": source.get("source_file"),
        "source_locator": source.get("source_locator"),
    }


def safe_trace_list(value: object, *, limit: int = 6, item_limit: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()
        if text:
            result.append(text[:item_limit])
    return result


def gbrain_think_trace(think_result: dict) -> dict:
    metadata = think_result.get("metadata") if isinstance(think_result.get("metadata"), dict) else {}
    gaps = safe_trace_list(metadata.get("gaps"))
    conflicts = safe_trace_list(metadata.get("conflicts"))
    warnings = safe_trace_list(metadata.get("warnings"))
    diagnostics = metadata.get("diagnostics") if isinstance(metadata.get("diagnostics"), dict) else {}
    return {
        "source_id": think_result.get("source_id"),
        "status": think_result.get("status"),
        "model": think_result.get("model"),
        "gap_count": len(metadata.get("gaps") if isinstance(metadata.get("gaps"), list) else []),
        "conflict_count": len(metadata.get("conflicts") if isinstance(metadata.get("conflicts"), list) else []),
        "warning_count": len(metadata.get("warnings") if isinstance(metadata.get("warnings"), list) else []),
        "gaps": gaps,
        "conflicts": conflicts,
        "warnings": warnings,
        "diagnostics": {
            "trace_id": diagnostics.get("trace_id"),
            "pipeline": diagnostics.get("pipeline"),
        },
    }


def skill_context_extra(skill_response: dict) -> dict:
    skill_run = skill_response.get("skill_run") or {}
    skill = skill_run.get("skill") or {}
    return {
        "skill": {
            "run_id": skill_run.get("id"),
            "skill_name": skill_run.get("skill_name"),
            "display_name": skill.get("display_name"),
            "status": skill_run.get("status"),
            "missing_input_count": len(skill_run.get("missing_inputs") or []),
        },
        "generated_file": generated_file_context(skill_response.get("generated_file")),
    }


def generated_file_context(generated_file: dict | None) -> dict | None:
    if not generated_file:
        return None
    return {
        "id": generated_file.get("id"),
        "filename": generated_file.get("filename"),
        "mime_type": generated_file.get("mime_type"),
        "download_url": generated_file.get("download_url"),
    }


def trace_preview(value: str | None, limit: int = 160) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
