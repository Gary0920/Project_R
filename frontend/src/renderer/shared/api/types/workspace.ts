// ==========================================================================
// Workspace / Files / Meetings
// ==========================================================================

export type WorkspaceResponse = {
  id: number;
  name: string;
  slug: string;
  description: string;
  created_by: number;
  member_count: number;
  brand: "AURA" | "BFI" | "SPECWISE" | "SYNOVA" | string;
  workspace_kind: "project" | "user" | "customer" | string;
  is_default: boolean;
  is_archived: boolean;
  is_hidden: boolean;
  can_rename: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkspaceDetailResponse = WorkspaceResponse & {
  storage_path: string;
  members: WorkspaceMemberResponse[];
  access_groups: string[];
};

export type WorkspaceFileItemResponse = {
  id: number | null;
  name: string;
  path: string;
  type: "directory" | "file" | string;
  size: number | null;
  updated_at: string | null;
  uploaded_by: number | null;
  uploader_name: string | null;
  deleted_at: string | null;
  deleted_by: number | null;
  rag_status: "pending" | "indexed" | "not_indexed" | "pending_extractor_capability" | "pending_transcription" | "failed" | "skipped" | string | null;
  can_delete: boolean;
  can_restore: boolean;
  children: WorkspaceFileItemResponse[];
};

export type WorkspaceFilesResponse = {
  workspace_id: number;
  root_name: string;
  items: WorkspaceFileItemResponse[];
};

export type WorkspaceFileMutationResponse = {
  ok: boolean;
  path: string;
  file_id: number | null;
  rag_status: string | null;
  agent_run?: AgentRunResponse | null;
};

export type WorkspaceMultiUploadResponse = {
  ok: boolean;
  files: WorkspaceFileMutationResponse[];
  agent_run?: AgentRunResponse | null;
};

export type WorkspaceTrashClearResponse = {
  ok: boolean;
  deleted_files: number;
  agent_run?: AgentRunResponse | null;
};

export type MeetingFolderResponse = {
  ok: boolean;
  meeting_folder_path: string;
  created_dirs: string[];
  created_files: string[];
  gbrain_ingest: boolean;
  agent_run?: AgentRunResponse | null;
};

export type SaveMeetingTranscriptResponse = {
  ok: boolean;
  meeting_folder_path: string;
  transcript_v1_path: string;
  transcript_latest_path: string;
  gbrain_ingest: boolean;
  agent_run?: AgentRunResponse | null;
};

export type MeetingGenerateResponse = {
  ok: boolean;
  meeting_folder_path: string;
  minutes_v_path: string;
  minutes_latest_path: string;
  actions_v_path: string;
  actions_latest_path: string;
  gbrain_ingest: boolean;
  agent_run?: AgentRunResponse | null;
  model_used: string;
  token_cost: number;
};

export type DetectedSpeaker = {
  speaker_id: string;
  display_name: string;
  ratio: string;
  duration: string;
};

export type MeetingSpeakersResponse = {
  ok: boolean;
  detected_speakers: DetectedSpeaker[];
};

export type SpeakerMapResponse = {
  ok: boolean;
  meeting_folder_path: string;
  speaker_map_path: string;
  gbrain_ingest: boolean;
};

export type TermCorrectionsResponse = {
  ok: boolean;
  meeting_folder_path: string;
  corrections_path: string;
  gbrain_ingest: boolean;
};

export type MediaTranscribeResponse = {
  ok: boolean;
  meeting_folder_path: string;
  media_path: string;
  transcript_v1_path: string;
  transcript_latest_path: string;
  transcription_status: string;
  segment_count: number;
  warnings: string[];
  gbrain_ingest: boolean;
  agent_run?: AgentRunResponse | null;
  token_cost: number;
};

export type MeetingIngestResponse = {
  ok: boolean;
  meeting_folder_path: string;
  gbrain_ready_path: string;
  source_id: string;
  source_scope: string;
  ingested_files: string[];
  skipped_files: string[];
  gbrain_ingest: boolean;
  agent_run?: AgentRunResponse | null;
  warning?: string;
};

export type MediaPreflightResponse = {
  ok: boolean;
  filename: string;
  size_mb: number;
  estimated_duration_minutes: number | null;
  is_long_media: boolean;
  estimated_segments: number;
  estimated_cost_note: string;
  warnings: string[];
  model: string;
};

export type MeetingRetryResponse = {
  ok: boolean;
  meeting_folder_path: string;
  operation: string;
  status: string;
  message: string;
  agent_run?: AgentRunResponse | null;
};

export type WorkspaceKnowledgeRefreshResponse = {
  ok: boolean;
  workspace_id: number;
  indexed_files: number;
  rag_status: string;
  compiled_files: number;
  pending_extractor_capability_files: number;
  pending_transcription_files: number;
  skipped_files: number;
  failed_files: number;
  pending_reviews_created: number;
  ingest_path?: string;
  ingest_recursive?: boolean;
  gbrain_source_id: string | null;
  gbrain_status: string | null;
  gbrain_sync_status: string | null;
  gbrain_think_status?: string | null;
  gbrain_error: string | null;
  manifest: Record<string, unknown> | null;
  agent_run?: AgentRunResponse | null;
};

export type WorkspaceKnowledgeIngestJobResponse = {
  id: number;
  workspace_id: number;
  requested_by: number;
  status: "queued" | "running" | "succeeded" | "failed" | string;
  result: Partial<WorkspaceKnowledgeRefreshResponse> & Record<string, unknown>;
  error_message: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  agent_run?: AgentRunResponse | null;
};

export type AgentEventResponse = {
  id: number;
  run_id: number;
  sequence: number;
  event_type: string;
  title: string;
  detail: string;
  status: "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled" | string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type AgentRunResponse = {
  id: number;
  user_id: number;
  session_id: number | null;
  message_id: number | null;
  workspace_id: number | null;
  source_type: string;
  source_id: string;
  title: string;
  status: "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled" | string;
  result: Record<string, unknown>;
  error_message: string;
  events: AgentEventResponse[];
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type WorkspaceMemberResponse = {
  user_id: number;
  username: string;
  nickname: string;
  role: "admin" | "member";
  joined_at: string;
};

export type WorkspaceMemberCandidateResponse = {
  user_id: number;
  username: string;
  nickname: string;
  work_group: string;
  role: "admin" | "employee" | string;
  is_member: boolean;
  member_role: "admin" | "member" | string | null;
};

export type WorkspaceGroupCandidateResponse = {
  group_name: string;
  source: "user" | "workspace" | string;
  is_authorized: boolean;
};

export type WorkspaceSearchResult = WorkspaceResponse & {
  is_member: boolean;
  can_open: boolean;
};
