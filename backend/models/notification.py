from datetime import datetime, timezone

from sqlalchemy import Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="system"
    )  # system / agent / distillation / changelog
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    link: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="system", index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info", index=True)
    action_status: Mapped[str] = mapped_column(String(16), nullable=False, default="none", index=True)
    action_kind: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    event_key: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
