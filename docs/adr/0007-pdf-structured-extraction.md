# ADR 0007: PDF Structured Extraction Before GBrain Ingest

Date: 2026-05-29

## Status

Accepted

## Context

Project_R tested real company samples in `backend/workspace_data/global/company-wiki/raw/`, including two PDF standards. The first implementation used `pypdf` to extract text and wrote the result directly into GBrain-derived Markdown.

That proved the pipeline can move PDF content into GBrain, but the resulting Markdown was not acceptable as company knowledge: standard documents, tables, multi-column layouts, headers, footers, and clause numbering became fragmented and hard to read. Feeding that output directly into GBrain would make retrieval find low-quality chunks.

## Decision

PDF files must not enter `company-wiki/derived/` through plain text extraction by default.

PDFs should first enter a structured extraction workflow that can use model-assisted document understanding, OCR, or vision when needed. The output should be reviewed Markdown, organized around useful knowledge units such as:

- source document and page references
- section or clause headings
- key requirements
- parameters and tables
- risks, exceptions, and applicability
- review status

All generated extraction output must follow the Project_R language policy `bilingual_zh_en_aligned`: Chinese and English must coexist and express the same facts. Neither language may contain facts omitted from the other. When translation or extraction confidence is insufficient, the item belongs in review questions instead of becoming a single-language fact.

Only the structured Markdown output should be imported into the GBrain source used for `/query`.

Plain text PDF extraction may still be used as a diagnostic or intermediate artifact, but it is not accepted as a default knowledge-ingest path.

## Consequences

- `core/gbrain_ingest.py` skips PDFs unless PDF structured extraction is explicitly enabled.
- `core/pdf_structured_extraction.py` implements the MVP path: full text extraction as intermediate evidence, optional PNG sidecar vision pages, model-assisted synthesis, and `pending_review` output.
- PDF structured output carries `language_policy: bilingual_zh_en_aligned` in frontmatter and manifest.
- Existing PDF pages imported during the first real-sample test are treated as validation artifacts, not as accepted long-term knowledge quality.
- PDF ingestion will cost more time and possibly LLM/vision tokens, but it protects the knowledge base from unreadable source material.
- The admin GBrain panel should show PDFs as pending extraction, failed extraction, or awaiting review instead of silently marking them indexed.
- `/query` should prefer reviewed structured Markdown over raw extraction output.
