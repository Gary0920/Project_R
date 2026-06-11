from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.shared.time.utils import serialize_datetime_utc


class AgentEventResponse(BaseModel):
    id: int
    run_id: int
    sequence: int
    event_type: str
    title: str
    detail: str = ""
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)


class AgentRunResponse(BaseModel):
    id: int
    user_id: int
    session_id: int | None = None
    message_id: int | None = None
    workspace_id: int | None = None
    source_type: str
    source_id: str = ""
    title: str
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    events: list[AgentEventResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    @field_serializer("created_at", "updated_at", "completed_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return serialize_datetime_utc(value) if value else None
