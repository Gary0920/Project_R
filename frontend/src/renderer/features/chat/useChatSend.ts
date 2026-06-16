import type { Dispatch, SetStateAction } from "react";

import type { ChatStreamDelta } from "./api";
import { makeLocalMessage } from "./localMessages";
import type { ChatMessage } from "./state";
import type { PendingSessionAttachment } from "./attachments";
import type { SendChatMessageResponse, SessionAttachmentResponse } from "../../shared/api/types";

type MessagesBySession = Record<number, ChatMessage[]>;

type UseChatSendResultsOptions = {
  setMessagesBySession: Dispatch<SetStateAction<MessagesBySession>>;
};

type AgentSuggestion = {
  reason: string;
  request: string;
} | null;

export type NormalizedStreamResponse = SendChatMessageResponse;

function mergeServerUserAttachments(
  serverAttachments: SessionAttachmentResponse[] | ChatStreamDelta["user_attachments"] | undefined,
  sentAttachments: PendingSessionAttachment[],
  sessionId: number,
  userMessageId: number,
) {
  return (
    serverAttachments ??
    sentAttachments.map((attachment) => ({
      ...attachment,
      session_id: sessionId,
      message_id: userMessageId,
    }))
  ).map((attachment: any) => {
    const localAttachment = sentAttachments.find((item) => item.id === attachment.id);
    return localAttachment
      ? {
          ...attachment,
          source_scope: localAttachment.source_scope,
          source_label: localAttachment.source_label,
          authorization_status: localAttachment.authorization_status,
        }
      : attachment;
  });
}

export function normalizeStreamResponse(
  finalDelta: ChatStreamDelta,
  fallback: {
    accumulatedText: string;
    assistantMessageId: number;
    userMessageId: number;
    provider: string;
    model: string;
  },
): NormalizedStreamResponse {
  return {
    assistant_message_id: finalDelta.assistant_message_id ?? fallback.assistantMessageId,
    user_message_id: finalDelta.user_message_id ?? fallback.userMessageId,
    reply: finalDelta.reply ?? fallback.accumulatedText,
    provider: finalDelta.provider ?? fallback.provider,
    model: finalDelta.model ?? fallback.model,
    key_index: null,
    usage: finalDelta.usage ?? { input_tokens: 0, output_tokens: 0 },
    sources: (finalDelta.sources as SendChatMessageResponse["sources"]) ?? [],
    user_attachments: (finalDelta.user_attachments as SendChatMessageResponse["user_attachments"]) ?? [],
    context_trace: (finalDelta.context_trace as SendChatMessageResponse["context_trace"]) ?? null,
    generated_file: (finalDelta.generated_file as SendChatMessageResponse["generated_file"]) ?? null,
    skill_run: (finalDelta.skill_run as SendChatMessageResponse["skill_run"]) ?? null,
    agent_run: (finalDelta.agent_run as SendChatMessageResponse["agent_run"]) ?? null,
    intent: finalDelta.intent ?? "chat",
  };
}

export function useChatSendResults({ setMessagesBySession }: UseChatSendResultsOptions) {
  function appendLegacyAssistantResponse(params: {
    sessionId: number;
    localUserMessageId: number;
    response: SendChatMessageResponse;
    sentAttachments: PendingSessionAttachment[];
    agentSuggestion: AgentSuggestion;
  }) {
    const { sessionId, localUserMessageId, response, sentAttachments, agentSuggestion } = params;
    const assistantMessage = makeLocalMessage(sessionId, "assistant", "", {
      id: response.assistant_message_id,
      provider: response.provider,
      model: response.model,
      token_input: response.usage.input_tokens ?? null,
      token_output: response.usage.output_tokens ?? null,
      token_total:
        typeof response.usage.input_tokens === "number" &&
        typeof response.usage.output_tokens === "number"
          ? response.usage.input_tokens + response.usage.output_tokens
          : null,
      rag_used: Boolean(response.sources?.length),
      sources: response.sources ?? [],
      generated_file: response.generated_file ?? null,
      skill_run: response.skill_run ?? null,
      agent_run: response.agent_run ?? null,
      context_trace: response.context_trace ?? null,
      agent_suggestion: agentSuggestion,
      isTyping: true,
    });
    const serverUserAttachments = mergeServerUserAttachments(
      response.user_attachments,
      sentAttachments,
      sessionId,
      response.user_message_id,
    );
    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: [
        ...(current[sessionId] ?? []).map((message) =>
          message.id === localUserMessageId
            ? { ...message, id: response.user_message_id, isOptimistic: false, attachments: serverUserAttachments }
            : message,
        ),
        assistantMessage,
      ],
    }));
    return assistantMessage;
  }

  function finalizeStreamAssistantResponse(params: {
    sessionId: number;
    localUserMessageId: number;
    placeholderId: number;
    finalResponse: NormalizedStreamResponse;
    sentAttachments: PendingSessionAttachment[];
    accumulatedText: string;
    agentSuggestion: AgentSuggestion;
  }) {
    const {
      sessionId,
      localUserMessageId,
      placeholderId,
      finalResponse,
      sentAttachments,
      accumulatedText,
      agentSuggestion,
    } = params;
    const serverUserAttachments = mergeServerUserAttachments(
      finalResponse.user_attachments,
      sentAttachments,
      sessionId,
      finalResponse.user_message_id,
    );

    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: (current[sessionId] ?? []).map((message) => {
        if (message.id === placeholderId) {
          return {
            ...message,
            id: finalResponse.assistant_message_id,
            content: accumulatedText || finalResponse.reply,
            provider: finalResponse.provider,
            model: finalResponse.model,
            token_input: finalResponse.usage?.input_tokens ?? null,
            token_output: finalResponse.usage?.output_tokens ?? null,
            token_total: (finalResponse.usage?.input_tokens ?? 0) + (finalResponse.usage?.output_tokens ?? 0),
            rag_used: Boolean(finalResponse.sources?.length),
            sources: finalResponse.sources ?? [],
            context_trace: finalResponse.context_trace ?? null,
            agent_suggestion: agentSuggestion,
            isTyping: false,
          } satisfies ChatMessage;
        }
        if (message.id === localUserMessageId) {
          return { ...message, id: finalResponse.user_message_id, isOptimistic: false, attachments: serverUserAttachments };
        }
        return message;
      }),
    }));
  }

  return {
    appendLegacyAssistantResponse,
    finalizeStreamAssistantResponse,
  };
}
