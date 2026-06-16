import { ApiError, apiRequest, type ApiClientOptions } from "../../shared/api/client";
import type {
  ChatMessageListResponse,
  ChatSearchResultResponse,
  ChatSessionResponse,
  ActivateMessageVersionResponse,
  EditMessageResponse,
  GBrainThinkReviewResponse,
  MessageFeedbackResponse,
  RegenerateMessageResponse,
  RestoreMessagesResponse,
  SendChatMessageResponse,
  SessionAttachmentResponse,
} from "../../shared/api/types";

export function listChatSessions(options: ApiClientOptions, workspaceId?: number | null) {
  const suffix = workspaceId ? `?workspace_id=${workspaceId}` : "";
  return apiRequest<ChatSessionResponse[]>(options, `/chat/sessions${suffix}`);
}

export function createChatSession(
  options: ApiClientOptions,
  title = "新对话",
  workspaceId?: number | null,
) {
  return apiRequest<ChatSessionResponse>(options, "/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title, workspace_id: workspaceId ?? null }),
  });
}

export function deleteChatSession(options: ApiClientOptions, sessionId: number) {
  return apiRequest<{ ok: boolean }>(options, `/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

export function deleteChatMessage(options: ApiClientOptions, sessionId: number, messageId: number) {
  return apiRequest<{ ok: boolean; excluded_message_ids: number[] }>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}`,
    {
      method: "DELETE",
    },
  );
}

export function restoreDeletedChatMessages(options: ApiClientOptions, sessionId: number, messageIds: number[]) {
  return apiRequest<RestoreMessagesResponse>(options, `/chat/sessions/${sessionId}/messages/restore`, {
    method: "POST",
    body: JSON.stringify({ message_ids: messageIds }),
  });
}

export function regenerateChatMessage(
  options: ApiClientOptions,
  sessionId: number,
  messageId: number,
  data: {
    provider?: string | null;
    modelProfile?: string | null;
    systemPrompt?: string | null;
    thinking?: boolean;
    webSearch?: boolean;
    temperature?: number;
  },
) {
  return apiRequest<RegenerateMessageResponse>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify({
        provider: data.provider ?? null,
        model_profile: data.modelProfile ?? null,
        system_prompt: data.systemPrompt ?? null,
        thinking: Boolean(data.thinking),
        web_search: Boolean(data.webSearch),
        temperature: data.temperature ?? 0.9,
      }),
    },
  );
}

export function editChatMessage(
  options: ApiClientOptions,
  sessionId: number,
  messageId: number,
  data: {
    content: string;
    provider?: string | null;
    modelProfile?: string | null;
    systemPrompt?: string | null;
    thinking?: boolean;
    webSearch?: boolean;
  },
) {
  return apiRequest<EditMessageResponse>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}/edit`,
    {
      method: "PUT",
      body: JSON.stringify({
        content: data.content,
        provider: data.provider ?? null,
        model_profile: data.modelProfile ?? null,
        system_prompt: data.systemPrompt ?? null,
        thinking: Boolean(data.thinking),
        web_search: Boolean(data.webSearch),
      }),
    },
  );
}

export function activateChatMessageVersion(
  options: ApiClientOptions,
  sessionId: number,
  messageId: number,
  versionId: number,
) {
  return apiRequest<ActivateMessageVersionResponse>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}/versions/${versionId}/activate`,
    { method: "POST" },
  );
}

