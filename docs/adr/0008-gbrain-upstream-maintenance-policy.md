# ADR 0008: GBrain Upstream Maintenance Policy

Date: 2026-05-30

## Status

Accepted

## Context

Project_R uses GBrain as the knowledge-base core. Runtime integration is through the Project_R backend adapter, which starts and calls GBrain as an external HTTP/MCP/CLI service.

During the first Ollama + `mxbai-embed-large` validation, the downloaded local copy in `reference/gbrain-master` was also changed directly. The current local copy is not an independent Git repository, fork, or submodule, so direct edits inside it are easy to lose during an upstream refresh and hard to audit during later upgrades.

The confirmed local upstream-source changes are:

- `src/core/ai/recipes/ollama.ts`: add fixed embedding dimensions and a conservative local batch cap for Ollama embeddings.
- `src/core/chunkers/recursive.ts`: lower the default Markdown chunk hard cap from 6000 chars to 400 chars for local Ollama embedding stability.
- `src/core/think/*` / search paths: carry source scope through `think` gather, hybrid search, takes, and graph traversal.
- OAuth client registration: allow local GBrain CLI/provider registration of agent-bound clients with tool/source/slug/budget bindings.
- Subagent brain tools: carry the OAuth-bound source id into subagent `search/get_page/put_page` calls instead of falling back to `default`.
- AI gateway tool loop: wrap provider-neutral JSON Schema with AI SDK `jsonSchema()` and convert provider-neutral tool results into AI SDK v6 `tool` messages for DeepSeek gateway-loop execution.

## Decision

Project_R treats GBrain as an external upstream component, not as Project_R-owned application code.

Project_R must not silently modify GBrain upstream source files. The preferred order is:

1. Use GBrain native configuration, commands, recipes, operations, skills, schema, or jobs.
2. Add Project_R adapter logic around GBrain for permissions, source scope, audit, paths, manifests, review, and UI.
3. Improve Project_R-generated `derived/` Markdown structure so GBrain receives better source material.
4. Propose a change upstream to GBrain when the requirement is generally useful.
5. Only if the requirement cannot be met above, maintain an explicit Project_R GBrain patch or fork.

Any unavoidable GBrain source change must be recorded as either:

- a patch file under `patches/gbrain/`, or
- a named Project_R-maintained fork/submodule with pinned upstream version and patch notes.

The current six local changes are recorded under `patches/gbrain/` and are treated as temporary Project_R patches until replaced by upstream configuration, an upstream PR, or a maintained fork:

- `0001-ollama-local-embedding-limits.patch`
- `0002-recursive-chunker-local-ollama-cap.patch`
- `0003-think-source-scope-gather-and-takes.patch`
- `0004-agent-bound-oauth-client-registration.patch`
- `0005-subagent-tool-source-scope.patch`
- `0006-chat-tool-json-schema-wrapper.patch`

## Consequences

- Updating GBrain must include a patch audit: compare upstream, re-apply or retire Project_R patches, then run GBrain sync/query regression checks.
- Future agents must not edit `reference/gbrain-master` without adding or updating a patch record and documenting why adapter/config changes were insufficient.
- GBrain upgrade work can be reviewed as a small upstream-delta problem instead of an unknown vendored-code diff.
- If the patch set grows beyond a small number of files, Project_R should switch from patch files to a proper fork/submodule strategy.
