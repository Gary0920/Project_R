import { apiRequest, type ApiClientOptions } from "./client";
import type {
  AdminGroupCandidateResponse,
  AdminTemplateStatusResponse,
  AdminUserCandidateResponse,
  AdminUserResponse,
  AuditLogResponse,
  GBrainCitationFixerPollResponse,
  GBrainCitationFixerRequest,
  GBrainCitationFixerRollbackResponse,
  GBrainContradictionProbeConfigResponse,
  GBrainContradictionProbeRunResponse,
  GBrainDreamCycleConfigResponse,
  GBrainDreamCyclePollResponse,
  GBrainDreamCycleRunResponse,
  GBrainEntityMergeActionResponse,
  GBrainEntityMergeCandidatesResponse,
  GBrainEntityMergePreviewResponse,
  GBrainGraphResponse,
  GBrainJobSubmitRequest,
  GBrainMaintenanceResponse,
  GBrainMaintenanceWorkerRestartResponse,
  GBrainServiceActionResponse,
  GBrainToolResponse,
  KnowledgeRefreshResponse,
  KnowledgeRegressionResponse,
  KnowledgeReviewCitationFixerResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
} from "./types";

export function listAdminUsers(options: ApiClientOptions) {
  return apiRequest<AdminUserResponse[]>(options, "/admin/users");
}

