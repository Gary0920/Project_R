import { useState, type Dispatch, type SetStateAction } from "react";

import { ApiError, type ApiClientOptions } from "../../shared/api/client";
import type { ChatSessionResponse } from "../../shared/api/types";
import { listChatSessions, regenerateChatMessage } from "./api";
import type { ChatMessage } from "./state";
import type { ModelOption } from "./modelOptions";
import { composeSystemPrompt } from "../prompts/sessionPrompt";

type MessagesBySession = Record<number, ChatMessage[]>;
type Mode = "chat" | "agent";

type UseChatRegenerateOptions = {
  activeWorkspaceId: number | null;
  apiOptions: ApiClientOptions;
  clearAuth: () => void;
  mode: Mode;
  modelOptions: ModelOption[];
  selectedModelOption: ModelOption | null;
  selectedPromptContent: string;
  setError: (message: string | null) => void;
  setMessageActionBusyId: (id: number | null) => void;
  setMessagesBySession: Dispatch<SetStateAction<MessagesBySession>>;
  setSessions: Dispatch<SetStateAction<ChatSessionResponse[]>>;
  thinkingEnabled: boolean;
  typeAssistantReply: (sessionId: number, message: ChatMessage, fullText: string) => void;
  webSearchEnabled: boolean;
};

export function useChatRegenerate({
  activeWorkspaceId,
  apiOptions,
  clearAuth,
  mode,
  modelOptions,
  selectedModelOption,
  selectedPromptContent,
  setError,
  setMessageActionBusyId,
  setMessagesBySession,
  setSessions,
  thinkingEnabled,
  typeAssistantReply,
  webSearchEnabled,
}: UseChatRegenerateOptions) {
  const [regenerateTarget, setRegenerateTarget] = useState<ChatMessage | null>(null);
  const [regenerateModelKey, setRegenerateModelKey] = useState<string | null>(null);
  const regenerateModelOption = modelOptions.find((option) => option.key === regenerateModelKey) ?? selectedModelOption;

  function openRegenerateDialog(message: ChatMessage) {
    setRegenerateTarget(message);
    setRegenerateModelKey(selectedModelOption?.key ?? null);
  }

  async function handleRegenerateMessage(target: ChatMessage) {
    if (target.id < 0 || !regenerateModelOption) return;
    setError(null);
    setMessageActionBusyId(target.id);
    setRegenerateTarget(null);
    setMessagesBySession((current) => ({
      ...current,
      [target.session_id]: (current[target.session_id] ?? []).map((message) =>
        message.id === target.id ? { ...message, isRegenerating: true, isTyping: false } : message,
      ),
    }));
    try {
      const response = await regenerateChatMessage(apiOptions, target.session_id, target.id, {
        provider: regenerateModelOption.provider,
        modelProfile: regenerateModelOption.profile,
        systemPrompt: composeSystemPrompt(selectedPromptContent, mode),
        thinking: thinkingEnabled,
        webSearch: webSearchEnabled,
        temperature: 0.9,
      });
      const excludedIds = new Set(response.excluded_message_ids);
      const typingMessage: ChatMessage = {
        ...response.assistant_message,
        content: "",
        isTyping: true,
        isRegenerating: false,
      };
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? [])
          .filter((message) => !excludedIds.has(message.id))
          .map((message) => message.id === target.id ? typingMessage : message),
      }));
      typeAssistantReply(target.session_id, typingMessage, response.assistant_message.content);
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    } catch (regenerateError: unknown) {
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? []).map((message) =>
          message.id === target.id ? { ...target, isRegenerating: false, isTyping: false } : message,
        ),
      }));
      if (regenerateError instanceof ApiError && regenerateError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(regenerateError instanceof ApiError ? regenerateError.message : "重新生成失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  return {
    handleRegenerateMessage,
    openRegenerateDialog,
    regenerateModelKey,
    regenerateModelOption,
    regenerateTarget,
    setRegenerateModelKey,
    setRegenerateTarget,
  };
}
