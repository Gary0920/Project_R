import type { AgentRunResponse } from "./workspace";
import type { SkillRunResponse } from "./skills";

// ==========================================================================
// Chat
// ==========================================================================

export type ChatSessionResponse = {
  id: number;
  title: string;
  workspace_id: number | null;
  is_archived: boolean;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
  last_message_preview?: string;
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
  feedback: "like" | "dislike" | null;
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
  feedback: "like" | "dislike";
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
  email_draft?: {
    subject?: string;
    body?: string;
    from?: string;
    to?: string | string[];
    cc?: string | string[];
    bcc?: string | string[];
  } | null;
};

export type TransformTextResponse = {
  ok: boolean;
  action: "rewrite" | "translate" | "summarize" | "expand" | string;
  text: string;
  provider: string;
  model: string;
  usage: Record<string, number>;
};

export type ChatSourceResponse = {
  file: string;
  source_title: string;
  section_path: string;
  content: string;
  score: number;
  source_file?: string | null;
  derived_file?: string | null;
  display_title?: string | null;
  evidence_excerpt?: string | null;
  original_source_file?: string | null;
  locator_label?: string | null;
  metadata_only?: boolean | null;
  page_slug?: string | null;
  row_num?: number | string | null;
  source_id?: string | null;
  source_slug?: string | null;
  source_line?: number | null;
  source_page?: number | null;
  source_locator?: string | null;
};