export function submitMessageFeedback(
  options: ApiClientOptions,
  sessionId: number,
  messageId: number,
  data: { rating: number; comment: string },
) {
  return apiRequest<MessageFeedbackResponse>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}/feedback`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
}

export function submitGBrainThinkReview(
  options: ApiClientOptions,
  sessionId: number,
  messageId: number,
  data: { note?: string } = {},
) {
  return apiRequest<GBrainThinkReviewResponse>(
    options,
    `/chat/sessions/${sessionId}/messages/${messageId}/gbrain-think-review`,
    {
      method: "POST",
      body: JSON.stringify(data),
    },
  );
}

export function listChatMessages(options: ApiClientOptions, sessionId: number) {
  return apiRequest<ChatMessageListResponse>(options, `/chat/sessions/${sessionId}/messages`);
}

export function sendChatMessage(
  options: ApiClientOptions,
  sessionId: number,
  content: string,
  systemPrompt?: string | null,
  files: string[] = [],
  provider?: string | null,
  modelProfile?: string | null,
  selectedSkill?: string | null,
  selectedPromptId?: string | null,
  forceKnowledgeQuery?: boolean,
  thinking?: boolean,
  webSearch?: boolean,
  signal?: AbortSignal,
) {
  return apiRequest<SendChatMessageResponse>(options, `/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    signal,
    body: JSON.stringify({
      content,
      system_prompt: systemPrompt ?? null,
      files,
      provider: provider ?? null,
      model_profile: modelProfile ?? null,
      selected_skill: selectedSkill ?? null,
      selected_prompt_id: selectedPromptId ?? null,
      force_knowledge_query: Boolean(forceKnowledgeQuery),
      thinking: Boolean(thinking),
      web_search: Boolean(webSearch),
    }),
  });
}

export interface ChatStreamDelta {
  delta?: string;
  done?: boolean;
  reply?: string;
  provider?: string;
  model?: string;
  usage?: Record<string, number>;
  assistant_message_id?: number;
  user_message_id?: number;
  intent?: string;
  error?: string;
  sources?: any[];
  user_attachments?: any[];
  context_trace?: any;
  generated_file?: any;
  skill_run?: any;
  agent_run?: any;
}

export async function sendChatMessageStream(
  options: ApiClientOptions,
  sessionId: number,
  content: string,
  systemPrompt: string | null | undefined,
  files: string[],
  provider: string | null | undefined,
  modelProfile: string | null | undefined,
  selectedSkill: string | null | undefined,
  selectedPromptId: string | null | undefined,
  forceKnowledgeQuery: boolean | undefined,
  thinking: boolean | undefined,
  webSearch: boolean | undefined,
  signal: AbortSignal | undefined,
  onDelta: (text: string) => void,
): Promise<ChatStreamDelta> {
  const url = `${options.baseUrl.replace(/\/+$/, "")}/chat/sessions/${sessionId}/messages`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    signal,
    body: JSON.stringify({
      content,
      system_prompt: systemPrompt ?? null,
      files,
      provider: provider ?? null,
      model_profile: modelProfile ?? null,
      selected_skill: selectedSkill ?? null,
      selected_prompt_id: selectedPromptId ?? null,
      force_knowledge_query: Boolean(forceKnowledgeQuery),
      thinking: Boolean(thinking),
      web_search: Boolean(webSearch),
      stream: true,
    }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      options.onUnauthorized?.();
      throw new ApiError("认证失效", 401);
    }
    const text = await response.text().catch(() => "");
    throw new ApiError(text || `HTTP ${response.status}`, response.status);
  }

  // 非 SSE 响应（后端在流式分支前返回的 JSON，如自动 Skill 触发/知识查询）→ 直接解析
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json") || !contentType.includes("text/event-stream")) {
    const json: any = await response.json();
    return {
      done: true,
      reply: json.reply ?? "",
      provider: json.provider,
      model: json.model,
      usage: json.usage ?? {},
      assistant_message_id: json.assistant_message_id,
      user_message_id: json.user_message_id,
      sources: json.sources ?? [],
      user_attachments: json.user_attachments ?? [],
      context_trace: json.context_trace ?? null,
      intent: json.intent ?? "chat",
      generated_file: json.generated_file ?? null,
      skill_run: json.skill_run ?? null,
      agent_run: json.agent_run ?? null,
    } satisfies ChatStreamDelta;
  }

  const reader = response.body?.getReader();
  if (!reader) throw new ApiError("浏览器不支持流式读取", 0);

  const decoder = new TextDecoder();
  let lastDelta: ChatStreamDelta = {};

  try {
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith("data:")) continue;
        const payload = trimmed.slice(5).trim();
        if (payload === "[STREAM-DONE]") continue;

        try {
          const event: ChatStreamDelta = JSON.parse(payload);
          if (event.delta) {
            onDelta(event.delta);
          }
          if (event.done) {
            lastDelta = event;
          }
          if (event.error) {
            throw new ApiError(event.error, 503);
          }
        } catch (err) {
          if (err instanceof ApiError) throw err;
          // 非 JSON 行跳过
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!lastDelta.done) {
    throw new ApiError("流式响应未完成", 503);
  }
  return lastDelta;
}

