from __future__ import annotations

import logging
from typing import Callable

from app.shared.web_search.service import (
    WEB_SEARCH_SKILL_NAME,
    WebSearchResponse,
    format_web_search_prompt,
    search_web,
    web_results_to_sources,
)


def maybe_run_web_search(
    query: str,
    enabled: bool,
    *,
    source_start_index: int = 1,
    logger: logging.Logger | None = None,
    runner: Callable[[str], WebSearchResponse] | None = None,
) -> tuple[list[dict], str, dict | None]:
    if not enabled:
        return [], "", None
    response = runner(query) if runner else run_web_search_skill(query, logger=logger)
    sources = web_results_to_sources(response)
    prompt = format_web_search_prompt(response, start_index=source_start_index)
    return sources, prompt, web_search_trace(response, len(sources))


def run_web_search_skill(query: str, *, logger: logging.Logger | None = None) -> WebSearchResponse:
    try:
        return search_web(query)
    except Exception as exc:  # pragma: no cover - defensive guard for provider bugs.
        if logger:
            logger.warning("web search skill failed unexpectedly", exc_info=True)
        return WebSearchResponse(
            query=" ".join(query.split()).strip(),
            provider="unknown",
            warnings=[f"unexpected_error:{type(exc).__name__}"],
        )


def web_search_trace(response: WebSearchResponse, result_count: int) -> dict:
    return {
        "enabled": True,
        "skill_name": WEB_SEARCH_SKILL_NAME,
        "query": response.query,
        "provider": response.provider,
        "result_count": result_count,
        "warnings": response.warnings,
    }


def web_search_context_extra(trace: dict | None) -> dict:
    if not trace:
        return {}
    return {"web_search": trace}
