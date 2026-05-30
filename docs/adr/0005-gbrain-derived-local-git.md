# ADR 0005: Local Git for GBrain Derived Markdown

Date: 2026-05-28

## Status

Accepted

## Context

GBrain treats Markdown/frontmatter as the system of record and the database as a derived cache. Project_R's first GBrain source, `company-wiki`, uses:

```text
backend/workspace_data/global/company-wiki/
  raw/
  derived/
  manifests/
```

`derived/` is the GBrain-readable Markdown source repo. These files are generated or curated from Project_R-managed originals, and they need a practical way to compare changes, audit generated knowledge, and roll back bad transformations.

`backend/workspace_data/` is ignored by the Project_R main Git repository, so runtime knowledge files should not be committed to the application codebase.

## Decision

Initialize `backend/workspace_data/global/company-wiki/derived/` as a local Git repository.

This Git repository is local-only by default. It is used for audit, diff, and rollback of generated/reviewable Markdown. It must not be treated as the Project_R application repository, and it must not be configured to push to GitHub by default.

## Consequences

- Project_R and the GBrain adapter can commit derived Markdown changes after successful ingest/update steps.
- Commit messages should include enough traceability to connect a change to Project_R manifests, source files, ingestion jobs, or review actions.
- The Project_R main repository remains clean because `backend/workspace_data/` is ignored.
- Git history complements, but does not replace, Project_R manifests, audit logs, and knowledge-review records.
- If company backup or remote synchronization is needed later, it must be a separate explicit decision with access-control and retention rules.
- GBrain `sources_status` may report `clone_state=corrupted` for this local-only repo because its clone diagnostic expects an `origin` remote. That diagnostic is not treated as registration failure for Project_R-managed local sources; path match, source id, and sync behavior are the decisive checks.
