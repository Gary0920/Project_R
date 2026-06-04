# ADR 0019: GBrain-Ready Preprocessing Source Repos

Date: 2026-06-04

## Status

Accepted

Supersedes the `derived/` source-repo layout from [ADR 0004](0004-gbrain-company-wiki-source-path.md) and amends [ADR 0009](0009-pr-owned-extraction-to-gbrain-markdown.md), [ADR 0010](0010-source-scoped-knowledge-ingest-review-policy.md), and [ADR 0011](0011-automatic-extractor-routing-by-file-type.md).

## Context

The first GBrain integration used `workspace_data/.../derived/` inside each source-material directory as the GBrain source repo. That worked for MVP validation, but it mixed user-visible source files, generated Markdown, process artifacts, manifests, and GBrain source concerns in the same area.

Gary confirmed on 2026-06-04 that user source-file folders should contain only user-managed originals. Project_R should preprocess source files into GBrain-friendly Markdown, but ordinary users do not need to see process files or generated source Markdown in the file panel. GBrain source repos should point at a separate preprocessed output area.

## Decision

Project_R will separate source files from GBrain-ready preprocessing outputs.

User source-file directories remain the source-of-record for originals and must not contain `derived/` in the new architecture.

Project_R writes preprocessing artifacts under:

```text
backend/workspace_data/_preprocessed/
├── company/
│   └── company-wiki/
│       ├── gbrain-ready/
│       ├── runs/
│       └── manifests/
├── project/
│   └── {brand}/{workspace_id}-{project_slug}/
│       ├── gbrain-ready/
│       ├── runs/
│       └── manifests/
└── customer/
    └── {workspace_id}-{customer_slug}/
        ├── gbrain-ready/
        ├── runs/
        └── manifests/
```

- `gbrain-ready/` is the GBrain source repo.
- `runs/{preprocess_run_id}/` stores process files, extracted text, rendered pages, transcripts, intermediate model outputs, diagnostics, and retry evidence.
- `manifests/` stores source-file mapping, hashes, preprocess status, model profile, prompt version, output paths, errors, user actions, and GBrain sync results.

Each click on "录入" creates one `preprocess_run_id`. The run covers the current file-panel path or the explicitly selected single file. Folder ingest is recursive and requires a second confirmation that shows path, child-folder inclusion, file counts, file-type counts, and high-cost model/transcription warnings.

Process files are retained by run. Final GBrain-ready Markdown uses stable paths derived from the source file so repeated preprocessing updates the same page instead of creating duplicate GBrain pages.

Deleting a source file, moving it to trash, or permanently deleting it does not automatically delete GBrain-ready Markdown and does not remove knowledge from GBrain. Source-file deletion only updates manifest state. GBrain-ready cleanup requires an explicit administrator knowledge/source cleanup action.

Changing a source file hash does not automatically rerun preprocessing. Project_R marks the file as `source_changed` / `needs_repreprocess`. A user or administrator must explicitly trigger ingest before the stable GBrain-ready Markdown is updated and GBrain is synced again.

Successful preprocessing may automatically trigger GBrain sync for the current source. It must not automatically trigger expensive or mutating post-processing such as Entity Enrichment, graph merge, citation-fixer, contradiction probe, maintain, or dream cycle.

## Consequences

- User file panels stay clean: they show original source files and ingest status, not generated Markdown or process files.
- GBrain source registration points at stable `gbrain-ready/` repos.
- Project_R manifests become the bridge between source files, preprocessing runs, GBrain-ready pages, and sync state.
- Citation stability improves because GBrain sees stable Markdown paths across reprocessing runs.
- Source-file cleanup no longer risks accidental knowledge-base deletion.
- Existing code and docs that assume `workspace_data/.../derived/` is the source repo must be migrated or treated as legacy MVP behavior.
