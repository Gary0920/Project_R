// ==========================================================================
// Knowledge / GBrain
// ==========================================================================

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
