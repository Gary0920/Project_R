from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models import Base


class SessionAttachment(Base):
    __tablename__ = "session_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_messages.id"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False, default="text/plain")
    size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="session_upload")
    source_label: Mapped[str] = mapped_column(String(80), nullable=False, default="会话临时上传")
    authorization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
