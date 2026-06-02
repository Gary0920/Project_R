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
  work_group: string;
  last_login_at: string | null;
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
  attachments: SessionAttachmentResponse[];
  generated_file?: GeneratedFileResponse | null;
  skill_run?: SkillRunResponse | null;
  agent_run: AgentRunResponse | null;
  context_trace: ChatContextTraceResponse | null;
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
  message_id: number | null;
  original_name: string;
  content_type: string;
  size: number;
  source_scope?: "local_private" | "session_upload" | "project" | "company" | string;
  source_label?: string;
  authorization_status?: "pending" | "authorized" | "uploaded" | string;
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
  user_attachments?: SessionAttachmentResponse[];
  agent_run?: AgentRunResponse | null;
  context_trace?: ChatContextTraceResponse | null;
};

export type ChatContextTraceResponse = {
  schema_version?: number;
  workspace_id?: number | null;
  intent?: string;
  model?: {
    provider?: string | null;
    model?: string | null;
    requested_model?: string | null;
    thinking?: boolean;
    web_search?: boolean;
  };
  prompt?: {
    selected_prompt_id?: string | null;
    selected_skill?: string | null;
    system_prompt_provided?: boolean;
    system_prompt_preview?: string;
  };
  attachments?: Array<{
    id?: number;
    session_id?: number;
    message_id?: number | null;
    name?: string;
    content_type?: string;
    size?: number;
  }>;
  knowledge?: {
    reduce_context?: boolean;
    source_count?: number;
    sources?: Array<{
      index?: number;
      file?: string | null;
      source_title?: string | null;
      section_path?: string | null;
      score?: number | null;
      source_file?: string | null;
      source_locator?: string | null;
    }>;
  };
  gbrain_think?: {
    source_id?: string | null;
    status?: string | null;
    model?: string | null;
    gap_count?: number;
    conflict_count?: number;
    warning_count?: number;
    gaps?: string[];
    conflicts?: string[];
    warnings?: string[];
    diagnostics?: {
      trace_id?: string | null;
      pipeline?: string | null;
    };
  };
  skill?: {
    run_id?: number | null;
    skill_name?: string | null;
    display_name?: string | null;
    status?: string | null;
    missing_input_count?: number;
  };
  generated_file?: GeneratedFileResponse | null;
  knowledge_query?: string;
  gbrain_source_id?: string | null;
  gbrain_status?: string | null;
  [key: string]: unknown;
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

export type GBrainThinkReviewResponse = {
  ok: boolean;
  knowledge_review_id: number;
  knowledge_review_status: string;
  created: boolean;
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
  execution: Record<string, unknown>;
  governance: Record<string, unknown>;
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
  dispatch: Record<string, unknown> | null;
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
  work_group: string;
  is_active: boolean;
  is_system_account?: boolean;
  created_at: string;
};

export type AdminUserCandidateResponse = {
  user_id: number;
  username: string;
  nickname: string;
  work_group: string;
  role: "admin" | "employee" | string;
  is_active: boolean;
  is_system_account?: boolean;
};

export type AdminGroupCandidateResponse = {
  group_name: string;
  user_count: number;
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

export type KnowledgeReviewCitationFixerResponse = {
  ok: boolean;
  status: string;
  review: KnowledgeReviewResponse;
  result?: GBrainToolResponse;
  tracking?: GBrainCitationFixerJobState & { tracked?: boolean; tracked_job?: GBrainCitationFixerTrackedJob };
  tracked_job?: GBrainCitationFixerTrackedJob;
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
  quality_reports?: KnowledgeQualityReportsResponse;
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
  id?: string;
  ok: boolean;
  ran_at: string;
  actor?: string;
  include_think: boolean;
  query: KnowledgeRegressionSuiteResponse;
  think: KnowledgeRegressionSuiteResponse;
  summary?: {
    query?: { total?: number; passed?: number; failed?: number };
    think?: { total?: number; passed?: number; failed?: number; skipped?: boolean };
    failed_cases?: string[];
    preflight_failures?: string[];
  };
};

export type KnowledgeQualityReportsResponse = {
  path?: string;
  count?: number;
  latest?: KnowledgeRegressionResponse | null;
  reports?: KnowledgeRegressionResponse[];
  trend?: KnowledgeQualityReportTrendItem[];
};

export type KnowledgeQualityReportTrendItem = {
  id?: string;
  ran_at?: string;
  actor?: string;
  ok?: boolean;
  include_think?: boolean;
  query_pass_rate?: number | null;
  think_pass_rate?: number | null;
  query_failed?: number;
  think_failed?: number;
  failed_case_count?: number;
  preflight_failure_count?: number;
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
  dream_cycle?: GBrainDreamCycleConfig;
  dream_cycle_worker?: GBrainMaintenanceWorkerStatus;
  citation_fixer_jobs?: GBrainCitationFixerJobState;
  contradiction_probe?: GBrainContradictionProbeConfig;
};

export type GBrainDreamCycleConfig = {
  enabled: boolean;
  interval_hours: number;
  target_score: number;
  source_id: string;
  job_names: string[];
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_result?: Record<string, unknown> | null;
  tracked_jobs?: GBrainDreamCycleTrackedJob[];
  last_job_poll_at?: string | null;
  last_job_poll_by?: string;
  last_job_poll_result?: Record<string, unknown> | null;
  updated_at?: string | null;
  updated_by?: string;
  path?: string;
};

export type GBrainDreamCycleTrackedJob = {
  job_id: number;
  name: string;
  status: string;
  submitted_at?: string | null;
  last_checked_at?: string | null;
  last_notified_status?: string;
};

export type GBrainDreamCycleConfigResponse = {
  ok: boolean;
  config: GBrainDreamCycleConfig;
};

export type GBrainDreamCycleRunResponse = {
  ok: boolean;
  status: string;
  ran: boolean;
  due?: boolean;
  ran_at?: string;
  forced?: boolean;
  maintain_check?: GBrainToolResponse;
  jobs?: Array<{ name: string; result: GBrainToolResponse }>;
  config?: GBrainDreamCycleConfig;
};

export type GBrainDreamCyclePollResponse = {
  ok: boolean;
  status: string;
  checked: number;
  transitions: Array<{ job_id: number; name: string; status: string; previous_status?: string; checked_at?: string }>;
  config?: GBrainDreamCycleConfig;
};

export type GBrainContradictionProbeConfig = {
  enabled: boolean;
  interval_hours: number;
  source_id: string;
  queries: string[];
  top_k: number;
  budget_usd: number;
  judge_model?: string;
  timeout_seconds: number;
  result_limit: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_result?: Record<string, unknown> | null;
  last_summary?: Record<string, unknown> | null;
  updated_at?: string | null;
  updated_by?: string;
  path?: string;
};

export type GBrainContradictionProbeConfigResponse = {
  ok: boolean;
  config: GBrainContradictionProbeConfig;
};

export type GBrainContradictionProbeRunResponse = {
  ok: boolean;
  status: string;
  ran: boolean;
  due?: boolean;
  ran_at?: string;
  actor?: string;
  summary?: Record<string, unknown>;
  probe?: Record<string, unknown>;
  latest_contradictions?: GBrainToolResponse | null;
  config?: GBrainContradictionProbeConfig;
};

export type GBrainCitationFixerTrackedJob = {
  job_id: number;
  name?: string;
  source_id?: string;
  page_slug?: string;
  review_id?: number | null;
  allowed_slug_prefixes?: string[];
  status?: string;
  submitted_at?: string | null;
  submitted_by?: string;
  last_checked_at?: string | null;
  last_notified_status?: string;
  last_result?: Record<string, unknown> | null;
  reconcile?: Record<string, unknown> | null;
  rollback?: Record<string, unknown> | null;
};

export type GBrainCitationFixerJobState = {
  tracked_jobs?: GBrainCitationFixerTrackedJob[];
  last_job_poll_at?: string | null;
  last_job_poll_by?: string;
  last_job_poll_result?: Record<string, unknown> | null;
  last_rollback_at?: string | null;
  last_rollback_by?: string;
  last_rollback_result?: Record<string, unknown> | null;
  last_submit_without_job_id?: Record<string, unknown> | null;
  path?: string;
};

export type GBrainCitationFixerPollResponse = {
  ok: boolean;
  status: string;
  checked: number;
  transitions: Array<{
    job_id: number;
    name: string;
    source_id?: string;
    page_slug?: string;
    review_id?: number | null;
    status: string;
    previous_status?: string;
    checked_at?: string;
    reconcile?: Record<string, unknown> | null;
  }>;
  state?: GBrainCitationFixerJobState;
};

export type GBrainCitationFixerRollbackResponse = {
  ok: boolean;
  status: string;
  job_id: number;
  rollback?: Record<string, unknown> | null;
  state?: GBrainCitationFixerJobState;
};

export type GBrainMaintenanceWorkerStatus = {
  enabled: boolean;
  running: boolean;
  thread_alive?: boolean;
  interval_seconds: number;
  started_at?: string | null;
  stopped_at?: string | null;
  last_heartbeat_at?: string | null;
  last_tick_result?: Record<string, unknown> | null;
  last_poll_result?: Record<string, unknown> | null;
  last_citation_fixer_poll_result?: Record<string, unknown> | null;
  last_contradiction_probe_result?: Record<string, unknown> | null;
  last_error?: string | null;
  run_count?: number;
};

export type GBrainMaintenanceWorkerRestartResponse = {
  ok: boolean;
  worker: GBrainMaintenanceWorkerStatus;
};

export type GBrainGraphNode = {
  id: string;
  title: string;
  entity_type: string;
  source_id: string;
  file: string;
  source_file?: string;
  citation?: Record<string, unknown>;
};

export type GBrainGraphEdge = {
  id: string;
  from: string;
  to: string;
  relation_type: string;
  source_field?: string;
  confidence?: number;
  evidence?: string;
  citation?: Record<string, unknown>;
};

export type GBrainGraphEvent = {
  id: string;
  entity_id: string;
  event_id: string;
  title: string;
  date?: string;
  source_file?: string;
  citation?: Record<string, unknown>;
};

export type GBrainGraphResponse = {
  ok: boolean;
  source_id: string;
  derived_path?: string;
  focus?: string | null;
  entity_type?: string | null;
  nodes: GBrainGraphNode[];
  edges: GBrainGraphEdge[];
  events: GBrainGraphEvent[];
  stats?: {
    pages_scanned?: number;
    nodes?: number;
    edges?: number;
    events?: number;
  };
  warnings?: string[];
};

export type WorkspaceKnowledgeGraphResponse = GBrainGraphResponse & {
  workspace_id: number;
  workspace_name: string;
  workspace_kind: string;
  source_scope: string;
  intelligence_kind: string;
  profile_cards: Array<{
    id: string;
    title: string;
    entity_type: string;
    relation_count: number;
    event_count: number;
    citation?: Record<string, unknown> | null;
  }>;
};

export type GBrainEntityMergeCandidate = {
  id: string;
  source_id: string;
  candidate_type: string;
  title: string;
  entity_type?: string;
  confidence?: number;
  suggested_action: string;
  reason?: string;
  unresolved_node?: GBrainGraphNode | null;
  target_nodes?: GBrainGraphNode[];
  evidence_edges?: GBrainGraphEdge[];
  citations?: Record<string, unknown>[];
  review_source?: string;
};

export type GBrainEntityMergeCandidatesResponse = {
  ok: boolean;
  source_id: string;
  derived_path?: string;
  focus?: string | null;
  candidates: GBrainEntityMergeCandidate[];
  stats?: {
    pages_scanned?: number;
    candidates?: number;
    unresolved?: number;
    duplicates?: number;
  };
  warnings?: string[];
};

export type WorkspaceEntityMergeCandidatesResponse = GBrainEntityMergeCandidatesResponse & {
  workspace_id: number;
  workspace_name: string;
  workspace_kind: string;
  source_scope: string;
};

export type WorkspaceNativeGraphContextResponse = {
  status: string;
  method?: string;
  source_id?: string;
  slug?: string;
  source_scope?: Record<string, unknown>;
  traverse_graph?: Record<string, unknown>;
  timeline?: Record<string, unknown>;
  backlinks?: Record<string, unknown>;
  error?: string;
};

export type GBrainEntityMergeActionResponse = {
  ok: boolean;
  status: string;
  candidate?: GBrainEntityMergeCandidate;
  created_file?: string;
  decision?: Record<string, unknown>;
  sync?: GBrainToolResponse;
  error?: string;
};

export type GBrainEntityMergePreviewResponse = {
  ok: boolean;
  status: string;
  source_id: string;
  derived_path?: string;
  candidate: GBrainEntityMergeCandidate;
  canonical_entity?: GBrainGraphNode | null;
  alias_entities?: GBrainGraphNode[];
  planned_alias_review_file?: string;
  planned_relink_changes?: Array<{
    file: string;
    source_file?: string;
    page_id: string;
    page_title: string;
    field: string;
    index: number;
    current_ref: string;
    proposed_ref: string;
    diff_preview: string;
    citation?: Record<string, unknown>;
  }>;
  stats?: {
    pages_scanned?: number;
    alias_entities?: number;
    planned_relink_changes?: number;
  };
  warnings?: string[];
  error?: string;
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