export function listAdminUserCandidates(options: ApiClientOptions, q = "", limit = 30) {
  const search = new URLSearchParams();
  if (q.trim()) search.set("q", q.trim());
  search.set("limit", String(limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<AdminUserCandidateResponse[]>(options, `/admin/user-candidates${suffix}`);
}

export function listAdminGroupCandidates(options: ApiClientOptions, q = "", limit = 30) {
  const search = new URLSearchParams();
  if (q.trim()) search.set("q", q.trim());
  search.set("limit", String(limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<AdminGroupCandidateResponse[]>(options, `/admin/group-candidates${suffix}`);
}

export function createAdminUser(
  options: ApiClientOptions,
  data: { username: string; password: string; role?: string; nickname?: string; work_group?: string },
) {
  return apiRequest<AdminUserResponse>(options, "/admin/users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateAdminUser(
  options: ApiClientOptions,
  userId: number,
  data: { role?: string; nickname?: string; work_group?: string; is_active?: boolean },
) {
  return apiRequest<AdminUserResponse>(options, `/admin/users/${userId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function resetAdminUserPassword(options: ApiClientOptions, userId: number, password: string) {
  return apiRequest<AdminUserResponse>(options, `/admin/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export function deleteAdminUser(options: ApiClientOptions, userId: number) {
  return apiRequest<{ ok: boolean; deleted_user_id: number; deleted_username: string }>(options, `/admin/users/${userId}`, {
    method: "DELETE",
  });
}

export function listAuditLogs(
  options: ApiClientOptions,
  params: { user_id?: number; date_from?: string; date_to?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.user_id) search.set("user_id", String(params.user_id));
  if (params.date_from) search.set("date_from", params.date_from);
  if (params.date_to) search.set("date_to", params.date_to);
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<AuditLogResponse[]>(options, `/admin/audit-logs${suffix}`);
}

export function listKnowledgeReviews(options: ApiClientOptions, status?: string) {
  const suffix = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<KnowledgeReviewResponse[]>(options, `/admin/knowledge-reviews${suffix}`);
}

export function reviewKnowledge(
  options: ApiClientOptions,
  reviewId: number,
  status: "approved" | "rejected",
  content?: string,
) {
  return apiRequest<KnowledgeReviewResponse>(options, `/admin/knowledge-reviews/${reviewId}`, {
    method: "POST",
    body: JSON.stringify({ status, content }),
  });
}

export function submitKnowledgeReviewCitationFixer(
  options: ApiClientOptions,
  reviewId: number,
  request: { page_slug?: string | null; notes?: string | null; allowed_slug_prefixes?: string[]; max_turns?: number } = {},
) {
  return apiRequest<KnowledgeReviewCitationFixerResponse>(options, `/admin/knowledge-reviews/${reviewId}/citation-fixer`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listAdminTemplates(options: ApiClientOptions) {
  return apiRequest<AdminTemplateStatusResponse>(options, "/admin/templates");
}

export function getKnowledgeStatus(options: ApiClientOptions) {
  return apiRequest<KnowledgeStatusResponse>(options, "/admin/knowledge/status");
}

export function refreshKnowledge(options: ApiClientOptions, enablePdfStructuredExtraction?: boolean) {
  const suffix =
    typeof enablePdfStructuredExtraction === "boolean"
      ? `?enable_pdf_structured_extraction=${enablePdfStructuredExtraction ? "true" : "false"}`
      : "";
  return apiRequest<KnowledgeRefreshResponse>(options, `/admin/knowledge/refresh${suffix}`, {
    method: "POST",
  });
}

export function runKnowledgeRegression(options: ApiClientOptions, includeThink = false) {
  const suffix = includeThink ? "?include_think=true" : "";
  return apiRequest<KnowledgeRegressionResponse>(options, `/admin/knowledge/regression${suffix}`, {
    method: "POST",
  });
}

export function getKnowledgeQualityReport(options: ApiClientOptions, reportId: string) {
  return apiRequest<KnowledgeRegressionResponse>(
    options,
    `/admin/knowledge/quality-reports/${encodeURIComponent(reportId)}`,
  );
}

export function startGBrainService(options: ApiClientOptions) {
  return apiRequest<GBrainServiceActionResponse>(options, "/admin/knowledge/gbrain/start", {
    method: "POST",
  });
}

export function restartGBrainService(options: ApiClientOptions) {
  return apiRequest<GBrainServiceActionResponse>(options, "/admin/knowledge/gbrain/restart", {
    method: "POST",
  });
}

export function getGBrainMaintenance(options: ApiClientOptions) {
  return apiRequest<GBrainMaintenanceResponse>(options, "/admin/knowledge/gbrain/maintenance");
}

export function runGBrainMaintenanceCheck(options: ApiClientOptions, targetScore = 90) {
  return apiRequest<{ ok: boolean; result: GBrainToolResponse }>(
    options,
    `/admin/knowledge/gbrain/maintenance/check?target_score=${targetScore}`,
    { method: "POST" },
  );
}

export function updateGBrainDreamCycle(
  options: ApiClientOptions,
  request: { enabled: boolean; interval_hours: number; target_score: number; source_id: string; job_names: string[] },
) {
  return apiRequest<GBrainDreamCycleConfigResponse>(options, "/admin/knowledge/gbrain/dream-cycle", {
    method: "PUT",
    body: JSON.stringify(request),
  });
}

export function runGBrainDreamCycle(options: ApiClientOptions, force = false) {
  const suffix = force ? "?force=true" : "";
  return apiRequest<GBrainDreamCycleRunResponse>(options, `/admin/knowledge/gbrain/dream-cycle/run${suffix}`, {
    method: "POST",
  });
}

export function tickGBrainDreamCycle(options: ApiClientOptions) {
  return apiRequest<GBrainDreamCycleRunResponse>(options, "/admin/knowledge/gbrain/dream-cycle/tick", {
    method: "POST",
  });
}

export function pollGBrainDreamCycleJobs(options: ApiClientOptions) {
  return apiRequest<GBrainDreamCyclePollResponse>(options, "/admin/knowledge/gbrain/dream-cycle/poll-jobs", {
    method: "POST",
  });
}

export function restartGBrainDreamCycleWorker(options: ApiClientOptions) {
  return apiRequest<GBrainMaintenanceWorkerRestartResponse>(options, "/admin/knowledge/gbrain/dream-cycle/worker/restart", {
    method: "POST",
  });
}

export function updateGBrainContradictionProbe(
  options: ApiClientOptions,
  request: {
    enabled: boolean;
    interval_hours: number;
    source_id: string;
    queries: string[];
    top_k: number;
    budget_usd: number;
    judge_model?: string | null;
    timeout_seconds: number;
    result_limit: number;
  },
) {
  return apiRequest<GBrainContradictionProbeConfigResponse>(options, "/admin/knowledge/gbrain/contradiction-probe", {
    method: "PUT",
    body: JSON.stringify(request),
  });
}

export function runGBrainContradictionProbe(options: ApiClientOptions, force = false) {
  const suffix = force ? "?force=true" : "";
  return apiRequest<GBrainContradictionProbeRunResponse>(options, `/admin/knowledge/gbrain/contradiction-probe/run${suffix}`, {
    method: "POST",
  });
}

export function tickGBrainContradictionProbe(options: ApiClientOptions) {
  return apiRequest<GBrainContradictionProbeRunResponse>(options, "/admin/knowledge/gbrain/contradiction-probe/tick", {
    method: "POST",
  });
}

export function listGBrainJobs(options: ApiClientOptions, limit = 20) {
  return apiRequest<GBrainToolResponse>(options, `/admin/knowledge/gbrain/jobs?limit=${limit}`);
}

export function submitGBrainJob(options: ApiClientOptions, request: GBrainJobSubmitRequest) {
  return apiRequest<GBrainToolResponse>(options, "/admin/knowledge/gbrain/jobs", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function cancelGBrainJob(options: ApiClientOptions, jobId: number) {
  return apiRequest<GBrainToolResponse>(options, `/admin/knowledge/gbrain/jobs/${jobId}/cancel`, {
    method: "POST",
  });
}

export function retryGBrainJob(options: ApiClientOptions, jobId: number) {
  return apiRequest<GBrainToolResponse>(options, `/admin/knowledge/gbrain/jobs/${jobId}/retry`, {
    method: "POST",
  });
}

export function getGBrainContradictions(options: ApiClientOptions, limit = 20) {
  return apiRequest<GBrainToolResponse>(options, `/admin/knowledge/gbrain/contradictions?limit=${limit}`);
}

export function getGBrainGraph(
  options: ApiClientOptions,
  params: { source_id?: string; focus?: string; entity_type?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.source_id) search.set("source_id", params.source_id);
  if (params.focus) search.set("focus", params.focus);
  if (params.entity_type) search.set("entity_type", params.entity_type);
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<GBrainGraphResponse>(options, `/admin/knowledge/gbrain/graph${suffix}`);
}

export function getGBrainEntityMergeCandidates(
  options: ApiClientOptions,
  params: { source_id?: string; focus?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.source_id) search.set("source_id", params.source_id);
  if (params.focus) search.set("focus", params.focus);
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<GBrainEntityMergeCandidatesResponse>(options, `/admin/knowledge/gbrain/entity-merge-candidates${suffix}`);
}

export function applyGBrainEntityMergeCandidateAction(
  options: ApiClientOptions,
  request: { source_id: string; candidate_id: string; action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes" },
) {
  return apiRequest<GBrainEntityMergeActionResponse>(options, "/admin/knowledge/gbrain/entity-merge-candidates/action", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getGBrainEntityMergeCandidatePreview(
  options: ApiClientOptions,
  params: { source_id: string; candidate_id: string },
) {
  const search = new URLSearchParams();
  search.set("source_id", params.source_id);
  search.set("candidate_id", params.candidate_id);
  return apiRequest<GBrainEntityMergePreviewResponse>(options, `/admin/knowledge/gbrain/entity-merge-candidates/preview?${search.toString()}`);
}

export function submitGBrainCitationFixer(options: ApiClientOptions, request: GBrainCitationFixerRequest) {
  return apiRequest<GBrainToolResponse>(options, "/admin/knowledge/gbrain/citation-fixer", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function pollGBrainCitationFixerJobs(options: ApiClientOptions) {
  return apiRequest<GBrainCitationFixerPollResponse>(options, "/admin/knowledge/gbrain/citation-fixer/poll-jobs", {
    method: "POST",
  });
}

export function rollbackGBrainCitationFixerJob(options: ApiClientOptions, jobId: number) {
  return apiRequest<GBrainCitationFixerRollbackResponse>(options, `/admin/knowledge/gbrain/citation-fixer/${jobId}/rollback`, {
    method: "POST",
  });
}
