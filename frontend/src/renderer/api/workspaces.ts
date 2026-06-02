import { ApiError, apiRequest, type ApiClientOptions } from "./client";
import type {
  DistillationSuggestionResponse,
  NotificationsListResponse,
  WorkspaceResponse,
  WorkspaceDetailResponse,
  WorkspaceFilesResponse,
  WorkspaceFileMutationResponse,
  WorkspaceKnowledgeIngestJobResponse,
  WorkspaceKnowledgeGraphResponse,
  WorkspaceKnowledgeRefreshResponse,
  WorkspaceEntityMergeCandidatesResponse,
  WorkspaceNativeGraphContextResponse,
  GBrainEntityMergeActionResponse,
  GBrainEntityMergePreviewResponse,
  WorkspaceGroupCandidateResponse,
  WorkspaceMemberCandidateResponse,
  WorkspaceMemberResponse,
  WorkspaceMultiUploadResponse,
  WorkspaceSearchResult,
  WorkspaceTrashClearResponse,
} from "./types";

// Workspaces
export function listWorkspaces(options: ApiClientOptions) {
  return apiRequest<WorkspaceResponse[]>(options, "/workspaces");
}

export function createWorkspace(options: ApiClientOptions, name: string, description = "", brand = "BFI", workspaceKind = "project") {
  return apiRequest<WorkspaceResponse>(options, "/workspaces", {
    method: "POST",
    body: JSON.stringify({ name, description, brand, workspace_kind: workspaceKind }),
  });
}

