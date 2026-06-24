from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .adapter_utils import mcp_tool_invocation_succeeded
from .paths import (
    _gbrain_path_migration_status,
    _warn_if_source_repo_scope_mismatch,
    customer_source_registration_plan,
    ensure_customer_gbrain_environment,
    ensure_project_gbrain_environment,
    project_source_registration_plan,
    resolve_gbrain_source_paths,
)


class GBrainSourceManagerMixin:
    def latest_ingest_manifest(self) -> dict[str, Any]:
        source_paths = resolve_gbrain_source_paths("company", settings=self.settings)
        manifest_path = source_paths.manifests / "company-wiki-ingest-manifest.json"
        legacy_manifest_path = self.settings.manifests_path / "company-wiki-ingest-manifest.json"
        if not manifest_path.exists() and legacy_manifest_path.exists():
            manifest_path = legacy_manifest_path
        if not manifest_path.exists():
            return {
                "exists": False,
                "path": str(manifest_path.resolve()),
                "legacy_path": str(legacy_manifest_path.resolve()),
                "summary": {"total": 0, "compiled": 0, "skipped": 0, "failed": 0},
                "items": [],
            }
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "exists": True,
                "path": str(manifest_path.resolve()),
                "error": str(exc),
                "summary": {"total": 0, "compiled": 0, "skipped": 0, "failed": 0},
                "items": [],
            }
        payload["exists"] = True
        payload["path"] = str(manifest_path.resolve())
        payload["legacy_path"] = str(legacy_manifest_path.resolve())
        return payload

    def source_registration_plan(self) -> dict[str, Any]:
        source_paths = resolve_gbrain_source_paths("company", settings=self.settings)
        return {
            "source_id": self.settings.company_source_id,
            "name": self.settings.company_source_name,
            "path": str(source_paths.gbrain_ready.resolve()),
            "gbrain_ready_path": str(source_paths.gbrain_ready.resolve()),
            "legacy_derived_path": str((source_paths.legacy_derived or self.settings.derived_path).resolve()),
            "migration_status": _gbrain_path_migration_status(source_paths.gbrain_ready, source_paths.legacy_derived),
            "federated": True,
            "operator_command": (
                f"gbrain sources add {self.settings.company_source_id} "
                f"--path {source_paths.gbrain_ready.resolve()} "
                f"--name \"{self.settings.company_source_name}\" --federated"
            ),
        }

    def list_sources(self) -> dict[str, Any]:
        response = self._call_mcp_tool("sources_list", {"include_archived": True})
        if response["status"] != "ok":
            return response
        result = response.get("result")
        sources = result.get("sources", []) if isinstance(result, dict) else []
        return {
            "status": "ok",
            "sources": sources,
        }

    def company_source_status(self) -> dict[str, Any]:
        plan = self.source_registration_plan()
        return self._source_status(
            self.settings.company_source_id,
            Path(plan["path"]).resolve(),
            plan,
        )

    def source_status(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        return self._source_status(
            str(registration_plan["source_id"]),
            Path(registration_plan["path"]).resolve(),
            registration_plan,
        )

    def ensure_source(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        before = self.source_status(registration_plan)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": True,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for source registration",
                },
                "source": before,
            }
        registration = self.register_source(registration_plan)
        after = self.source_status(registration_plan) if registration.get("ok") else before
        return {
            "ok": bool(registration.get("ok")),
            "registration": registration,
            "source": after,
        }

    def register_source(self, registration_plan: dict[str, Any]) -> dict[str, Any]:
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": registration_plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            str(registration_plan["source_id"]),
            "--path",
            str(registration_plan["path"]),
            "--name",
            str(registration_plan["name"]),
        ]
        if registration_plan.get("federated"):
            args.append("--federated")
        else:
            args.append("--no-federated")
        result = self._run_cli_exclusive(args, reason=f"register_source:{registration_plan['source_id']}", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": registration_plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_registered_source(
        self,
        registration_plan: dict[str, Any],
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        return self.sync_source(
            source_id=str(registration_plan["source_id"]),
            repo_path=Path(registration_plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def project_source_registration_plan(self, workspace: Any) -> dict[str, Any]:
        return project_source_registration_plan(workspace)

    def customer_source_registration_plan(self, workspace: Any) -> dict[str, Any]:
        return customer_source_registration_plan(workspace)

    def project_source_status(self, workspace: Any) -> dict[str, Any]:
        if str(getattr(workspace, "workspace_kind", "project") or "project") != "project":
            return {
                "status": "not_project",
                "registered": False,
                "expected": None,
                "source": {},
            }
        plan = project_source_registration_plan(workspace)
        return self._source_status(
            plan["source_id"],
            Path(plan["path"]).resolve(),
            plan,
        )

    def ensure_project_source(self, workspace: Any) -> dict[str, Any]:
        environment = ensure_project_gbrain_environment(workspace, self.settings)
        before = self.project_source_status(workspace)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": environment.get("ok"),
                "environment": environment,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "environment": environment,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for source registration",
                },
                "source": before,
            }
        registration = self.register_project_source(workspace)
        after = self.project_source_status(workspace) if registration.get("ok") else before
        return {
            "ok": bool(environment.get("ok") and registration.get("ok")),
            "environment": environment,
            "registration": registration,
            "source": after,
        }

    def register_project_source(self, workspace: Any) -> dict[str, Any]:
        plan = project_source_registration_plan(workspace)
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            plan["source_id"],
            "--path",
            plan["path"],
            "--name",
            plan["name"],
            "--no-federated",
        ]
        result = self._run_cli_exclusive(args, reason="register_project_source", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_project_source(
        self,
        workspace: Any,
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        plan = project_source_registration_plan(workspace)
        return self.sync_source(
            source_id=plan["source_id"],
            repo_path=Path(plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def customer_source_status(self, workspace: Any) -> dict[str, Any]:
        if str(getattr(workspace, "workspace_kind", "") or "") != "customer":
            return {
                "status": "not_customer",
                "registered": False,
                "expected": None,
                "source": {},
            }
        plan = customer_source_registration_plan(workspace)
        return self._source_status(
            plan["source_id"],
            Path(plan["path"]).resolve(),
            plan,
        )

    def ensure_customer_source(self, workspace: Any) -> dict[str, Any]:
        environment = ensure_customer_gbrain_environment(workspace, self.settings)
        before = self.customer_source_status(workspace)
        if before.get("registered") and before.get("path_matches"):
            return {
                "ok": environment.get("ok"),
                "environment": environment,
                "registration": {"status": "already_registered", "ok": True},
                "source": before,
            }
        if before.get("status") in {"auth_required", "disabled", "not_configured"}:
            return {
                "ok": False,
                "environment": environment,
                "registration": {
                    "status": "skipped",
                    "ok": False,
                    "error": before.get("error") or "GBrain service is not ready for customer source registration",
                },
                "source": before,
            }
        registration = self.register_customer_source(workspace)
        after = self.customer_source_status(workspace) if registration.get("ok") else before
        return {
            "ok": bool(environment.get("ok") and registration.get("ok")),
            "environment": environment,
            "registration": registration,
            "source": after,
        }

    def register_customer_source(self, workspace: Any) -> dict[str, Any]:
        plan = customer_source_registration_plan(workspace)
        cli_file = self.settings.cli_workdir / "src" / "cli.ts"
        if not cli_file.exists():
            return {
                "ok": False,
                "status": "cli_unavailable",
                "error": f"GBrain CLI not found at {cli_file}",
                "expected": plan,
            }
        args = [
            self.settings.bun_executable,
            "src/cli.ts",
            "sources",
            "add",
            plan["source_id"],
            "--path",
            plan["path"],
            "--name",
            plan["name"],
            "--no-federated",
        ]
        result = self._run_cli_exclusive(args, reason="register_customer_source", timeout=120)
        return {
            "ok": result.get("status") == "ok",
            "status": result.get("status"),
            "expected": plan,
            "result": result.get("result"),
            "error": result.get("error"),
            "service_restart": result.get("service_restart"),
        }

    def sync_customer_source(
        self,
        workspace: Any,
        *,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        plan = customer_source_registration_plan(workspace)
        return self.sync_source(
            source_id=plan["source_id"],
            repo_path=Path(plan["path"]),
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
        )

    def _source_status(
        self,
        source_id: str,
        expected_path: Path,
        registration_plan: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._call_mcp_tool("sources_status", {"id": source_id})
        if response["status"] != "ok":
            return {
                "status": response["status"],
                "registered": False,
                "expected": registration_plan,
                "error": response.get("error"),
                "http_status": response.get("http_status"),
            }

        result = response.get("result")
        source = result if isinstance(result, dict) else {}
        local_path = source.get("local_path")
        path_matches = False
        if isinstance(local_path, str) and local_path:
            try:
                path_matches = os.path.normcase(str(Path(local_path).resolve())) == os.path.normcase(str(expected_path))
            except OSError:
                path_matches = False

        registered = source.get("id") == source_id
        status = "registered" if registered and path_matches else "path_mismatch" if registered else "missing"

        # D0 Fix: normalize stale / incorrect GBrain return values
        if isinstance(source, dict):
            # Normalize clone_state: corrupted → available when the dir is usable
            clone_state = str(source.get("clone_state") or "").lower()
            if clone_state == "corrupted":
                source["clone_state"] = "available"

            # Fix page_count: count actual .md files in gbrain-ready/ (recursive)
            try:
                if expected_path.is_dir():
                    md_files = list(expected_path.rglob("*.md"))
                    if md_files:
                        source["page_count"] = len(md_files)
                    else:
                        source["page_count"] = 0
                else:
                    source["page_count"] = 0
            except OSError:
                pass

        return {
            "status": status,
            "registered": registered,
            "path_matches": path_matches,
            "expected": registration_plan,
            "source": source,
        }

    def sync_source(
        self,
        *,
        source_id: str | None = None,
        repo_path: Path | None = None,
        full: bool = False,
        no_pull: bool = True,
        no_embed: bool = False,
    ) -> dict[str, Any]:
        """Sync a GBrain source repo.

        When source_id is omitted or matches the company source, repo_path
        defaults to the company gbrain-ready directory.  For project or
        customer sources you MUST pass repo_path explicitly — use
        sync_project_source() / sync_customer_source() which do this for you.
        """
        source_id = source_id or self.settings.company_source_id

        if repo_path is None:
            if source_id != self.settings.company_source_id:
                raise ValueError(
                    f"repo_path is required for non-company source "
                    f"'{source_id}'. Use sync_project_source() or "
                    f"sync_customer_source() instead, or pass repo_path "
                    f"explicitly."
                )
            repo_path = resolve_gbrain_source_paths(
                "company", settings=self.settings
            ).gbrain_ready

        repo = repo_path.resolve()

        # Safety net: if source_id and repo_path were both passed explicitly,
        # warn (but don't block) when the repo looks like it belongs to a
        # different scope than the source_id.
        _warn_if_source_repo_scope_mismatch(
            source_id=source_id, repo_path=repo, settings=self.settings
        )

        mcp_response = self._call_mcp_tool(
            "sync_brain",
            {
                "repo": str(repo),
                "full": full,
                "no_pull": no_pull,
                "no_embed": no_embed,
            },
        )
        if mcp_tool_invocation_succeeded(mcp_response):
            return {**mcp_response, "method": "mcp"}
        return self._sync_source_via_cli(
            source_id=source_id,
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
            mcp_response=mcp_response,
        )

    def _sync_source_via_cli(
        self,
        *,
        source_id: str,
        full: bool,
        no_pull: bool,
        no_embed: bool,
        mcp_response: dict[str, Any],
    ) -> dict[str, Any]:
        return self._transport.sync_source_via_cli(
            source_id=source_id,
            full=full,
            no_pull=no_pull,
            no_embed=no_embed,
            mcp_response=mcp_response,
            probe_service_health=self._probe_service_health,
            stop_http_service=self.stop_http_service,
            start_http_service=self.start_http_service,
            clear_stale_pglite_state=self._clear_stale_pglite_state,
        )

    def _run_cli_exclusive(self, args: list[str], *, reason: str, timeout: int) -> dict[str, Any]:
        return self._transport.run_cli_exclusive(
            args,
            reason=reason,
            timeout=timeout,
            probe_service_health=self._probe_service_health,
            stop_http_service=self.stop_http_service,
            start_http_service=self.start_http_service,
            clear_stale_pglite_state=self._clear_stale_pglite_state,
        )

    def _run_gbrain_cli(self, args: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
        return self._transport.run_gbrain_cli(args, env, timeout)

    def _run_sync_cli(self, args: list[str], env: dict[str, str]) -> dict[str, Any]:
        return self._transport.run_sync_cli(args, env)
