from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class KnowledgeReview(Base):
    __tablename__ = "knowledge_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submitter_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")  # pending / approved / rejected
    reviewer_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
