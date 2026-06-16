import type { Dispatch, SetStateAction } from "react";

import type { ApiClientOptions } from "../../shared/api/client";
import type { ChatSessionResponse, SkillResponse } from "../../shared/api/types";
import { listChatSessions, sendChatMessage, sendChatMessageStream, updateChatSession } from "./api";
import {
  isAudioTranscriptionRequest,
  isAudioVideoAttachment,
  isLocalPrivatePendingAttachment,
  isUploadedPendingAttachment,
  pendingAttachmentKey,
  type PendingSessionAttachment,
} from "./attachments";
import { makeLocalMessage } from "./localMessages";
import type { ModelOption } from "./modelOptions";
import type { ChatMessage } from "./state";
import type { Tab } from "./tabs-state";
import { normalizeStreamResponse, type NormalizedStreamResponse } from "./useChatSend";
import { isAbortError } from "./useChatStream";
import { composeSystemPrompt, shouldSuggestAgentMode } from "../prompts/sessionPrompt";
import type { BuiltinSlashCommand, SlashCommandMatch } from "./slashCommands";
import { makeSessionTitle } from "./sessionDisplay";

type MessagesBySession = Record<number, ChatMessage[]>;
type SendingSessions = Record<number, boolean>;
type Mode = "chat" | "agent";

type UseChatSendOrchestratorOptions = {
  activeSessionId: number | null;
  activeSessionIsSending: boolean;
  activeWorkspaceId: number | null;
  apiOptions: ApiClientOptions;
  appendLegacyAssistantResponse: (params: {
    sessionId: number;
    localUserMessageId: number;
    response: any;
    sentAttachments: PendingSessionAttachment[];
    agentSuggestion: { reason: string; request: string } | null;
  }) => ChatMessage;
  clearAuth: () => void;
  clearCurrentDraft: () => void;
  createSessionFromInput: (
    content?: string,
    openInNewTab?: boolean,
    promptIdForNewSession?: string | null,
  ) => Promise<ChatSessionResponse>;
  draft: string;
  finalizeStreamAssistantResponse: (params: {
    sessionId: number;
    localUserMessageId: number;
    placeholderId: number;
    finalResponse: NormalizedStreamResponse;
    sentAttachments: PendingSessionAttachment[];
    accumulatedText: string;
    agentSuggestion: { reason: string; request: string } | null;
  }) => void;
  finishSessionSend: (sessionId: number) => void;
  mode: Mode;
  pendingAttachments: PendingSessionAttachment[];
  registerSendAbortController: (sessionId: number, controller: AbortController) => void;
  removeStreamPlaceholder: (sessionId: number, placeholderId: number | null) => void;
  revokeAttachmentPreviews: (attachments: PendingSessionAttachment[]) => void;
  selectedBuiltinCommand: BuiltinSlashCommand | null;
  selectedModelOption: ModelOption | null;
  selectedPrompt: { content: string };
  selectedPromptId: string | null;
  selectedSkill: SkillResponse | null;
  sendingSessions: SendingSessions;
  setDraft: Dispatch<SetStateAction<string>>;
  setError: (message: string | null) => void;
  setIsUploadingAttachments: (value: boolean) => void;
  setMessagesBySession: Dispatch<SetStateAction<MessagesBySession>>;
  setMode: (mode: Mode) => void;
  setPendingAttachments: Dispatch<SetStateAction<PendingSessionAttachment[]>>;
  setSelectedBuiltinCommand: (command: BuiltinSlashCommand | null) => void;
  setSelectedSkill: (skill: SkillResponse | null) => void;
  setSessions: Dispatch<SetStateAction<ChatSessionResponse[]>>;
  setSessionSending: (sessionId: number, value: boolean) => void;
  setSkillPanelVisible: (visible: boolean) => void;
  setSlashCommand: (match: SlashCommandMatch | null) => void;
  setTabs: Dispatch<SetStateAction<Tab[]>>;
  sessions: ChatSessionResponse[];
  thinkingEnabled: boolean;
  typeAssistantReply: (sessionId: number, message: ChatMessage, fullText: string) => void;
  updateStreamPlaceholder: (sessionId: number, placeholderId: number, content: string) => void;
  uploadPendingAttachmentForSend: (attachment: PendingSessionAttachment, sessionId: number) => Promise<PendingSessionAttachment>;
  webSearchEnabled: boolean;
};

