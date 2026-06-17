import { MouseEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";

import { ApiError, type ApiClientOptions } from "../shared/api/client";
import { createApiOptions } from "../shared/api/options";
import {
  activateChatMessageVersion,
  archiveChatSession,
  createChatSession,
  deleteChatMessage,
  deleteChatSession,
  editChatMessage,
  fetchSessionAttachmentBlob,
  listChatMessages,
  listChatSessions,
  restoreDeletedChatMessages,
  exportChatSession,
  searchChatSessions,
  submitGBrainThinkReview,
  submitMessageFeedback,
  updateChatSession,
} from "../features/chat/api";
import { useChatDraft } from "../features/chat/useChatDraft";
import { getLLMHealth } from "../shared/api/health";
import type { NotificationView } from "../features/notifications/api";
import { listCompanyPrompts } from "../features/prompts/api";
import { listSkills } from "../features/skills/api";
import { authTokenAtom, clearAuthAtom, currentUserAtom } from "../features/auth/state";
import { parseApiDate } from "../shared/utils/time";
import {
  activeMessagesAtom,
  activeSessionAtom,
  activeSessionIdAtom,
  chatErrorAtom,
  chatLoadingAtom,
  chatMessagesBySessionAtom,
  chatSessionsAtom,
  type ChatMessage,
} from "../features/chat/state";
import { serverUrlAtom } from "../shared/state/server";
import { activeModeAtom } from "../shared/state/ui";
import { activeTabIdAtom, tabsAtom } from "../features/chat/tabs-state";
import { activeWorkspaceIdAtom, workspacesAtom } from "../features/workspace/state";
import { saveGeneratedFileToWorkspace } from "../features/workspace/api";
import {
  formatNotificationTime,
  notificationCategoryLabel,
} from "../features/notifications/formatters";
import type {
  ChatSearchResultResponse,
  ChatSessionResponse,
  ChatMessageVersionResponse,
  ChatContextTraceResponse,
  ChatSourceResponse,
  AgentRunResponse,
  CompanyPromptResponse,
  GeneratedFileResponse,
  LLMProviderStatusResponse,
  SkillResponse,
  SkillRunResponse,
} from "../shared/api/types";
import { APP_NAME } from "../shared/config/app";
import { useContextMenu, type ContextMenuItemDef } from "../shared/components/ContextMenu";
import { getPromptOptionId, PromptPanel, type PromptOption } from "../features/prompts/components/PromptPanel";
import { ScratchPad } from "../features/chat/components/ScratchPad";
import { SearchDialog } from "../features/chat/components/SearchDialog";
import { SettingsModal } from "../features/settings/components/SettingsModal";
import { TabBar } from "../features/chat/components/TabBar";
import { WorkspaceSelector } from "../features/workspace/components/WorkspaceSelector";
import { WorkspaceFilePanel } from "../features/workspace/components/WorkspaceFilePanel";
import { copyText } from "../features/chat/clipboard";
import { downloadGeneratedFile } from "../features/chat/generatedFiles";
import { EmailDraftEditor } from "../features/chat/components/EmailDraftEditor";
import { AppWorkspaceChrome } from "../features/chat/components/AppWorkspaceChrome";
import { ChatConversationPane } from "../features/chat/components/ChatConversationPane";
import { useGeneratedEmailDraftActions } from "../features/chat/useGeneratedEmailDraftActions";
import { useTextTransformActions } from "../features/chat/useTextTransformActions";
import {
  attachmentSourceLabel,
  formatAttachmentSize,
  isLocalPrivatePendingAttachment,
  pendingAttachmentKey,
  pendingAttachmentSendFormLabel,
  pendingAttachmentStatusLabel,
  pendingAttachmentTargetLabel,
} from "../features/chat/attachments";
import {
  UPDATE_DOWNLOAD_DRY_RUN,
  formatUpdateBytes,
  formatUpdateSpeed,
} from "../features/updates/clientVersion";
import {
  formatClockTime,
  formatSessionDisplayTitle,
  formatSidebarTime,
  getInitials,
  groupSessionsByTime,
  makeSessionTitle,
  renderAvatar,
  resolveAvatarUrl,
} from "../features/chat/sessionDisplay";
import {
  BUILTIN_SLASH_COMMANDS,
  findSlashCommand,
  getSkillScopeLabel,
  scoreBuiltinSlashCommand,
  scoreSkill,
  type BuiltinSlashCommand,
  type SkillSlashCandidate,
  type SlashCommandMatch,
} from "../features/chat/slashCommands";
import { toModelOption } from "../features/chat/modelOptions";
import { makeLocalMessage } from "../features/chat/localMessages";
import {
  PROMPT_SELECTION_KEY,
  composeSystemPrompt,
  makePromptId,
  readPromptSelectionMap,
  readWebSearchPreference,
  shouldSuggestAgentMode,
  writeWebSearchPreference,
} from "../features/prompts/sessionPrompt";
import { PROJECT_R_BUILTIN_PROMPT } from "../features/prompts/constants";
import { useChatSendResults } from "../features/chat/useChatSend";
import { useChatSendOrchestrator } from "../features/chat/useChatSendOrchestrator";
import { useChatStreamControls } from "../features/chat/useChatStream";
import { useChatRegenerate } from "../features/chat/useChatRegenerate";
import { useChatGlobalShortcuts } from "../features/chat/useChatGlobalShortcuts";
import { useChatComposerShortcuts } from "../features/chat/useChatComposerShortcuts";
import { useNotificationCenter } from "../features/notifications/hooks/useNotificationCenter";
import { useClientUpdate } from "../features/updates/hooks/useClientUpdate";
import { useAppShellPanels } from "../features/chat/hooks/useAppShellPanels";
import { useChatAttachments } from "../features/chat/hooks/useChatAttachments";
import { useAppShellPointerDismiss } from "../features/chat/hooks/useAppShellPointerDismiss";
type SplitPaneKey = "left" | "right";
type UtilityPanel = "workspace" | "customer-intelligence" | "prompt" | "skills" | "source" | "crm";
type RenameScope = "header" | "sidebar";
type SettingsAdminTab = "overview" | "users" | "reviews" | "gbrain" | "templates" | "updates" | "audit";
type SourcePreview = {
  index: number;
  source: ChatSourceResponse;
  sessionId?: number | null;
};

export function AppPage() {
  const serverUrl = useAtomValue(serverUrlAtom);
  const token = useAtomValue(authTokenAtom);
  const currentUser = useAtomValue(currentUserAtom);
  const clearAuth = useSetAtom(clearAuthAtom);
  const [sessions, setSessions] = useAtom(chatSessionsAtom);
  const [activeSessionId, setActiveSessionId] = useAtom(activeSessionIdAtom);
  const activeSession = useAtomValue(activeSessionAtom);
  const activeMessages = useAtomValue(activeMessagesAtom);
  const [messagesBySession, setMessagesBySession] = useAtom(chatMessagesBySessionAtom);
  const [isLoading, setIsLoading] = useAtom(chatLoadingAtom);
  const [error, setError] = useAtom(chatErrorAtom);
  const [actionNotice, setActionNotice] = useState("");
  const [workspaceFilePanelRefreshKey, setWorkspaceFilePanelRefreshKey] = useState(0);
  const [draft, setDraft, clearCurrentDraft] = useChatDraft(activeSessionId);
  const [mode, setMode] = useAtom(activeModeAtom);
  const [tabs, setTabs] = useAtom(tabsAtom);
  const [activeTabId, setActiveTabId] = useAtom(activeTabIdAtom);
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(readWebSearchPreference);
  const [temperature, setTemperature] = useState<number | undefined>(undefined);
  const [quotedMessage, setQuotedMessage] = useState<{ sessionId: number; messageId: number; content: string; role: string } | null>(null);
  // 切换会话时清空引用（防止 A 会话内容被发送到 B 会话）
  useEffect(() => {
    if (quotedMessage && quotedMessage.sessionId !== activeSessionId) {
      setQuotedMessage(null);
    }
  }, [activeSessionId, quotedMessage?.sessionId]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useAtom(activeWorkspaceIdAtom);
  const [workspaces] = useAtom(workspacesAtom);
  const [showScratchPad, setShowScratchPad] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; items: ContextMenuItemDef[] } | null>(null);
  const [showSearch, setShowSearch] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ChatSearchResultResponse[]>([]);
  const [renameInput, setRenameInput] = useState<{ id: number; value: string; scope: RenameScope } | null>(null);
  const [companyPrompts, setCompanyPrompts] = useState<CompanyPromptResponse[]>([]);
  const [userPrompts, setUserPrompts] = useState<UserPromptRecord[]>([]);
  const [promptSelections, setPromptSelections] = useState<Record<string, string>>(readPromptSelectionMap);
  const [pendingPromptId, setPendingPromptId] = useState<string | null>(null);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel | null>(null);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [sideBySideOpen, setSideBySideOpen] = useState(false);
  const [activeSplitPane, setActiveSplitPane] = useState<SplitPaneKey>("left");
  const [splitPaneSessionIds, setSplitPaneSessionIds] = useState<Record<SplitPaneKey, number | null>>({ left: null, right: null });
  const [sendingSessions, setSendingSessions] = useState<Record<number, boolean>>({});
  const { appendLegacyAssistantResponse, finalizeStreamAssistantResponse } = useChatSendResults({ setMessagesBySession });
  const { cancelSessionSend, finishSessionSend, registerSendAbortController, removeStreamPlaceholder, setSessionSending, typeAssistantReply, updateStreamPlaceholder } =
    useChatStreamControls({ setMessagesBySession, setSendingSessions });
  const [deleteConfirmSessionId, setDeleteConfirmSessionId] = useState<number | null>(null);
  const [deleteMessageTarget, setDeleteMessageTarget] = useState<ChatMessage | null>(null);
  const [deleteLastMessageTarget, setDeleteLastMessageTarget] = useState<ChatMessage | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);
  const [deletedMessageUndo, setDeletedMessageUndo] = useState<{ sessionId: number; messageIds: number[] } | null>(null);
  const [editingMessageId, setEditingMessageId] = useState<number | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [feedbackTarget, setFeedbackTarget] = useState<ChatMessage | null>(null);
  const [feedbackRating, setFeedbackRating] = useState(0);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [messageActionBusyId, setMessageActionBusyId] = useState<number | null>(null);
  const [emailDraftEditorFile, setEmailDraftEditorFile] = useState<GeneratedFileResponse | null>(null);
  const [moveSessionId, setMoveSessionId] = useState<number | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [skillPanelVisible, setSkillPanelVisible] = useState(false);
  const [skillPanelIndex, setSkillPanelIndex] = useState(0);
  const [slashCommand, setSlashCommand] = useState<SlashCommandMatch | null>(null);
  const [selectedSkill, setSelectedSkill] = useState<SkillResponse | null>(null);
  const [selectedBuiltinCommand, setSelectedBuiltinCommand] = useState<BuiltinSlashCommand | null>(null);
  const [llmProviders, setLlmProviders] = useState<LLMProviderStatusResponse[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelConfigError, setModelConfigError] = useState("");
  const [selectedModelKey, setSelectedModelKey] = useState<string | null>(null);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [settingsInitialAdminTab, setSettingsInitialAdminTab] = useState<SettingsAdminTab | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);
  const sidebarRenameInputRef = useRef<HTMLInputElement | null>(null);
  const composerRef = useRef<HTMLDivElement | null>(null);
  const modelSelectRef = useRef<HTMLDivElement | null>(null);
  const notificationPanelRef = useRef<HTMLDivElement | null>(null);
  const notificationButtonRef = useRef<HTMLButtonElement | null>(null);
  const copyResetTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);
  const undoDeleteTimerRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const apiOptions = useMemo(
    () => createApiOptions(serverUrl, token, clearAuth),
    [clearAuth, serverUrl, token],
  );
  const {
    handleMarkAllNotificationsRead,
    handleNotificationAction,
    handleNotificationActionStatus,
    notificationPanelOpen,
    notificationToast,
    notificationView,
    notifications,
    notificationsLoading,
    pendingNotificationCount,
    setNotificationPanelOpen,
    setNotificationView,
    unreadNotificationCount,
  } = useNotificationCenter({
    apiOptions,
    downloadGeneratedFile: (file) => downloadGeneratedFile(serverUrl, token, file),
    selectSession,
    serverUrl,
    sessions,
    setActiveWorkspaceId,
    setError,
    setSettingsInitialAdminTab,
    setShowSettings,
    setUtilityPanel,
    token,
  });
  const {
    availableUpdate,
    clientVersion,
    downloadedUpdatePath,
    setUpdateDialogOpen,
    setUpdateStep,
    startClientUpdateDownload,
    updateDialogOpen,
    updateError,
    updateProgress,
    updateStep,
  } = useClientUpdate({ serverUrl, token });
  const {
    auxiliaryPanelMaxWidth,
    auxiliaryPanelRef,
    auxiliaryPanelResizing,
    auxiliaryPanelWidth,
    handleAuxiliaryPanelResizeStart,
    handleSidebarResizeStart,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
    handleWorkspacePanelResizeStart,
    sidebarRef,
    sidebarResizing,
    sidebarWidth,
    workspacePanelMaxWidth,
    workspacePanelRef,
    workspacePanelResizing,
    workspacePanelWidth,
  } = useAppShellPanels();
  useAppShellPointerDismiss({
    composerRef,
    modelMenuOpen,
    modelSelectRef,
    notificationButtonRef,
    notificationPanelOpen,
    notificationPanelRef,
    setModelMenuOpen,
    setNotificationPanelOpen,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelVisible,
  });

  function toggleWebSearch() {
    setWebSearchEnabled((current) => {
      const next = !current;
      writeWebSearchPreference(next);
      return next;
    });
  }

  const activeSessionIsSending = activeSessionId ? Boolean(sendingSessions[activeSessionId]) : false;
  useChatGlobalShortcuts({
    activeSessionId,
    activeSessionIsSending,
    cancelSessionSend,
    setNotificationPanelOpen,
    onOpenSearch: () => setShowSearch(true),
    onNewSession: () => void handleCreateSession(),
  });
  const activeWorkspace = workspaces.find((item) => item.id === activeWorkspaceId);
  const promptOptions = useMemo<PromptOption[]>(() => [
    PROJECT_R_BUILTIN_PROMPT,
    ...companyPrompts.map((prompt) => ({
      id: prompt.id,
      source: "company" as const,
      name: prompt.name,
      description: prompt.description,
      content: prompt.content,
    })),
    ...userPrompts.map((prompt) => ({
      id: prompt.id,
      source: "user" as const,
      name: prompt.name,
      description: "仅本机可用",
      content: prompt.content,
    })),
  ], [companyPrompts, userPrompts]);
  const defaultPromptId = makePromptId(PROJECT_R_BUILTIN_PROMPT.source, PROJECT_R_BUILTIN_PROMPT.id);
  const selectedPromptId = activeSessionId
    ? promptSelections[String(activeSessionId)] ?? defaultPromptId
    : pendingPromptId ?? defaultPromptId;
  const matchedPrompt = promptOptions.find((prompt) => getPromptOptionId(prompt) === selectedPromptId);
  const selectedPrompt = matchedPrompt ?? PROJECT_R_BUILTIN_PROMPT;
  const selectedPromptIsDefault = !matchedPrompt || selectedPromptId === defaultPromptId;
  const modelOptions = useMemo(() => {
    return llmProviders
      .filter((provider) => provider.configured)
      .map(toModelOption)
      .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.label.localeCompare(b.label, "zh-CN"));
  }, [llmProviders]);
  const selectedModelOption = modelOptions.find((option) => option.key === selectedModelKey) ?? modelOptions.find((option) => option.isDefault) ?? modelOptions[0] ?? null;
  const {
    handleCopyEditableEmailDraft,
    handleCopyGeneratedEmailBody,
    handleDownloadEditableEmailDraft,
    handleOpenEditableEmailDraft,
    handleOpenGeneratedEmailClient,
  } = useGeneratedEmailDraftActions(copyText);
  const {
    clearTextTransformResult,
    handleApplyTextTransformResult,
    handleCopyTextTransformResult,
    handleTransformMessage,
    textTransformResult,
  } = useTextTransformActions({
    apiOptions,
    clearAuth,
    copyText,
    selectedModelOption,
    setActionNotice,
    setDraft,
    setError,
    setMessageActionBusyId,
    temperature,
    textareaRef,
    thinkingEnabled,
  });
  const {
    handleRegenerateMessage,
    openRegenerateDialog,
    regenerateModelKey,
    regenerateModelOption,
    regenerateTarget,
    setRegenerateModelKey,
    setRegenerateTarget,
  } = useChatRegenerate({
    activeWorkspaceId,
    apiOptions,
    clearAuth,
    mode,
    modelOptions,
    selectedModelOption,
    selectedPromptContent: selectedPrompt.content,
    setError,
    setMessageActionBusyId,
    setMessagesBySession,
    setSessions,
    thinkingEnabled,
    typeAssistantReply,
    webSearchEnabled,
  });
  const {
    attachmentDragTargetPane,
    authorizeLocalPrivateAttachments,
    fileInputRef,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleReferenceWorkspaceFile,
    handleRemovePendingAttachment,
    handleSelectAttachmentFiles,
    isUploadingAttachments,
    pendingAttachments,
    resolveAttachmentSession,
    revokeAttachmentPreviews,
    setIsUploadingAttachments,
    setPendingAttachments,
    uploadPendingAttachmentForSend,
  } = useChatAttachments({
    activeSessionId,
    activeSplitPane,
    activeWorkspaceId,
    activeWorkspaceKind: activeWorkspace?.workspace_kind,
    apiOptions,
    createSessionFromInput,
    focusComposerRef: textareaRef,
    mode,
    sessions,
    setActiveSplitPane,
    setError,
    activateConversationPane,
  });
  const handleSend = useChatSendOrchestrator({
    activeSessionId,
    activeSessionIsSending,
    activeWorkspaceId,
    apiOptions,
    appendLegacyAssistantResponse,
    clearAuth,
    clearCurrentDraft,
    createSessionFromInput,
    draft,
    finalizeStreamAssistantResponse,
    finishSessionSend,
    mode,
    pendingAttachments,
    registerSendAbortController,
    removeStreamPlaceholder,
    revokeAttachmentPreviews,
    selectedBuiltinCommand,
    selectedModelOption,
    selectedPrompt,
    selectedPromptId,
    selectedSkill,
    sendingSessions,
    sessions,
    setDraft,
    setError,
    setIsUploadingAttachments,
    setMessagesBySession,
    setMode,
    setPendingAttachments,
    quotedMessage,
    setQuotedMessage,
    setSelectedBuiltinCommand,
    setSelectedSkill,
    setSessions,
    setSessionSending,
    setSkillPanelVisible,
    setSlashCommand,
    setTabs,
    temperature,
    thinkingEnabled,
    typeAssistantReply,
    updateStreamPlaceholder,
    uploadPendingAttachmentForSend,
    webSearchEnabled,
  });
  const sessionGroups = useMemo(() => {
    const pinned = sessions.filter((item) => item.is_pinned);
    const recent = sessions.filter((item) => !item.is_pinned);
    const timeGroups = groupSessionsByTime(recent);
    return [
      ...(pinned.length ? [{ key: "pinned", label: null as string | null, items: pinned }] : []),
      ...timeGroups,
    ];
  }, [sessions]);

  const skillQuery = slashCommand?.query ?? "";
  const slashCandidates = useMemo<SkillSlashCandidate[]>(() => {
    const builtinCandidates: SkillSlashCandidate[] = BUILTIN_SLASH_COMMANDS
      .map((command) => ({ kind: "command" as const, command, score: scoreBuiltinSlashCommand(command, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    const skillCandidates: SkillSlashCandidate[] = skills
      .map((skill) => ({ kind: "skill" as const, skill, score: scoreSkill(skill, skillQuery) }))
      .filter((item) => !skillQuery || item.score > 0);
    return [...builtinCandidates, ...skillCandidates]
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        if (a.kind !== b.kind) return a.kind === "command" ? -1 : 1;
        const aName = a.kind === "command" ? a.command.displayName : a.skill.display_name;
        const bName = b.kind === "command" ? b.command.displayName : b.skill.display_name;
        return aName.localeCompare(bName, "zh-CN");
      })
      .slice(0, 8);
  }, [skills, skillQuery]);
  const handleKeyDown = useChatComposerShortcuts({
    handleSend,
    insertSlashCandidate,
    setSkillPanelIndex,
    setSkillPanelVisible,
    setSlashCommand,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
  });

  function syncSlashCommand(value: string, caret: number) {
    const command = findSlashCommand(value, caret);
    setSlashCommand(command);
    setSkillPanelVisible(Boolean(command));
    if (!command) setSkillPanelIndex(0);
  }

  function clearSelectedSkillIfMissing(_value: string) {
    // Skill 选择是本次发送的上下文状态，不再依赖输入框里的触发词。
  }

  function insertSkill(skill: SkillResponse) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
  }

  function insertBuiltinSlashCommand(command: BuiltinSlashCommand) {
    const target = slashCommand ?? findSlashCommand(draft, textareaRef.current?.selectionStart ?? draft.length);
    if (!target) return;
    const before = draft.slice(0, target.start).replace(/[ \t]+$/, "");
    const after = draft.slice(target.end).replace(/^[ \t]+/, "");
    const spacer = before && after ? " " : "";
    const nextDraft = `${before}${spacer}${after}`;
    const nextCaret = before.length + spacer.length;
    setDraft(nextDraft);
    setSelectedSkill(null);
    setSelectedBuiltinCommand(command);
    setSlashCommand(null);
    setSkillPanelVisible(false);
    window.requestAnimationFrame(() => {
      textareaRef.current?.focus();
      textareaRef.current?.setSelectionRange(nextCaret, nextCaret);
    });
  }

  function insertSlashCandidate(candidate: SkillSlashCandidate) {
    if (candidate.kind === "command") {
      insertBuiltinSlashCommand(candidate.command);
      return;
    }
    insertSkill(candidate.skill);
  }

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    };
    onScroll();
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [scrollRef.current, activeSplitPane, splitPaneSessionIds]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    // Follow bottom only if user was already near bottom BEFORE this update
    if (isNearBottomRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    }
  }, [activeMessages]);

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

  useEffect(() => {
    setSkillPanelIndex(0);
  }, [skillQuery]);

  useEffect(() => {
    setSkillPanelIndex((index) => {
      if (slashCandidates.length === 0) return 0;
      return Math.min(index, slashCandidates.length - 1);
    });
  }, [slashCandidates.length]);

  useEffect(() => {
    if (utilityPanel === "source" && sourcePreview?.sessionId != null && sourcePreview.sessionId !== activeSessionId) {
      setSourcePreview(null);
      setUtilityPanel(null);
    }
  }, [activeSessionId, sourcePreview?.sessionId, utilityPanel]);

  useEffect(() => {
    setTabs((current) => {
      if (!current.some((tab) => tab.id === "scratch")) return current;
      return current.filter((tab) => tab.id !== "scratch");
    });
    if (activeTabId === "scratch") {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }, [activeTabId, setActiveSessionId, setActiveTabId, setTabs]);

  useEffect(() => {
    let mounted = true;
    setIsLoading(true);
    setError(null);
    if (!activeWorkspaceId) {
      setSessions([]);
      setActiveSessionId(null);
      setIsLoading(false);
      return;
    }
    listChatSessions(apiOptions, activeWorkspaceId)
      .then((loadedSessions) => {
        if (!mounted) return;
        setSessions(loadedSessions);
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法加载会话列表，请确认后端正在运行。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeWorkspaceId, apiOptions, clearAuth, setActiveSessionId, setError, setIsLoading, setSessions]);

  useEffect(() => {
    let mounted = true;
    setModelsLoading(true);
    setModelConfigError("");
    getLLMHealth(apiOptions)
      .then((health) => {
        if (!mounted) return;
        setLlmProviders(health.providers);
      })
      .catch(() => {
        if (!mounted) return;
        setLlmProviders([]);
        setModelConfigError("无法读取模型配置");
      })
      .finally(() => {
        if (mounted) setModelsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (modelOptions.length === 0) {
      setSelectedModelKey(null);
      return;
    }
    if (selectedModelKey && modelOptions.some((option) => option.key === selectedModelKey)) return;
    setSelectedModelKey((modelOptions.find((option) => option.isDefault) ?? modelOptions[0]).key);
  }, [modelOptions, selectedModelKey]);

  useEffect(() => {
    let mounted = true;
    listCompanyPrompts(apiOptions)
      .then((items) => {
        if (mounted) setCompanyPrompts(items);
      })
      .catch(() => {
        if (mounted) setCompanyPrompts([]);
      });
    listSkills(apiOptions)
      .then((items) => {
        if (mounted) setSkills(items);
      })
      .catch(() => {
        if (mounted) setSkills([]);
      });
    window.projectR?.prompts?.listUser()
      .then((items) => {
        if (mounted) setUserPrompts(items);
      })
      .catch(() => {
        if (mounted) setUserPrompts([]);
      });
    return () => {
      mounted = false;
    };
  }, [apiOptions]);

  useEffect(() => {
    if (!activeSessionId || messagesBySession[activeSessionId]) return;
    let mounted = true;
    setIsLoading(true);
    setError(null);
    listChatMessages(apiOptions, activeSessionId)
      .then((response) => {
        if (!mounted) return;
        setMessagesBySession((current) => ({ ...current, [activeSessionId]: response.items }));
      })
      .catch((loadError: unknown) => {
        if (!mounted) return;
        if (loadError instanceof ApiError && loadError.status === 401) {
          clearAuth();
          window.location.hash = "#/login";
          return;
        }
        setError("无法读取消息历史，请稍后重试。");
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [activeSessionId, apiOptions, clearAuth, messagesBySession, setError, setIsLoading, setMessagesBySession]);

  useEffect(() => {
    if (!showSearch || !searchTerm.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = window.setTimeout(() => {
      searchChatSessions(apiOptions, searchTerm, activeWorkspaceId)
        .then(setSearchResults)
        .catch(() => setSearchResults([]));
    }, 180);
    return () => window.clearTimeout(timer);
  }, [activeWorkspaceId, apiOptions, searchTerm, showSearch]);

  function selectSession(session: ChatSessionResponse, openInNewTab = false) {
    setShowScratchPad(false);
    setActiveSessionId(session.id);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: session.id }));
    }
    const tabId = `chat-${session.id}`;
    setTabs((current) => {
      const existing = current.find((tab) => tab.id === tabId);
      if (existing) return current;
      const nextTab = {
        id: tabId,
        sessionId: session.id,
        workspaceId: session.workspace_id,
        title: session.title,
      };
      if (openInNewTab || !activeTabId) return [...current, nextTab];
      if (!current.some((tab) => tab.id === activeTabId)) return [...current, nextTab];
      return current.map((tab) => tab.id === activeTabId ? nextTab : tab);
    });
    setActiveTabId(tabId);
  }

  async function handleArchiveRestored(session: ChatSessionResponse) {
    const workspaceId = session.workspace_id ?? activeWorkspaceId;
    if (!workspaceId) return;
    if (workspaceId !== activeWorkspaceId) {
      setActiveWorkspaceId(workspaceId);
    }
    try {
      const refreshedSessions = await listChatSessions(apiOptions, workspaceId);
      setSessions(refreshedSessions);
      const restoredSession = refreshedSessions.find((item) => item.id === session.id) ?? { ...session, is_archived: false };
      selectSession(restoredSession);
    } catch {
      if (workspaceId === activeWorkspaceId) {
        const restoredSession = { ...session, is_archived: false };
        setSessions((current) => current.some((item) => item.id === session.id) ? current : [restoredSession, ...current]);
        selectSession(restoredSession);
      }
    }
  }

  function storePromptSelection(sessionId: number, promptId: string) {
    setPromptSelections((current) => {
      const next = { ...current, [String(sessionId)]: promptId };
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
  }

  function clearPromptSelection() {
    if (!activeSessionId) {
      setPendingPromptId(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    setPromptSelections((current) => {
      const next = { ...current };
      delete next[String(activeSessionId)];
      localStorage.setItem(PROMPT_SELECTION_KEY, JSON.stringify(next));
      return next;
    });
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function createSessionFromInput(
    content = "新对话",
    openInNewTab = true,
    promptIdForNewSession: string | null = null,
    paneForNewSession: SplitPaneKey = activeSplitPane,
  ) {
    const resolvedPromptId = promptIdForNewSession ?? (!activeSessionId ? pendingPromptId : null);
    const session = await createChatSession(apiOptions, makeSessionTitle(content), activeWorkspaceId);
    setSessions((current) => [session, ...current]);
    setMessagesBySession((current) => ({ ...current, [session.id]: [] }));
    if (resolvedPromptId) {
      if (resolvedPromptId !== defaultPromptId) {
        storePromptSelection(session.id, resolvedPromptId);
      }
      setPendingPromptId(null);
    }
    selectSession(session, openInNewTab);
    if (sideBySideOpen) {
      setSplitPaneSessionIds((current) => ({ ...current, [paneForNewSession]: session.id }));
    }
    return session;
  }

  async function handleCreateSession() {
    setError(null);
    if (!activeWorkspaceId) {
      setError("请先选择或创建一个项目。");
      return;
    }
    try {
      await createSessionFromInput();
    } catch (createError: unknown) {
      if (createError instanceof ApiError && createError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("新建会话失败，请确认后端连接正常。");
    }
  }

  function handleOpenScratch() {
    setShowScratchPad((current) => {
      const next = !current;
      if (next) {
        setUtilityPanel(null);
      }
      return next;
    });
  }

  async function handleDeleteSession(sessionId: number) {
    setError(null);
    try {
      await deleteChatSession(apiOptions, sessionId);
      const nextSessions = sessions.filter((session) => session.id !== sessionId);
      setSessions(nextSessions);
      setMessagesBySession((current) => {
        const next = { ...current };
        delete next[sessionId];
        return next;
      });
      setTabs((current) => current.filter((tab) => tab.sessionId !== sessionId));
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeSessionId === sessionId) setActiveSessionId(nextSessions[0]?.id ?? null);
    } catch (deleteError: unknown) {
      if (deleteError instanceof ApiError && deleteError.status === 401) {
        clearAuth();
        window.location.hash = "#/login";
        return;
      }
      setError("删除会话失败，请稍后重试。");
    }
  }

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

  function getMessageDeleteTargetIds(target: ChatMessage) {
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

  function willDeleteEntireSession(target: ChatMessage) {
    if (target.id < 0) return false;
    const sessionMessages = (messagesBySession[target.session_id] ?? []).filter((message) => message.id > 0);
    if (sessionMessages.length === 0) return false;
    const deleteIds = new Set(getMessageDeleteTargetIds(target));
    return sessionMessages.every((message) => deleteIds.has(message.id));
  }

  function requestDeleteMessageContext(target: ChatMessage) {
    if (willDeleteEntireSession(target)) {
      setDeleteLastMessageTarget(target);
      return;
    }
    setDeleteMessageTarget(target);
  }

  async function handleDeleteMessageContext(target: ChatMessage) {
    if (target.id < 0) return;
    setError(null);
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
      if (sourcePreview?.sessionId === target.session_id) {
        setSourcePreview(null);
        setUtilityPanel((value) => value === "source" ? null : value);
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
    setError(null);
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
    setError(null);
    setMessageActionBusyId(message.id);
    try {
      const response = await editChatMessage(apiOptions, message.session_id, message.id, {
        content,
        provider: selectedModelOption?.provider ?? null,
        modelProfile: selectedModelOption?.profile ?? null,
        systemPrompt: composeSystemPrompt(selectedPrompt.content, mode),
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
    setError(null);
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
    setError(null);
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

  async function handleSubmitGBrainThinkReview(message: ChatMessage) {
    if (message.id < 0) return;
    setError(null);
    setActionNotice("");
    setMessageActionBusyId(message.id);
    try {
      const response = await submitGBrainThinkReview(apiOptions, message.session_id, message.id, {});
      setActionNotice(
        response.created
          ? `已提交 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`
          : `已更新 GBrain 缺口/冲突审核 #${response.knowledge_review_id}。`,
      );
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

  async function handlePinSession(sessionId: number) {
    const session = sessions.find((item) => item.id === sessionId);
    if (!session) return;
    const nextPinned = !session.is_pinned;
    setSessions((prev) => prev.map((item) => item.id === sessionId ? { ...item, is_pinned: nextPinned } : item));
    try {
      const updated = await updateChatSession(apiOptions, sessionId, { is_pinned: nextPinned });
      setSessions((prev) => prev.map((item) => item.id === sessionId ? updated : item));
    } catch {
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    }
  }

  function handleRenameSession(sessionId: number, scope: RenameScope = "sidebar") {
    const session = sessions.find((item) => item.id === sessionId);
    setRenameInput({ id: sessionId, value: session?.title ?? "", scope });
    window.requestAnimationFrame(() => {
      const input = scope === "header" ? titleInputRef.current : sidebarRenameInputRef.current;
      input?.focus();
      input?.select();
    });
  }

  async function commitRename() {
    if (!renameInput) return;
    const title = renameInput.value.trim();
    const current = sessions.find((item) => item.id === renameInput.id);
    if (!title || title === current?.title) {
      setRenameInput(null);
      return;
    }
    const sid = renameInput.id;
    setSessions((prev) => prev.map((item) => item.id === sid ? { ...item, title } : item));
    setTabs((prev) => prev.map((tab) => tab.sessionId === sid ? { ...tab, title } : tab));
    setRenameInput(null);
    try {
      const updated = await updateChatSession(apiOptions, sid, { title });
      setSessions((prev) => prev.map((item) => item.id === sid ? updated : item));
    } catch {
      setSessions(await listChatSessions(apiOptions, activeWorkspaceId));
    }
  }

  async function handleArchiveSession(sessionId: number) {
    try {
      await archiveChatSession(apiOptions, sessionId);
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      const archivedTabId = `chat-${sessionId}`;
      const nextTabs = tabs.filter((tab) => tab.sessionId !== sessionId);
      setSessions(nextSessions);
      setTabs(nextTabs);
      setMessagesBySession((prev) => {
        const next = { ...prev };
        delete next[sessionId];
        return next;
      });
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeTabId === archivedTabId) {
        const nextTab = nextTabs[0];
        if (nextTab?.sessionId) {
          setActiveTabId(nextTab.id);
          setActiveSessionId(nextTab.sessionId);
          if (nextTab.workspaceId && nextTab.workspaceId !== activeWorkspaceId) {
            setActiveWorkspaceId(nextTab.workspaceId);
          }
        } else {
          setActiveTabId("");
          setActiveSessionId(nextSessions[0]?.id ?? null);
        }
      } else if (activeSessionId === sessionId) {
        setActiveSessionId(nextSessions[0]?.id ?? null);
      }
    } catch {
      setError("归档失败，请稍后重试。");
    }
  }

  async function handleMoveSession(sessionId: number, workspaceId: number) {
    try {
      await updateChatSession(apiOptions, sessionId, { workspace_id: workspaceId });
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      setSessions(nextSessions);
      setTabs((current) => current.filter((tab) => tab.sessionId !== sessionId));
      setSplitPaneSessionIds((current) => ({
        left: current.left === sessionId ? null : current.left,
        right: current.right === sessionId ? null : current.right,
      }));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setActiveTabId("");
      }
      setMoveSessionId(null);
    } catch {
      setError("迁移会话失败，请稍后重试。");
    }
  }

  function openSessionMenu(event: MouseEvent, session: ChatSessionResponse) {
    event.preventDefault();
    const moveTargets = workspaces.filter((workspace) => workspace.id !== session.workspace_id);
    const items: ContextMenuItemDef[] = [
      { type: "item", label: "在新标签页打开", action: () => selectSession(session, true) },
      { type: "separator" },
      { type: "item", label: session.is_pinned ? "取消置顶" : "置顶", action: () => void handlePinSession(session.id) },
      { type: "item", label: "重命名", action: () => handleRenameSession(session.id, "sidebar") },
      { type: "item", label: "归档", action: () => void handleArchiveSession(session.id) },
    ];
    if (moveTargets.length > 0) {
      items.push({ type: "separator" });
      items.push({ type: "item", label: "迁移项目", action: () => setMoveSessionId(session.id) });
    }
    items.push(
      { type: "separator" },
      {
        type: "item",
        label: "导出 Markdown",
        action: () => {
          setActionNotice("正在导出...");
          exportChatSession(apiOptions, session.id, "markdown")
            .then(() => setActionNotice(""))
            .catch((err: unknown) => {
              setActionNotice(err instanceof ApiError ? err.message : "导出失败");
            });
        },
      },
      {
        type: "item",
        label: "导出 JSON",
        action: () => {
          setActionNotice("正在导出...");
          exportChatSession(apiOptions, session.id, "json")
            .then(() => setActionNotice(""))
            .catch((err: unknown) => {
              setActionNotice(err instanceof ApiError ? err.message : "导出失败");
            });
        },
      },
      { type: "separator" },
      { type: "item", label: "删除", destructive: true, action: () => setDeleteConfirmSessionId(session.id) },
    );
    setContextMenu({ x: event.clientX, y: event.clientY, items });
  }

  function handleLogout() {
    clearAuth();
    window.location.hash = "#/login";
  }

  function handleSelectTab(id: string) {
    setShowScratchPad(false);
    setActiveTabId(id);
    const tab = tabs.find((item) => item.id === id);
    if (tab?.sessionId) {
      setActiveSessionId(tab.sessionId);
      if (sideBySideOpen) {
        setSplitPaneSessionIds((current) => ({ ...current, [activeSplitPane]: tab.sessionId ?? null }));
      }
      if (tab.workspaceId && tab.workspaceId !== activeWorkspaceId) {
        setActiveWorkspaceId(tab.workspaceId);
      }
    }
  }

  function handleWorkspaceChanged(workspaceId: number | null) {
    setActiveWorkspaceId(workspaceId);
    const tab = tabs.find((item) => item.id === activeTabId);
    if (tab?.sessionId && tab.workspaceId !== workspaceId) {
      setActiveTabId("");
      setActiveSessionId(null);
    }
  }

  function handleCloseTab(id: string) {
    const tab = tabs.find((item) => item.id === id);
    if (!tab) return;
    const nextTabs = tabs.filter((item) => item.id !== id);
    setTabs(nextTabs);
    if (activeTabId === id) {
      const next = nextTabs[0];
      if (next) handleSelectTab(next.id);
      else {
        setActiveTabId("");
        setActiveSessionId(null);
      }
    }
  }

  function handleSwitchToAgent(_messageId: number) {
    setMode("agent");
  }

  function handleSelectPrompt(prompt: PromptOption) {
    const promptId = getPromptOptionId(prompt);
    if (!activeSessionId) {
      setPendingPromptId(promptId);
      setUtilityPanel(null);
      window.requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    storePromptSelection(activeSessionId, promptId);
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function handleCreateUserPrompt(name: string, content: string) {
    const saved = await window.projectR?.prompts?.saveUser({ name, content });
    if (!saved) return;
    setUserPrompts((prev) => [saved, ...prev.filter((item) => item.id !== saved.id)]);
  }

  async function handleDeleteUserPrompt(id: string) {
    const next = await window.projectR?.prompts?.deleteUser(id);
    setUserPrompts(next ?? []);
    if (activeSessionId && promptSelections[String(activeSessionId)] === makePromptId("user", id)) {
      handleSelectPrompt(PROJECT_R_BUILTIN_PROMPT);
    }
    if (pendingPromptId === makePromptId("user", id)) {
      setPendingPromptId(null);
    }
  }

  function handleToggleSideBySide() {
    setSideBySideOpen((current) => {
      if (!current) {
        setActiveSplitPane("left");
        setSplitPaneSessionIds((paneIds) => ({
          left: paneIds.left ?? activeSessionId,
          right: paneIds.right === activeSessionId ? null : paneIds.right,
        }));
      }
      return !current;
    });
  }

  function activateConversationPane(pane: SplitPaneKey, sessionId: number | null) {
    setActiveSplitPane(pane);
    if (sessionId) {
      setActiveSessionId(sessionId);
      setActiveTabId(`chat-${sessionId}`);
    } else {
      setActiveSessionId(null);
      setActiveTabId("");
    }
  }

  function handleSelectSkillFromSidePanel(skill: SkillResponse) {
    setSelectedSkill(skill);
    setSelectedBuiltinCommand(null);
    if (mode === "chat" && skill.outputs.length > 0) {
      setMode("agent");
    }
    setUtilityPanel(null);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function handleSaveGeneratedFileToWorkspace(file: GeneratedFileResponse) {
    if (!activeWorkspaceId || !activeWorkspace || activeWorkspace.workspace_kind === "user") {
      throw new Error("当前工作区不支持保存生成文件");
    }
    const result = await saveGeneratedFileToWorkspace(apiOptions, activeWorkspaceId, {
      generated_file_id: file.id,
      conflict_strategy: "keep_both",
    });
    setWorkspaceFilePanelRefreshKey((value) => value + 1);
    setUtilityPanel("workspace");
    setActionNotice(`已保存到 ${result.path}`);
    return { path: result.path };
  }

  // 当前会话已消耗 tokens（从最后一条非 typing assistant 消息取）
  const activeSessionTokenTotal = (() => {
    if (!activeSessionId) return 0;
    const msgs = messagesBySession[activeSessionId];
    if (!msgs || msgs.length === 0) return 0;
    const nonTyping = msgs.filter((m) => !m.isTyping);
    for (let i = nonTyping.length - 1; i >= 0; i--) {
      const token = nonTyping[i].token_total ?? nonTyping[i].token_output;
      if (token != null) return token;
    }
    return 0;
  })();

  const conversationPaneController = {
    activeSessionTokenTotal,
    activeSessionId,
    quotedMessage,
    setQuotedMessage,
    activeSplitPane,
    activeWorkspace,
    apiOptions,
    activateConversationPane,
    attachmentDragTargetPane,
    copiedMessageId,
    currentUser,
    draft,
    editingDraft,
    editingMessageId,
    fileInputRef,
    formatClockTime,
    formatSessionDisplayTitle,
    handleActivateVersion,
    handleAttachmentDragEnter,
    handleAttachmentDragLeave,
    handleAttachmentDragOver,
    handleAttachmentDrop,
    handleCancelSend: cancelSessionSend,
    handleChoosePrivateWorkspaceFiles,
    handleComposerPaste,
    handleCopyMessage,
    handleKeyDown,
    handlePinSession,
    handleRemovePendingAttachment,
    handleRenameSession,
    handleSelectAttachmentFiles,
    handleSubmitEditedMessage,
    handleSubmitGBrainThinkReview,
    onCopyGeneratedEmailBody: handleCopyGeneratedEmailBody,
    onEditGeneratedEmailDraft: setEmailDraftEditorFile,
    onOpenGeneratedEmailClient: handleOpenGeneratedEmailClient,
    onSaveGeneratedFileToWorkspace: handleSaveGeneratedFileToWorkspace,
    onTransformMessage: handleTransformMessage,
    onApplyTextTransformResult: handleApplyTextTransformResult,
    onClearTextTransformResult: clearTextTransformResult,
    onCopyTextTransformResult: handleCopyTextTransformResult,
    handleSwitchToAgent,
    handleToggleSideBySide,
    messageActionBusyId,
    messagesBySession,
    mode,
    openFeedbackDialog,
    openRegenerateDialog,
    renameInput,
    renderAvatar,
    requestDeleteMessageContext,
    scrollRef,
    serverUrl,
    sessions,
    sendingSessions,
    setDeleteConfirmSessionId,
    setDraft,
    setEditingDraft,
    setEditingMessageId,
    setRenameInput,
    setSourcePreview,
    setUtilityPanel,
    sideBySideOpen,
    splitPaneSessionIds,
    startEditingMessage,
    titleInputRef,
    token,
    textTransformResult,
    utilityPanel,
    attachmentSourceLabel,
    authorizeLocalPrivateAttachments,
    clearPromptSelection,
    clearSelectedSkillIfMissing,
    composerRef,
    formatAttachmentSize,
    getSkillScopeLabel,
    handleSend,
    insertSlashCandidate,
    isLocalPrivatePendingAttachment,
    isUploadingAttachments,
    modelConfigError,
    modelMenuOpen,
    modelOptions,
    modelsLoading,
    modelSelectRef,
    pendingAttachmentKey,
    pendingAttachmentSendFormLabel,
    pendingAttachmentStatusLabel,
    pendingAttachmentTargetLabel,
    pendingAttachments,
    selectedBuiltinCommand,
    selectedModelOption,
    selectedPrompt,
    selectedPromptIsDefault,
    selectedSkill,
    setModelMenuOpen,
    setSelectedBuiltinCommand,
    setSelectedModelKey,
    setSelectedSkill,
    setSkillPanelIndex,
    setThinkingEnabled,
    skillPanelIndex,
    skillPanelVisible,
    slashCandidates,
    syncSlashCommand,
    textareaRef,
    temperature,
    setTemperature,
    thinkingEnabled,
    toggleWebSearch,
    webSearchEnabled,
  };

  function renderConversationPane(pane: SplitPaneKey) {
    return <ChatConversationPane controller={{ ...conversationPaneController, pane }} />;
  }
  return (
    <>
      <AppWorkspaceChrome
        controller={{
        UPDATE_DOWNLOAD_DRY_RUN,
        actionNotice,
        activeSessionId,
        activeTabId,
        activeWorkspace,
        activeWorkspaceId,
        apiOptions,
        auxiliaryPanelMaxWidth,
        auxiliaryPanelRef,
        auxiliaryPanelResizing,
        auxiliaryPanelWidth,
        availableUpdate,
        commitRename,
        companyPrompts,
        contextMenu,
        currentUser,
        clientVersion,
        deleteConfirmSessionId,
        deleteLastMessageTarget,
        deleteMessageTarget,
        deletedMessageUndo,
        downloadedUpdatePath,
        error,
        feedbackComment,
        feedbackRating,
        feedbackTarget,
        formatNotificationTime,
        formatSessionDisplayTitle,
        formatSidebarTime,
        formatUpdateBytes,
        formatUpdateSpeed,
        getInitials,
        getSkillScopeLabel,
        handleArchiveRestored,
        handleAuxiliaryPanelResizeStart,
        handleCloseTab,
        handleCreateSession,
        handleCreateUserPrompt,
        handleDeleteMessageContext,
        handleDeleteSession,
        handleDeleteUserPrompt,
        handleLogout,
        handleMarkAllNotificationsRead,
        handleMoveSession,
        handleNotificationAction,
        handleNotificationActionStatus,
        handleOpenScratch,
        handleReferenceWorkspaceFile,
        handleRegenerateMessage,
        handleSelectPrompt,
        handleSelectSkillFromSidePanel,
        handleSelectTab,
        handleSubmitFeedback,
        handleSidebarResizeStart,
        handleUndoDeleteMessages,
    handleWorkspaceChanged,
    handleWorkspaceFilePreviewClose,
    handleWorkspaceFilePreviewOpen,
        handleWorkspacePanelResizeStart,
        isLoading,
        messageActionBusyId,
        mode,
        modelOptions,
        moveSessionId,
        notificationButtonRef,
        notificationCategoryLabel,
        notificationPanelOpen,
        notificationPanelRef,
        notificationToast,
        notificationView,
        notifications,
        notificationsLoading,
        openSessionMenu,
        pendingNotificationCount,
        regenerateModelKey,
        regenerateModelOption,
        regenerateTarget,
        renderConversationPane,
        renameInput,
        resolveAvatarUrl,
        searchResults,
        searchTerm,
        selectedPromptId,
        selectSession,
        serverUrl,
        sessionGroups,
        sessions,
        setSourcePreview,
        setActiveMode: setMode,
        setContextMenu,
        setDeleteConfirmSessionId,
        setDeleteLastMessageTarget,
        setDeleteMessageTarget,
        setFeedbackComment,
        setFeedbackRating,
        setFeedbackTarget,
        setMoveSessionId,
        setNotificationPanelOpen,
        setNotificationView,
        setRegenerateModelKey,
        setRegenerateTarget,
        setRenameInput,
        setSearchTerm,
        setSettingsInitialAdminTab,
        setShowScratchPad,
        setShowSearch,
        setShowSettings,
        setUpdateDialogOpen,
        setUpdateStep,
        setUtilityPanel,
        settingsInitialAdminTab,
        showScratchPad,
        showSearch,
        showSettings,
        sideBySideOpen,
        skills,
        sidebarRef,
        sidebarRenameInputRef,
        sidebarResizing,
        sidebarWidth,
        splitPaneSessionIds,
        startClientUpdateDownload,
        sourcePreview,
        tabs,
        unreadNotificationCount,
        updateDialogOpen,
        updateError,
        updateProgress,
        updateStep,
        userPrompts,
        utilityPanel,
        workspaceFilePanelRefreshKey,
        workspacePanelMaxWidth,
        workspacePanelRef,
        workspacePanelResizing,
        workspacePanelWidth,
        workspaces,
        }}
      />
      {emailDraftEditorFile ? (
        <EmailDraftEditor
          file={emailDraftEditorFile}
          onClose={() => setEmailDraftEditorFile(null)}
          onCopy={handleCopyEditableEmailDraft}
          onDownload={handleDownloadEditableEmailDraft}
          onOpenEmailClient={handleOpenEditableEmailDraft}
        />
      ) : null}
    </>
  );
}
