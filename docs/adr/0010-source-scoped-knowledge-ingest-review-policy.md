# ADR 0010: Source-Scoped Knowledge Ingest Review Policy

Date: 2026-05-30

## Status

Accepted, amended by [ADR 0019: GBrain-Ready Preprocessing Source Repos](0019-gbrain-ready-preprocessing-source-repos.md)

## Context

Project_R has three different places where knowledge-like files can appear:

- administrator-maintained company knowledge
- user private-space attachments
- project workspace files

Treating every generated Markdown page as a central `KnowledgeReview` item would slow the product down and blur ownership. Gary has confirmed a simpler responsibility model: the person or space that owns the knowledge also owns the ingestion responsibility.

## Decision

Knowledge ingestion review policy is scoped by where the file is submitted.

Administrator backend knowledge entry is administrator-approved by definition. Admin-entered or admin-triggered company knowledge does not need an additional review queue step. It can be extracted to Markdown, written into the company GBrain-ready source repo, synced to GBrain, audited, and reported back to the administrator. The MVP used the company `derived/` source; ADR 0019 changes the target path to `_preprocessed/.../gbrain-ready/`.

User private-space attachments must not be ingested into the company knowledge base. They may be used as session or private context, but they do not flow into `company-wiki` and do not become shared company knowledge.

Project workspace files are project-scoped knowledge only. They must sync only to that project's GBrain source, not to the company public source. The user who clicks the project file-panel ingestion action is responsible for triggering ingestion; no administrator review is required for the default project-source path.

Project_R should provide a clear ingestion action in the project file panel for ingesting eligible project files into the project knowledge source. The product definition of "not-yet-indexed project files" includes all target knowledge-bearing file types in the project workspace: text files, Markdown, DOCX, PDFs, audio/video files, images/screenshots, emails, and future supported business attachments. A file stops being not-yet-indexed only after Project_R has successfully extracted it into source-scoped GBrain-ready Markdown and GBrain has synced that Markdown into the current project source.

The 2026-05 MVP ingested all currently processable files in the project. The 2026-06-04 product decision narrows the default scope: the file-panel "录入" action processes the currently opened path recursively and must show a secondary confirmation explaining child-folder recursion, file counts, file types, high-cost model/transcription risks, and permission scope. File right-click menus should also offer "录入此文件". If a file type is in the product definition but its extractor is not implemented yet, Project_R should keep it visible as `pending_capability` rather than treating it as out of scope. After ingestion completes or fails, Project_R should notify the user who clicked the action.

## Consequences

- The default chain becomes faster: project files do not wait for company administrators before becoming usable inside the project.
- Company shared knowledge remains controlled by administrators rather than being polluted by user or project uploads.
- Project sources become the permission boundary for project files. Project_R must continue enforcing project membership before query and ingestion actions.
- The knowledge review queue is reserved for company-level user feedback, explicit promotion into company knowledge, corrections, and exceptional cases rather than every project upload.
- Future UI must distinguish "ingest into this project" from "promote to company knowledge"; the second action, if added, needs a separate confirmation and review policy.
- As of 2026-05-31, project-source MVPs exist for complex-PDF/drawing extraction, image/screenshot understanding, MP4 audio-first automatic transcription, long-media segmentation, speaker/terminology refinement, `.eml` email-thread extraction, and `.eml` attachment recursion. Remaining gaps include confidence scoring, absolute timestamp backlinks, region-level image citations, batch email-thread merging, file preview UI, and formal reusable extractor Skills.
- Ingestion buttons should trigger Project_R's automatic extractor routing. Ordinary users should not select provider keys; routing is decided by file type, extraction complexity, source scope, and backend `model_profile` policy.
- Source-file deletion must not delete GBrain-ready Markdown or GBrain knowledge. A source modification after successful sync marks the file as `source_changed` / `needs_repreprocess`; it does not automatically reprocess or delete existing knowledge.
- Project permissions: system administrators and workspace administrators may trigger recursive folder ingestion and single-file ingestion; ordinary project members may only ingest their own uploaded single file. Customer ingestion is restricted to system administrators and customer workspace administrators. Company global ingestion is system-administrator only.
