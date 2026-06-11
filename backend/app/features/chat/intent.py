from dataclasses import dataclass
from enum import StrEnum


class IntentType(StrEnum):
    CHAT = "chat"
    RAG_QUERY = "rag_query"
    DOCUMENT_GENERATION = "document_generation"
    SKILL_TRIGGER = "skill_trigger"


@dataclass(frozen=True)
class IntentResult:
    intent: IntentType
    confidence: float
    reason: str


def classify_intent(text: str) -> IntentResult:
    normalized = text.strip().lower()
    if not normalized:
        return IntentResult(IntentType.CHAT, 0.3, "empty message fallback")
    return IntentResult(IntentType.CHAT, 0.5, "explicit routing only")