export function updateWorkspace(
  options: ApiClientOptions,
  workspaceId: number,
  data: { name?: string; description?: string; is_hidden?: boolean },
) {
  return apiRequest<WorkspaceResponse>(options, `/workspaces/${workspaceId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function searchWorkspaces(options: ApiClientOptions, q: string, brand?: string | null) {
  const params = new URLSearchParams({ q });
  if (brand) params.set("brand", brand);
  return apiRequest<WorkspaceSearchResult[]>(options, `/workspaces/search?${params.toString()}`);
}

export function getWorkspace(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<WorkspaceDetailResponse>(options, `/workspaces/${workspaceId}`);
}

export function listWorkspaceMemberCandidates(options: ApiClientOptions, workspaceId: number, q = "") {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<WorkspaceMemberCandidateResponse[]>(options, `/workspaces/${workspaceId}/member-candidates${suffix}`);
}

export function listWorkspaceGroupCandidates(options: ApiClientOptions, workspaceId: number, q = "") {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<WorkspaceGroupCandidateResponse[]>(options, `/workspaces/${workspaceId}/group-candidates${suffix}`);
}

export function upsertWorkspaceMember(
  options: ApiClientOptions,
  workspaceId: number,
  data: { user_id?: number; username?: string; role?: "admin" | "member" | string },
) {
  return apiRequest<WorkspaceMemberResponse>(options, `/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function updateWorkspaceMemberRole(
  options: ApiClientOptions,
  workspaceId: number,
  userId: number,
  role: "admin" | "member" | string,
) {
  return apiRequest<WorkspaceMemberResponse>(options, `/workspaces/${workspaceId}/members/${encodeURIComponent(String(userId))}`, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export function removeWorkspaceMember(options: ApiClientOptions, workspaceId: number, userId: number) {
  return apiRequest<{ ok: boolean }>(options, `/workspaces/${workspaceId}/members/${encodeURIComponent(String(userId))}`, {
    method: "DELETE",
  });
}

export function addWorkspaceAccessGroup(options: ApiClientOptions, workspaceId: number, groupName: string) {
  return apiRequest<{ group_name: string }>(options, `/workspaces/${workspaceId}/groups`, {
    method: "POST",
    body: JSON.stringify({ group_name: groupName }),
  });
}

export function removeWorkspaceAccessGroup(options: ApiClientOptions, workspaceId: number, groupName: string) {
  return apiRequest<{ ok: boolean }>(options, `/workspaces/${workspaceId}/groups/${encodeURIComponent(groupName)}`, {
    method: "DELETE",
  });
}

export function listWorkspaceFiles(options: ApiClientOptions, workspaceId: number, includeDeleted = false) {
  const suffix = includeDeleted ? "?include_deleted=true" : "";
  return apiRequest<WorkspaceFilesResponse>(options, `/workspaces/${workspaceId}/files${suffix}`);
}

export async function fetchWorkspaceFileBlob(
  options: ApiClientOptions,
  workspaceId: number,
  path: string,
  signal?: AbortSignal,
) {
  const response = await fetch(
    `${options.baseUrl}/workspaces/${workspaceId}/files/content?path=${encodeURIComponent(path)}`,
    {
      signal,
      headers: {
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      },
    },
  );
  if (!response.ok) {
    if (response.status === 401) {
      options.onUnauthorized?.();
    }
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // Keep the status text when the server returns no JSON body.
    }
    throw new ApiError(detail, response.status);
  }
  return response.blob();
}

export function uploadWorkspaceFiles(
  options: ApiClientOptions,
  workspaceId: number,
  directory: string,
  files: File[],
) {
  const form = new FormData();
  form.append("directory", directory);
  files.forEach((file) => form.append("files", file));
  return apiRequest<WorkspaceMultiUploadResponse>(options, `/workspaces/${workspaceId}/files/upload`, {
    method: "POST",
    body: form,
  });
}

export function uploadWorkspaceFile(
  options: ApiClientOptions,
  workspaceId: number,
  data: { directory: string; filename: string; content_base64: string; content_type?: string; conflict_strategy?: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/files`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function renameWorkspacePath(
  options: ApiClientOptions,
  workspaceId: number,
  data: { path: string; new_name: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/paths/rename`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function moveWorkspacePath(
  options: ApiClientOptions,
  workspaceId: number,
  data: { path: string; target_directory: string; conflict_strategy?: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/paths/move`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function copyWorkspacePath(
  options: ApiClientOptions,
  workspaceId: number,
  data: { path: string; target_directory: string; conflict_strategy?: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/paths/copy`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function clearWorkspaceTrash(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<WorkspaceTrashClearResponse>(options, `/workspaces/${workspaceId}/files/trash`, {
    method: "DELETE",
  });
}

export function saveAttachmentToWorkspace(
  options: ApiClientOptions,
  workspaceId: number,
  data: { session_id: number; attachment_id: number; conflict_strategy?: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/attachments/save`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function createWorkspaceFolder(
  options: ApiClientOptions,
  workspaceId: number,
  data: { parent_path: string; name: string },
) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/folders`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function deleteWorkspaceFile(options: ApiClientOptions, workspaceId: number, path: string) {
  return apiRequest<WorkspaceFileMutationResponse>(
    options,
    `/workspaces/${workspaceId}/files?path=${encodeURIComponent(path)}`,
    { method: "DELETE" },
  );
}

export function restoreWorkspaceFile(options: ApiClientOptions, workspaceId: number, fileId: number) {
  return apiRequest<WorkspaceFileMutationResponse>(options, `/workspaces/${workspaceId}/files/restore`, {
    method: "POST",
    body: JSON.stringify({ file_id: fileId }),
  });
}

export function permanentlyDeleteWorkspaceFile(options: ApiClientOptions, workspaceId: number, fileId: number) {
  return apiRequest<WorkspaceFileMutationResponse>(
    options,
    `/workspaces/${workspaceId}/files/permanent?file_id=${encodeURIComponent(String(fileId))}`,
    { method: "DELETE" },
  );
}

export function refreshWorkspaceKnowledge(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<WorkspaceKnowledgeRefreshResponse>(options, `/workspaces/${workspaceId}/knowledge/ingest`, {
    method: "POST",
  });
}

export function enqueueWorkspaceKnowledgeIngest(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<WorkspaceKnowledgeIngestJobResponse>(options, `/workspaces/${workspaceId}/knowledge/ingest/async`, {
    method: "POST",
  });
}

export function getWorkspaceKnowledgeIngestJob(options: ApiClientOptions, workspaceId: number, jobId: number) {
  return apiRequest<WorkspaceKnowledgeIngestJobResponse>(
    options,
    `/workspaces/${workspaceId}/knowledge/ingest/jobs/${encodeURIComponent(String(jobId))}`,
  );
}

export function getWorkspaceKnowledgeGraph(
  options: ApiClientOptions,
  workspaceId: number,
  params: { focus?: string; entity_type?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.focus?.trim()) search.set("focus", params.focus.trim());
  if (params.entity_type?.trim()) search.set("entity_type", params.entity_type.trim());
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<WorkspaceKnowledgeGraphResponse>(options, `/workspaces/${workspaceId}/knowledge/graph${suffix}`);
}

export function getWorkspaceEntityMergeCandidates(
  options: ApiClientOptions,
  workspaceId: number,
  params: { focus?: string; limit?: number } = {},
) {
  const search = new URLSearchParams();
  if (params.focus?.trim()) search.set("focus", params.focus.trim());
  if (params.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<WorkspaceEntityMergeCandidatesResponse>(options, `/workspaces/${workspaceId}/knowledge/entity-merge-candidates${suffix}`);
}

export function applyWorkspaceEntityMergeCandidateAction(
  options: ApiClientOptions,
  workspaceId: number,
  request: { candidate_id: string; action: "create_entity_page" | "dismiss" | "record_alias" | "apply_relink_changes" },
) {
  return apiRequest<GBrainEntityMergeActionResponse>(options, `/workspaces/${workspaceId}/knowledge/entity-merge-candidates/action`, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getWorkspaceEntityMergeCandidatePreview(
  options: ApiClientOptions,
  workspaceId: number,
  candidateId: string,
) {
  const search = new URLSearchParams({ candidate_id: candidateId });
  return apiRequest<GBrainEntityMergePreviewResponse>(options, `/workspaces/${workspaceId}/knowledge/entity-merge-candidates/preview?${search.toString()}`);
}

export function getWorkspaceNativeGraphContext(
  options: ApiClientOptions,
  workspaceId: number,
  params: { slug: string; depth?: number; direction?: "in" | "out" | "both" | string; link_type?: string } = { slug: "" },
) {
  const search = new URLSearchParams({ slug: params.slug });
  if (params.depth) search.set("depth", String(params.depth));
  if (params.direction) search.set("direction", params.direction);
  if (params.link_type?.trim()) search.set("link_type", params.link_type.trim());
  return apiRequest<WorkspaceNativeGraphContextResponse>(options, `/workspaces/${workspaceId}/knowledge/graph/native-context?${search.toString()}`);
}

export function deleteWorkspaceFolder(options: ApiClientOptions, workspaceId: number, path: string) {
  return apiRequest<WorkspaceFileMutationResponse>(
    options,
    `/workspaces/${workspaceId}/folders?path=${encodeURIComponent(path)}`,
    { method: "DELETE" },
  );
}

export function joinWorkspace(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<{ ok: boolean; message?: string }>(options, `/workspaces/${workspaceId}/join`, {
    method: "POST",
  });
}

export function deleteWorkspace(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<{ ok: boolean }>(options, `/workspaces/${workspaceId}`, {
    method: "DELETE",
  });
}

// Notifications
export function listNotifications(options: ApiClientOptions) {
  return apiRequest<NotificationsListResponse>(options, "/notifications");
}

export function markNotificationRead(options: ApiClientOptions, notificationId: number) {
  return apiRequest<{ ok: boolean }>(options, `/notifications/${notificationId}/read`, {
    method: "POST",
  });
}

export function markAllNotificationsRead(options: ApiClientOptions) {
  return apiRequest<{ ok: boolean }>(options, "/notifications/read-all", {
    method: "POST",
  });
}

// Distillation
export function listDistillationSuggestions(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<DistillationSuggestionResponse[]>(
    options,
    `/distillation/suggestions?workspace_id=${workspaceId}`,
  );
}

export function reviewDistillationSuggestion(
  options: ApiClientOptions,
  suggestionId: number,
  status: "approved" | "rejected",
  comment = "",
) {
  return apiRequest<{ ok: boolean }>(options, `/distillation/suggestions/${suggestionId}/review`, {
    method: "POST",
    body: JSON.stringify({ status, review_comment: comment }),
  });
}
