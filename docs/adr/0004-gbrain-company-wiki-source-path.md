# ADR 0004: GBrain Company Wiki Source Path

Date: 2026-05-28

## Status

Superseded by [ADR 0019: GBrain-Ready Preprocessing Source Repos](0019-gbrain-ready-preprocessing-source-repos.md)

## Context

Project_R will manage company knowledge source files under `backend/workspace_data/`. For the first GBrain integration slice, the company-wide source is `company-wiki` with this shape:

```text
backend/workspace_data/global/company-wiki/
  raw/
  derived/
  manifests/
```

There are two possible layouts:

1. Use `derived/` directly as the GBrain source repo.
2. Create a separate GBrain repo and copy/sync Project_R-derived Markdown into it.

Gary prefers fewer backend folders for the same knowledge-source concept, and Project_R already owns `workspace_data/` as the source-management root.

## Decision

Use `backend/workspace_data/global/company-wiki/derived/` directly as the GBrain `company-wiki` source repo.

This was the first GBrain MVP layout. ADR 0019 replaces it for the later architecture: GBrain source repos point to `backend/workspace_data/_preprocessed/.../gbrain-ready/`, while user source-file folders no longer contain `derived/`.

Project_R will not create a separate GBrain repository for `company-wiki` and then synchronize `derived/` into it.

## Consequences

- The filesystem is easier to understand: `raw/` is original input, `derived/` is GBrain-readable Markdown, `manifests/` is Project_R ingestion state.
- There is no extra copy step between Project_R and GBrain for the first global source.
- GBrain source registration should point directly at `derived/`.
- Project_R must treat `derived/` carefully: it is generated/reviewable knowledge, not a casual manual-edit folder.
- If versioning is needed, the next decision is whether `derived/` itself becomes a Git repo or whether Project_R stores equivalent version/audit metadata in `manifests/` and the database.
