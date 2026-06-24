"""KnowledgeSources singleton for chat feature.

Previously this instance lived in api/chat.py, which forced internal.py
to use deferred imports from the API layer to access it.
"""

from __future__ import annotations

from app.features.knowledge.sources import KnowledgeSources

KNOWLEDGE_SOURCES = KnowledgeSources()
