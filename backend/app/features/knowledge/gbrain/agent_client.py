from __future__ import annotations

import json
import time
from typing import Any

from .settings import GBRAIN_CITATION_FIXER_TOOLS


class GBrainAgentClientMixin:
    def _agent_gate(self) -> dict[str, Any] | None:
        if not self.settings.agent_enabled:
            return {
                "status": "disabled",
                "error": "GBRAIN_AGENT_ENABLED is not true",
            }
        if not self.settings.agent_oauth_client_id or not self.settings.agent_oauth_client_secret:
            return {
                "status": "oauth_required",
                "error": "GBRAIN_AGENT_OAUTH_CLIENT_ID and GBRAIN_AGENT_OAUTH_CLIENT_SECRET are required",
            }
        return None

    def _get_agent_bearer_token(self) -> tuple[str | None, dict[str, Any] | None]:
        gate = self._agent_gate()
        if gate:
            return None, gate
        if self._agent_oauth_access_token and time.time() < self._agent_oauth_expires_at:
            return self._agent_oauth_access_token, None
        token_response = self._fetch_oauth_token(
            client_id=self.settings.agent_oauth_client_id,
            client_secret=self.settings.agent_oauth_client_secret,
            scope=self.settings.agent_oauth_scope,
            token_auth_method=self.settings.agent_oauth_token_auth_method,
        )
        if token_response.get("status") != "ok":
            return None, token_response
        token = str(token_response.get("access_token") or "")
        if not token:
            return None, {
                "status": "invalid_response",
                "error": "GBrain agent OAuth token response did not include access_token",
            }
        try:
            expires_in = int(token_response.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600
        self._agent_oauth_access_token = token
        self._agent_oauth_expires_at = time.time() + max(30, expires_in - 30)
        return token, None

    def submit_agent(
        self,
        *,
        prompt: str,
        allowed_tools: list[str] | tuple[str, ...] | None = None,
        allowed_slug_prefixes: list[str] | tuple[str, ...] | None = None,
        max_turns: int = 20,
        model: str | None = None,
        queue: str | None = None,
    ) -> dict[str, Any]:
        token, gate_error = self._get_agent_bearer_token()
        if gate_error:
            return gate_error
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "max_turns": max(1, min(int(max_turns or 20), 100)),
        }
        selected_model = model or self.settings.agent_model
        if selected_model:
            arguments["model"] = selected_model
        if allowed_tools:
            arguments["allowed_tools"] = [str(tool).strip() for tool in allowed_tools if str(tool).strip()]
        if allowed_slug_prefixes:
            arguments["allowed_slug_prefixes"] = [
                prefix.strip() for prefix in allowed_slug_prefixes if isinstance(prefix, str) and prefix.strip()
            ]
        if queue:
            arguments["queue"] = queue.strip()
        response = self._call_mcp_tool(
            "submit_agent",
            arguments,
            bearer_token=token,
            timeout_seconds=self.settings.agent_timeout_seconds,
        )
        return {
            **response,
            "method": "mcp",
            "job_type": "subagent",
        }

    def submit_citation_fixer(
        self,
        *,
        page_slug: str | None = None,
        review_id: int | None = None,
        notes: str | None = None,
        allowed_slug_prefixes: list[str] | tuple[str, ...] | None = None,
        max_turns: int = 30,
        model: str | None = None,
        queue: str | None = None,
    ) -> dict[str, Any]:
        prompt = self._build_citation_fixer_prompt(
            page_slug=page_slug,
            review_id=review_id,
            notes=notes,
        )
        return self.submit_agent(
            prompt=prompt,
            allowed_tools=self.settings.citation_fixer_tools,
            allowed_slug_prefixes=allowed_slug_prefixes,
            max_turns=max_turns,
            model=model,
            queue=queue,
        )

    def _build_citation_fixer_prompt(
        self,
        *,
        page_slug: str | None,
        review_id: int | None,
        notes: str | None,
    ) -> str:
        scope = f"Only inspect and patch the GBrain page `{page_slug}`." if page_slug else (
            "Scan the bound source for citation-format issues in a small, safe batch."
        )
        review_line = f"Project_R KnowledgeReview id: {review_id}." if review_id is not None else (
            "No Project_R review id was provided."
        )
        notes_line = notes.strip() if isinstance(notes, str) and notes.strip() else "No extra operator notes."
        return (
            "Use the GBrain `citation-fixer` skill.\n"
            f"{scope}\n"
            f"{review_line}\n"
            f"Operator notes: {notes_line}\n\n"
            "Follow the upstream citation-fixer contract exactly: fix malformed citation formatting, "
            "resolve deterministic links only when a configured resolver/API provides the data, flag missing or "
            "uncitable facts, and never invent citations or delete unsupported facts. Report pages scanned, "
            "citations found, issues fixed, tweet links resolved, remaining gaps, and any pages left for human review."
        )

    def agent_status(self) -> dict[str, Any]:
        oauth_configured = bool(self.settings.agent_oauth_client_id and self.settings.agent_oauth_client_secret)
        missing_tools = [
            tool for tool in GBRAIN_CITATION_FIXER_TOOLS if tool not in set(self.settings.citation_fixer_tools)
        ]
        binding_submit_verified = bool(self.settings.agent_binding_submit_verified)
        inline_execution_verified = bool(self.settings.agent_inline_execution_verified)
        execution_verified = bool(self.settings.agent_execution_verified)
        status = "disabled"
        if self.settings.agent_enabled and not oauth_configured:
            status = "oauth_required"
        elif self.settings.agent_enabled and oauth_configured and not execution_verified:
            status = "configured_unverified"
        elif self.settings.agent_enabled and oauth_configured and execution_verified:
            status = "ready"
        worker = self._agent_worker_status()
        selected_model = self.settings.agent_model.strip()
        model_requires_gateway_loop = bool(
            selected_model
            and not selected_model.lower().startswith(("anthropic:", "claude:", "claude-", "anthropic-"))
        )
        gateway_loop_status = "not_required"
        if model_requires_gateway_loop:
            gateway_loop_status = "verified" if self.settings.agent_gateway_loop_verified else "not_checked"
        return {
            "status": status,
            "enabled": self.settings.agent_enabled,
            "oauth_configured": oauth_configured,
            "client_configured": bool(self.settings.agent_oauth_client_id),
            "scope": self.settings.agent_oauth_scope,
            "model_configured": bool(self.settings.agent_model),
            "model_requires_gateway_loop": model_requires_gateway_loop,
            "gateway_loop_status": gateway_loop_status,
            "binding_submit_verified": binding_submit_verified,
            "inline_execution_verified": inline_execution_verified,
            "execution_verified": execution_verified,
            "execution_ready": status == "ready",
            "citation_fixer_tools": list(self.settings.citation_fixer_tools),
            "citation_fixer_missing_tools": missing_tools,
            "binding_requirements": {
                "scope": "agent",
                "tools": list(GBRAIN_CITATION_FIXER_TOOLS),
                "source_bound": True,
                "slug_prefix_bound": True,
                "budget_bound": True,
            },
            "binding_status": (
                "execution_verified"
                if execution_verified
                else "inline_execution_verified"
                if inline_execution_verified
                else "submit_verified"
                if binding_submit_verified
                else "not_verified"
            ),
            "worker": worker,
            "timeout_seconds": self.settings.agent_timeout_seconds,
        }

    def _agent_worker_status(self) -> dict[str, Any]:
        config_path = self.settings.home_path / ".gbrain" / "config.json"
        if not config_path.exists():
            return {
                "engine": None,
                "config_exists": False,
                "persistent_worker_supported": None,
                "mode": "unknown",
                "reason": "gbrain config not found",
            }
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "engine": None,
                "config_exists": True,
                "persistent_worker_supported": None,
                "mode": "unknown",
                "reason": f"gbrain config unreadable: {exc}",
            }
        engine = str(config.get("engine") or "").strip().lower() or None
        if engine == "pglite":
            return {
                "engine": engine,
                "config_exists": True,
                "persistent_worker_supported": False,
                "mode": "inline_only",
                "reason": "GBrain jobs worker daemon is Postgres-only; PGLite uses inline/follow execution.",
            }
        if engine in {"postgres", "postgresql"}:
            return {
                "engine": engine,
                "config_exists": True,
                "persistent_worker_supported": True,
                "mode": "persistent_worker_supported",
                "reason": None,
            }
        return {
            "engine": engine,
            "config_exists": True,
            "persistent_worker_supported": None,
            "mode": "unknown",
            "reason": "unknown GBrain engine",
        }
