import { apiRequest, type ApiClientOptions } from "./client";
import type {
  DistillationSuggestionResponse,
  NotificationsListResponse,
  WorkspaceResponse,
  WorkspaceDetailResponse,
  WorkspaceFilesResponse,
  WorkspaceFileMutationResponse,
  WorkspaceKnowledgeIngestJobResponse,
  WorkspaceKnowledgeRefreshResponse,
  WorkspaceMultiUploadResponse,
  WorkspaceSearchResult,
} from "./types";

// Workspaces
export function listWorkspaces(options: ApiClientOptions) {
  return apiRequest<WorkspaceResponse[]>(options, "/workspaces");
}

export function createWorkspace(options: ApiClientOptions, name: string, description = "", brand = "BFI") {
  return apiRequest<WorkspaceResponse>(options, "/workspaces", {
    method: "POST",
    body: JSON.stringify({ name, description, brand }),
  });
}

export function updateWorkspace(
  options: ApiClientOptions,
  workspaceId: number,
  data: { name?: string; description?: string },
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

export function listWorkspaceFiles(options: ApiClientOptions, workspaceId: number, includeDeleted = false) {
  const suffix = includeDeleted ? "?include_deleted=true" : "";
  return apiRequest<WorkspaceFilesResponse>(options, `/workspaces/${workspaceId}/files${suffix}`);
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

export function clearWorkspaceTrash(options: ApiClientOptions, workspaceId: number) {
  return apiRequest<{ ok: boolean; deleted_files: number }>(options, `/workspaces/${workspaceId}/files/trash`, {
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
