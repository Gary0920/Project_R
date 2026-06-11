from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.features.agents.schemas import AgentRunResponse
from app.shared.time.schemas import UTCDateTimeModel


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    brand: str = "BFI"
    workspace_kind: str = "project"


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_hidden: bool | None = None


class WorkspaceResponse(UTCDateTimeModel):
    id: int
    name: str
    slug: str
    description: str
    created_by: int
    member_count: int = 0
    brand: str = "BFI"
    workspace_kind: str = "project"
    is_default: bool = False
    is_archived: bool
    is_hidden: bool = False
    can_rename: bool = True
    can_delete: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkspaceDetailResponse(WorkspaceResponse):
    storage_path: str
    members: list["MemberResponse"]
    access_groups: list[str] = Field(default_factory=list)


class WorkspaceFileItemResponse(UTCDateTimeModel):
    id: int | None = None
    name: str
    path: str
    type: str
    size: int | None = None
    updated_at: datetime | None = None
    uploaded_by: int | None = None
    uploader_name: str | None = None
    deleted_at: datetime | None = None
    deleted_by: int | None = None
    rag_status: str | None = None
    can_delete: bool = False
    can_restore: bool = False
    children: list["WorkspaceFileItemResponse"] = Field(default_factory=list)


class WorkspaceFilesResponse(BaseModel):
    workspace_id: int
    root_name: str
    items: list[WorkspaceFileItemResponse]


class WorkspaceKnowledgeGraphResponse(BaseModel):
    ok: bool
    workspace_id: int
    workspace_name: str
    workspace_kind: str
    source_id: str
    source_scope: str
    intelligence_kind: str
    derived_path: str | None = None
    focus: str | None = None
    entity_type: str | None = None
    nodes: list[dict]
    edges: list[dict]
    events: list[dict]
    profile_cards: list[dict] = Field(default_factory=list)
    stats: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspaceEntityMergeCandidatesResponse(BaseModel):
    ok: bool
    workspace_id: int
    workspace_name: str
    workspace_kind: str
    source_id: str
    source_scope: str
    derived_path: str | None = None
    focus: str | None = None
    candidates: list[dict]
    stats: dict | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkspaceEntityMergeActionRequest(BaseModel):
    candidate_id: str
    action: str


class UploadWorkspaceFileRequest(BaseModel):
    directory: str = ""
    filename: str
    content_base64: str
    content_type: str = "application/octet-stream"
    conflict_strategy: str = "keep_both"


class CreateWorkspaceFolderRequest(BaseModel):
    parent_path: str = ""
    name: str


class CreateMeetingFolderRequest(BaseModel):
    topic: str
    meeting_time: str | None = None  # ISO-8601 datetime string, optional
    meeting_type: str = "其他"


class SaveMeetingTranscriptRequest(BaseModel):
    folder_path: str  # relative path of the meeting folder inside the workspace
    content: str
    input_type: str = "paste"  # paste / txt / md / docx
    original_filename: str = ""


class MeetingFolderResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    created_dirs: list[str]
    created_files: list[str]
    gbrain_ingest: bool = False
    agent_run: AgentRunResponse | None = None


class SaveMeetingTranscriptResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    transcript_v1_path: str
    transcript_latest_path: str
    gbrain_ingest: bool = False
    agent_run: AgentRunResponse | None = None


class RenameWorkspacePathRequest(BaseModel):
    path: str
    new_name: str


class MoveWorkspacePathRequest(BaseModel):
    path: str
    target_directory: str = ""
    conflict_strategy: str = "keep_both"


class CopyWorkspacePathRequest(BaseModel):
    path: str
    target_directory: str = ""
    conflict_strategy: str = "keep_both"


class SaveAttachmentToWorkspaceRequest(BaseModel):
    session_id: int
    attachment_id: int
    conflict_strategy: str = "keep_both"


class WorkspaceFileMutationResponse(BaseModel):
    ok: bool
    path: str
    file_id: int | None = None
    rag_status: str | None = None
    agent_run: AgentRunResponse | None = None


class WorkspaceMultiUploadResponse(BaseModel):
    ok: bool
    files: list[WorkspaceFileMutationResponse]
    agent_run: AgentRunResponse | None = None


class WorkspaceTrashClearResponse(BaseModel):
    ok: bool
    deleted_files: int
    agent_run: AgentRunResponse | None = None


class RestoreWorkspaceFileRequest(BaseModel):
    file_id: int


class WorkspaceKnowledgeIngestRequest(BaseModel):
    path: str = ""
    recursive: bool = True


