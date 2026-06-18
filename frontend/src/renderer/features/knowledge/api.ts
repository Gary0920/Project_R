import { apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type {
  KnowledgeSearchResponse,
  KnowledgeSourcesResponse,
} from "../../shared/api/types";

export function listKnowledgeSources(options: ApiClientOptions, workspaceId?: number | null) {
  const search = new URLSearchParams();
  if (workspaceId != null) search.set("workspace_id", String(workspaceId));
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return apiRequest<KnowledgeSourcesResponse>(options, `/knowledge/sources${suffix}`);
}

export function searchKnowledge(
  options: ApiClientOptions,
  query: string,
  params: {
    workspaceId?: number | null;
    sourceScope?: string;
    limit?: number;
  } = {},
) {
  const search = new URLSearchParams({ q: query });
  if (params.workspaceId != null) search.set("workspace_id", String(params.workspaceId));
  if (params.sourceScope) search.set("source_scope", params.sourceScope);
  if (params.limit) search.set("limit", String(params.limit));
  return apiRequest<KnowledgeSearchResponse>(options, `/knowledge/search?${search.toString()}`);
}
