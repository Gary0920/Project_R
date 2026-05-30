# ADR 0011: Automatic Extractor Routing by File Type and Complexity

Date: 2026-05-30

## Status

Accepted

## Context

Project_R now owns raw-file extraction before Markdown is handed to GBrain. Different source files need different extraction paths: readable text can be handled cheaply by a text model, while scanned PDFs, screenshots, drawings, tables-as-images, audio, video, and email threads need specialized handling.

Gary confirmed that users should not manually choose API keys during knowledge ingestion. The software should identify the file type and extraction difficulty, then route to the correct backend model profile or pending-capability state.

## Decision

Project_R must run an automatic extraction classifier before a raw file is processed for GBrain.

The classifier records at least these dimensions in the manifest:

- `source_scope`: `company`, `project`, `private`, or future scoped source.
- `file_kind`: `text`, `markdown`, `docx`, `pdf`, `image`, `audio`, `video`, `email`, `archive`, or `unknown`.
- `extraction_complexity`: `simple_text`, `complex_layout`, `vision_required`, `transcription_required`, `email_thread_required`, `unsupported`, or `unknown`.
- `extractor_profile`: the backend model profile or workflow selected for extraction, such as `deepseek_text`, `mimo_vision`, `transcription`, or `pending_extractor_capability`.
- `classifier_reason`: a short non-secret explanation of why the route was selected.

Users trigger ingestion, but they do not choose API keys. Project_R selects a backend `model_profile`; the profile is mapped server-side to the provider and API key group. API keys remain in backend configuration and must not be exposed to the frontend, logs, manifests, or GBrain user-facing state.

Default routing:

| Source file condition | Default route |
|---|---|
| Markdown, TXT, clean DOCX text, readable transcript, readable email body | DeepSeek text extraction profile |
| Clean/simple PDF with selectable text and reliable reading order | PDF text extraction as evidence, then DeepSeek text extraction profile |
| Complex PDF: scanned/image PDF, multi-column layout, tables/forms, drawings/spec sheets, fragmented extraction order, key information in layout or images | MiMo vision/layout extraction profile |
| Image, screenshot, table image, photo, drawing snapshot | MiMo vision extraction profile |
| Audio or video with no transcript | transcription workflow, then DeepSeek meeting/knowledge extraction after transcript exists |
| Audio or video where visual frames carry knowledge | transcription workflow plus MiMo key-frame/visual extraction when implemented |
| Email thread or mailbox export | email parser workflow plus DeepSeek text extraction; attachments are classified recursively |
| Target knowledge type whose extractor is not implemented yet | `pending_extractor_capability` |

Simple versus complex PDF is decided by diagnostics, not by file extension alone. Useful signals include selectable-text ratio, extracted text length per page, page count, table/column patterns, image/scanned-page ratio, sidecar PNG presence, and whether plain text extraction preserves a readable order.

Administrators may configure default model profiles and future overrides, but ordinary users should see only ingestion status and results, not provider keys or low-level routing controls.

## Consequences

- Project ingestion becomes one-click for users while still using the right model path for each file.
- Token cost is controlled because DeepSeek is used for text-first material and MiMo is reserved for vision/layout-heavy material.
- Manifest records become the audit trail for why a file was processed, skipped, or marked pending.
- Project_R now has a formal classifier module for project one-click ingest. Future work should harden the classifier with regression cases for image quality, fragmented PDFs, long media, nested attachments, and unsupported business attachment types.
- GBrain continues to receive only Project_R-produced Markdown and remains responsible for sync, chunking, embeddings, query, think, citations, graph, timeline, jobs, and maintenance after Markdown exists.
