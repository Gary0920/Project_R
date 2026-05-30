from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, UniqueConstraint

from models import Base


class ClientUpdateRelease(Base):
    __tablename__ = "client_update_releases"
    __table_args__ = (UniqueConstraint("platform", "version", name="uq_client_update_platform_version"),)

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(32), nullable=False, default="win32", index=True)
    version = Column(String(64), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    release_notes = Column(Text, nullable=False, default="")
    minimum_supported_version = Column(String(64), nullable=False, default="")
    is_force_update = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