export function useChatSendOrchestrator(options: UseChatSendOrchestratorOptions) {
  const handleSend = async () => {
    const content = options.draft.trim();
    if ((!content && !options.pendingAttachments.length) || options.activeSessionIsSending) return;
    const forceKnowledgeQuery = options.selectedBuiltinCommand?.name === "query";
    const startedFromWorkspaceHome = !options.activeSessionId;
    options.setError(null);
    let requestSessionId: number | null = null;
    let isStreamPath = false;
    let streamPlaceholderId: number | null = null;
    let uploadingForSend = false;

    try {
      const sessionTitleSeed = content || options.pendingAttachments[0]?.original_name || "附件提问";
      const session = options.activeSessionId
        ? options.sessions.find((item) => item.id === options.activeSessionId) ?? await options.createSessionFromInput(sessionTitleSeed)
        : await options.createSessionFromInput(sessionTitleSeed, true, options.selectedPromptId);
      const sessionId = session.id;
      if (options.sendingSessions[sessionId]) return;
      requestSessionId = sessionId;
      const attachmentsForSend = options.pendingAttachments.filter((attachment) => attachment.session_id === null || attachment.session_id === sessionId);
      if (!content && !attachmentsForSend.length) throw new Error("请先输入消息或添加当前会话附件。");
      const unauthorizedLocalAttachments = attachmentsForSend.filter(
        (attachment) => isLocalPrivatePendingAttachment(attachment) && attachment.authorization_status !== "authorized",
      );
      if (unauthorizedLocalAttachments.length) throw new Error("请先确认本机选择文件的本次发送授权。");
      const audioVideoAttachments = attachmentsForSend.filter(isAudioVideoAttachment);
      const canHandleAudioVideo =
        options.selectedSkill?.name === "audio-transcription" || (audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content));
      if (audioVideoAttachments.length > 0 && !canHandleAudioVideo) {
        throw new Error("当前版本暂未接入视频/音频附件理解，请先改用图片或可提取文本的附件。");
      }
      if (attachmentsForSend.some((attachment) => attachment.kind === "image") && !options.selectedModelOption?.supportsVision) {
        throw new Error("当前模型不支持图片理解，请切换到 MiMo V2.5 或 MiMo V2.5 Pro 后再发送。");
      }

      uploadingForSend = attachmentsForSend.some((attachment) => !isUploadedPendingAttachment(attachment));
      if (uploadingForSend) options.setIsUploadingAttachments(true);
      const sentAttachments: PendingSessionAttachment[] = [];
      for (const attachment of attachmentsForSend) {
        sentAttachments.push(await options.uploadPendingAttachmentForSend(attachment, sessionId));
      }
      if (uploadingForSend) {
        options.setIsUploadingAttachments(false);
        uploadingForSend = false;
      }

      const attachmentIds = sentAttachments.map((attachment) => String(attachment.id));
      options.setDraft("");
      options.clearCurrentDraft();
      options.setSelectedSkill(null);
      options.setSelectedBuiltinCommand(null);
      options.setSlashCommand(null);
      options.setSkillPanelVisible(false);
      const localUserMessage = makeLocalMessage(sessionId, "user", content, {
        isOptimistic: true,
        attachments: sentAttachments.map((attachment) => ({ ...attachment, session_id: sessionId, message_id: attachment.message_id ?? null })),
      });
      options.setMessagesBySession((current) => ({
        ...current,
        [sessionId]: [...(current[sessionId] ?? []), localUserMessage],
      }));
      const abortController = new AbortController();
      options.registerSendAbortController(sessionId, abortController);
      options.setSessionSending(sessionId, true);

      if (session.title === "新对话") {
        const title = makeSessionTitle(content || sentAttachments[0]?.original_name || "附件提问");
        updateChatSession(options.apiOptions, sessionId, { title })
          .then((updated) => {
            options.setSessions((current) => current.map((item) => item.id === sessionId ? updated : item));
            options.setTabs((current) => current.map((tab) => tab.sessionId === sessionId ? { ...tab, title } : tab));
          })
          .catch(() => {});
      }

      const autoAudioTranscription = audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content);
      const needsLegacyPath =
        forceKnowledgeQuery ||
        options.selectedSkill?.name ||
        options.selectedBuiltinCommand?.name === "query" ||
        autoAudioTranscription;
      if (needsLegacyPath) {
        const response = await sendChatMessage(
          options.apiOptions,
          sessionId,
          content,
          composeSystemPrompt(options.selectedPrompt.content, options.mode),
          attachmentIds,
          options.selectedModelOption?.provider ?? null,
          options.selectedModelOption?.profile ?? null,
          options.selectedSkill?.name ?? (audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content) ? "audio-transcription" : null),
          options.selectedPromptId,
          forceKnowledgeQuery,
          options.thinkingEnabled,
          options.webSearchEnabled,
          abortController.signal,
        );
        if (
          startedFromWorkspaceHome &&
          (response.skill_run || response.generated_file || response.intent === "skill_trigger" || response.intent === "document_generation")
        ) {
          options.setMode("agent");
        }
        options.setPendingAttachments((current) =>
          current.filter((attachment) => !attachmentsForSend.some((sent) => pendingAttachmentKey(sent) === pendingAttachmentKey(attachment))),
        );
        options.revokeAttachmentPreviews(attachmentsForSend);
        options.setSelectedSkill(null);
        const agentRequest = content || sentAttachments.map((attachment) => attachment.original_name).join(" ");
        const agentSuggestion = shouldSuggestAgentMode(agentRequest, response, options.mode);
        const assistantMessage = options.appendLegacyAssistantResponse({
          sessionId,
          localUserMessageId: localUserMessage.id,
          response,
          sentAttachments,
          agentSuggestion: agentSuggestion ? { reason: agentSuggestion, request: agentRequest } : null,
        });
        options.typeAssistantReply(sessionId, assistantMessage, response.reply);
        options.setSessions(await listChatSessions(options.apiOptions, options.activeWorkspaceId));
        return;
      }

      isStreamPath = true;
      const assistantMessagePlaceholder = makeLocalMessage(sessionId, "assistant", "", {
        id: -(Date.now()),
        provider: options.selectedModelOption?.provider ?? "",
        model: options.selectedModelOption?.model ?? "",
        rag_used: false,
        isTyping: true,
      });
      streamPlaceholderId = assistantMessagePlaceholder.id;
      options.setMessagesBySession((current) => ({
        ...current,
        [sessionId]: [
          ...(current[sessionId] ?? []).map((message) =>
            message.id === localUserMessage.id
              ? { ...message, isOptimistic: false, attachments: sentAttachments.map((a) => ({ ...a, session_id: sessionId })) }
              : message,
          ),
          assistantMessagePlaceholder,
        ],
      }));

      let accumulatedText = "";
      const finalDelta = await sendChatMessageStream(
        options.apiOptions,
        sessionId,
        content,
        composeSystemPrompt(options.selectedPrompt.content, options.mode),
        attachmentIds,
        options.selectedModelOption?.provider ?? null,
        options.selectedModelOption?.profile ?? null,
        options.selectedSkill?.name ?? (audioVideoAttachments.length > 0 && isAudioTranscriptionRequest(content) ? "audio-transcription" : null),
        options.selectedPromptId,
        forceKnowledgeQuery,
        options.thinkingEnabled,
        options.webSearchEnabled,
        abortController.signal,
        (delta) => {
          accumulatedText += delta;
          options.updateStreamPlaceholder(sessionId, assistantMessagePlaceholder.id, accumulatedText);
        },
      );

      const finalResponse = normalizeStreamResponse(finalDelta, {
        accumulatedText,
        assistantMessageId: assistantMessagePlaceholder.id,
        userMessageId: localUserMessage.id,
        provider: options.selectedModelOption?.provider ?? "",
        model: options.selectedModelOption?.model ?? "",
      });

      if (startedFromWorkspaceHome && (finalResponse.intent === "skill_trigger" || finalResponse.intent === "document_generation")) {
        options.setMode("agent");
      }
      options.setPendingAttachments((current) =>
        current.filter((attachment) => !attachmentsForSend.some((sent) => pendingAttachmentKey(sent) === pendingAttachmentKey(attachment))),
      );
      options.revokeAttachmentPreviews(attachmentsForSend);
      options.setSelectedSkill(null);

      const agentRequest = content || sentAttachments.map((attachment) => attachment.original_name).join(" ");
      const agentSuggestion = shouldSuggestAgentMode(agentRequest, finalResponse, options.mode);
      options.finalizeStreamAssistantResponse({
        sessionId,
        localUserMessageId: localUserMessage.id,
        placeholderId: assistantMessagePlaceholder.id,
        finalResponse,
        sentAttachments,
        accumulatedText,
        agentSuggestion: agentSuggestion ? { reason: agentSuggestion, request: agentRequest } : null,
      });
      options.setSessions(await listChatSessions(options.apiOptions, options.activeWorkspaceId));
    } catch (sendError: unknown) {
      if (isAbortError(sendError)) {
        if (requestSessionId != null) options.removeStreamPlaceholder(requestSessionId, streamPlaceholderId);
        return;
      }
      if ((sendError as { status?: number }).status === 401) {
        options.clearAuth();
        window.location.hash = "#/login";
        return;
      }
      options.setError(sendError instanceof Error ? sendError.message : "消息发送失败，请稍后重试。");
      if (requestSessionId != null && isStreamPath && streamPlaceholderId != null) {
        options.removeStreamPlaceholder(requestSessionId, streamPlaceholderId);
      }
    } finally {
      if (requestSessionId != null) options.finishSessionSend(requestSessionId);
      if (uploadingForSend) options.setIsUploadingAttachments(false);
    }
  };

  return handleSend;
}
