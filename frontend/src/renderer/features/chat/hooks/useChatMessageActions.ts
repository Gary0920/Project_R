import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { ApiError, type ApiClientOptions } from "../../../shared/api/client";
import type {
  ChatMessageVersionResponse,
  ChatSessionResponse,
} from "../../../shared/api/types";
import { parseApiDate } from "../../../shared/utils/time";
import {
  activateChatMessageVersion,
  deleteChatMessage,
  editChatMessage,
  exportChatSession,
  listChatSessions,
  restoreDeletedChatMessages,
  submitGBrainThinkReview,
  submitMessageFeedback,
} from "../api";
import { copyText } from "../clipboard";
import type { ChatMessage } from "../state";
import { composeSystemPrompt } from "../../prompts/sessionPrompt";

type ModelSelection = {
  provider?: string | null;
  profile?: string | null;
} | null;

export type GBrainReviewDraft = {
  sourceHint: string;
  userNote: string;
};

const EMPTY_GBRAIN_REVIEW_DRAFT: GBrainReviewDraft = {
  sourceHint: "",
  userNote: "",
};

export function useChatMessageActions({
  activeWorkspaceId,
  apiOptions,
  clearAuth,
  mode,
  selectedModelOption,
  selectedPromptContent,
  messagesBySession,
  setActionNotice,
  setError,
  setMessagesBySession,
  setSessions,
  sourcePreviewSessionId,
  clearSourcePreview,
  thinkingEnabled,
  webSearchEnabled,
}: {
  activeWorkspaceId: number | null;
  apiOptions: ApiClientOptions;
  clearAuth: () => void;
  mode: "chat" | "agent";
  selectedModelOption: ModelSelection;
  selectedPromptContent: string;
  messagesBySession: Record<number, ChatMessage[]>;
  setActionNotice: (notice: string) => void;
  setError: (message: string) => void;
  setMessagesBySession: Dispatch<SetStateAction<Record<number, ChatMessage[]>>>;
  setSessions: Dispatch<SetStateAction<ChatSessionResponse[]>>;
  sourcePreviewSessionId?: number | null;
  clearSourcePreview: () => void;
  thinkingEnabled: boolean;
  webSearchEnabled: boolean;
}) {
  const [deleteMessageTarget, setDeleteMessageTarget] = useState<ChatMessage | null>(null);
  const [deleteLastMessageTarget, setDeleteLastMessageTarget] = useState<ChatMessage | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);
  const [deletedMessageUndo, setDeletedMessageUndo] = useState<{ sessionId: number; messageIds: number[] } | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState<ChatMessage | null>(null);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [gbrainReviewTarget, setGBrainReviewTarget] = useState<ChatMessage | null>(null);
  const [gbrainReviewDraft, setGBrainReviewDraft] = useState<GBrainReviewDraft>(EMPTY_GBRAIN_REVIEW_DRAFT);
  const [messageActionBusyId, setMessageActionBusyId] = useState<number | null>(null);
  const copyResetTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const undoDeleteTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
      }
    };
  }, []);

  async function handleCopyMessage(message: ChatMessage) {
    try {
      await copyText(message.content, true);
      setCopiedMessageId(message.id);
      if (copyResetTimerRef.current) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedMessageId(null);
        copyResetTimerRef.current = null;
      }, 1500);
    } catch {
      setError("复制失败：当前浏览器拒绝剪贴板权限。");
    }
  }

  function getMessageDeleteTargetIds(target: ChatMessage, messagesBySession: Record<number, ChatMessage[]>) {
    const sessionMessages = (messagesBySession[target.session_id] ?? [])
      .filter((message) => message.id > 0)
      .sort((a, b) => {
        const timeDiff = parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime();
        return timeDiff || a.id - b.id;
      });
    const targetIndex = sessionMessages.findIndex((message) => message.id === target.id);
    if (targetIndex < 0) return target.id > 0 ? [target.id] : [];
    if (target.role !== "user") return [target.id];

    const targetIds: number[] = [];
    for (let index = targetIndex; index < sessionMessages.length; index += 1) {
      const message = sessionMessages[index];
      if (index !== targetIndex && message.role === "user") break;
      targetIds.push(message.id);
    }
    return targetIds.length > 0 ? targetIds : [target.id];
  }

  function willDeleteEntireSession(target: ChatMessage, messagesBySession: Record<number, ChatMessage[]>) {
    if (target.id < 0) return false;
    const sessionMessages = (messagesBySession[target.session_id] ?? []).filter((message) => message.id > 0);
    if (sessionMessages.length === 0) return false;
    const deleteIds = new Set(getMessageDeleteTargetIds(target, messagesBySession));
    return sessionMessages.every((message) => deleteIds.has(message.id));
  }

  function requestDeleteMessageContext(target: ChatMessage) {
    if (willDeleteEntireSession(target, messagesBySession)) {
      setDeleteLastMessageTarget(target);
      return;
    }
    setDeleteMessageTarget(target);
  }

  async function handleDeleteMessageContext(target: ChatMessage) {
    if (target.id < 0) return;
    setError("");
    try {
      const response = await deleteChatMessage(apiOptions, target.session_id, target.id);
      const excludedIds = new Set(response.excluded_message_ids);
      setMessagesBySession((current) => ({
        ...current,
        [target.session_id]: (current[target.session_id] ?? []).filter((message) => !excludedIds.has(message.id)),
      }));
      setDeletedMessageUndo({ sessionId: target.session_id, messageIds: response.excluded_message_ids });
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
      }
      undoDeleteTimerRef.current = window.setTimeout(() => {
        setDeletedMessageUndo(null);
        undoDeleteTimerRef.current = null;
      }, 8000);
      if (sourcePreviewSessionId === target.session_id) {
        clearSourcePreview();
      }
    } catch (deleteError: unknown) {
      if (deleteError instanceof ApiError && deleteError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("删除消息失败，请稍后重试。");
    }
  }

  async function handleUndoDeleteMessages() {
    if (!deletedMessageUndo) return;
    const undo = deletedMessageUndo;
    setError("");
    try {
      const response = await restoreDeletedChatMessages(apiOptions, undo.sessionId, undo.messageIds);
      setMessagesBySession((current) => {
        const merged = [...(current[undo.sessionId] ?? []), ...response.messages];
        const byId = new Map<number, ChatMessage>();
        for (const message of merged) {
          byId.set(message.id, message);
        }
        return {
          ...current,
          [undo.sessionId]: Array.from(byId.values()).sort((a, b) => {
            const timeDiff = parseApiDate(a.created_at).getTime() - parseApiDate(b.created_at).getTime();
            return timeDiff || a.id - b.id;
          }),
        };
      });
      setDeletedMessageUndo(null);
      if (undoDeleteTimerRef.current) {
        window.clearTimeout(undoDeleteTimerRef.current);
        undoDeleteTimerRef.current = null;
      }
    } catch (restoreError: unknown) {
      if (restoreError instanceof ApiError && restoreError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("撤回删除失败，请刷新消息后确认。");
    }
  }

  function replaceMessageInSession(sessionId: number, currentMessage: ChatMessage, nextMessage: ChatMessage) {
    setMessagesBySession((current) => ({
      ...current,
      [sessionId]: (current[sessionId] ?? []).map((message) =>
        message.id === currentMessage.id ||
        (message.version_group_id && message.version_group_id === currentMessage.version_group_id)
          ? { ...nextMessage }
          : message,
      ),
    }));
  }

  function startEditingMessage(message: ChatMessage) {
    setEditingMessageId(message.id);
    setEditingDraft(message.content);
  }

  async function handleSubmitEditedMessage(message: ChatMessage) {
    const content = editingDraft.trim();
    if (!content || content === message.content || message.id < 0) {
      setEditingMessageId(null);
      setEditingDraft("");
      return;
    }
    setError("");
    setMessageActionBusyId(message.id);
    try {
      const response = await editChatMessage(apiOptions, message.session_id, message.id, {
        content,
        provider: selectedModelOption?.provider ?? null,
        modelProfile: selectedModelOption?.profile ?? null,
        systemPrompt: composeSystemPrompt(selectedPromptContent, mode),
        thinking: thinkingEnabled,
        webSearch: webSearchEnabled,
      });
      const excludedIds = new Set(response.excluded_message_ids);
      setMessagesBySession((current) => {
        const existing = current[message.session_id] ?? [];
        const next: ChatMessage[] = [];
        for (const item of existing) {
          if (excludedIds.has(item.id)) continue;
          if (item.id === message.id) {
            next.push(response.user_message, response.assistant_message);
          } else {
            next.push(item);
          }
        }
        return { ...current, [message.session_id]: next };
      });
      setEditingMessageId(null);
      setEditingDraft("");
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    } catch (editError: unknown) {
      if (editError instanceof ApiError && editError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(editError instanceof ApiError ? editError.message : "编辑消息失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  async function handleActivateVersion(message: ChatMessage, version: ChatMessageVersionResponse) {
    if (version.active_version || message.id < 0) return;
    setError("");
    setMessageActionBusyId(message.id);
    try {
      const response = await activateChatMessageVersion(apiOptions, message.session_id, message.id, version.id);
      replaceMessageInSession(message.session_id, message, response.message);
    } catch (versionError: unknown) {
      if (versionError instanceof ApiError && versionError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(versionError instanceof ApiError ? versionError.message : "切换消息版本失败。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  function openFeedbackDialog(message: ChatMessage) {
    setFeedbackTarget(message);
    setFeedbackRating(message.feedback_rating ?? 0);
    setFeedbackComment(message.feedback_comment ?? "");
  }

  async function handleSubmitFeedback() {
    if (!feedbackTarget || feedbackRating < 1) return;
    setError("");
    setMessageActionBusyId(feedbackTarget.id);
    try {
      const response = await submitMessageFeedback(apiOptions, feedbackTarget.session_id, feedbackTarget.id, {
        rating: feedbackRating,
        comment: feedbackComment,
      });
      setMessagesBySession((current) => ({
        ...current,
        [feedbackTarget.session_id]: (current[feedbackTarget.session_id] ?? []).map((message) =>
          message.id === feedbackTarget.id
            ? { ...message, feedback_rating: response.rating, feedback_comment: response.comment }
            : message,
        ),
      }));
      setFeedbackTarget(null);
      setFeedbackRating(0);
      setFeedbackComment("");
    } catch (feedbackError: unknown) {
      if (feedbackError instanceof ApiError && feedbackError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(feedbackError instanceof ApiError ? feedbackError.message : "保存评分失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  async function handleSetBinaryFeedback(message: ChatMessage, feedback: "like" | "dislike") {
    if (message.id < 0 || message.role !== "assistant") return;
    setError("");
    setMessageActionBusyId(message.id);
    try {
      const response = await submitMessageFeedback(apiOptions, message.session_id, message.id, { feedback });
      setMessagesBySession((current) => ({
        ...current,
        [message.session_id]: (current[message.session_id] ?? []).map((item) =>
          item.id === message.id
            ? {
                ...item,
                feedback: response.feedback,
                feedback_rating: response.rating,
                feedback_comment: response.comment,
              }
            : item,
        ),
      }));
      setActionNotice(feedback === "like" ? "已记录喜欢反馈。" : "已记录不喜欢反馈。");
    } catch (feedbackError: unknown) {
      if (feedbackError instanceof ApiError && feedbackError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(feedbackError instanceof ApiError ? feedbackError.message : "保存反馈失败，请稍后重试。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  async function handleExportConversation(sessionId: number) {
    setActionNotice("正在导出 Markdown...");
    try {
      await exportChatSession(apiOptions, sessionId, "markdown");
      setActionNotice("已导出对话。");
    } catch (exportError: unknown) {
      if (exportError instanceof ApiError && exportError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setActionNotice(exportError instanceof ApiError ? exportError.message : "导出失败");
    }
  }

  function handleSubmitGBrainThinkReview(message: ChatMessage) {
    if (message.id < 0) return;
    setError("");
    setActionNotice("");
    setGBrainReviewTarget(message);
    setGBrainReviewDraft(EMPTY_GBRAIN_REVIEW_DRAFT);
  }

  async function handleConfirmGBrainThinkReview() {
    if (!gbrainReviewTarget || gbrainReviewTarget.id < 0) return;
    const sourceHint = gbrainReviewDraft.sourceHint.trim();
    const userNote = gbrainReviewDraft.userNote.trim();
    if (!userNote) return;
    const message = gbrainReviewTarget;
    if (message.id < 0) return;
    setError("");
    setActionNotice("");
    setMessageActionBusyId(message.id);
    try {
      const response = await submitGBrainThinkReview(apiOptions, message.session_id, message.id, {
        source_hint: sourceHint,
        user_note: userNote,
      });
      setActionNotice(
        response.created
          ? `已提交 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`
          : `已更新 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`,
      );
      setGBrainReviewTarget(null);
      setGBrainReviewDraft(EMPTY_GBRAIN_REVIEW_DRAFT);
    } catch (reviewError: unknown) {
      if (reviewError instanceof ApiError && reviewError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError(reviewError instanceof ApiError ? reviewError.message : "提交 GBrain 缺口/冲突审核失败。");
    } finally {
      setMessageActionBusyId(null);
    }
  }

  function gbrainReviewOriginalQuestion() {
    if (!gbrainReviewTarget) return "";
    const sessionMessages = (messagesBySession[gbrainReviewTarget.session_id] ?? [])
      .filter((message) => message.id > 0)
      .sort((left, right) => left.id - right.id);
    const targetIndex = sessionMessages.findIndex((message) => message.id === gbrainReviewTarget.id);
    const previousMessages = targetIndex >= 0 ? sessionMessages.slice(0, targetIndex) : sessionMessages;
    return [...previousMessages].reverse().find((message) => message.role === "user")?.content ?? "";
  }

  return {
    copiedMessageId,
    deleteLastMessageTarget,
    deleteMessageTarget,
    deletedMessageUndo,
    editingDraft,
    editingMessageId,
    feedbackComment,
    feedbackRating,
    feedbackTarget,
    gbrainReviewDraft,
    gbrainReviewOriginalQuestion: gbrainReviewOriginalQuestion(),
    gbrainReviewTarget,
    handleActivateVersion,
    handleConfirmGBrainThinkReview,
    handleCopyMessage,
    handleDeleteMessageContext,
    handleSubmitEditedMessage,
    handleSubmitFeedback,
    handleSetBinaryFeedback,
    handleExportConversation,
    handleSubmitGBrainThinkReview,
    handleUndoDeleteMessages,
    messageActionBusyId,
    openFeedbackDialog,
    requestDeleteMessageContext,
    setDeleteConfirmMessageTarget: setDeleteMessageTarget,
    setDeleteLastMessageTarget,
    setDeleteMessageTarget,
    setEditingDraft,
    setEditingMessageId,
    setFeedbackComment,
    setFeedbackRating,
    setFeedbackTarget,
    setGBrainReviewDraft,
    setGBrainReviewTarget,
    setMessageActionBusyId,
    startEditingMessage,
  };
}
