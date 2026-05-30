export type ApiErrorPayload = {
  detail?: string;
};

export type HealthResponse = {
  status: string;
};

export type LLMProviderStatusResponse = {
  profile?: string | null;
  provider: string;
  label?: string;
  description?: string;
  default: boolean;
  configured: boolean;
  key_count: number;
  model: string;
  base_url: string;
  api_version: string | null;
  reasoning_effort?: string | null;
  supports_vision?: boolean;
};

export type LLMHealthResponse = {
  profile?: string | null;
  label?: string | null;
  description?: string | null;
  provider: string;
  configured: boolean;
  key_count: number;
  model: string;
  base_url: string;
  api_version: string | null;
  reasoning_effort?: string | null;
  supports_vision?: boolean;
  providers: LLMProviderStatusResponse[];
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type LoginResponse = {
  token: string;
  user_id: number;
  username: string;
  role: "admin" | "employee" | string;
  nickname: string;
  avatar: string;
};

export type CurrentUserResponse = Omit<LoginResponse, "token">;

export type ChatSessionResponse = {
  id: number;
  title: string;
  workspace_id: number | null;
  is_archived: boolean;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
};

export type ChatSearchResultResponse = ChatSessionResponse & {
  matched_message: string | null;
};

export type ChatMessageResponse = {
  id: number;
  session_id: number;
  role: "user" | "assistant" | string;
  content: string;
  provider: string | null;
  model: string | null;
  token_input: number | null;
  token_output: number | null;
  token_total: number | null;
  status: "success" | "failed" | string;
  error_message: string | null;
  rag_used: boolean;
  is_excluded: boolean;
  version_group_id: string | null;
  version_index: number;
  version_count: number;
  active_version: boolean;
  versions: ChatMessageVersionResponse[];
  feedback_rating: number | null;
  feedback_comment: string | null;
  sources: ChatSourceResponse[];
  created_at: string;
};

export type ChatMessageVersionResponse = {
  id: number;
  content: string;
  provider: string | null;
  model: string | null;
  version_index: number;
  active_version: boolean;
  created_at: string;
};

export type ChatMessageListResponse = {
  items: ChatMessageResponse[];
  total: number;
  limit: number;
  offset: number;
};

export type SessionAttachmentResponse = {
  id: number;
  session_id: number;
  original_name: string;
  content_type: string;
  size: number;
  created_at: string;
};

export type CompanyPromptResponse = {
  id: string;
  name: string;
  description: string;
  content: string;
  updated_at: string;
};

export type SendChatMessageResponse = {
  user_message_id: number;
  assistant_message_id: number;
  reply: string;
  provider: string;
  model: string;
  key_index: number | null;
  usage: Record<string, number>;
  intent?: "chat" | "rag_query" | "document_generation" | "skill_trigger" | string;
  sources?: ChatSourceResponse[];
  generated_file?: GeneratedFileResponse | null;
  skill_run?: SkillRunResponse | null;
};

export type RegenerateMessageResponse = {
  ok: boolean;
  assistant_message: ChatMessageResponse;
  excluded_message_ids: number[];
  usage: Record<string, number>;
};

export type EditMessageResponse = {
  ok: boolean;
  user_message: ChatMessageResponse;
  assistant_message: ChatMessageResponse;
  excluded_message_ids: number[];
  usage: Record<string, number>;
};

export type ActivateMessageVersionResponse = {
  ok: boolean;
  message: ChatMessageResponse;
};

export type MessageFeedbackResponse = {
  ok: boolean;
  feedback_id: string;
  rating: number;
  comment: string;
  created_at: string;
  knowledge_review_id: number | null;
  knowledge_review_status: string | null;
};

export type RestoreMessagesResponse = {
  ok: boolean;
  restored_message_ids: number[];
  messages: ChatMessageResponse[];
};

export type GeneratedFileResponse = {
  id: string;
  filename: string;
  mime_type: string;
  download_url: string;
};

export type ChatSourceResponse = {
  file: string;
  source_title: string;
  section_path: string;
  content: string;
  score: number;
  source_file?: string | null;
  derived_file?: string | null;
  source_line?: number | null;
  source_page?: number | null;
  source_locator?: string | null;
};

export type WorkspaceResponse = {
  id: number;
  name: string;
  slug: string;
  description: string;
  created_by: number;
  member_count: number;
  brand: "AURA" | "BFI" | "SPECWISE" | "SYNOVA" | string;
  workspace_kind: "project" | "user" | string;
  is_default: boolean;
  is_archived: boolean;
  can_rename: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
};

export type WorkspaceDetailResponse = WorkspaceResponse & {
  storage_path: string;
  members: WorkspaceMemberResponse[];
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
};

export type WorkspaceMultiUploadResponse = {
  ok: boolean;
  files: WorkspaceFileMutationResponse[];
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
  gbrain_source_id: string | null;
  gbrain_status: string | null;
  gbrain_sync_status: string | null;
  gbrain_error: string | null;
  manifest: Record<string, unknown> | null;
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
};

export type WorkspaceMemberResponse = {
  user_id: number;
  username: string;
  nickname: string;
  role: "admin" | "member";
  joined_at: string;
};

export type WorkspaceSearchResult = WorkspaceResponse & {
  is_member: boolean;
};

export type NotificationResponse = {
  id: number;
  type: string;
  category: "system" | "task" | "workspace" | "approval" | "risk";
  severity: "info" | "success" | "warning" | "critical";
  title: string;
  content: string;
  is_read: boolean;
  action_status: "none" | "pending" | "done" | "dismissed";
  action_kind: "" | "open_session" | "open_workspace" | "open_skill_run" | "download_file" | "open_admin_review" | "open_settings";
  action_payload: Record<string, unknown>;
  event_key: string;
  link: string;
  created_at: string;
  expires_at: string | null;
};

export type NotificationsListResponse = {
  items: NotificationResponse[];
  unread_count: number;
  pending_count: number;
};

export type NotificationCountsResponse = {
  unread_count: number;
  pending_count: number;
};

export type ClientUpdateInfo = {
  id: number;
  version: string;
  platform: string;
  release_notes: string;
  minimum_supported_version: string;
  is_force_update: boolean;
  size_bytes: number;
  sha256: string;
  filename: string;
  download_url: string;
  is_active: boolean;
  created_at: string;
};

export type LatestClientUpdateResponse = {
  update_available: boolean;
  current_version: string;
  latest: ClientUpdateInfo | null;
};

export type ClientUpdateReleaseListResponse = {
  items: ClientUpdateInfo[];
};

export type DistillationSuggestionResponse = {
  id: number;
  workspace_id: number;
  session_id: number | null;
  title: string;
  content: string;
  status: "pending" | "approved" | "rejected";
  reviewer_id: number | null;
  created_at: string;
  reviewed_at: string | null;
};

export type SkillResponse = {
  name: string;
  display_name: string;
  description: string;
  category: string;
  priority: string;
  trigger: string[];
  inputs: Array<Record<string, unknown>>;
  outputs: Array<Record<string, unknown>>;
  references: string[];
  path: string;
};

export type SkillMatchResponse = {
  skill: SkillResponse | null;
  confidence: number;
  reason: string;
};

export type SkillRunResponse = {
  id: number;
  skill_name: string;
  skill: SkillResponse | null;
  user_id: number;
  session_id: number | null;
  status: string;
  inputs: Record<string, unknown>;
  missing_inputs: Array<Record<string, unknown>>;
  generated_file: GeneratedFileResponse | null;
  created_at: string;
  updated_at: string;
};

export type AdminUserResponse = {
  id: number;
  username: string;
  role: "admin" | "employee" | string;
  nickname: string;
  avatar: string;
  is_active: boolean;
  created_at: string;
};

export type AuditLogResponse = {
  id: number;
  user_id: number;
  action: string;
  detail: string;
  token_cost: number | null;
  success: boolean;
  created_at: string;
};

export type KnowledgeReviewResponse = {
  id: number;
  submitter_id: number;
  content: string;
  source: string;
  status: "pending" | "approved" | "rejected" | string;
  reviewer_id: number | null;
  created_at: string;
  reviewed_at: string | null;
};

export type AdminTemplateStatusResponse = {
  items: Array<{
    skill_name: string;
    display_name: string;
    outputs: Array<Record<string, unknown>>;
    references: string[];
  }>;
};

export type KnowledgeStatusResponse = {
  source_dirs: string[];
  knowledge_base_dir?: string;
  embedding_model: string;
  indexed_files: number;
  indexed_chunks: number;
  last_refresh: number | null;
  ok?: boolean;
  source_id?: string;
  base_url?: string;
  service?: {
    status?: string;
    http_status?: number;
    error?: string;
    body?: Record<string, unknown>;
  };
  service_process?: {
    record_exists?: boolean;
    pid?: number | null;
    pid_alive?: boolean;
    cli_workdir?: string;
    bun_executable?: string;
    port?: number;
    bind?: string;
    log_path?: string;
  };
  source?: {
    status?: string;
    registered?: boolean;
    path_matches?: boolean;
    source?: Record<string, unknown>;
    error?: string;
  };
  embedding?: {
    semantic_search_ready?: boolean;
    disabled?: boolean;
    model?: string | null;
    dimensions?: number | string | null;
    provider?: string | null;
    provider_configured?: boolean | null;
    reason?: string | null;
  };
  semantic_search_ready?: boolean;
  page_count?: number;
  chunk_count?: number;
  last_sync?: string | number | null;
  ingest?: {
    exists?: boolean;
    path?: string;
    started_at?: string;
    finished_at?: string;
    summary?: {
      total?: number;
      compiled?: number;
      skipped?: number;
      failed?: number;
    };
    items?: Array<Record<string, unknown>>;
    error?: string;
  };
  doctor?: {
    status?: string;
    health_score?: number;
    brain_checks_score?: number;
    warning_or_failed_checks?: Array<{ name?: string; status?: string; message?: string }>;
    check_count?: number;
    error?: string;
  };
  readiness?: {
    ok?: boolean;
    errors?: string[];
    warnings?: string[];
  };
};

export type KnowledgeRefreshResponse = {
  ok: boolean;
  error: string | null;
  indexed: number;
  synced: number;
  skipped: number;
  removed: number;
  chunks: number;
  errors: number;
  pending_reviews_created?: number;
  manifest?: Record<string, unknown>;
  sync?: Record<string, unknown>;
};

export type KnowledgeRegressionCaseResponse = {
  id: string;
  ok: boolean;
  reason?: string;
  query?: string;
  top_file?: string;
  top_title?: string;
  candidates?: Array<string | null>;
  source_id?: string;
  model?: string;
  citations?: number;
  warnings?: string[];
};

export type KnowledgeRegressionSuiteResponse = {
  ok: boolean;
  skipped?: boolean;
  reason?: string;
  total: number;
  passed: number;
  failed: number;
  preflight_failures?: string[];
  cases: KnowledgeRegressionCaseResponse[];
};

export type KnowledgeRegressionResponse = {
  ok: boolean;
  ran_at: string;
  include_think: boolean;
  query: KnowledgeRegressionSuiteResponse;
  think: KnowledgeRegressionSuiteResponse;
};

export type GBrainServiceActionResponse = {
  ok: boolean;
  status: string;
  pid?: number;
  error?: string;
  service?: Record<string, unknown>;
  start?: Record<string, unknown>;
  stop?: Record<string, unknown>;
};

export type GBrainToolResponse = {
  status?: string;
  ok?: boolean;
  error?: string;
  http_status?: number;
  result?: unknown;
  [key: string]: unknown;
};

export type GBrainMaintenanceResponse = {
  ok: boolean;
  ran_at?: string;
  doctor?: GBrainToolResponse;
  doctor_summary?: Record<string, unknown>;
  status_snapshot?: GBrainToolResponse;
  jobs?: GBrainToolResponse;
  contradictions?: GBrainToolResponse;
  onboard_check?: GBrainToolResponse;
  agent?: Record<string, unknown>;
  allowed_job_names?: string[];
};

export type GBrainJobSubmitRequest = {
  name: string;
  data?: Record<string, unknown>;
  queue?: string | null;
  priority?: number | null;
  max_attempts?: number | null;
  delay?: number | null;
  timeout_ms?: number | null;
};

export type GBrainCitationFixerRequest = {
  page_slug?: string | null;
  review_id?: number | null;
  notes?: string | null;
  allowed_slug_prefixes?: string[];
  max_turns?: number;
  model?: string | null;
  queue?: string | null;
};