export function createSessionAttachment(
  options: ApiClientOptions,
  sessionId: number,
  data: {
    filename: string;
    content: string;
    content_type?: string;
    source_scope?: string;
    source_label?: string;
    authorization_status?: string;
  },
) {
  return apiRequest<SessionAttachmentResponse>(options, `/chat/sessions/${sessionId}/attachments`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function uploadSessionAttachmentFile(
  options: ApiClientOptions,
  sessionId: number,
  file: File,
  metadata?: {
    source_scope?: string;
    source_label?: string;
    authorization_status?: string;
  },
) {
  const form = new FormData();
  form.append("file", file);
  if (metadata?.source_scope) form.append("source_scope", metadata.source_scope);
  if (metadata?.source_label) form.append("source_label", metadata.source_label);
  if (metadata?.authorization_status) form.append("authorization_status", metadata.authorization_status);
  return apiRequest<SessionAttachmentResponse>(options, `/chat/sessions/${sessionId}/attachments/upload`, {
    method: "POST",
    body: form,
  });
}

export function listSessionAttachments(options: ApiClientOptions, sessionId: number) {
  return apiRequest<SessionAttachmentResponse[]>(options, `/chat/sessions/${sessionId}/attachments`);
}

export async function fetchSessionAttachmentBlob(
  options: ApiClientOptions,
  sessionId: number,
  attachmentId: number,
  signal?: AbortSignal,
) {
  const response = await fetch(
    `${options.baseUrl}/chat/sessions/${sessionId}/attachments/${attachmentId}/content`,
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

export function deleteSessionAttachment(options: ApiClientOptions, sessionId: number, attachmentId: number) {
  return apiRequest<{ ok: boolean }>(options, `/chat/sessions/${sessionId}/attachments/${attachmentId}`, {
    method: "DELETE",
  });
}

export function updateChatSession(
  options: ApiClientOptions,
  sessionId: number,
  data: { title?: string; workspace_id?: number; is_pinned?: boolean },
) {
  return apiRequest<ChatSessionResponse>(options, `/chat/sessions/${sessionId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export function archiveChatSession(options: ApiClientOptions, sessionId: number) {
  return apiRequest<{ ok: boolean }>(options, `/chat/sessions/${sessionId}/archive`, {
    method: "POST",
  });
}

export function restoreChatSession(options: ApiClientOptions, sessionId: number) {
  return apiRequest<{ ok: boolean }>(options, `/chat/sessions/${sessionId}/restore`, {
    method: "POST",
  });
}

export function listArchivedChatSessions(options: ApiClientOptions) {
  return apiRequest<ChatSessionResponse[]>(options, "/chat/sessions/archived");
}

export function searchChatSessions(
  options: ApiClientOptions,
  query: string,
  workspaceId?: number | null,
) {
  const params = new URLSearchParams({ q: query });
  if (workspaceId) params.set("workspace_id", String(workspaceId));
  return apiRequest<ChatSearchResultResponse[]>(options, `/chat/search?${params.toString()}`);
}
