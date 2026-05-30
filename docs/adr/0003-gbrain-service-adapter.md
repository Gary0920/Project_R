# ADR 0003: GBrain Service Adapter

Date: 2026-05-28

## Status

Accepted

## Context

Project_R will use GBrain as the knowledge-base core. The integration can be done by shelling out to the GBrain CLI, embedding GBrain as a TypeScript library, or running GBrain as a separate HTTP/MCP service and calling it through a backend adapter.

Project_R is a Python FastAPI desktop-backed business app. It owns users, permissions, workspaces/projects, raw-file lifecycle, audit logs, knowledge review, and the UI. GBrain owns source indexing, search/query/think, citations, graph, jobs, maintenance, skills, and schema behavior.

## Decision

Project_R first-version production behavior will call GBrain as an independent HTTP/MCP service through a Project_R backend service-account adapter.

The GBrain CLI is allowed for development-time setup, diagnostics, manual operations, and emergency troubleshooting. It is not the main production business-call path. Project_R will not directly depend on GBrain internal database tables or embed GBrain as an in-process TypeScript library inside FastAPI.

Health and source status checks also use this rule: `/health/gbrain` may probe GBrain `/health` without auth, but `sources_list` and `sources_status` must go through HTTP/MCP with a Project_R service bearer token. When the token is absent, the adapter reports `auth_required` instead of guessing source state.

For GBrain `think`, Project_R uses a stricter rule than ordinary service-account query. Because GBrain HTTP legacy bearer tokens default to `source_id='default'`, and because `think` source scope is token/context-bound rather than a normal `source_id` parameter, Project_R may only call `think` through a source-scoped OAuth client after the source-scope retrieval chain has been verified. Until then, the adapter must fail closed with an auditable `source_scope_unverified` style status.

As of 2026-05-30, Project_R patch `patches/gbrain/0003-think-source-scope-gather-and-takes.patch` completes the upstream code-level retrieval chain for `think`: `runThink()` forwards scope to `runGather()`, and gather forwards it to hybrid page search, takes keyword/vector search, and graph traversal; PGLite/Postgres takes search SQL now filters by `pages.source_id`. A real `company-wiki` source-scoped OAuth client has also been created and verified through service-level MCP `think` with token-bound source scope. GBrain `think` now uses `deepseek:deepseek-chat` in this local Project_R setup and has produced a citation-bearing answer for `company-wiki`; `backend/scripts/gbrain_think_regression.py` fixes the first repeatable service-level check. This still does not enable `think` by default, because promotion to the default answer layer requires project-source OAuth/scope verification, broader answer/citation/gap regression, and frontend gap/conflict presentation.

## Consequences

- Project_R can keep Python/FastAPI business code isolated from GBrain internals.
- GBrain upgrades should mainly affect the adapter layer.
- Project_R remains responsible for enforcing user/workspace/source permissions before every GBrain call.
- Every GBrain query/import/sync call should carry explicit allowed source scope and be auditable in Project_R.
- GBrain `think` must not be silently promoted to the default answer layer until source-scoped OAuth, upstream retrieval scoping, answer quality, citations, gaps, and conflicts have been verified for `company-wiki` and project sources.
- Local development may still use CLI commands to initialize, inspect, or repair the GBrain service.
- For PGLite brains, running the HTTP service can hold the active database connection; concurrent local CLI reads may time out. Do not build production health or source-state checks on sidecar CLI calls.