class WorkspaceKnowledgeRefreshResponse(BaseModel):
    ok: bool
    workspace_id: int
    indexed_files: int
    rag_status: str
    compiled_files: int = 0
    pending_extractor_capability_files: int = 0
    pending_transcription_files: int = 0
    skipped_files: int = 0
    failed_files: int = 0
    pending_reviews_created: int = 0
    ingest_path: str = ""
    ingest_recursive: bool = True
    gbrain_source_id: str | None = None
    gbrain_status: str | None = None
    gbrain_sync_status: str | None = None
    gbrain_think_status: str | None = None
    gbrain_error: str | None = None
    run_status: str | None = None
    run_id: str | None = None
    manifest: dict | None = None
    agent_run: AgentRunResponse | None = None


class WorkspaceKnowledgeIngestJobResponse(UTCDateTimeModel):
    id: int
    workspace_id: int
    requested_by: int
    status: str
    result: dict = Field(default_factory=dict)
    error_message: str = ""
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    agent_run: AgentRunResponse | None = None


class MemberResponse(UTCDateTimeModel):
    user_id: int
    username: str
    nickname: str
    role: str
    joined_at: datetime


class UpsertWorkspaceMemberRequest(BaseModel):
    user_id: int | None = None
    username: str | None = None
    role: str = "member"


class UpdateWorkspaceMemberRoleRequest(BaseModel):
    role: str


class UpsertWorkspaceGroupRequest(BaseModel):
    group_name: str


class WorkspaceGroupResponse(BaseModel):
    group_name: str


class WorkspaceMemberCandidateResponse(BaseModel):
    user_id: int
    username: str
    nickname: str
    work_group: str = ""
    role: str
    is_member: bool = False
    member_role: str | None = None


class WorkspaceGroupCandidateResponse(BaseModel):
    group_name: str
    source: str = "user"
    is_authorized: bool = False


class MeetingGenerateRequest(BaseModel):
    folder_path: str
    regenerate: bool = False  # if True, create a new version even if already generated
    allow_partial: bool = True


class MeetingGenerateResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    minutes_v_path: str
    minutes_latest_path: str
    actions_v_path: str
    actions_latest_path: str
    gbrain_ingest: bool = False
    agent_run: AgentRunResponse | None = None
    model_used: str = ""
    token_cost: int = 0


class SpeakerMapItem(BaseModel):
    speaker_id: str  # e.g. "Speaker 1"
    display_name: str  # e.g. "张三"


class SaveSpeakerMapRequest(BaseModel):
    folder_path: str
    speakers: list[SpeakerMapItem]


class SpeakerMapResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    speaker_map_path: str
    gbrain_ingest: bool = False


class TermCorrectionItem(BaseModel):
    original: str
    corrected: str
    type: str = "general"  # general / name / technical / acronym
    confidence: str = "中"


class SaveTermCorrectionsRequest(BaseModel):
    folder_path: str
    corrections: list[TermCorrectionItem]


class TermCorrectionsResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    corrections_path: str
    gbrain_ingest: bool = False


class DetectedSpeaker(BaseModel):
    speaker_id: str
    display_name: str
    ratio: str
    duration: str = "—"


class MeetingSpeakersResponse(BaseModel):
    ok: bool
    detected_speakers: list[DetectedSpeaker]


class MediaTranscribeResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    media_path: str
    transcript_v1_path: str
    transcript_latest_path: str
    transcription_status: str
    segment_count: int = 1
    warnings: list[str] = []
    gbrain_ingest: bool = False
    agent_run: AgentRunResponse | None = None
    token_cost: int = 0


class MediaTranscribePreflightRequest(BaseModel):
    folder_path: str
    filename: str
    size_bytes: int
    content_type: str = "application/octet-stream"


class MediaTranscribePreflightResponse(BaseModel):
    ok: bool
    filename: str
    size_mb: float
    estimated_duration_minutes: int | None = None
    is_long_media: bool = False
    estimated_segments: int
    estimated_cost_note: str = ""
    warnings: list[str] = []
    model: str = "MiMo V2.5"


class MeetingRetryRequest(BaseModel):
    folder_path: str
    operation: str = "transcribe"  # transcribe / generate_minutes


class MeetingRetryResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    operation: str
    status: str  # queued / completed / partial / failed
    message: str = ""
    agent_run: AgentRunResponse | None = None


class MeetingIngestRequest(BaseModel):
    folder_path: str
    recursive: bool = True
    single_file_path: str | None = None  # For single-file actions-only ingest


class MeetingIngestResponse(BaseModel):
    ok: bool
    meeting_folder_path: str
    gbrain_ready_path: str
    source_id: str
    source_scope: str
    ingested_files: list[str]
    skipped_files: list[str]
    gbrain_ingest: bool = True
    agent_run: AgentRunResponse | None = None
    warning: str = ""
