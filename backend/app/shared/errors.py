"""Project_R domain exception hierarchy.

These exceptions describe *what went wrong* in domain terms, without
tying themselves to any particular transport (HTTP, WebSocket, etc.).
FastAPI exception handlers in main.py map them to HTTP responses.
"""

from __future__ import annotations


class ProjectRError(Exception):
    """Base for all Project_R domain errors."""


# ── Authentication / Authorization ──────────────────────────────────────────

class AuthenticationError(ProjectRError):
    """The callerʼs identity could not be verified (expired / missing token)."""


class AuthorizationError(ProjectRError):
    """The authenticated caller lacks permission for the requested action."""


# ── Workspace access ────────────────────────────────────────────────────────

class WorkspaceNotFoundError(ProjectRError):
    """The requested workspace does not exist (or has been archived).

    IMPORTANT: this must always map to HTTP 404.  Never collapse it into a
    403, because that would leak the existence of a hidden workspace.
    """


class WorkspaceAccessDeniedError(ProjectRError):
    """The authenticated user is not allowed to enter this workspace.

    Maps to HTTP 403.  The detail message should NOT reveal whether the
    workspace exists.
    """


# ── Resource errors ─────────────────────────────────────────────────────────

class ResourceNotFoundError(ProjectRError):
    """A requested resource (session, file, message, …) does not exist."""


# ── LLM / external service ──────────────────────────────────────────────────

class LLMServiceError(ProjectRError):
    """An upstream LLM provider returned an error or is unreachable.

    The ``retryable`` flag hints whether the caller should back off and retry.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class GBrainServiceError(ProjectRError):
    """The GBrain knowledge engine returned an error."""


# ── Validation ──────────────────────────────────────────────────────────────

class ValidationError(ProjectRError):
    """Client input failed business-rule validation."""
