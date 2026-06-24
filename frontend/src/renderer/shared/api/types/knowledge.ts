export type KnowledgeSourceScopeResponse = {
  scope: "all" | "company" | "project" | "customer" | string;
  label: string;
  description: string;
  workspace_kind: string;
};

export type KnowledgeSourcesResponse = {
  workspace_id: number | null;
  workspace_kind: string;
  scopes: KnowledgeSourceScopeResponse[];
};

export type KnowledgeSearchResultResponse = {
  scope: "company" | "project" | "customer" | string;
  title: string;
  excerpt: string;
  reference_label: string;
};

export type KnowledgeSearchResponse = {
  query: string;
  workspace_id: number | null;
  workspace_kind: string;
  source_scope: string;
  results: KnowledgeSearchResultResponse[];
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
