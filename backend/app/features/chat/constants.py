"""Chat feature constants shared across API and feature layers.

These constants were previously defined in api/chat.py, which created
a circular dependency when app.features.chat.internal imported them.
Moving them here breaks the cycle.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

# ── Backend root ───────────────────────────────────────────────────────────

# constants.py is at backend/app/features/chat/constants.py
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ── Paths ──────────────────────────────────────────────────────────────────

MESSAGE_FEEDBACK_ROOT = Path(
    os.getenv("MESSAGE_FEEDBACK_PATH", str(BACKEND_ROOT / "feedback_data" / "message_ratings"))
)

GENERATED_FILES_ROOT = Path(
    os.getenv("GENERATED_FILES_PATH", str(BACKEND_ROOT / "generated_files"))
)

GLOBAL_BASE_PROMPT_PATH = BACKEND_ROOT / "prompt_presets" / "global-base-prompt.md"

# ── Knowledge review ───────────────────────────────────────────────────────

ANSWER_CORRECTION_REVIEW_PREFIX = "gbrain_answer_correction:message:"
GBRAIN_THINK_REVIEW_PREFIX = "gbrain_think_review:message:"
ANSWER_CORRECTION_RATING_THRESHOLD = 2

# ── Session attachments ────────────────────────────────────────────────────

SESSION_ATTACHMENT_CLEANUP_INTERVAL = timedelta(hours=6)
