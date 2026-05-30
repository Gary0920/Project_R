# ADR 0010: Source-Scoped Knowledge Ingest Review Policy

Date: 2026-05-30

## Status

Accepted

## Context

Project_R has three different places where knowledge-like files can appear:

- administrator-maintained company knowledge
- user private-space attachments
- project workspace files

Treating every generated Markdown page as a central `KnowledgeReview` item would slow the product down and blur ownership. Gary has confirmed a simpler responsibility model: the person or space that owns the knowledge also owns the ingestion responsibility.

## Decision

Knowledge ingestion review policy is scoped by where the file is submitted.

Administrator backend knowledge entry is administrator-approved by definition. Admin-entered or admin-triggered company knowledge does not need an additional review queue step. It can be extracted to Markdown, written into the company `derived/` source, synced to GBrain, audited, and reported back to the administrator.

User private-space attachments must not be ingested into the company knowledge base. They may be used as session or private context, but they do not flow into `company-wiki` and do not become shared company knowledge.

Project workspace files are project-scoped knowledge only. They must sync only to that project's GBrain source, not to the company public source. The user who clicks the project file-panel ingestion action is responsible for triggering ingestion; no administrator review is required for the default project-source path.

Project_R should provide a clear one-click action in the project file panel for ingesting eligible project files into the project knowledge source. The product definition of "not-yet-indexed project files" includes all target knowledge-bearing file types in the project workspace: text files, Markdown, DOCX, PDFs including complex PDFs, audio/video files, images/screenshots, emails, and future supported business attachments. A file stops being not-yet-indexed only after Project_R has successfully extracted it into source-scoped Markdown and GBrain has synced that Markdown into the current project source.

In the first implementation, this action should ingest all currently processable, not-yet-indexed files in the current project rather than only user-selected files. The button should show the pending count, for example "Ingest 12 unindexed files". If a file type is in the product definition but its extractor is not implemented yet, Project_R should keep it visible as pending/unsupported-capability rather than treating it as out of scope. After ingestion completes or fails, Project_R should notify the user who clicked the action.

## Consequences

- The default chain becomes faster: project files do not wait for company administrators before becoming usable inside the project.
- Company shared knowledge remains controlled by administrators rather than being polluted by user or project uploads.
- Project sources become the permission boundary for project files. Project_R must continue enforcing project membership before query and ingestion actions.
- The knowledge review queue is reserved for company-level user feedback, explicit promotion into company knowledge, corrections, and exceptional cases rather than every project upload.
- Future UI must distinguish "ingest into this project" from "promote to company knowledge"; the second action, if added, needs a separate confirmation and review policy.
- As of 2026-05-31, project-source MVPs exist for complex-PDF/drawing extraction, image/screenshot understanding, MP4 audio-first automatic transcription, long-media segmentation, speaker/terminology refinement, `.eml` email-thread extraction, and `.eml` attachment recursion. Remaining gaps include confidence scoring, absolute timestamp backlinks, region-level image citations, batch email-thread merging, file preview UI, and formal reusable extractor Skills.
- Ingestion buttons should trigger Project_R's automatic extractor routing. Ordinary users should not select provider keys; routing is decided by file type, extraction complexity, source scope, and backend `model_profile` policy.
