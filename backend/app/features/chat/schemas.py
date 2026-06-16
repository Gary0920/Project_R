from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.features.agents.schemas import AgentRunResponse
from app.shared.time.utils import serialize_datetime_utc


class CreateSessionRequest(BaseModel):
    title: str = "新对话"
    workspace_id: int | None = None


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    workspace_id: int | None = None
    is_pinned: bool | None = None


class SessionResponse(BaseModel):
    id: int
    title: str
    workspace_id: int | None = None
    is_archived: bool = False
    is_pinned: bool = False
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class SessionDetailResponse(SessionResponse):
    message_count: int


class SendMessageRequest(BaseModel):
    content: str
    files: list[str] = []
    provider: str | None = None
    model_profile: str | None = None
    selected_skill: str | None = None
    selected_prompt_id: str | None = None
    force_knowledge_query: bool = False
    stream: bool = False
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


class RegenerateMessageRequest(BaseModel):
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)


class EditMessageRequest(BaseModel):
    content: str
    provider: str | None = None
    model_profile: str | None = None
    thinking: bool = False
    web_search: bool = False
    system_prompt: str | None = None


class MessageFeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = ""


class RestoreMessagesRequest(BaseModel):
    message_ids: list[int] = Field(default_factory=list)


class ChatSourceResponse(BaseModel):
    file: str
    source_title: str
    section_path: str
    content: str
    score: float
    source_file: str | None = None
    derived_file: str | None = None
    source_line: int | None = None
    source_page: int | None = None
    source_locator: str | None = None


class CreateAttachmentRequest(BaseModel):
    filename: str
    content: str
    content_type: str = "text/plain"
    source_scope: str = "session_upload"
    source_label: str = "会话临时上传"
    authorization_status: str = "uploaded"


class AttachmentResponse(BaseModel):
    id: int
    session_id: int
    message_id: int | None = None
    original_name: str
    content_type: str
    size: int
    source_scope: str = "session_upload"
    source_label: str = "会话临时上传"
    authorization_status: str = "uploaded"
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    provider: str | None
    model: str | None
    token_input: int | None
    token_output: int | None
    token_total: int | None
    status: str
    error_message: str | None
    rag_used: bool = False
    is_excluded: bool = False
    version_group_id: str | None = None
    version_index: int = 1
    version_count: int = 1
    active_version: bool = True
    versions: list["MessageVersionResponse"] = Field(default_factory=list)
    feedback_rating: int | None = None
    feedback_comment: str | None = None
    sources: list[ChatSourceResponse] = Field(default_factory=list)
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    generated_file: dict[str, Any] | None = None
    skill_run: dict[str, Any] | None = None
    agent_run: AgentRunResponse | None = None
    context_trace: dict = Field(default_factory=dict)
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class MessageVersionResponse(BaseModel):
    id: int
    content: str
    provider: str | None = None
    model: str | None = None
    version_index: int = 1
    active_version: bool = True
    created_at: datetime

    @field_serializer("created_at")
    def serialize_datetime(self, value: datetime) -> str:
        return serialize_datetime_utc(value)

    class Config:
        from_attributes = True


class RegenerateMessageResponse(BaseModel):
    ok: bool
    assistant_message: MessageResponse
    excluded_message_ids: list[int] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class EditMessageResponse(BaseModel):
    ok: bool
    user_message: MessageResponse
    assistant_message: MessageResponse
    excluded_message_ids: list[int] = Field(default_factory=list)
    usage: dict[str, int] = Field(default_factory=dict)


class ActivateMessageVersionResponse(BaseModel):
    ok: bool
    message: MessageResponse


class MessageFeedbackResponse(BaseModel):
    ok: bool
    feedback_id: str
    rating: int
    comment: str
    created_at: str
    knowledge_review_id: int | None = None
    knowledge_review_status: str | None = None


class GBrainThinkReviewRequest(BaseModel):
    note: str = Field(default="", max_length=2000)


class GBrainThinkReviewResponse(BaseModel):
    ok: bool
    knowledge_review_id: int
    knowledge_review_status: str
    created: bool


class RestoreMessagesResponse(BaseModel):
    ok: bool
    restored_message_ids: list[int] = Field(default_factory=list)
    messages: list[MessageResponse] = Field(default_factory=list)


class MessageListResponse(BaseModel):
    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class SearchResultResponse(SessionResponse):
    matched_message: str | None = None
