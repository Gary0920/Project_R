import type { ChatMessage } from "./state";

export function makeLocalMessage(
  sessionId: number,
  role: "user" | "assistant",
  content: string,
  extras: Partial<ChatMessage> = {},
): ChatMessage {
  const now = new Date().toISOString();
  return {
    id: -Date.now() - Math.floor(Math.random() * 1000),
    session_id: sessionId,
    role,
    content,
    provider: null,
    model: null,
    token_input: null,
    token_output: null,
    token_total: null,
    status: "success",
    error_message: null,
    rag_used: false,
    is_excluded: false,
    version_group_id: null,
    version_index: 1,
    version_count: 1,
    active_version: true,
    versions: [],
    feedback_rating: null,
    feedback_comment: null,
    sources: [],
    attachments: [],
    agent_run: null,
    context_trace: null,
    created_at: now,
    ...extras,
  };
}
