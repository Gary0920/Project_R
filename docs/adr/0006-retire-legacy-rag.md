# ADR 0006: Retire Legacy Project_R RAG

Date: 2026-05-28

## Status

Accepted

## Context

Project_R currently has a development-stage RAG stack based on:

- `backend/knowledge_base/wiki/`
- `core/wiki_router.py`
- `core/rag_engine.py`
- `backend/vector_store/`

This stack was useful as a local tracer bullet, but Project_R has not been formally deployed or used as the company knowledge base. Gary has decided to replace the knowledge core with GBrain and to re-feed source files into Project_R/GBrain rather than preserve the old RAG outputs.

## Decision

Do not migrate the legacy Project_R RAG stack into the GBrain architecture.

When GBrain `company-wiki` is implemented, the legacy Wiki Router / Chroma / vector-store path can be retired directly. The old `knowledge_base/wiki` contents and old vector indexes are not the authority for the new system and should not be treated as a fallback layer.

The new company knowledge base will be generated from source files placed under:

```text
backend/workspace_data/global/company-wiki/raw/
```

GBrain-derived Markdown will be written to:

```text
backend/workspace_data/global/company-wiki/derived/
```

## Consequences

- Implementation can avoid maintaining two RAG systems in parallel.
- Old Chroma/vector-store compatibility code should not influence the new adapter design.
- Existing `knowledge_base/wiki` files may be kept temporarily as development reference, but not as a production source of truth.
- Knowledge review writes that currently target `knowledge_base/wiki` need to move to the GBrain `company-wiki` path during implementation.
- Any valuable knowledge should be reintroduced through Project_R-managed raw source files, not by trusting legacy vector indexes.
