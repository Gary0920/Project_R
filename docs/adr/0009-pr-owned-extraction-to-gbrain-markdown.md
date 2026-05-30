# ADR 0009: Project_R Owns Raw-File Extraction Before GBrain

Date: 2026-05-30

## Status

Accepted

## Context

Project_R is integrating GBrain as its knowledge-base core. Earlier planning used a broad "GBrain-native first" rule for ingestion, which left ambiguity about whether GBrain should directly process raw PDFs, recordings, screenshots, emails, and other original business files.

Gary has confirmed a tighter product boundary: Project_R should own the agent-facing extraction skills for original files. GBrain should not be treated as the first component that receives arbitrary raw files.

## Decision

Project_R owns the raw-file-to-reviewed-Markdown stage.

Project_R will store original files, choose the correct extraction skill, call the configured model provider, generate structured Markdown, and write manifests. Whether the output needs a review queue depends on the source scope: administrator-entered company knowledge can go straight to the company source, project workspace files go straight to the project source after a user-triggered ingest action, and private-space attachments never flow into the company source.

GBrain receives the Markdown that Project_R has produced under the relevant `derived/` source path. After that point, GBrain owns the knowledge-base core work: source sync/import, chunking, embeddings, query, think, citations, graph, timeline, maintain, jobs, contradiction checks, and other post-Markdown knowledge operations.

Model usage follows Project_R's existing backend LLM provider configuration:

- DeepSeek is the default extraction model for text-only original content such as Markdown, TXT, DOCX text, transcripts, email bodies, and other readable text.
- MiMo is the default extraction model for formats DeepSeek cannot reliably understand directly, including visual PDFs, scanned PDFs, screenshots, images, tables embedded as images, and layout-heavy documents.
- API keys are managed through Project_R backend model/provider configuration. They are not exposed to the frontend and are not duplicated as user-managed GBrain keys.
- Users do not choose API keys during ingestion. Project_R classifies file type and extraction complexity, then chooses the backend `model_profile` or pending-capability state as defined in `docs/adr/0011-automatic-extractor-routing-by-file-type.md`.

GBrain ingestion, media, meeting, voice, recipe, and Skillify ideas may still be used as references for extraction design, but Project_R production extraction skills remain the owning boundary unless a later ADR explicitly changes this.

The source-scoped review and ownership policy is defined in `docs/adr/0010-source-scoped-knowledge-ingest-review-policy.md`.

## Consequences

- The Project_R-to-GBrain chain is easier to reason about: `raw original file -> Project_R extraction skill -> source-scoped Markdown -> GBrain source sync -> query/think`.
- GBrain no longer needs to be made responsible for every original file type before Project_R can progress.
- Extraction quality, model choice, token cost, review status, and retry policy are controlled in Project_R, close to users, permissions, projects, audit logs, and admin UI.
- GBrain remains an upstream component for knowledge operations after Markdown exists, which reduces the need to patch GBrain raw-ingestion internals.
- The old "GBrain-native first" rule is narrowed: it still applies to GBrain-native search, think, citation, graph, maintenance, jobs, schema, and post-Markdown knowledge evolution, but not to Project_R raw-file extraction.
- Existing Project_R extraction MVPs for PDF structured extraction and meeting transcript sidecar extraction now become the model for future extractor skills rather than temporary bridges to GBrain-native raw ingestion.
