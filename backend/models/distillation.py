from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class DistillationSuggestion(Base):
    __tablename__ = "distillation_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    suggested_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # null = AI suggested
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_message_ids: Mapped[str] = mapped_column(Text, nullable=False, default="")  # JSON array of message IDs
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )  # pending / approved / rejected
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    review_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
