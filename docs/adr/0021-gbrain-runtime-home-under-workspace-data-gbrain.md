# ADR 0021: GBrain Runtime Home Under workspace_data/_gbrain

Status: Accepted

Date: 2026-06-05

## Context

Project_R previously initialized GBrain with `GBRAIN_HOME=backend/workspace_data/global/company-wiki`, which caused GBrain runtime files such as `.gbrain/`, PGLite brain data, audit files, service logs, and historical database backups to live beside company knowledge source files.

ADR 0019 already separates user source files from GBrain-ready Markdown source repos under `_preprocessed/.../gbrain-ready/`. The remaining issue is that GBrain runtime state also needs a dedicated home outside any business source folder.

## Decision

GBrain runtime home is fixed at:

```text
backend/workspace_data/_gbrain/
```

GBrain may create and manage its internal `.gbrain/` directory under that root:

```text
backend/workspace_data/_gbrain/.gbrain/
```

`backend/workspace_data/global/company-wiki/` is only the company knowledge source-file area. It must not contain `.gbrain/`, PGLite brain files, runtime audit files, service logs, or temporary GBrain databases.

Business source repos remain source-scoped:

```text
backend/workspace_data/_preprocessed/company/company-wiki/gbrain-ready/
backend/workspace_data/_preprocessed/project/{BRAND}/{workspace_id}-{slug}/gbrain-ready/
backend/workspace_data/_preprocessed/customer/{workspace_id}-{slug}/gbrain-ready/
```

## Consequences

- Resetting GBrain knowledge data can wipe `_gbrain/.gbrain/brain.pglite*` without touching source files.
- Source files, preprocessed Markdown, and GBrain runtime data now have separate ownership boundaries.
- Source registrations and OAuth clients are runtime state; after a hard reset they should be recreated by Project_R source ensure routines.
- Startup scripts, `.env`, tests, and agent docs must use `_gbrain` as the default `GBRAIN_HOME`.
