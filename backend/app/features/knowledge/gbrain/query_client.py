from __future__ import annotations

from typing import Any


class GBrainQueryClientMixin:
    def query(
        self,
        query: str,
        *,
        source_id: str | None = None,
        limit: int = 5,
        expand: bool = False,
        detail: str = "medium",
    ) -> dict[str, Any]:
        return self._call_mcp_tool(
            "query",
            {
                "query": query,
                "source_id": source_id or self.settings.company_source_id,
                "limit": limit,
                "expand": expand,
                "detail": detail,
            },
        )

    def think(
        self,
        query: str,
        *,
        source_id: str | None = None,
        rounds: int | None = None,
        model: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error

        arguments: dict[str, Any] = {
            "question": query,
            "rounds": max(1, rounds or self.settings.think_rounds),
        }
        selected_model = model or self.settings.think_model
        if selected_model:
            arguments["model"] = selected_model
        if since:
            arguments["since"] = since
        if until:
            arguments["until"] = until

        response = self._call_mcp_tool(
            "think",
            arguments,
            bearer_token=token,
            timeout_seconds=self.settings.think_timeout_seconds,
        )
        return {
            **response,
            "method": "mcp",
            "source_id": target_source_id,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
        }

    def get_page(self, slug: str, *, include_deleted: bool = False) -> dict[str, Any]:
        arguments: dict[str, Any] = {"slug": slug}
        if include_deleted:
            arguments["include_deleted"] = True
        return self._call_mcp_tool("get_page", arguments)

    def graph_context(
        self,
        slug: str,
        *,
        source_id: str | None = None,
        depth: int = 2,
        direction: str = "both",
        link_type: str | None = None,
        include_timeline: bool = True,
        include_backlinks: bool = True,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error
        clean_slug = str(slug or "").strip().removesuffix(".md")
        if not clean_slug:
            return {"status": "invalid_request", "error": "slug is required"}
        traversal_arguments: dict[str, Any] = {
            "slug": clean_slug,
            "depth": max(1, min(int(depth or 2), 10)),
            "direction": direction if direction in {"in", "out", "both"} else "both",
        }
        if link_type:
            traversal_arguments["link_type"] = str(link_type).strip()
        response: dict[str, Any] = {
            "status": "ok",
            "method": "mcp",
            "source_id": target_source_id,
            "slug": clean_slug,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
            "traverse_graph": self._call_mcp_tool(
                "traverse_graph",
                traversal_arguments,
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
        }
        if include_timeline:
            response["timeline"] = self._call_mcp_tool(
                "get_timeline",
                {"slug": clean_slug},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            )
        if include_backlinks:
            response["backlinks"] = self._call_mcp_tool(
                "get_backlinks",
                {"slug": clean_slug},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            )
        return response

    def schema_context(
        self,
        *,
        source_id: str | None = None,
        orphan_limit: int = 20,
    ) -> dict[str, Any]:
        target_source_id = source_id or self.settings.company_source_id
        token, gate_error, credentials = self._get_think_bearer_token(target_source_id)
        if gate_error:
            return gate_error
        response: dict[str, Any] = {
            "status": "ok",
            "method": "mcp",
            "source_id": target_source_id,
            "source_scope": {
                "verified": self.settings.think_source_scope_verified,
                "allowed_sources": list((credentials or {}).get("allowed_sources") or self._think_allowed_sources()),
                "scope_is_token_bound": True,
                "credential_source": (credentials or {}).get("source"),
            },
            "active_schema_pack": self._call_mcp_tool(
                "get_active_schema_pack",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_stats": self._call_mcp_tool(
                "schema_stats",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_graph": self._call_mcp_tool(
                "schema_graph",
                {},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
            "schema_review_orphans": self._call_mcp_tool(
                "schema_review_orphans",
                {"limit": max(1, min(int(orphan_limit or 20), 200))},
                bearer_token=token,
                timeout_seconds=max(self.settings.timeout_seconds, 15.0),
            ),
        }
        return response
