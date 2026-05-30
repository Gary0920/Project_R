import { apiRequest, type ApiClientOptions } from "./client";
import type {
  ChatMessageListResponse,
  ChatSearchResultResponse,
  ChatSessionResponse,
  ActivateMessageVersionResponse,
  EditMessageResponse,
  MessageFeedbackResponse,
  RegenerateMessageResponse,
  RestoreMessagesResponse,
  SendChatMessageResponse,
  SessionAttachmentResponse,
} from "./types";

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
  thinking?: boolean,
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
      thinking: Boolean(thinking),
    }),
  });
}

export function createSessionAttachment(
  options: ApiClientOptions,
  sessionId: number,
  data: { filename: string; content: string; content_type?: string },
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
) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<SessionAttachmentResponse>(options, `/chat/sessions/${sessionId}/attachments/upload`, {
    method: "POST",
    body: form,
  });
}

export function listSessionAttachments(options: ApiClientOptions, sessionId: number) {
  return apiRequest<SessionAttachmentResponse[]>(options, `/chat/sessions/${sessionId}/attachments`);
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
