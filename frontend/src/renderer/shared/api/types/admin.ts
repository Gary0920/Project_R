import type {
  GBrainCitationFixerJobState,
  GBrainCitationFixerTrackedJob,
  GBrainToolResponse,
} from "./gbrain";

// ==========================================================================
// Admin
// ==========================================================================

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

export type KnowledgeReviewDraftResponse = {
  ok: boolean;
  draft: string;
  summary: string;
  generated_by: string;
  model: string;
};

export type AdminTemplateStatusResponse = {
  items: Array<{
    skill_name: string;
    display_name: string;
    outputs: Array<Record<string, unknown>>;
    references: string[];
  }>;
};
