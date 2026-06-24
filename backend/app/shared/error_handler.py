"""FastAPI exception handlers that map Project_R domain errors to HTTP.

Registered in main.py via register_error_handlers(app).
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.shared.errors import (
    AuthenticationError,
    AuthorizationError,
    GBrainServiceError,
    LLMServiceError,
    ProjectRError,
    ResourceNotFoundError,
    ValidationError,
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
)

logger = logging.getLogger(__name__)

# ── Mapping table ───────────────────────────────────────────────────────────
# Each entry: (exception_type, http_status, default_detail)
# Order matters: more specific types must come before their base type.

_STATUS_MAP: list[tuple[type[ProjectRError], int, str]] = [
    (WorkspaceNotFoundError, 404, "工作区不存在"),
    (WorkspaceAccessDeniedError, 403, "你尚未加入该项目"),
    (ResourceNotFoundError, 404, "资源不存在"),
    (AuthenticationError, 401, "认证失败"),
    (AuthorizationError, 403, "权限不足"),
    (ValidationError, 422, "请求参数无效"),
    (LLMServiceError, 503, "AI 服务暂时不可用"),
    (GBrainServiceError, 502, "知识库服务暂时不可用"),
]


def _to_json_response(exc: ProjectRError, status: int, default_detail: str) -> JSONResponse:
    detail = str(exc) or default_detail
    return JSONResponse(
        status_code=status,
        content={"detail": detail},
    )


async def _project_r_error_handler(request: Request, exc: ProjectRError) -> JSONResponse:
    for exc_type, status, default_detail in _STATUS_MAP:
        if isinstance(exc, exc_type):
            # LLM errors carry extra info for the caller
            if isinstance(exc, LLMServiceError) and exc.retryable:
                logger.warning("LLM service error (retryable): %s", exc)
            return _to_json_response(exc, status, default_detail)

    # Fallback for unclassified ProjectRError subclasses
    logger.exception("Unhandled ProjectRError: %s", exc)
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content={"detail": "内部错误"},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register domain-error → HTTP mappers on the FastAPI app.

    Call once during startup, before any routes are served.
    """
    app.add_exception_handler(ProjectRError, _project_r_error_handler)
