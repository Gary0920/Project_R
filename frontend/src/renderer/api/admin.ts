import { apiRequest, type ApiClientOptions } from "./client";
import type {
  AdminTemplateStatusResponse,
  AdminUserResponse,
  AuditLogResponse,
  GBrainCitationFixerRequest,
  GBrainJobSubmitRequest,
  GBrainMaintenanceResponse,
  GBrainServiceActionResponse,
  GBrainToolResponse,
  KnowledgeRefreshResponse,
  KnowledgeRegressionResponse,
  KnowledgeReviewResponse,
  KnowledgeStatusResponse,
} from "./types";

export function listAdminUsers(options: ApiClientOptions) {
  return apiRequest<AdminUserResponse[]>(options, "/admin/users");
}

export function createAdminUser(
  options: ApiClientOptions,
  data: { username: string; password: string; role?: string; nickname?: string },
) {
  return apiRequest<AdminUserResponse>(options, "/admin/users", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateAdminUser(
  options: ApiClientOptions,
  userId: number,
  data: { role?: string; nickname?: string; is_active?: boolean },
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

export function submitGBrainCitationFixer(options: ApiClientOptions, request: GBrainCitationFixerRequest) {
  return apiRequest<GBrainToolResponse>(options, "/admin/knowledge/gbrain/citation-fixer", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
